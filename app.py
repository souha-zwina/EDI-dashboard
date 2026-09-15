"""
app.py - EDI Dashboard Lear Corporation
==========================================
Point d'entrée unique. Toute la logique métier vit dans src/, ce fichier
ne fait que : configurer la page, gérer la navigation, et démarrer le
watcher en arrière-plan (plus besoin d'ouvrir un terminal séparé).

La navigation et le vocabulaire sont pensés pour un agent Customer Service
/ Logistique, pas pour un data analyst : aucune page ne s'appelle "Prophet"
ou "XGBoost", et la question posée à chaque écran est "y a-t-il un
problème, lequel, que dois-je faire ?" plutôt que "voici des courbes".
"""

from __future__ import annotations

import logging

import streamlit as st

from src import analytics, config, database
from src.ui import components, login, style
from src.ui.context import AppContext
from src.ui.pages import admin as admin_page
from src.ui.pages import alerts as alerts_page
from src.ui.pages import data_view, forecast, home, partners
from src.watcher_service import EdiWatcherService

# ------------------------------------------------------------------
# Configuration de la page (doit être le premier appel Streamlit)
# ------------------------------------------------------------------
st.set_page_config(
    page_title="EDI Dashboard - Lear Corporation",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.FileHandler(config.LOG_PATH), logging.StreamHandler()],
)
logger = logging.getLogger("edi.app")

style.inject()


# ------------------------------------------------------------------
# Initialisation de la base : une seule fois par process (pas à chaque
# rerun/clic) grâce à st.cache_resource.
# ------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def _init_db_once() -> bool:
    database.init_db()
    return True


_init_db_once()


# ------------------------------------------------------------------
# Watcher en arrière-plan : démarré UNE SEULE fois par process grâce à
# st.cache_resource, même si Streamlit ré-exécute ce script à chaque clic.
# -> Remplace l'ancien besoin de lancer `python watcher.py` dans un terminal.
# ------------------------------------------------------------------
@st.cache_resource(show_spinner="Démarrage de la surveillance des dossiers EDI...")
def _get_watcher_service() -> EdiWatcherService:
    if not config.AUTO_START_WATCHER:
        return EdiWatcherService()
    return EdiWatcherService().start()


watcher_service = _get_watcher_service()

# ------------------------------------------------------------------
# Authentification
# ------------------------------------------------------------------
if not login.check_password():
    st.stop()

components.top_header()

# ------------------------------------------------------------------
# Chargement + analyse des données (mis en cache : recalculé seulement
# quand de nouvelles données arrivent, pas à chaque clic de l'utilisateur)
# ------------------------------------------------------------------
@st.cache_data(ttl=config.DATA_CACHE_TTL_SECONDS)
def _load_data():
    return database.fetch_all_messages(), database.get_stats()


@st.cache_data(ttl=config.DATA_CACHE_TTL_SECONDS, show_spinner=False)
def _prepare_data(_raw_records: list, cache_key: int):
    return analytics.prepare_dataframes(_raw_records)


@st.cache_data(ttl=config.DATA_CACHE_TTL_SECONDS, show_spinner=False)
def _role_scoped_analysis(
    _raw_records: list, role: str, cache_key: int,
    spike_threshold: float, lookback_weeks: int, _alert_statuses: dict,
):
    """Toutes les analyses (dataframes filtrés + alertes consolidées) pour
    un rôle donné, calculées une seule fois et partagées entre les pages."""
    df_msg_all, df_fc_all = _prepare_data(_raw_records, cache_key)
    df_msg = analytics.filter_by_role(df_msg_all, role)
    df_fc = analytics.filter_by_role(df_fc_all, role)
    alert_list = analytics.build_alerts(
        _raw_records, df_msg, df_fc,
        spike_threshold=spike_threshold, lookback_weeks=lookback_weeks,
        alert_statuses=_alert_statuses,
    )
    return df_msg_all, df_msg, df_fc, alert_list


