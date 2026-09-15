"""
parser_edi.py - Parseur EDI ANSI X12 et EDIFACT
==================================================
Corrections apportées par rapport à la version d'origine :
- lecture de fichier avec repli automatique d'encodage (utf-8 -> latin-1 ->
  cp1252) : un seul fichier mal encodé ne fait plus planter tout le batch.
- toutes les erreurs sont explicites (jamais de `except: pass` silencieux).
- séparation claire entre erreurs "fichier illisible" et erreurs "standard
  non reconnu" pour un meilleur diagnostic dans le contrôle qualité.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("edi.parser")

_ENCODINGS_TO_TRY = ("utf-8", "latin-1", "cp1252")


class EdiParseError(Exception):
    """Erreur métier lors du parsing d'un fichier EDI (fichier illisible, etc.)."""


def _read_text_with_fallback(filepath: Path) -> str:
    last_error: Exception | None = None
    for encoding in _ENCODINGS_TO_TRY:
        try:
            return filepath.read_text(encoding=encoding)
        except (UnicodeDecodeError, LookupError) as exc:
            last_error = exc
            continue
    raise EdiParseError(
        f"Impossible de décoder {filepath.name} avec les encodages {_ENCODINGS_TO_TRY}: {last_error}"
    )


def detect_standard(raw_text: str) -> str:
    head = raw_text.strip()[:4]
    if head.startswith("ISA"):
        return "ANSI_X12"
    if head.startswith("UNB") or head.startswith("UNA"):
        return "EDIFACT"
    return "UNKNOWN"


def _split_segments(raw_text: str, standard: str) -> list[str]:
    terminator = "~" if standard == "ANSI_X12" else "'"
    segments = raw_text.replace("\r", "").replace("\n", "").split(terminator)
    return [s.strip() for s in segments if s.strip()]


def _elements(segment: str, standard: str) -> list[str]:
    sep = "*" if standard == "ANSI_X12" else "+"
    return segment.split(sep)


def parse_edi_file(filepath: str | Path) -> dict[str, Any]:
    """Parse un fichier EDI et retourne un dict prêt à insérer en base.

    Ne lève jamais d'exception pour un problème de contenu (standard inconnu,
    segment mal formé) : ces cas sont remontés via `parse_error` pour être
    visibles dans le tableau de bord qualité. Ne lève une exception que si
    le fichier est physiquement illisible (droits, encodage impossible).
    """
    filepath = Path(filepath)
    raw_text = _read_text_with_fallback(filepath)

    standard = detect_standard(raw_text)
    segments = _split_segments(raw_text, standard)

    record: dict[str, Any] = {
        "standard": standard,
        "raw_segment_count": len(segments),
    }

    try:
        if standard == "ANSI_X12":
            record.update(_parse_x12(segments))
        elif standard == "EDIFACT":
            record.update(_parse_edifact(segments))
        else:
            record["parse_error"] = "Standard EDI non reconnu (en-tête ISA/UNB/UNA absente)"
    except Exception as exc:  # un segment mal formé ne doit pas faire planter tout le batch
        logger.warning("Erreur de parsing sur %s : %s", filepath.name, exc)
        record["parse_error"] = f"Erreur de parsing : {exc}"

    return record


