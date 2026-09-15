"""Page Prévisions.

Objectif métier : "combien de pièces vais-je recevoir/livrer dans les
prochaines semaines, et dois-je m'attendre à un pic ?" — jamais "quel
modèle de machine learning utiliser". Le choix de la méthode de calcul
(modèle entraîné ou moyenne mobile de secours) est entièrement masqué :
voir analytics.forecast_demand().
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ..components import page_header
from ..context import AppContext
from ...analytics import forecast_demand, get_relevant_partners, reliability_label


def render(ctx: AppContext) -> None:
    page_header("📈", "Prévisions de la demande", "Anticiper les volumes et détecter les pics à venir")

    partners = get_relevant_partners(ctx.df_forecasts, ctx.role)
    if not partners:
        st.info("Pas encore assez d'historique de prévisions pour ce rôle.")
        return

    col1, col2 = st.columns([2, 1])
    choix = col1.selectbox("Partenaire", partners)
    semaines = col2.slider("Semaines à anticiper", 2, 12, 6)

    df_pred, method = forecast_demand(ctx.df_forecasts, choix, semaines)

    if df_pred is None:
        st.warning(
            f"⚠️ Pas assez d'historique pour {choix} afin de calculer une prévision fiable. "
            "Il faut au moins quelques semaines de données passées."
        )
        return

    df_pred["Fiabilité"] = df_pred["Semaine"].apply(lambda w: reliability_label(method, w))

    pics = df_pred[df_pred["Anomalie"] == True]  # noqa: E712
    if len(pics) > 0:
        semaines_pic = ", ".join(d.strftime("%d/%m") for d in pics["Date"])
        st.markdown(
            f"""<div class="alert-warning"><div class="alert-title">
            ⚠️ Pic de demande anticipé — {choix}</div>
            <div style="margin-top:6px;">Semaine(s) concernée(s) : {semaines_pic}.
            Volume attendu nettement supérieur à la moyenne habituelle.</div>
            </div>""",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""<div class="alert-success"><div class="alert-title">
            ✅ Aucun pic anticipé pour {choix} sur les {semaines} prochaines semaines</div>
            </div>""",
            unsafe_allow_html=True,
        )

    col1, col2, col3 = st.columns(3)
    col1.metric("Total anticipé", f"{df_pred['Prévision'].sum():,.0f}")
    col2.metric("Moyenne / semaine", f"{df_pred['Prévision'].mean():,.0f}")
    moyenne_hist = ctx.df_forecasts[ctx.df_forecasts["partenaire"] == choix]["quantite"].mean()
    col3.metric("Moyenne habituelle", f"{moyenne_hist:,.0f}")

    fig = go.Figure()
    normal = df_pred[df_pred["Anomalie"] == False]  # noqa: E712
    if len(normal) > 0:
        fig.add_trace(go.Bar(x=normal["Date"], y=normal["Prévision"], name="Prévision normale",
                              marker_color="#4a90d9", text=normal["Prévision"], textposition="outside"))
    if len(pics) > 0:
        fig.add_trace(go.Bar(x=pics["Date"], y=pics["Prévision"], name="⚠️ Pic anticipé",
                              marker_color="#ff8c42", text=pics["Prévision"], textposition="outside"))
    fig.add_trace(go.Scatter(
        x=pd.concat([df_pred["Date"], df_pred["Date"][::-1]]),
        y=pd.concat([df_pred["Max"], df_pred["Min"][::-1]]),
        fill="toself", fillcolor="rgba(74,144,217,0.15)", line=dict(color="rgba(74,144,217,0)"),
        name="Marge d'incertitude",
    ))
    fig.update_layout(title=f"Volume anticipé par semaine — {choix}", xaxis_title="", yaxis_title="Quantité",
                       height=380, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#f0f0f0")
    st.plotly_chart(fig, width='stretch')

    st.markdown("#### Détail par semaine")
    df_show = df_pred.copy()
    df_show["Date"] = df_show["Date"].dt.strftime("%d/%m/%Y")
    df_show["Statut"] = df_show["Anomalie"].apply(lambda x: "⚠️ Pic anticipé" if x else "✅ Normal")
    st.dataframe(
        df_show[["Date", "Prévision", "Min", "Max", "Fiabilité", "Statut"]],
        width='stretch', hide_index=True,
    )
    st.caption(
        "« Min / Max » = fourchette réaliste autour de la prévision. "
        "« Fiabilité » diminue naturellement plus on anticipe loin dans le temps."
    )

    csv = df_pred.drop(columns=["Anomalie"]).to_csv(index=False)
    st.download_button("📥 Exporter cette prévision (CSV)", data=csv,
                        file_name=f"previsions_{choix}_{datetime.now().strftime('%Y%m%d')}.csv")
