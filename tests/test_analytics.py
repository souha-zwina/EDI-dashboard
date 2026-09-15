"""Tests du moteur d'analyse : détection d'alertes, filtrage par rôle,
prévisions. C'est le cœur métier de l'application."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from src import analytics


def _messages_df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


# ------------------------------------------------------------------
# Filtrage par rôle
# ------------------------------------------------------------------
def test_filter_by_role_customer_service_sees_only_clients():
    df = _messages_df([
        {"partenaire": "RENAULTFR", "type_partenaire": "Client", "date": "2026-01-01", "quantite": 10, "type": "830", "sense": "Inbound", "standard": "ANSI_X12"},
        {"partenaire": "CABLEX0022", "type_partenaire": "Fournisseur", "date": "2026-01-01", "quantite": 5, "type": "810", "sense": "Outbound", "standard": "ANSI_X12"},
    ])
    result = analytics.filter_by_role(df, "Customer Service")
    assert set(result["partenaire"]) == {"RENAULTFR"}


def test_filter_by_role_logistics_sees_only_suppliers():
    df = _messages_df([
        {"partenaire": "RENAULTFR", "type_partenaire": "Client", "date": "2026-01-01", "quantite": 10, "type": "830", "sense": "Inbound", "standard": "ANSI_X12"},
        {"partenaire": "CABLEX0022", "type_partenaire": "Fournisseur", "date": "2026-01-01", "quantite": 5, "type": "810", "sense": "Outbound", "standard": "ANSI_X12"},
    ])
    result = analytics.filter_by_role(df, "Logistics")
    assert set(result["partenaire"]) == {"CABLEX0022"}


def test_filter_by_role_admin_sees_everything():
    df = _messages_df([
        {"partenaire": "RENAULTFR", "type_partenaire": "Client", "date": "2026-01-01", "quantite": 10, "type": "830", "sense": "Inbound", "standard": "ANSI_X12"},
        {"partenaire": "CABLEX0022", "type_partenaire": "Fournisseur", "date": "2026-01-01", "quantite": 5, "type": "810", "sense": "Outbound", "standard": "ANSI_X12"},
    ])
    result = analytics.filter_by_role(df, "Administrateur")
    assert len(result) == 2


# ------------------------------------------------------------------
# Détection de pics de volume
# ------------------------------------------------------------------
def test_spike_detection_flags_abnormal_week():
    base = datetime(2026, 1, 5)  # un lundi
    rows = []
    # 8 semaines normales autour de 100
    for i in range(8):
        rows.append({"partenaire": "BMWDEU01", "type_partenaire": "Client", "date": base + timedelta(weeks=i),
                      "quantite": 100, "type": "830", "sense": "Inbound", "standard": "ANSI_X12"})
    # une semaine avec un pic x9
    rows.append({"partenaire": "BMWDEU01", "type_partenaire": "Client", "date": base + timedelta(weeks=8),
                  "quantite": 900, "type": "830", "sense": "Inbound", "standard": "ANSI_X12"})
    df = _messages_df(rows)

    spikes = analytics.detect_spikes_in_history(df, threshold=1.5, weeks_lookback=12)
    assert len(spikes) == 1
    assert spikes.iloc[0]["partenaire"] == "BMWDEU01"
    assert spikes.iloc[0]["ratio"] > 1.5


def test_spike_threshold_is_configurable():
    base = datetime(2026, 1, 5)
    rows = [
        {"partenaire": "BMWDEU01", "type_partenaire": "Client", "date": base + timedelta(weeks=i),
         "quantite": 100, "type": "830", "sense": "Inbound", "standard": "ANSI_X12"}
        for i in range(8)
    ]
    rows.append({"partenaire": "BMWDEU01", "type_partenaire": "Client", "date": base + timedelta(weeks=8),
                  "quantite": 180, "type": "830", "sense": "Inbound", "standard": "ANSI_X12"})  # x1.8
    df = _messages_df(rows)

    # seuil bas (x1.5) -> détecté
    assert len(analytics.detect_spikes_in_history(df, threshold=1.5)) == 1
    # seuil haut (x3.0) -> pas détecté
    assert len(analytics.detect_spikes_in_history(df, threshold=3.0)) == 0


# ------------------------------------------------------------------
# Alertes consolidées (build_alerts)
# ------------------------------------------------------------------
def test_build_alerts_detects_format_error():
    raw_records = [{
        "partner_id": "UNKNOWN", "file_name": "bad.txt", "standard": "UNKNOWN",
        "message_type": None, "doc_date_parsed": None, "doc_date_raw": None,
        "raw_segment_count": 0, "forecast_lines": [], "parse_error": "Standard non reconnu",
    }]
    df_empty = pd.DataFrame()
    alerts = analytics.build_alerts(raw_records, df_empty, df_empty)

    assert any(a["categorie"] == "Erreur de format" for a in alerts)
    assert all(a["gravite"] in ("critique", "attention") for a in alerts)


def test_build_alerts_alert_key_is_stable_across_recomputation():
    """Un même problème doit produire la MÊME clé d'une exécution à
    l'autre -> condition nécessaire pour que le statut persisté (voir
    test_database.py) s'applique bien à la bonne alerte après recalcul."""
    raw_records = [{
        "partner_id": "BMWDEU01", "file_name": "bad.txt", "standard": "UNKNOWN",
        "message_type": None, "doc_date_parsed": None, "doc_date_raw": None,
        "raw_segment_count": 0, "forecast_lines": [], "parse_error": "Standard non reconnu",
    }]
    df_empty = pd.DataFrame()
    alerts1 = analytics.build_alerts(raw_records, df_empty, df_empty)
    alerts2 = analytics.build_alerts(raw_records, df_empty, df_empty)

    assert alerts1[0]["alert_key"] == alerts2[0]["alert_key"]


