"""components.py - Blocs UI réutilisables entre les pages."""

from __future__ import annotations

import base64
import imghdr
from pathlib import Path

import streamlit as st

from .. import config


@st.cache_data
def image_data_uri(path: Path) -> str | None:
    """Encode une image en data-URI en détectant le vrai type MIME du
    contenu (et pas l'extension du fichier, qui peut mentir)."""
    if not path.exists():
        return None
    raw = path.read_bytes()
    kind = imghdr.what(None, h=raw) or "png"
    mime = "jpeg" if kind == "jpeg" else kind
    return f"data:image/{mime};base64,{base64.b64encode(raw).decode()}"


def top_header() -> None:
    logo_uri = image_data_uri(config.LOGO_PATH)
    logo_html = f'<img src="{logo_uri}">' if logo_uri else "🏭"
    st.markdown(
        f"""<div class="top-header">{logo_html}
        <p class="top-header-title">Lear Corporation — EDI Dashboard</p>
        </div>""",
        unsafe_allow_html=True,
    )


def alert(kind: str, title: str, subtitle: str = "") -> None:
    """kind: 'danger' | 'warning' | 'success'"""
    sub_html = f'<div style="color:#9aa0ad;font-size:0.9rem;">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f"""<div class="alert-{kind}"><div class="alert-title">{title}</div>{sub_html}</div>""",
        unsafe_allow_html=True,
    )


def watcher_status_pill(is_running: bool) -> str:
    if is_running:
        return '<span class="status-pill online">● Watcher actif</span>'
    return '<span class="status-pill offline">● Watcher arrêté</span>'


_STATUS_BADGE = {
    "nouveau": ("🆕", "Nouveau", "#4a90d9"),
    "en_cours": ("⏳", "En cours", "#ffb100"),
    "resolu": ("✅", "Résolu", "#3ddc84"),
}


def alert_card(
    a: dict,
    raw_records: list,
    df_messages,
    interactive: bool = False,
    username: str = "",
) -> None:
    """Affiche une alerte avec un vrai bouton « Voir le détail » qui
    révèle le contexte utile selon le type de problème : extrait du
    fichier en erreur, mini-graphique pour un pic de volume, liste des
    semaines manquantes pour un silence partenaire.

    Si `interactive=True` (page Alertes), affiche aussi les actions de
    traitement (Prendre en charge / Marquer résolu / note) et persiste le
    statut en base — sinon (aperçu en Vue d'ensemble), lecture seule.
    """
    from .. import database  # import différé pour éviter tout cycle

    icon = {"critique": "🔴", "attention": "🟠", "info": "🔵"}.get(a["gravite"], "🔵")
    badge_icon, badge_label, badge_color = _STATUS_BADGE.get(a["status"], _STATUS_BADGE["nouveau"])

    with st.container(border=True):
        c1, c2 = st.columns([5, 1])
        with c1:
            st.markdown(f"**{icon} {a['titre']}**")
            st.caption(a["description"])
            st.caption(f"➡️ {a['action']}")
        with c2:
            st.markdown(f"`{a['partenaire']}`")
            st.markdown(
                f'<span style="color:{badge_color};font-weight:700;font-size:0.85rem;">'
                f'{badge_icon} {badge_label}</span>',
                unsafe_allow_html=True,
            )
        if a.get("status") != "nouveau" and a.get("status_updated_by"):
            when = (a.get("status_updated_at") or "")[:19].replace("T", " ")
            st.caption(f"Dernière mise à jour par {a['status_updated_by']} le {when}")
            if a.get("status_note"):
                st.caption(f"Note : {a['status_note']}")

        with st.expander("🔍 Voir le détail"):
            if a.get("fichier"):
                _render_file_detail(a["fichier"], raw_records)
            elif a.get("semaine"):
                _render_spike_detail(a["partenaire"], a["semaine"], df_messages)
            elif a.get("semaines_manquantes"):
                st.markdown("**Semaines sans prévision reçue :**")
                for s in a["semaines_manquantes"]:
                    st.markdown(f"- {s}")
            else:
                st.caption("Pas de détail supplémentaire disponible.")

        if interactive:
            st.markdown("---")
            note = st.text_input(
                "Note (optionnel)", key=f"note_{a['alert_key']}",
                placeholder="Ex : partenaire recontacté, en attente de confirmation...",
                label_visibility="collapsed",
            )
            bc1, bc2, bc3 = st.columns(3)
            if bc1.button("⏳ Prendre en charge", key=f"encours_{a['alert_key']}",
                           disabled=a["status"] == "en_cours", width='stretch'):
                database.set_alert_status(a["alert_key"], "en_cours", username, note)
                database.log_audit(username, "alerte_prise_en_charge", a["titre"])
                st.cache_data.clear()
                st.rerun()
            if bc2.button("✅ Marquer résolu", key=f"resolu_{a['alert_key']}",
                           disabled=a["status"] == "resolu", width='stretch'):
                database.set_alert_status(a["alert_key"], "resolu", username, note)
                database.log_audit(username, "alerte_resolue", a["titre"])
                st.cache_data.clear()
                st.rerun()
            if bc3.button("↩️ Rouvrir", key=f"reouvrir_{a['alert_key']}",
                           disabled=a["status"] == "nouveau", width='stretch'):
                database.set_alert_status(a["alert_key"], "nouveau", username, note)
                database.log_audit(username, "alerte_reouverte", a["titre"])
                st.cache_data.clear()
                st.rerun()


