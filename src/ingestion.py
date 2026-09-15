"""
ingestion.py - Logique d'ingestion des fichiers EDI
======================================================
Fait le lien entre le parseur (parser_edi.py) et la base (database.py).
Aucune dépendance à Streamlit ni au watcher : testable isolément.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from . import config, database
from .parser_edi import EdiParseError, normalize_date, parse_edi_file

logger = logging.getLogger("edi.ingestion")


def _file_hash(filepath: Path) -> str:
    hasher = hashlib.sha256()  # sha256 : plus sûr que md5, coût négligeable ici
    with filepath.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _classify_partner(record: dict[str, Any]) -> tuple[str, str]:
    sender = record.get("sender")
    receiver = record.get("receiver")
    if sender and sender != config.OWN_PARTNER_ID:
        partner_id = sender
    elif receiver and receiver != config.OWN_PARTNER_ID:
        partner_id = receiver
    else:
        partner_id = "UNKNOWN"

    partner_type = database.partner_type_map().get(partner_id, "Autre")
    return partner_id, partner_type


def ingest_file(filepath: str | Path) -> tuple[bool, str]:
    """Ingère un seul fichier. Retourne (succès, message)."""
    filepath = Path(filepath)

    try:
        file_hash = _file_hash(filepath)
    except OSError as exc:
        database.log_ingestion_event(filepath.name, "error", f"Fichier illisible : {exc}")
        return False, f"Fichier illisible : {exc}"

    if database.file_hash_exists(file_hash):
        return False, "duplicate"

    try:
        record = parse_edi_file(filepath)
    except EdiParseError as exc:
        database.log_ingestion_event(filepath.name, "error", str(exc))
        return False, str(exc)

    record["file_hash"] = file_hash
    record["source_file"] = str(filepath)
    record["file_name"] = filepath.name
    record["sense"] = "Inbound" if "inbound" in str(filepath).replace("\\", "/").lower() else "Outbound"

    partner_id, partner_type = _classify_partner(record)
    record["partner_id"] = partner_id
    record["partner_type"] = partner_type

    raw_date = record.get("doc_date") or record.get("isa_date") or record.get("unb_date")
    record["doc_date_raw"] = raw_date
    parsed_date = normalize_date(raw_date) if raw_date else None
    record["doc_date_parsed"] = parsed_date.isoformat() if parsed_date else None

    total_qty = 0
    for line in record.get("forecast_lines") or []:
        qty = line.get("qty")
        if qty is not None and str(qty).lstrip("-").isdigit():
            total_qty += int(qty)
    record["total_forecast_qty"] = total_qty

    database.insert_message(record)
    status = "ok" if not record.get("parse_error") else "error"
    database.log_ingestion_event(filepath.name, status, record.get("parse_error") or "")

    return True, record.get("parse_error") or "ok"


def run_batch() -> dict[str, int]:
    """Ingère tous les fichiers présents dans inbound/ et outbound/."""
    counts = {"ok": 0, "duplicate": 0, "failed": 0}

    for folder in (config.EDI_INBOUND_DIR, config.EDI_OUTBOUND_DIR):
        if not folder.exists():
            logger.warning("Dossier manquant : %s", folder)
            continue

        files = sorted(p for p in folder.iterdir() if p.is_file())
        logger.info("%s : %d fichier(s) trouvé(s)", folder.name, len(files))

        for fpath in files:
            ok, result = ingest_file(fpath)
            if ok:
                counts["ok"] += 1
            elif result == "duplicate":
                counts["duplicate"] += 1
            else:
                counts["failed"] += 1
                logger.warning("Échec ingestion %s : %s", fpath.name, result)

    logger.info(
        "Batch terminé : %d nouveaux, %d doublons ignorés, %d échecs",
        counts["ok"], counts["duplicate"], counts["failed"],
    )
    return counts
