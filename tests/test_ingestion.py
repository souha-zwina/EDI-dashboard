"""Tests du pipeline d'ingestion : classification partenaire, gestion des
fichiers dupliqués, et non-régression sur les erreurs de format."""

from __future__ import annotations

from src import ingestion


def test_ingest_valid_file_succeeds(db, tmp_path, sample_x12_valid):
    f = tmp_path / "inbound" / "valid.x12"
    f.parent.mkdir(parents=True)
    f.write_text(sample_x12_valid, encoding="utf-8")

    ok, result = ingestion.ingest_file(f)

    assert ok is True
    assert result == "ok"
    messages = db.fetch_all_messages()
    assert len(messages) == 1
    assert messages[0]["partner_id"] == "BMWDEU01"


def test_ingest_same_file_twice_is_deduplicated(db, tmp_path, sample_x12_valid):
    f = tmp_path / "valid.x12"
    f.write_text(sample_x12_valid, encoding="utf-8")

    ok1, result1 = ingestion.ingest_file(f)
    ok2, result2 = ingestion.ingest_file(f)

    assert ok1 is True
    assert ok2 is False
    assert result2 == "duplicate"
    assert len(db.fetch_all_messages()) == 1


def test_ingest_bad_quantity_still_ingests_with_error_flag(db, tmp_path, sample_x12_bad_quantity):
    """Un message avec une quantité invalide doit être conservé (pas
    rejeté silencieusement) pour être visible dans le contrôle qualité."""
    f = tmp_path / "bad_qty.x12"
    f.write_text(sample_x12_bad_quantity, encoding="utf-8")

    ok, result = ingestion.ingest_file(f)

    assert ok is True  # le fichier est bien ingéré...
    messages = db.fetch_all_messages()
    assert len(messages) == 1
    # ... mais sa ligne de prévision contient bien la valeur non numérique,
    # ce que la détection d'erreurs qualité doit repérer (voir test_analytics)
    assert messages[0]["forecast_lines"][0]["qty"] == "ABC"


def test_ingest_unreadable_file_logs_error(db, tmp_path, sample_illisible):
    f = tmp_path / "illisible.txt"
    f.write_text(sample_illisible, encoding="utf-8")

    ok, result = ingestion.ingest_file(f)

    assert ok is True  # ingéré quand même, avec parse_error renseigné
    messages = db.fetch_all_messages()
    assert messages[0]["parse_error"] is not None


def test_partner_classification_uses_db_partners_table(db, tmp_path, sample_x12_valid):
    """Vérifie que la classification vient bien de la table `partners`
    (modifiable en admin) et pas d'une valeur codée en dur."""
    db.upsert_partner("BMWDEU01", "Fournisseur", "BMW (reclassé)", active=True)  # reclassé volontairement

    f = tmp_path / "valid.x12"
    f.write_text(sample_x12_valid, encoding="utf-8")
    ingestion.ingest_file(f)

    messages = db.fetch_all_messages()
    assert messages[0]["partner_type"] == "Fournisseur"


def test_unknown_partner_classified_as_autre(db, tmp_path):
    content = (
        "ISA*00*          *00*          *ZZ*INCONNU01      *ZZ*LEARX88        "
        "*260725*0800*U*00401*000009999*0*P*>~\r\n"
        "GS*SH*INCONNU01*LEARX88*20260725*0800*1*X*004010~\r\n"
        "ST*830*0001~\r\nSE*2*0001~\r\nGE*1*1~\r\nIEA*1*000009999~\r\n"
    )
    f = tmp_path / "inconnu.x12"
    f.write_text(content, encoding="utf-8")
    ingestion.ingest_file(f)

    messages = db.fetch_all_messages()
    assert messages[0]["partner_type"] == "Autre"
