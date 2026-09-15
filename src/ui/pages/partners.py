"""Page Partenaires.

Vue par partenaire : combien de messages, combien de pièces, tendance.
Remplace l'ancienne page "Drill-down" (terme technique) — même
fonctionnalité, présentée simplement.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from ..components import page_header
from ..context import AppContext
from ...analytics import get_relevant_partners


def render(ctx: AppContext) -> None:
    page_header("🏢", "Partenaires", "Détail des échanges par client ou fournisseur")

    partners = get_relevant_partners(ctx.df_messages, ctx.role)
    if not partners:
        st.info("Aucun partenaire disponible pour votre rôle.")
        return

    cols = st.columns(3)
    for idx, p in enumerate(partners):
        with cols[idx % 3], st.container(border=True):
            data = ctx.df_messages[ctx.df_messages["partenaire"] == p]
            st.markdown(f"**🏢 {p}**")
            st.caption(f"📨 {len(data)} messages · 📦 {data['quantite'].sum():,.0f} pièces")
            if st.button("Voir le détail", key=f"partner_{p}", width='stretch'):
                st.session_state.selected_partner = p

    selected = st.session_state.get("selected_partner")
    if selected and selected in partners:
        data = ctx.df_messages[ctx.df_messages["partenaire"] == selected]

        st.markdown("---")
        st.markdown(f"### 🏢 {selected}")

        c1, c2, c3 = st.columns(3)
        c1.metric("Messages", len(data))
        c2.metric("Pièces échangées", f"{data['quantite'].sum():,.0f}")
        c3.metric("Moyenne / message", f"{data['quantite'].mean():,.0f}")

        df_weekly = data.groupby(pd.Grouper(key="date", freq="W"))["quantite"].sum().reset_index()
        fig = px.line(df_weekly, x="date", y="quantite", markers=True, title="Évolution hebdomadaire")
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#f0f0f0")
        st.plotly_chart(fig, width='stretch')

        if st.button("❌ Fermer le détail"):
            st.session_state.selected_partner = None
            st.rerun()
