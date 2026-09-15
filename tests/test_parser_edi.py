"""Tests du parseur EDI : standards reconnus, extraction des champs,
robustesse face aux fichiers mal formés ou mal encodés."""

from __future__ import annotations

from src.parser_edi import detect_standard, normalize_date, parse_edi_file


def test_detect_standard_ansi_x12():
    assert detect_standard("ISA*00*...") == "ANSI_X12"


def test_detect_standard_edifact():
    assert detect_standard("UNB+UNOA:...") == "EDIFACT"


def test_detect_standard_unknown():
    assert detect_standard("Bonjour, ceci n'est pas de l'EDI") == "UNKNOWN"


def test_parse_valid_x12_extracts_key_fields(tmp_path, sample_x12_valid):
    f = tmp_path / "valid.x12"
    f.write_text(sample_x12_valid, encoding="utf-8")

    record = parse_edi_file(f)

    assert record["standard"] == "ANSI_X12"
    assert record["sender"] == "BMWDEU01"
    assert record["receiver"] == "LEARX88"
    assert record["message_type"] == "830"
    assert record.get("parse_error") is None
    assert len(record.get("forecast_lines", [])) == 2


def test_parse_illisible_flags_unknown_standard(tmp_path, sample_illisible):
    f = tmp_path / "illisible.txt"
    f.write_text(sample_illisible, encoding="utf-8")

    record = parse_edi_file(f)

    assert record["standard"] == "UNKNOWN"
    assert "non reconnu" in record["parse_error"]


def test_parse_file_with_latin1_encoding_does_not_crash(tmp_path):
    """Un fichier encodé en latin-1 (accents) ne doit jamais faire planter
    le parseur, contrairement à l'ancienne version (open utf-8 strict)."""
    content = "ISA*00*Société Générale*ZZ*É~\r\n"
    f = tmp_path / "latin1.x12"
    f.write_bytes(content.encode("latin-1"))

    record = parse_edi_file(f)  # ne doit pas lever d'exception
    assert record["standard"] == "ANSI_X12"


def test_normalize_date_8_digits():
    dt = normalize_date("20260725")
    assert dt is not None
    assert (dt.year, dt.month, dt.day) == (2026, 7, 25)


def test_normalize_date_6_digits():
    dt = normalize_date("260725")
    assert dt is not None
    assert (dt.year, dt.month, dt.day) == (2026, 7, 25)


def test_normalize_date_invalid_returns_none():
    assert normalize_date("not-a-date") is None
    assert normalize_date(None) is None
    assert normalize_date("") is None
