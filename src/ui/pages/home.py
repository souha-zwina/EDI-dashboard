"""Page Vue d'ensemble.

Conçue pour un agent Customer Service / Logistique, pas pour un data
analyst : la première chose visible est "y a-t-il un problème
maintenant ?", pas des courbes à interpréter. Aucune mention d'algorithme
ou de terme technique (Prophet, XGBoost, drill-down...).
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from ..components import page_header, alert_card
from ..context import AppContext


def render(ctx: AppContext) -> None:
    page_header("🏠", "Vue d'ensemble", "État du flux EDI en temps réel")

    actives = [a for a in ctx.alerts if a["status"] != "resolu"]
    critiques = [a for a in actives if a["gravite"] == "critique"]
    attentions = [a for a in actives if a["gravite"] == "attention"]

    # ---- Bandeau de statut : LA chose que l'agent doit voir en 1 seconde ----
    if not actives:
        st.markdown(
            """<div class="alert-success"><div class="alert-title">
            ✅ Tout est normal — aucun problème actif sur le flux EDI</div>
            </div>""",
            unsafe_allow_html=True,
        )
    else:
        parts = []
        if critiques:
            parts.append(f"{len(critiques)} problème(s) urgent(s)")
        if attentions:
            parts.append(f"{len(attentions)} point(s) à surveiller")
        st.markdown(
            f"""<div class="alert-danger"><div class="alert-title">
            🚨 {' et '.join(parts)} nécessitent votre attention</div>
            <div style="margin-top:6px;">Voir le détail ci-dessous, ou dans l'onglet « Alertes ».</div>
            </div>""",
            unsafe_allow_html=True,
        )

    # ---- Les 5 alertes actives les plus urgentes, en langage clair ----
    if actives:
        st.markdown("#### À traiter en priorité")
        for a in actives[:5]:
            alert_card(a, ctx.raw_records, ctx.df_messages)
        if len(actives) > 5:
            st.caption(f"+ {len(actives) - 5} autre(s) alerte(s) — voir l'onglet « Alertes ».")

    st.markdown("---")

    # ---- Chiffres clés du jour, en gros et sans ambiguïté ----
    today = datetime.now().strftime("%Y-%m-%d")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📨 Messages aujourd'hui", ctx.stats["daily_history"].get(today, 0))
    col2.metric("📊 Messages (période)", f"{len(ctx.df_messages):,}")
    col3.metric("📦 Pièces échangées", f"{ctx.df_messages['quantite'].sum():,.0f}" if not ctx.df_messages.empty else "0")
    col4.metric("🏢 Partenaires actifs", ctx.df_messages["partenaire"].nunique() if not ctx.df_messages.empty else 0)

    if ctx.df_messages.empty:
        return

    st.markdown("---")
    st.markdown("#### Activité récente")
    col1, col2 = st.columns(2)

    with col1:
        st.caption("Messages reçus par partenaire (top 10)")
        top = ctx.df_messages["partenaire"].value_counts().head(10).reset_index()
        top.columns = ["Partenaire", "Messages"]
        fig = px.bar(top, x="Partenaire", y="Messages", color="Messages", color_continuous_scale="Blues")
        fig.update_layout(showlegend=False, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#f0f0f0")
        st.plotly_chart(fig, width='stretch')

    with col2:
        st.caption("Répartition par type de document")
        types = ctx.df_messages["type"].value_counts().reset_index()
        types.columns = ["Type", "Messages"]
        fig = px.pie(types, values="Messages", names="Type")
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#f0f0f0")
        st.plotly_chart(fig, width='stretch')

    st.caption("Volume quotidien (30 derniers jours)")
    df_daily = ctx.df_messages.groupby(pd.Grouper(key="date", freq="D"))["quantite"].sum().reset_index().tail(30)
    fig = px.bar(df_daily, x="date", y="quantite", color="quantite", color_continuous_scale="Blues")
    fig.update_layout(showlegend=False, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#f0f0f0")
    st.plotly_chart(fig, width='stretch')
