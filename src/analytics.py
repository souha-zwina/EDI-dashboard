"""
analytics.py - Préparation des données, détection d'anomalies, prévisions
=============================================================================
Logique métier pure (aucun `st.*`) -> testable sans lancer Streamlit,
et réutilisable si un jour on expose une API en plus du dashboard.
"""

from __future__ import annotations

import hashlib
import logging
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from . import config

logger = logging.getLogger("edi.analytics")

try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False


# ------------------------------------------------------------------
# Préparation des données
# ------------------------------------------------------------------
def prepare_dataframes(raw_records: list[dict[str, Any]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    messages, forecasts = [], []

    for rec in raw_records:
        doc_date = rec.get("doc_date_parsed") or rec.get("doc_date_raw")
        if not doc_date:
            continue
        try:
            doc_date = pd.to_datetime(doc_date)
        except (ValueError, TypeError):
            continue

        partner_id = rec.get("partner_id", "Inconnu")
        partner_type = rec.get("partner_type") or (
            "Client" if partner_id in config.CLIENTS
            else "Fournisseur" if partner_id in config.SUPPLIERS
            else "Autre"
        )

        messages.append({
            "partenaire": partner_id,
            "type": rec.get("message_type", "Inconnu"),
            "date": doc_date,
            "quantite": rec.get("total_forecast_qty", 0),
            "sense": rec.get("sense", "Inconnu"),
            "type_partenaire": partner_type,
            "standard": rec.get("standard", "Inconnu"),
        })

        for line in rec.get("forecast_lines") or []:
            qty_raw = line.get("qty")
            date_str = line.get("date")
            if qty_raw is None or not str(qty_raw).lstrip("-").isdigit() or not date_str:
                continue
            try:
                f_date = (
                    pd.to_datetime(str(date_str), format="%Y%m%d")
                    if len(str(date_str)) == 8
                    else pd.to_datetime(date_str)
                )
            except (ValueError, TypeError):
                continue
            forecasts.append({
                "partenaire": partner_id,
                "date": f_date,
                "quantite": int(qty_raw),
                "type_partenaire": partner_type,
            })

    df_messages = pd.DataFrame(messages)
    df_forecasts = pd.DataFrame(forecasts)
    return df_messages, df_forecasts


# ------------------------------------------------------------------
# Détections
# ------------------------------------------------------------------
def detect_missing_forecast(df_forecasts: pd.DataFrame, df_messages: pd.DataFrame, weeks_lookback: int = 12) -> list[dict]:
    if df_messages.empty:
        return []
    alerts = []
    for partner in df_messages["partenaire"].unique():
        partner_forecasts = df_forecasts[df_forecasts["partenaire"] == partner] if not df_forecasts.empty else pd.DataFrame()
        if partner_forecasts.empty:
            continue

        max_date = datetime.now()
        min_date = max_date - timedelta(weeks=weeks_lookback)
        all_weeks = pd.date_range(start=min_date, end=max_date, freq="W-MON")
        forecast_weeks = partner_forecasts["date"].dt.to_period("W").unique()

        for week_start in all_weeks:
            if week_start.to_period("W") not in forecast_weeks:
                alerts.append({
                    "partenaire": partner,
                    "semaine": week_start.strftime("%Y-%m-%d"),
                    "type": "Prévision manquante",
                    "gravite": "Critique",
                })
    return alerts


def detect_spikes_in_history(df_messages: pd.DataFrame, threshold: float = 1.5, weeks_lookback: int = 12) -> pd.DataFrame:
    if df_messages.empty:
        return pd.DataFrame()

    spikes = []
    for partner in df_messages["partenaire"].unique():
        partner_data = df_messages[df_messages["partenaire"] == partner]
        df_weekly = partner_data.groupby(pd.Grouper(key="date", freq="W"))["quantite"].sum().reset_index()
        df_weekly = df_weekly.tail(weeks_lookback)
        if len(df_weekly) < 4:
            continue

        moyenne = df_weekly["quantite"].mean()
        if moyenne == 0:
            continue

        for _, row in df_weekly.iterrows():
            if row["quantite"] > moyenne * threshold:
                spikes.append({
                    "partenaire": partner,
                    "semaine": row["date"].strftime("%Y-%m-%d"),
                    "quantite": row["quantite"],
                    "moyenne": round(moyenne, 1),
                    "ratio": round(row["quantite"] / moyenne, 1),
                })
    return pd.DataFrame(spikes)


def calculate_variance_metrics(df_pred: pd.DataFrame, moyenne_hist: float) -> dict | None:
    if df_pred is None or df_pred.empty:
        return None
    max_pred = df_pred["Prévision"].max()
    variance_abs = max_pred - moyenne_hist
    variance_pct = (variance_abs / moyenne_hist * 100) if moyenne_hist > 0 else 0
    return {
        "max_pred": max_pred,
        "min_pred": df_pred["Prévision"].min(),
        "avg_pred": df_pred["Prévision"].mean(),
        "variance_abs": variance_abs,
        "variance_pct": variance_pct,
        "is_spike": variance_pct > 50,
    }


def detect_edi_errors(raw_records: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    errors, warnings_local = [], []

    for rec in raw_records:
        partner = rec.get("partner_id", "Inconnu")
        source = rec.get("file_name", rec.get("source_file", "Inconnu"))

        standard = rec.get("standard")
        if standard in (None, "UNKNOWN"):
            errors.append({"type": "Standard non reconnu", "partner": partner, "file": source, "severity": "Erreur"})

        if rec.get("message_type") is None:
            errors.append({"type": "Type de message manquant", "partner": partner, "file": source, "severity": "Erreur"})

        if partner in ("UNKNOWN", "Inconnu"):
            warnings_local.append({"type": "Partenaire non identifié", "partner": partner, "file": source, "severity": "Avertissement"})

        if rec.get("doc_date_parsed") is None and rec.get("doc_date_raw") is None:
            warnings_local.append({"type": "Date manquante", "partner": partner, "file": source, "severity": "Avertissement"})

        for line in rec.get("forecast_lines") or []:
            qty = line.get("qty")
            if not qty or not str(qty).isdigit():
                errors.append({"type": "Quantité invalide", "partner": partner, "file": source, "severity": "Erreur"})
                break

        if rec.get("raw_segment_count", 0) < 3:
            warnings_local.append({"type": "Message trop court", "partner": partner, "file": source, "severity": "Avertissement"})

        if rec.get("parse_error"):
            errors.append({"type": f"Erreur de parsing : {rec['parse_error']}", "partner": partner, "file": source, "severity": "Erreur"})

    return errors, warnings_local


# ------------------------------------------------------------------
# Filtrage par rôle
# ------------------------------------------------------------------
def filter_by_role(df: pd.DataFrame, role: str) -> pd.DataFrame:
    if df.empty:
        return df
    if role == "Customer Service":
        return df[df["type_partenaire"] == "Client"]
    if role == "Logistics":
        return df[df["type_partenaire"] == "Fournisseur"]
    return df


def get_relevant_partners(df: pd.DataFrame, role: str) -> list[str]:
    if df.empty:
        return []
    if role == "Customer Service":
        return sorted(df[df["type_partenaire"] == "Client"]["partenaire"].unique())
    if role == "Logistics":
        return sorted(df[df["type_partenaire"] == "Fournisseur"]["partenaire"].unique())
    return sorted(df["partenaire"].unique())


# ------------------------------------------------------------------
# Modèle XGBoost
# ------------------------------------------------------------------
def load_or_train_xgboost(df_forecasts: pd.DataFrame) -> tuple[Any, bool]:
    if not XGB_AVAILABLE:
        return None, False

    model_path = Path(config.MODEL_PATH)
    current_n = len(df_forecasts)

    if model_path.exists():
        try:
            with model_path.open("rb") as f:
                cached = pickle.load(f)
            # Le modèle en cache n'est réutilisé que s'il a été entraîné sur
            # un volume de données comparable. Sans ce contrôle, un modèle
            # entraîné sur un petit échantillon resterait utilisé pour
            # toujours, même après l'arrivée de centaines de nouveaux
            # messages -> prévisions basées sur des données périmées.
            if isinstance(cached, dict) and abs(cached.get("n_rows", 0) - current_n) <= max(5, current_n * 0.05):
                return cached["model"], True
        except (pickle.PickleError, EOFError, OSError, KeyError) as exc:
            logger.warning("Modèle corrompu, ré-entraînement : %s", exc)

    if current_n < 20:
        return None, False

    df = df_forecasts.sort_values("date").copy()
    df["week"] = df["date"].dt.isocalendar().week
    df["month"] = df["date"].dt.month
    df["year"] = df["date"].dt.year
    for i in range(1, 5):
        df[f"lag_{i}"] = df["quantite"].shift(i)
    df["rolling_mean_4"] = df["quantite"].rolling(4).mean()
    df["rolling_std_4"] = df["quantite"].rolling(4).std()
    df = df.dropna()

    if len(df) < 20:
        return None, False

    features = ["week", "month", "year", "lag_1", "lag_2", "lag_3", "lag_4", "rolling_mean_4", "rolling_std_4"]
    try:
        model = xgb.XGBRegressor(n_estimators=100, max_depth=4, learning_rate=0.05, random_state=42, verbosity=0)
        model.fit(df[features], df["quantite"])
        model_path.parent.mkdir(parents=True, exist_ok=True)
        with model_path.open("wb") as f:
            pickle.dump({"model": model, "n_rows": current_n}, f)
        return model, True
    except Exception:
        logger.exception("Échec de l'entraînement XGBoost")
        return None, False


def predict_with_xgboost(model: Any, df_forecasts: pd.DataFrame, partenaire: str, weeks: int = 6) -> pd.DataFrame | None:
    if model is None:
        return None

    df_partenaire = df_forecasts[df_forecasts["partenaire"] == partenaire].sort_values("date")
    if len(df_partenaire) < 4:
        return None

    last_date = df_partenaire["date"].max()
    last_quantities = df_partenaire["quantite"].tail(4).tolist()
    moyenne_hist = df_partenaire["quantite"].mean()
    std_hist = df_partenaire["quantite"].std() or 0.0

    predictions = []
    for i in range(1, weeks + 1):
        future_date = last_date + timedelta(weeks=i)
        features = pd.DataFrame([{
            "week": future_date.isocalendar().week,
            "month": future_date.month,
            "year": future_date.year,
            "lag_1": last_quantities[-1] if len(last_quantities) > 0 else 0,
            "lag_2": last_quantities[-2] if len(last_quantities) > 1 else 0,
            "lag_3": last_quantities[-3] if len(last_quantities) > 2 else 0,
            "lag_4": last_quantities[-4] if len(last_quantities) > 3 else 0,
            "rolling_mean_4": np.mean(last_quantities[-4:]) if len(last_quantities) >= 4 else 0,
            "rolling_std_4": np.std(last_quantities[-4:]) if len(last_quantities) >= 4 else 0,
        }])

        try:
            pred = max(0, int(model.predict(features)[0]))
        except Exception:
            pred = int(moyenne_hist)

        confiance = max(0.5, 0.9 - (i * 0.04))
        marge = std_hist * 1.96 * (1 + i * 0.02)

        predictions.append({
            "Semaine": i,
            "Date": future_date,
            "Prévision": pred,
            "Min": max(0, int(pred - marge)),
            "Max": int(pred + marge),
            "Confiance": confiance,
            "Anomalie": pred > moyenne_hist * 1.5,
        })

        last_quantities.append(pred)
        if len(last_quantities) > 8:
            last_quantities = last_quantities[-4:]

    return pd.DataFrame(predictions)


def _forecast_moving_average(df_forecasts: pd.DataFrame, partenaire: str, weeks: int = 6) -> pd.DataFrame | None:
    """Prévision de secours, toujours disponible (aucune dépendance externe).
    Moyenne mobile pondérée + tendance linéaire simple sur les 8 dernières
    semaines. Moins précise qu'un modèle entraîné, mais garantit que la
    page de prévisions fonctionne TOUJOURS, même sur un poste où xgboost/
    prophet ne sont pas installés (jamais de message technique affiché à
    un utilisateur métier)."""
    df_p = df_forecasts[df_forecasts["partenaire"] == partenaire].sort_values("date")
    if len(df_p) < 3:
        return None

    last_date = df_p["date"].max()
    recent = df_p["quantite"].tail(8).tolist()
    moyenne_hist = df_p["quantite"].mean()
    std_hist = df_p["quantite"].std() or 0.0

    # tendance : régression linéaire simple sur les derniers points
    y = np.array(recent, dtype=float)
    x = np.arange(len(y))
    if len(y) >= 2 and np.std(x) > 0:
        slope = np.polyfit(x, y, 1)[0]
    else:
        slope = 0.0

    weights = np.linspace(1, 2, num=min(4, len(recent)))
    base = np.average(recent[-len(weights):], weights=weights)

    predictions = []
    for i in range(1, weeks + 1):
        pred = max(0, base + slope * i)
        marge = std_hist * 1.5 * (1 + i * 0.05)
        predictions.append({
            "Semaine": i,
            "Date": last_date + timedelta(weeks=i),
            "Prévision": int(round(pred)),
            "Min": max(0, int(pred - marge)),
            "Max": int(pred + marge),
            "Confiance": max(0.4, 0.75 - i * 0.04),
            "Anomalie": pred > moyenne_hist * 1.5,
        })
    return pd.DataFrame(predictions)


def forecast_demand(df_forecasts: pd.DataFrame, partenaire: str, weeks: int = 6) -> tuple[pd.DataFrame | None, str]:
    """Point d'entrée UNIQUE pour la prévision, utilisé par l'interface.

    La méthode utilisée (modèle entraîné ou moyenne mobile de secours) est
    choisie automatiquement et n'est JAMAIS montrée à l'utilisateur métier
    -- un agent Customer Service n'a pas à savoir ce qu'est XGBoost, il a
    besoin d'un chiffre fiable et d'une alerte s'il y a un pic à prévoir.

    Retourne (dataframe_prévisions, méthode) où méthode est un identifiant
    interne ('modele' ou 'moyenne_mobile') utilisé uniquement pour ajuster
    le libellé de fiabilité affiché, jamais le nom de l'algorithme.
    """
    if XGB_AVAILABLE:
        model, ok = load_or_train_xgboost(df_forecasts)
        if ok:
            df_pred = predict_with_xgboost(model, df_forecasts, partenaire, weeks)
            if df_pred is not None:
                return df_pred, "modele"

    df_pred = _forecast_moving_average(df_forecasts, partenaire, weeks)
    if df_pred is not None:
        return df_pred, "moyenne_mobile"

    return None, "indisponible"


def reliability_label(method: str, week_index: int) -> str:
    """Traduit la méthode + l'horizon en un libellé compréhensible par un
    non-spécialiste, plutôt qu'un pourcentage de confiance technique."""
    if method == "modele":
        if week_index <= 2:
            return "Élevée"
        if week_index <= 4:
            return "Moyenne"
        return "Indicative"
    else:
        if week_index <= 2:
            return "Moyenne"
        return "Indicative"


# ------------------------------------------------------------------
# Alertes métier consolidées — langage clair pour un agent Customer
# Service / Logistique, sans jargon technique ni nom d'algorithme.
# ------------------------------------------------------------------
def build_alerts(
    raw_records: list[dict[str, Any]],
    df_messages: pd.DataFrame,
    df_forecasts: pd.DataFrame,
    spike_threshold: float = 1.5,
    lookback_weeks: int = 12,
    alert_statuses: dict[str, dict[str, Any]] | None = None,
    include_resolved: bool = True,
) -> list[dict[str, Any]]:
    """Retourne une liste d'alertes uniformes, triées par gravité :
    {gravite, categorie, partenaire, titre, description, action, alert_key,
     status, assigned_note, updated_by, updated_at}

    `alert_key` est un identifiant STABLE (hash déterministe) qui ne change
    pas d'un recalcul à l'autre pour la même situation -> permet de
    persister un statut de traitement (nouveau/en_cours/résolu) en base
    sans avoir à stocker l'alerte elle-même, qui reste toujours dérivée
    des données réelles.
    """
    alert_statuses = alert_statuses or {}
    alerts: list[dict[str, Any]] = []

    def _key(*parts: str) -> str:
        raw = "|".join(str(p) for p in parts)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    # 1) Messages EDI mal formés (problème technique de flux)
    errors, warnings_local = detect_edi_errors(raw_records)
    for e in errors:
        alerts.append({
            "gravite": "critique",
            "categorie": "Erreur de format",
            "partenaire": e["partner"],
            "titre": f"Message EDI illisible ou mal formé ({e['partner']})",
            "description": f"{e['type']} — fichier concerné : {e['file']}.",
            "action": "Vérifier le fichier source avec le partenaire, le message n'a pas pu être exploité.",
            "fichier": e["file"],
            "alert_key": _key("format", e["partner"], e["file"], e["type"]),
        })
    for w in warnings_local:
        alerts.append({
            "gravite": "attention",
            "categorie": "Anomalie de contenu",
            "partenaire": w["partner"],
            "titre": f"{w['type']} ({w['partner']})",
            "description": f"Fichier concerné : {w['file']}.",
            "action": "À vérifier, le message a été traité mais contient une information incomplète.",
            "fichier": w["file"],
            "alert_key": _key("contenu", w["partner"], w["file"], w["type"]),
        })

    # 2) Pics de volume déjà survenus (ex: client qui passe de 100 à 1000)
    spikes_df = detect_spikes_in_history(df_messages, threshold=spike_threshold, weeks_lookback=lookback_weeks)
    for _, row in spikes_df.iterrows():
        alerts.append({
            "gravite": "attention",
            "categorie": "Pic de volume détecté",
            "partenaire": row["partenaire"],
            "titre": f"Hausse inhabituelle de la demande — {row['partenaire']}",
            "description": (
                f"Semaine du {row['semaine']} : {row['quantite']:.0f} pièces reçues, "
                f"contre {row['moyenne']:.0f} en moyenne (x{row['ratio']:.1f})."
            ),
            "action": "Confirmer ce volume avec le partenaire et vérifier la capacité de traitement.",
            "semaine": row["semaine"],
            "alert_key": _key("pic", row["partenaire"], row["semaine"]),
        })

    # 3) Prévisions manquantes (silence d'un partenaire)
    missing = detect_missing_forecast(df_forecasts, df_messages, weeks_lookback=lookback_weeks)
    # on regroupe par partenaire pour ne pas noyer l'agent sous N lignes/semaine
    by_partner: dict[str, list[str]] = {}
    for m in missing:
        by_partner.setdefault(m["partenaire"], []).append(m["semaine"])
    for partner, weeks in by_partner.items():
        alerts.append({
            "gravite": "critique" if len(weeks) >= 3 else "attention",
            "categorie": "Silence partenaire",
            "partenaire": partner,
            "titre": f"Prévisions manquantes — {partner}",
            "description": f"{len(weeks)} semaine(s) sans prévision reçue (dernières {lookback_weeks} semaines).",
            "action": "Relancer le partenaire : il n'envoie plus ses prévisions comme attendu.",
            "semaines_manquantes": sorted(weeks),
            # la clé ne dépend PAS de la liste exacte des semaines : le
            # "problème" est le même d'une semaine à l'autre tant qu'il
            # n'est pas résolu, on ne veut pas une nouvelle clé à chaque
            # nouvelle semaine de silence.
            "alert_key": _key("silence", partner),
        })

    # Fusion avec le statut de traitement persisté
    for a in alerts:
        st_row = alert_statuses.get(a["alert_key"])
        a["status"] = st_row["status"] if st_row else "nouveau"
        a["status_note"] = st_row.get("note", "") if st_row else ""
        a["status_updated_by"] = st_row.get("updated_by") if st_row else None
        a["status_updated_at"] = st_row.get("updated_at") if st_row else None

    if not include_resolved:
        alerts = [a for a in alerts if a["status"] != "resolu"]

    severity_order = {"critique": 0, "attention": 1, "info": 2}
    status_order = {"nouveau": 0, "en_cours": 1, "resolu": 2}
    alerts.sort(key=lambda a: (status_order.get(a["status"], 0), severity_order.get(a["gravite"], 3)))
    for i, a in enumerate(alerts):
        a["id"] = i
    return alerts