def _render_file_detail(file_name: str, raw_records: list) -> None:
    match = next((r for r in raw_records if r.get("file_name") == file_name), None)
    st.markdown(f"**Fichier concerné :** `{file_name}`")
    if not match:
        st.caption("Fichier introuvable dans la base (a peut-être été déplacé/supprimé).")
        return

    st.markdown(f"**Reçu le :** {match.get('ingested_at', '?')[:19].replace('T', ' ')}")
    if match.get("parse_error"):
        st.error(f"Erreur de traitement : {match['parse_error']}")

    source_path = Path(match.get("source_file", ""))
    if source_path.exists():
        try:
            content = source_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            content = None
        if content:
            preview = "\n".join(content.splitlines()[:15])
            st.markdown("**Contenu du fichier (aperçu) :**")
            st.code(preview, language="text")
    else:
        st.caption("Le fichier source n'est plus accessible sur le disque.")


def _render_spike_detail(partenaire: str, semaine: str, df_messages) -> None:
    import pandas as pd
    import plotly.express as px

    data = df_messages[df_messages["partenaire"] == partenaire]
    if data.empty:
        st.caption("Pas d'historique disponible pour ce partenaire.")
        return

    df_weekly = data.groupby(pd.Grouper(key="date", freq="W"))["quantite"].sum().reset_index()
    df_weekly["est_le_pic"] = df_weekly["date"].dt.strftime("%Y-%m-%d") == semaine

    fig = px.bar(
        df_weekly.tail(16), x="date", y="quantite", color="est_le_pic",
        color_discrete_map={True: "#ff6b6b", False: "#4a90d9"},
        title=f"Volume hebdomadaire — {partenaire}",
    )
    fig.update_layout(showlegend=False, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#f0f0f0")
    st.plotly_chart(fig, width='stretch', key=f"spike_{partenaire}_{semaine}")


def section_title(text: str) -> None:
    st.markdown(f'<div class="section-title">{text}</div>', unsafe_allow_html=True)


def page_header(icon: str, title: str, subtitle: str = "") -> None:
    """En-tête de page cohérent, utilisé en haut de chaque page pour que
    l'utilisateur sache immédiatement dans quelle section il se trouve."""
    sub_html = f'<div class="page-header-subtitle">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f"""<div class="page-header">
            <div class="page-header-title">{icon} {title}</div>
            {sub_html}
        </div>""",
        unsafe_allow_html=True,
    )
