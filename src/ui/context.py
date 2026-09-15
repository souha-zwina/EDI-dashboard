"""context.py - Objet de contexte transmis à chaque page pour éviter les
variables globales et les recalculs dupliqués."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass
class AppContext:
    role: str
    username: str
    raw_records: list[dict[str, Any]]
    df_messages: pd.DataFrame          # déjà filtré par rôle
    df_forecasts: pd.DataFrame         # déjà filtré par rôle
    stats: dict[str, Any]
    alerts: list[dict[str, Any]]       # alertes consolidées, langage métier
    watcher_running: bool