def _parse_x12(segments: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for seg in segments:
        el = _elements(seg, "ANSI_X12")
        tag = el[0]

        if tag == "ISA":
            out["sender"] = el[6].strip() if len(el) > 6 else None
            out["receiver"] = el[8].strip() if len(el) > 8 else None
            out["isa_date"] = el[9] if len(el) > 9 else None
            out["isa_time"] = el[10] if len(el) > 10 else None

        elif tag == "ST":
            out["message_type"] = el[1] if len(el) > 1 else None
            out["transaction_control_number"] = el[2] if len(el) > 2 else None

        elif tag == "BSN":
            out["doc_number"] = el[2] if len(el) > 2 else None
            out["doc_date"] = el[3] if len(el) > 3 else None
            out["doc_time"] = el[4] if len(el) > 4 else None

        elif tag == "BEG":
            out["doc_number"] = el[3] if len(el) > 3 else None
            out["doc_date"] = el[5] if len(el) > 5 else None

        elif tag == "BFR":
            out["doc_number"] = el[2] if len(el) > 2 else None
            out["horizon_start"] = el[4] if len(el) > 4 else None
            out["horizon_end"] = el[5] if len(el) > 5 else None

        elif tag == "BIG":
            out["doc_date"] = el[1] if len(el) > 1 else None
            out["doc_number"] = el[2] if len(el) > 2 else None

        elif tag == "N1":
            role = el[1] if len(el) > 1 else None
            if role == "ST":
                out["ship_to"] = el[4] if len(el) > 4 else None
            elif role == "SU":
                out["supplier_code"] = el[4] if len(el) > 4 else None
            elif role == "BT":
                out["bill_to"] = el[4] if len(el) > 4 else None

        elif tag == "LIN":
            out.setdefault("line_items", []).append({
                "item_ref": el[3] if len(el) > 3 else None,
            })

        elif tag == "SN1":
            out.setdefault("quantities", []).append({
                "qty": el[2] if len(el) > 2 else None,
                "uom": el[3] if len(el) > 3 else None,
            })

        elif tag == "FST":
            out.setdefault("forecast_lines", []).append({
                "qty": el[1] if len(el) > 1 else None,
                "qualifier": el[2] if len(el) > 2 else None,
                "uom": el[3] if len(el) > 3 else None,
                "date": el[4] if len(el) > 4 else None,
            })

        elif tag == "SE":
            out["segment_count_declared"] = el[1] if len(el) > 1 else None

    return out


def _parse_edifact(segments: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    pending_qty = None

    for seg in segments:
        el = _elements(seg, "EDIFACT")
        tag = el[0]

        if tag == "UNB":
            out["sender"] = el[2] if len(el) > 2 else None
            out["receiver"] = el[3] if len(el) > 3 else None
            if len(el) > 4:
                dt = el[4].split(":")
                out["unb_date"] = dt[0] if len(dt) > 0 else None
                out["unb_time"] = dt[1] if len(dt) > 1 else None

        elif tag == "UNH":
            out["transaction_control_number"] = el[1] if len(el) > 1 else None
            if len(el) > 2:
                out["message_type"] = el[2].split(":")[0]

        elif tag == "BGM":
            out["doc_number"] = el[2] if len(el) > 2 else None

        elif tag == "DTM":
            if len(el) > 1:
                parts = el[1].split(":")
                qualifier = parts[0] if len(parts) > 0 else None
                date_val = parts[1] if len(parts) > 1 else None

                if qualifier in ("137", "11"):
                    out["doc_date"] = date_val
                elif qualifier == "2" and pending_qty is not None:
                    out.setdefault("forecast_lines", []).append({
                        "qty": pending_qty,
                        "date": date_val,
                    })
                    pending_qty = None

        elif tag == "NAD":
            role = el[1] if len(el) > 1 else None
            code = el[2].split(":")[0] if len(el) > 2 else None
            if role == "SU":
                out["supplier_code"] = code
            elif role == "ST":
                out["ship_to"] = code

        elif tag == "LIN":
            raw_ref = el[3] if len(el) > 3 else (el[2] if len(el) > 2 else None)
            if raw_ref:
                item_ref = raw_ref.split(":")[0] if ":" in raw_ref else raw_ref
            else:
                item_ref = None
            out.setdefault("line_items", []).append({"item_ref": item_ref})

        elif tag == "QTY":
            if len(el) > 1:
                parts = el[1].split(":")
                qualifier = parts[0] if len(parts) > 0 else None
                qty_val = parts[1] if len(parts) > 1 else None
                if qualifier == "1":
                    pending_qty = qty_val
                else:
                    out.setdefault("quantities", []).append({
                        "qualifier": qualifier,
                        "qty": qty_val,
                    })

    return out


def normalize_date(value: str | None) -> datetime | None:
    if not value:
        return None

    digits = re.sub(r"\D", "", value.strip())

    fmt_by_length = {
        6: "%y%m%d",
        8: "%Y%m%d",
        12: "%Y%m%d%H%M",
    }

    fmt = fmt_by_length.get(len(digits))
    if fmt is None:
        return None

    try:
        return datetime.strptime(digits, fmt)
    except ValueError:
        return None
