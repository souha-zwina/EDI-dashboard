"""Page Administration (Administrateur uniquement).

Centralise tout ce qui était auparavant codé en dur ou géré uniquement en
ligne de commande : partenaires, seuils de détection d'alerte, et donne
une vue d'audit de qui a fait quoi.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ... import auth, database
from ..components import page_header
from ..context import AppContext


def render(ctx: AppContext) -> None:
    page_header("⚙️", "Administration", "Partenaires, seuils d'alerte, utilisateurs et journal d'audit")

    if ctx.role != "Administrateur":
        st.error("⛔ Cette page est réservée aux administrateurs.")
        return

    tab_partners, tab_thresholds, tab_users, tab_audit = st.tabs(
        ["🏢 Partenaires", "🎚️ Seuils d'alerte", "👥 Utilisateurs", "📜 Journal d'audit"]
    )

    # ------------------------------------------------------------------
    with tab_partners:
        st.markdown("#### Partenaires enregistrés")
        st.caption(
            "Ajouter ou modifier un partenaire ici s'applique immédiatement aux "
            "NOUVEAUX messages ingérés. Pour appliquer le changement à l'historique "
            "déjà en base, utilisez le bouton de recalcul ci-dessous."
        )

        partners = database.list_partners()
        if partners:
            df = pd.DataFrame(partners)[["partner_id", "partner_type", "display_name", "active"]]
            df.columns = ["Identifiant", "Type", "Nom affiché", "Actif"]
            df["Actif"] = df["Actif"].apply(lambda x: "✅" if x else "❌")
            st.dataframe(df, width='stretch', hide_index=True)
        else:
            st.info("Aucun partenaire enregistré pour le moment.")

        with st.expander("➕ Ajouter / modifier un partenaire"):
            with st.form("partner_form", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                pid = c1.text_input("Identifiant EDI (ex: RENAULTFR)")
                ptype = c2.selectbox("Type", ["Client", "Fournisseur"])
                pname = c3.text_input("Nom affiché (optionnel)")
                active = st.checkbox("Actif", value=True)
                submitted = st.form_submit_button("Enregistrer")
                if submitted:
                    if not pid.strip():
                        st.error("L'identifiant EDI est obligatoire.")
                    else:
                        database.upsert_partner(pid, ptype, pname, active)
                        database.log_audit(ctx.username, "partenaire_modifie", f"{pid} -> {ptype}")
                        st.cache_data.clear()
                        st.success(f"Partenaire {pid.upper()} enregistré.")
                        st.rerun()

        if partners:
            with st.expander("🗑️ Supprimer un partenaire"):
                to_delete = st.selectbox("Partenaire à supprimer", [p["partner_id"] for p in partners])
                if st.button("Supprimer définitivement", type="primary"):
                    database.delete_partner(to_delete)
                    database.log_audit(ctx.username, "partenaire_supprime", to_delete)
                    st.cache_data.clear()
                    st.rerun()

        st.markdown("---")
        if st.button("🔄 Recalculer les types sur l'historique existant"):
            n = database.recompute_partner_types()
            database.log_audit(ctx.username, "recalcul_partenaires", f"{n} messages mis à jour")
            st.cache_data.clear()
            st.success(f"{n} message(s) mis à jour avec le type de partenaire actuel.")

    # ------------------------------------------------------------------
    with tab_thresholds:
        st.markdown("#### Sensibilité de détection")
        settings = database.get_settings()
        current_threshold = float(settings.get("spike_threshold", 1.5))
        current_lookback = int(settings.get("lookback_weeks", 12))

        col1, col2 = st.columns(2)
        new_threshold = col1.slider(
            "Seuil de pic de demande (x fois la moyenne)", 1.1, 5.0, current_threshold, 0.1,
            help="Un volume hebdomadaire dépassant CE multiple de la moyenne historique du "
                 "partenaire déclenche une alerte « Pic de volume détecté ».",
        )
        new_lookback = col2.slider(
            "Fenêtre d'analyse (semaines)", 4, 52, current_lookback,
            help="Nombre de semaines d'historique prises en compte pour calculer la moyenne "
                 "d'un partenaire et détecter les prévisions manquantes.",
        )

        if st.button("💾 Enregistrer les seuils"):
            database.set_setting("spike_threshold", str(new_threshold))
            database.set_setting("lookback_weeks", str(new_lookback))
            database.log_audit(ctx.username, "seuils_modifies", f"pic={new_threshold}, fenetre={new_lookback}")
            st.cache_data.clear()
            st.success("Seuils mis à jour — pris en compte au prochain rafraîchissement.")

    # ------------------------------------------------------------------
    with tab_users:
        st.markdown("#### Comptes utilisateurs")
        users = database.list_users()
        if users:
            df = pd.DataFrame(users)[["username", "role", "display_name"]]
            df.columns = ["Identifiant", "Rôle", "Nom affiché"]
            st.dataframe(df, width='stretch', hide_index=True)

        with st.expander("➕ Créer un utilisateur"):
            with st.form("user_form", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                new_username = c1.text_input("Identifiant de connexion")
                new_role = c2.selectbox("Rôle", ["Customer Service", "Logistics", "Administrateur"])
                new_icon = c3.text_input("Icône (emoji)", value="👤")
                new_password = st.text_input("Mot de passe (min. 8 caractères)", type="password")
                submitted = st.form_submit_button("Créer le compte")
                if submitted:
                    if not new_username.strip() or len(new_password) < 8:
                        st.error("Identifiant requis et mot de passe d'au moins 8 caractères.")
                    else:
                        database.upsert_user(
                            new_username.strip(), auth.hash_password(new_password),
                            new_role, new_role, new_icon or "👤",
                        )
                        database.log_audit(ctx.username, "utilisateur_cree", new_username)
                        st.success(f"Compte {new_username} créé.")
                        st.rerun()

        if users:
            with st.expander("🗑️ Supprimer un utilisateur"):
                deletable = [u["username"] for u in users if u["username"] != ctx.username]
                if deletable:
                    to_delete = st.selectbox("Utilisateur à supprimer", deletable)
                    if st.button("Supprimer définitivement", type="primary", key="del_user"):
                        database.delete_user(to_delete)
                        database.log_audit(ctx.username, "utilisateur_supprime", to_delete)
                        st.rerun()
                else:
                    st.caption("Vous ne pouvez pas supprimer votre propre compte depuis ici.")

    # ------------------------------------------------------------------
    with tab_audit:
        st.markdown("#### Historique des actions")
        logs = database.get_audit_log(200)
        if not logs:
            st.info("Aucune action enregistrée pour le moment.")
        else:
            df = pd.DataFrame(logs)[["created_at", "username", "action", "detail"]]
            df.columns = ["Date", "Utilisateur", "Action", "Détail"]
            df["Date"] = df["Date"].str[:19].str.replace("T", " ")
            st.dataframe(df, width='stretch', hide_index=True, height=500)
