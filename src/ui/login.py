"""login.py - Écran de connexion.

Corrections par rapport à l'original :
- plus aucun mot de passe affiché à l'écran.
- les comptes viennent de la base (gérés via manage_users.py), plus de
  dictionnaire codé en dur dans le code source.
- carte de connexion construite avec st.container(border=True), un vrai
  conteneur Streamlit natif. L'ancienne version ouvrait un <div> en HTML
  brut dans un st.markdown() séparé sans jamais réussir à l'entourer
  autour des widgets (impossible en Streamlit : chaque widget est un
  élément indépendant) -> le <div> vide s'affichait comme une boîte
  fantôme au-dessus du formulaire.
"""

from __future__ import annotations

import streamlit as st

from .. import auth, config, database
from .components import image_data_uri


def check_password() -> bool:
    if st.session_state.get("authenticated", False):
        return True

    users = database.list_users()
    if not users:
        st.error("⚠️ Aucun utilisateur n'est configuré.")
        st.info(
            "Créez un premier compte depuis un terminal :\n\n"
            "```\npython manage_users.py create admin Administrateur 🔧\n```"
        )
        return False

    st.markdown("<div style='margin-top:60px'></div>", unsafe_allow_html=True)
    col_center = st.columns([1, 1.4, 1])[1]

    with col_center, st.container(border=True):
        logo_uri = image_data_uri(config.LOGO_PATH)
        logo_col = st.columns([1, 2, 1])[1]
        with logo_col:
            if logo_uri:
                st.image(logo_uri, width='stretch')
            else:
                st.markdown("<h1 style='text-align:center;'>🏭 LEAR</h1>", unsafe_allow_html=True)

        st.markdown(
            "<p style='text-align:center;opacity:0.65;margin-top:-8px;'>Electronic Data Interchange</p>",
            unsafe_allow_html=True,
        )

        st.divider()
        st.markdown("#### 🔐 Connexion")

        user_by_username = {u["username"]: u for u in users}
        username = st.selectbox(
            "Utilisateur",
            options=list(user_by_username.keys()),
            format_func=lambda x: f"{user_by_username[x]['icon']} {user_by_username[x]['display_name']}",
        )
        password = st.text_input("Mot de passe", type="password", placeholder="Votre mot de passe")

        if st.button("🚀 Se connecter", width='stretch', type="primary"):
            ok, error_msg, user_info = auth.verify_login(username, password)
            if ok:
                st.session_state.authenticated = True
                st.session_state.username = user_info["username"]
                st.session_state.role = user_info["role"]
                st.session_state.role_icon = user_info["icon"]
                database.log_audit(user_info["username"], "connexion", "")
                st.rerun()
            else:
                st.error(f"❌ {error_msg}")

    return False
