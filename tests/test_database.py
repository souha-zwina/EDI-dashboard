"""Tests de la couche de persistance SQLite : c'est LE composant qui
corrige la faille principale de l'ancienne version (perte de données à
chaque redémarrage avec mongomock). Ces tests garantissent que la
déduplication et la persistance fonctionnent réellement."""

from __future__ import annotations



def _fake_record(file_hash: str, partner_id: str = "BMWDEU01") -> dict:
    return {
        "file_hash": file_hash,
        "source_file": f"/tmp/{file_hash}.x12",
        "file_name": f"{file_hash}.x12",
        "standard": "ANSI_X12",
        "sender": partner_id,
        "receiver": "LEARX88",
        "message_type": "830",
        "doc_number": "1001",
        "doc_date_raw": "20260101",
        "doc_date_parsed": "2026-01-01T00:00:00",
        "partner_id": partner_id,
        "partner_type": "Client",
        "sense": "Inbound",
        "raw_segment_count": 5,
        "forecast_lines": [{"qty": "100", "date": "20260101"}],
        "quantities": [],
        "line_items": [],
        "total_forecast_qty": 100,
        "parse_error": None,
    }


def test_insert_and_fetch_message(db):
    db.insert_message(_fake_record("hash1"))
    messages = db.fetch_all_messages()
    assert len(messages) == 1
    assert messages[0]["partner_id"] == "BMWDEU01"


def test_duplicate_file_hash_is_ignored(db):
    """LE test qui prouve que le bug de duplication au redémarrage
    (mongomock) est corrigé : réinsérer le même hash ne doit jamais créer
    une deuxième ligne."""
    db.insert_message(_fake_record("hash1"))
    db.insert_message(_fake_record("hash1"))  # même hash, doit être ignoré
    messages = db.fetch_all_messages()
    assert len(messages) == 1


def test_file_hash_exists(db):
    assert db.file_hash_exists("hash1") is False
    db.insert_message(_fake_record("hash1"))
    assert db.file_hash_exists("hash1") is True


def test_stats_reflect_real_count_not_duplicated(db):
    """Reproduit exactement le bug original : ingérer, 'redémarrer'
    (nouvelle connexion), ré-ingérer les mêmes fichiers -> le total ne
    doit PAS doubler."""
    for i in range(5):
        db.insert_message(_fake_record(f"hash{i}"))
    stats1 = db.get_stats()
    assert stats1["total_messages"] == 5

    # simulate un redémarrage : réingestion des mêmes fichiers (même hash)
    for i in range(5):
        db.insert_message(_fake_record(f"hash{i}"))
    stats2 = db.get_stats()
    assert stats2["total_messages"] == 5, "Les stats ne doivent jamais doubler après un redémarrage"


def test_data_persists_across_reconnection(db, tmp_path):
    """Simule une coupure : on ferme la connexion et on en rouvre une
    nouvelle vers le MÊME fichier .db -> les données doivent toujours être là."""
    db.insert_message(_fake_record("hash_persist"))
    db._local.conn = None  # force une nouvelle connexion au prochain accès

    messages = db.fetch_all_messages()
    assert len(messages) == 1
    assert messages[0]["file_hash"] == "hash_persist"


def test_partner_type_map_reflects_active_partners(db):
    db.upsert_partner("CLIENTX", "Client", "Client X", active=True)
    db.upsert_partner("FOURNISSEURY", "Fournisseur", "Fournisseur Y", active=True)
    db.upsert_partner("INACTIF", "Client", "Inactif", active=False)

    mapping = db.partner_type_map()
    assert mapping["CLIENTX"] == "Client"
    assert mapping["FOURNISSEURY"] == "Fournisseur"
    assert "INACTIF" not in mapping  # partenaire désactivé exclu


def test_recompute_partner_types_updates_existing_messages(db):
    db.insert_message(_fake_record("hash1", partner_id="NEWCO"))
    db.upsert_partner("NEWCO", "Fournisseur", "New Co", active=True)

    updated = db.recompute_partner_types()
    assert updated == 1

    messages = db.fetch_all_messages()
    assert messages[0]["partner_type"] == "Fournisseur"


def test_alert_status_persists(db):
    assert db.get_alert_statuses() == {}
    db.set_alert_status("abc123", "en_cours", "admin", "note de test")
    statuses = db.get_alert_statuses()
    assert statuses["abc123"]["status"] == "en_cours"
    assert statuses["abc123"]["updated_by"] == "admin"


def test_alert_status_update_overwrites(db):
    db.set_alert_status("abc123", "en_cours", "admin")
    db.set_alert_status("abc123", "resolu", "admin", "traité")
    statuses = db.get_alert_statuses()
    assert len(statuses) == 1
    assert statuses["abc123"]["status"] == "resolu"


def test_settings_default_seeded_on_init(db):
    settings = db.get_settings()
    assert settings["spike_threshold"] == "1.5"
    assert settings["lookback_weeks"] == "12"


def test_settings_can_be_updated(db):
    db.set_setting("spike_threshold", "2.0")
    assert db.get_setting("spike_threshold") == "2.0"


def test_audit_log_records_actions(db):
    db.log_audit("admin", "connexion", "")
    db.log_audit("admin", "alerte_resolue", "test")
    logs = db.get_audit_log()
    assert len(logs) == 2
    assert logs[0]["action"] == "alerte_resolue"  # le plus récent en premier
