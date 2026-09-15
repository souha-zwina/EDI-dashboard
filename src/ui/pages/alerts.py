"""Page Alertes.

Regroupe TOUT ce qui peut clocher dans le flux EDI (messages mal formés,
pics de volume, partenaires silencieux) en une seule liste priorisée,
décrite en langage métier. Chaque alerte peut être prise en charge et
marquée résolue : ce n'est plus un simple affichage, c'est un vrai suivi
de traitement, comme un outil de ticketing.
"""

from __future__ import annotations

import streamlit as st

from ..components import alert_card, page_header
from ..context import AppContext


def render(ctx: AppContext) -> None:
    page_header("🚨", "Alertes", "Tous les problèmes détectés sur le flux EDI, du plus urgent au moins urgent")

    non_resolues = [a for a in ctx.alerts if a["status"] != "resolu"]
    critiques = [a for a in non_resolues if a["gravite"] == "critique"]
    attentions = [a for a in non_resolues if a["gravite"] == "attention"]
    resolues = [a for a in ctx.alerts if a["status"] == "resolu"]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🔴 Urgent", len(critiques))
    col2.metric("🟠 À surveiller", len(attentions))
    col3.metric("✅ Résolues", len(resolues))
    col4.metric("📨 Messages traités", len(ctx.raw_records))

    if not ctx.alerts:
        st.markdown(
            '<div class="alert-success"><div class="alert-title">'
            '✅ Aucune alerte — le flux EDI fonctionne normalement.</div></div>',
            unsafe_allow_html=True,
        )
        return

    st.markdown("---")

    categories = sorted(set(a["categorie"] for a in ctx.alerts))
    partenaires = sorted(set(a["partenaire"] for a in ctx.alerts))

    col_f1, col_f2, col_f3 = st.columns([2, 2, 1])
    cat_filter = col_f1.multiselect("Filtrer par type de problème", categories, default=categories)
    partner_filter = col_f2.multiselect("Filtrer par partenaire", partenaires, default=partenaires)
    show_resolved = col_f3.checkbox("Voir les résolues", value=False)

    filtered = [
        a for a in ctx.alerts
        if a["categorie"] in cat_filter
        and a["partenaire"] in partner_filter
        and (show_resolved or a["status"] != "resolu")
    ]

    if not filtered:
        st.info("Aucune alerte ne correspond à ce filtre.")
        return

    for a in filtered:
        alert_card(a, ctx.raw_records, ctx.df_messages, interactive=True, username=ctx.username)
