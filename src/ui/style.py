"""style.py - Compléments visuels au-dessus du thème natif Streamlit.

Le thème (couleurs, fond, texte) vient de .streamlit/config.toml, qui est
appliqué nativement par Streamlit à TOUS les éléments (y compris les menus
déroulants). Ce fichier ne fait plus de `!important` global — seulement le
style des quelques composants custom (hero, alertes, pastille de statut)
qui n'ont pas d'équivalent natif.
"""

import streamlit as st

_CSS = """
<style>
    .top-header {
        display: flex; align-items: center; gap: 14px;
        padding: 10px 0 18px 0; margin-bottom: 4px;
        border-bottom: 1px solid rgba(255,255,255,0.1);
    }
    .top-header img { height: 46px; width: auto; border-radius: 4px; }
    .top-header-title { font-size: 1.3rem; font-weight: 700; margin: 0; }

    .hero-section {
        background: linear-gradient(135deg, #12151c 0%, #1c2130 100%);
        border: 1px solid rgba(255,255,255,0.08); padding: 50px 40px; border-radius: 15px;
        margin-bottom: 30px; text-align: center;
    }
    .hero-title { font-size: 2.6rem; font-weight: 800; margin: 0; }
    .hero-subtitle { font-size: 1.15rem; opacity: 0.75; margin: 10px 0 0 0; }
    .hero-badge {
        background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.15);
        padding: 8px 22px; border-radius: 24px; display: inline-block; margin-top: 16px;
    }

    .alert-danger, .alert-warning, .alert-success {
        padding: 14px 20px; border-radius: 8px; margin: 10px 0; border-left: 4px solid;
    }
    .alert-danger  { background: rgba(255,85,85,0.1);  border-color: #ff5555; }
    .alert-warning { background: rgba(255,177,0,0.1);  border-color: #ffb100; }
    .alert-success { background: rgba(61,220,132,0.1); border-color: #3ddc84; }
    .alert-title   { font-weight: 800; font-size: 1.05rem; }
    .alert-danger .alert-title  { color: #ff6b6b; }
    .alert-warning .alert-title { color: #ffb100; }
    .alert-success .alert-title { color: #3ddc84; }

    .section-title {
        font-size: 1.4rem; font-weight: 700;
        border-bottom: 2px solid rgba(255,255,255,0.1); padding-bottom: 8px; margin: 26px 0 16px 0;
    }

    .page-header {
        padding: 4px 0 20px 0; margin-bottom: 18px;
        border-bottom: 3px solid #3d6fd9;
    }
    .page-header-title {
        font-size: 2rem; font-weight: 800; letter-spacing: -0.02em;
    }
    .page-header-subtitle {
        font-size: 1rem; opacity: 0.65; margin-top: 4px;
    }

    .status-pill {
        display:inline-block; padding: 3px 12px; border-radius: 12px;
        font-size: 0.8rem; font-weight: 700;
    }
    .status-pill.online  { background: rgba(61,220,132,0.12); color: #3ddc84; border: 1px solid #3ddc84; }
    .status-pill.offline { background: rgba(255,107,107,0.12); color: #ff6b6b; border: 1px solid #ff6b6b; }

    /* Navigation par onglets (radio custom) */
    div[data-testid="stSidebar"] div[role="radiogroup"] > label {
        border-radius: 8px; padding: 6px 10px; margin-bottom: 2px;
    }
</style>
"""


def inject() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