def test_build_alerts_merges_persisted_status():
    raw_records = [{
        "partner_id": "BMWDEU01", "file_name": "bad.txt", "standard": "UNKNOWN",
        "message_type": None, "doc_date_parsed": None, "doc_date_raw": None,
        "raw_segment_count": 0, "forecast_lines": [], "parse_error": "Standard non reconnu",
    }]
    df_empty = pd.DataFrame()
    alerts = analytics.build_alerts(raw_records, df_empty, df_empty)
    key = alerts[0]["alert_key"]

    statuses = {key: {"status": "resolu", "note": "traité", "updated_by": "admin", "updated_at": "2026-01-01"}}
    alerts_with_status = analytics.build_alerts(raw_records, df_empty, df_empty, alert_statuses=statuses)

    updated = next(a for a in alerts_with_status if a["alert_key"] == key)
    assert updated["status"] == "resolu"
    assert updated["status_updated_by"] == "admin"


def test_build_alerts_exclude_resolved_when_requested():
    raw_records = [{
        "partner_id": "BMWDEU01", "file_name": "bad.txt", "standard": "UNKNOWN",
        "message_type": None, "doc_date_parsed": None, "doc_date_raw": None,
        "raw_segment_count": 0, "forecast_lines": [], "parse_error": "Standard non reconnu",
    }]
    df_empty = pd.DataFrame()
    alerts = analytics.build_alerts(raw_records, df_empty, df_empty)
    total_before = len(alerts)
    key = alerts[0]["alert_key"]
    statuses = {key: {"status": "resolu", "note": "", "updated_by": "admin", "updated_at": "2026-01-01"}}

    remaining = analytics.build_alerts(raw_records, df_empty, df_empty, alert_statuses=statuses, include_resolved=False)
    assert len(remaining) == total_before - 1
    assert all(a["alert_key"] != key for a in remaining)


def test_resolved_alerts_sort_after_active_ones():
    """Les alertes résolues doivent apparaître en dernier dans la liste
    triée, pour que l'agent voie d'abord ce qui reste à traiter."""
    raw_records = [{
        "partner_id": "BMWDEU01", "file_name": "bad.txt", "standard": "UNKNOWN",
        "message_type": None, "doc_date_parsed": None, "doc_date_raw": None,
        "raw_segment_count": 0, "forecast_lines": [], "parse_error": "Standard non reconnu",
    }]
    df_empty = pd.DataFrame()
    alerts = analytics.build_alerts(raw_records, df_empty, df_empty)
    key = alerts[0]["alert_key"]
    statuses = {key: {"status": "resolu", "note": "", "updated_by": "admin", "updated_at": "2026-01-01"}}

    alerts_sorted = analytics.build_alerts(raw_records, df_empty, df_empty, alert_statuses=statuses)
    assert alerts_sorted[-1]["alert_key"] == key
    assert alerts_sorted[-1]["status"] == "resolu"


# ------------------------------------------------------------------
# Prévisions (fallback moyenne mobile garanti disponible)
# ------------------------------------------------------------------
def test_forecast_demand_moving_average_fallback_always_works():
    """Sans modèle entraîné (xgboost non disponible ou pas assez de
    données), la prévision doit TOUJOURS retourner un résultat exploitable
    -- jamais un message d'erreur technique affiché à l'utilisateur."""
    base = datetime(2026, 1, 5)
    rows = [
        {"partenaire": "BMWDEU01", "date": base + timedelta(weeks=i), "quantite": 100 + i * 5, "type_partenaire": "Client"}
        for i in range(6)
    ]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])

    result = analytics._forecast_moving_average(df, "BMWDEU01", weeks=4)

    assert result is not None
    assert len(result) == 4
    assert (result["Prévision"] >= 0).all()


def test_forecast_demand_returns_none_for_unknown_partner():
    df = pd.DataFrame({"partenaire": [], "date": [], "quantite": [], "type_partenaire": []})
    df_pred, method = analytics.forecast_demand(df, "INCONNU", weeks=4)
    assert df_pred is None
    assert method == "indisponible"


def test_reliability_label_degrades_over_horizon():
    assert analytics.reliability_label("modele", 1) == "Élevée"
    assert analytics.reliability_label("modele", 6) == "Indicative"
    assert analytics.reliability_label("moyenne_mobile", 1) == "Moyenne"