with st.spinner("Chargement des données..."):
    raw_records, stats = _load_data()
    settings = database.get_settings()
    alert_statuses = database.get_alert_statuses()
    df_messages_all, df_messages, df_forecasts, alert_list = _role_scoped_analysis(
        raw_records, st.session_state.get("role", "Administrateur"), stats["total_messages"],
        float(settings.get("spike_threshold", 1.5)), int(settings.get("lookback_weeks", 12)),
        alert_statuses,
    )

# ------------------------------------------------------------------
# Sidebar : navigation métier par onglets. Le badge rouge sur "Alertes"
# indique immédiatement s'il y a quelque chose à traiter (résolues exclues).
# ------------------------------------------------------------------
alerts_actifs = [a for a in alert_list if a["status"] != "resolu"]
n_critiques = sum(1 for a in alerts_actifs if a["gravite"] == "critique")
alert_suffix = f" ({len(alerts_actifs)})" if alerts_actifs else ""

PAGES = {
    "accueil": "🏠 Vue d'ensemble",
    "alerts": f"🚨 Alertes{alert_suffix}",
    "forecast": "📈 Prévisions",
    "partners": "🏢 Partenaires",
    "data": "📋 Données",
}
if st.session_state.get("role") == "Administrateur":
    PAGES["admin"] = "⚙️ Administration"
if "page" not in st.session_state or st.session_state.page not in PAGES:
    st.session_state.page = "accueil"

with st.sidebar:
    st.markdown(f"### {st.session_state.role_icon} {st.session_state.role}")
    if st.button("🚪 Se déconnecter", width='stretch'):
        st.session_state.authenticated = False
        st.rerun()

    st.markdown(components.watcher_status_pill(watcher_service.is_running), unsafe_allow_html=True)
    if stats.get("last_ingestion"):
        st.caption(f"Dernière ingestion : {stats['last_ingestion'][:19].replace('T', ' ')}")

    if n_critiques:
        st.error(f"🔴 {n_critiques} alerte(s) urgente(s)")

    st.markdown("### Navigation")
    selected_label = st.radio(
        "Navigation",
        options=list(PAGES.values()),
        index=list(PAGES.keys()).index(st.session_state.page),
        label_visibility="collapsed",
    )
    st.session_state.page = next(k for k, v in PAGES.items() if v == selected_label)

    if st.button("🔄 Rafraîchir les données", width='stretch'):
        st.cache_data.clear()
        st.rerun()

# ------------------------------------------------------------------
# Pas de données -> message clair, plus de dépendance à un batch manuel
# ------------------------------------------------------------------
if df_messages_all.empty:
    st.warning("⚠️ Aucune donnée EDI trouvée pour le moment.")
    st.info(
        "Déposez des fichiers `.x12` / `.edifact` dans `data/edi_messages/inbound` "
        "ou `outbound` : ils seront pris en compte automatiquement dans les secondes "
        "qui suivent, sans action manuelle de votre part."
    )
    st.stop()

ctx = AppContext(
    role=st.session_state.role,
    username=st.session_state.username,
    raw_records=raw_records,
    df_messages=df_messages,
    df_forecasts=df_forecasts,
    stats=stats,
    alerts=alert_list,
    watcher_running=watcher_service.is_running,
)

# ------------------------------------------------------------------
# Routage des pages (chaque rendu est protégé : une erreur dans UNE page
# affiche un message clair au lieu de casser toute l'application)
# ------------------------------------------------------------------
PAGE_RENDERERS = {
    "accueil": home.render,
    "alerts": alerts_page.render,
    "forecast": forecast.render,
    "partners": partners.render,
    "data": data_view.render,
    "admin": admin_page.render,
}

try:
    PAGE_RENDERERS[st.session_state.page](ctx)
except Exception as exc:
    logger.exception("Erreur lors du rendu de la page '%s'", st.session_state.page)
    st.error(
        f"❌ Une erreur est survenue sur cette page : **{exc}**\n\n"
        "Le détail complet a été écrit dans `data/logs/edi_app.log`. "
        "Réessayez, ou changez de page depuis le menu à gauche."
    )

# ------------------------------------------------------------------
# Pied de page
# ------------------------------------------------------------------
st.markdown("---")
st.caption("🏭 Lear Corporation — EDI Dashboard")
