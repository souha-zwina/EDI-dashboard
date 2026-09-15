"""Page Données : table brute filtrable + export CSV."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from ..components import page_header
from ..context import AppContext
from ...analytics import get_relevant_partners


def render(ctx: AppContext) -> None:
    page_header("📋", "Données brutes", "Table filtrable et export CSV")

    partners = get_relevant_partners(ctx.df_messages, ctx.role)
    selected = st.multiselect("Filtrer par partenaire", options=partners,
                               default=partners[:3] if len(partners) > 3 else partners)

    df_show = ctx.df_messages.copy()
    if selected:
        df_show = df_show[df_show["partenaire"].isin(selected)]

    st.dataframe(df_show.sort_values("date", ascending=False), width='stretch', height=420)

    csv = df_show.to_csv(index=False)
    st.download_button("📥 Télécharger CSV", data=csv, file_name=f"edi_{datetime.now().strftime('%Y%m%d')}.csv")
