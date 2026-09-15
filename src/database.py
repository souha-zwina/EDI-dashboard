"""
database.py - Couche de persistance SQLite
=============================================
Remplace mongomock (base 100% en mémoire, qui se vidait à chaque
redémarrage / coupure de courant) par une vraie base SQLite sur disque.

Pourquoi SQLite et pas MongoDB "réel" :
- zéro service externe à installer/administrer, un seul fichier .db
- transactionnel (ACID) -> pas de corruption si le process est tué brutalement
- WAL mode -> lecture (dashboard) et écriture (watcher) simultanées sans blocage
- largement suffisant pour des dizaines/centaines de milliers de messages EDI

Toute la logique SQL est isolée ici : le reste de l'application ne
manipule jamais de requêtes brutes.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import config

logger = logging.getLogger("edi.database")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    file_hash           TEXT NOT NULL UNIQUE,
    source_file         TEXT NOT NULL,
    file_name           TEXT NOT NULL,
    standard            TEXT,
    sender              TEXT,
    receiver            TEXT,
    message_type        TEXT,
    doc_number          TEXT,
    doc_date_raw        TEXT,
    doc_date_parsed     TEXT,
    partner_id          TEXT,
    partner_type        TEXT,
    sense               TEXT,
    raw_segment_count   INTEGER DEFAULT 0,
    forecast_lines_json TEXT,
    quantities_json     TEXT,
    line_items_json     TEXT,
    total_forecast_qty  INTEGER DEFAULT 0,
    parse_error         TEXT,
    ingested_at         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_partner ON messages(partner_id);
CREATE INDEX IF NOT EXISTS idx_messages_date ON messages(doc_date_parsed);
CREATE INDEX IF NOT EXISTS idx_messages_sense ON messages(sense);

CREATE TABLE IF NOT EXISTS users (
    username        TEXT PRIMARY KEY,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL,
    display_name    TEXT NOT NULL,
    icon            TEXT DEFAULT '👤',
    failed_attempts INTEGER DEFAULT 0,
    locked_until    TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingestion_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name   TEXT NOT NULL,
    status      TEXT NOT NULL,          -- 'ok' | 'duplicate' | 'error'
    detail      TEXT,
    created_at  TEXT NOT NULL
);

-- Suivi du traitement des alertes (nouveau -> en_cours -> resolu). Les
-- alertes elles-mêmes sont recalculées à chaque rafraîchissement (elles
-- reflètent l'état réel des données), mais leur STATUT de traitement est
-- persistant : sans cette table, une alerte "prise en charge" par un
-- agent redeviendrait "nouveau" au rafraîchissement suivant.
CREATE TABLE IF NOT EXISTS alert_status (
    alert_key    TEXT PRIMARY KEY,
    status       TEXT NOT NULL DEFAULT 'nouveau',   -- nouveau | en_cours | resolu
    note         TEXT,
    updated_by   TEXT,
    updated_at   TEXT NOT NULL
);

-- Partenaires (clients/fournisseurs) gérés depuis l'interface Admin,
-- plus besoin d'éditer le fichier .env à la main pour en ajouter un.
CREATE TABLE IF NOT EXISTS partners (
    partner_id     TEXT PRIMARY KEY,
    partner_type   TEXT NOT NULL,        -- Client | Fournisseur
    display_name   TEXT,
    active         INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT NOT NULL
);

-- Paramètres modifiables sans redéploiement (seuils d'alerte, etc.)
CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);

-- Journal d'audit : qui a fait quoi, quand. Traçabilité exigée dans un
-- contexte professionnel (qui a traité telle alerte, modifié tel
-- partenaire, etc.)
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT NOT NULL,
    action      TEXT NOT NULL,
    detail      TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_date ON audit_log(created_at);
"""

_DEFAULT_SETTINGS = {
    "spike_threshold": "1.5",     # x fois la moyenne pour déclencher un pic
    "lookback_weeks": "12",       # fenêtre d'analyse historique (semaines)
}

_local = threading.local()
_write_lock = threading.Lock()  # sqlite gère un seul writer à la fois


def get_connection() -> sqlite3.Connection:
    """Une connexion par thread (Streamlit + watcher tournent sur des threads différents)."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(str(config.DB_PATH), timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")   # lecture/écriture concurrentes
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA busy_timeout=30000;")
        _local.conn = conn
    return conn


def init_db() -> None:
    conn = get_connection()
    with conn:
        conn.executescript(_SCHEMA)

    # Amorçage des partenaires depuis .env, UNE SEULE FOIS (si la table est
    # vide) : permet une transition en douceur depuis l'ancienne config
    # statique, sans perdre ce qui était déjà défini dans .env. Une fois
    # amorcée, la table `partners` est la source de vérité, gérée depuis
    # la page Administration.
    if not list_partners():
        now = datetime.now(timezone.utc).isoformat()
        with transaction() as conn:
            for pid in config.CLIENTS:
                conn.execute(
                    "INSERT OR IGNORE INTO partners (partner_id, partner_type, display_name, active, created_at) VALUES (?,?,?,1,?)",
                    (pid, "Client", pid, now),
                )
            for pid in config.SUPPLIERS:
                conn.execute(
                    "INSERT OR IGNORE INTO partners (partner_id, partner_type, display_name, active, created_at) VALUES (?,?,?,1,?)",
                    (pid, "Fournisseur", pid, now),
                )

    for key, value in _DEFAULT_SETTINGS.items():
        if get_setting(key) is None:
            set_setting(key, value)

    logger.info("Base SQLite initialisée : %s", config.DB_PATH)


@contextmanager
def transaction():
    """Sérialise les écritures pour éviter les 'database is locked' sous charge."""
    conn = get_connection()
    with _write_lock:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


# ------------------------------------------------------------------
# Messages
# ------------------------------------------------------------------
def file_hash_exists(file_hash: str) -> bool:
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM messages WHERE file_hash = ? LIMIT 1", (file_hash,)
    ).fetchone()
    return row is not None


def insert_message(record: dict[str, Any]) -> None:
    """Insère un message. Idempotent grâce à la contrainte UNIQUE(file_hash)."""
    now = datetime.now(timezone.utc).isoformat()
    payload = (
        record["file_hash"],
        record["source_file"],
        record["file_name"],
        record.get("standard"),
        record.get("sender"),
        record.get("receiver"),
        record.get("message_type"),
        record.get("doc_number"),
        record.get("doc_date_raw"),
        record.get("doc_date_parsed"),
        record.get("partner_id"),
        record.get("partner_type"),
        record.get("sense"),
        record.get("raw_segment_count", 0),
        json.dumps(record.get("forecast_lines") or [], ensure_ascii=False),
        json.dumps(record.get("quantities") or [], ensure_ascii=False),
        json.dumps(record.get("line_items") or [], ensure_ascii=False),
        record.get("total_forecast_qty", 0),
        record.get("parse_error"),
        now,
    )
    with transaction() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO messages (
                file_hash, source_file, file_name, standard, sender, receiver,
                message_type, doc_number, doc_date_raw, doc_date_parsed,
                partner_id, partner_type, sense, raw_segment_count,
                forecast_lines_json, quantities_json, line_items_json,
                total_forecast_qty, parse_error, ingested_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            payload,
        )


def log_ingestion_event(file_name: str, status: str, detail: str = "") -> None:
    with transaction() as conn:
        conn.execute(
            "INSERT INTO ingestion_events (file_name, status, detail, created_at) VALUES (?,?,?,?)",
            (file_name, status, detail, datetime.now(timezone.utc).isoformat()),
        )


def fetch_all_messages() -> list[dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM messages ORDER BY doc_date_parsed").fetchall()
    result = []
    for row in rows:
        rec = dict(row)
        rec["forecast_lines"] = json.loads(rec.pop("forecast_lines_json") or "[]")
        rec["quantities"] = json.loads(rec.pop("quantities_json") or "[]")
        rec["line_items"] = json.loads(rec.pop("line_items_json") or "[]")
        result.append(rec)
    return result


def get_stats() -> dict[str, Any]:
    """Statistiques calculées à la volée depuis la base -> jamais désynchronisées."""
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) c FROM messages").fetchone()["c"]

    today = datetime.now().strftime("%Y-%m-%d")
    today_count = conn.execute(
        "SELECT COUNT(*) c FROM messages WHERE substr(ingested_at,1,10) = ?", (today,)
    ).fetchone()["c"]

    last_ingestion_row = conn.execute(
        "SELECT MAX(ingested_at) m FROM messages"
    ).fetchone()

    by_partner = {
        r["partner_id"]: r["c"]
        for r in conn.execute(
            "SELECT partner_id, COUNT(*) c FROM messages GROUP BY partner_id"
        ).fetchall()
    }
    by_type = {
        r["message_type"]: r["c"]
        for r in conn.execute(
            "SELECT message_type, COUNT(*) c FROM messages GROUP BY message_type"
        ).fetchall()
    }
    daily_history = {
        r["day"]: r["c"]
        for r in conn.execute(
            "SELECT substr(ingested_at,1,10) day, COUNT(*) c FROM messages GROUP BY day ORDER BY day"
        ).fetchall()
    }

    return {
        "total_messages": total,
        "today_messages": today_count,
        "last_ingestion": last_ingestion_row["m"] if last_ingestion_row else None,
        "messages_by_partner": by_partner,
        "messages_by_type": by_type,
        "daily_history": daily_history,
    }


def get_recent_events(limit: int = 20) -> list[dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM ingestion_events ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------
# Utilisateurs
# ------------------------------------------------------------------
def get_user(username: str) -> dict[str, Any] | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else None


def list_users() -> list[dict[str, Any]]:
    conn = get_connection()
    return [dict(r) for r in conn.execute("SELECT username, role, display_name, icon FROM users").fetchall()]


def upsert_user(username: str, password_hash: str, role: str, display_name: str, icon: str = "👤") -> None:
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO users (username, password_hash, role, display_name, icon, created_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(username) DO UPDATE SET
                password_hash=excluded.password_hash,
                role=excluded.role,
                display_name=excluded.display_name,
                icon=excluded.icon
            """,
            (username, password_hash, role, display_name, icon, datetime.now(timezone.utc).isoformat()),
        )


def register_failed_login(username: str, lock_until: str | None) -> None:
    with transaction() as conn:
        conn.execute(
            "UPDATE users SET failed_attempts = failed_attempts + 1, locked_until = ? WHERE username = ?",
            (lock_until, username),
        )


def reset_failed_login(username: str) -> None:
    with transaction() as conn:
        conn.execute(
            "UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE username = ?",
            (username,),
        )


def delete_user(username: str) -> None:
    with transaction() as conn:
        conn.execute("DELETE FROM users WHERE username = ?", (username,))


# ------------------------------------------------------------------
# Partenaires (gérés depuis la page Administration)
# ------------------------------------------------------------------
def list_partners(active_only: bool = False) -> list[dict[str, Any]]:
    conn = get_connection()
    query = "SELECT * FROM partners"
    if active_only:
        query += " WHERE active = 1"
    query += " ORDER BY partner_type, partner_id"
    return [dict(r) for r in conn.execute(query).fetchall()]


def get_partner(partner_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM partners WHERE partner_id = ?", (partner_id,)).fetchone()
    return dict(row) if row else None


def upsert_partner(partner_id: str, partner_type: str, display_name: str = "", active: bool = True) -> None:
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO partners (partner_id, partner_type, display_name, active, created_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(partner_id) DO UPDATE SET
                partner_type=excluded.partner_type,
                display_name=excluded.display_name,
                active=excluded.active
            """,
            (partner_id.strip().upper(), partner_type, display_name or partner_id, int(active),
             datetime.now(timezone.utc).isoformat()),
        )


def delete_partner(partner_id: str) -> None:
    with transaction() as conn:
        conn.execute("DELETE FROM partners WHERE partner_id = ?", (partner_id,))


def partner_type_map() -> dict[str, str]:
    """{partner_id: 'Client'|'Fournisseur'} pour les partenaires actifs -
    utilisé à l'ingestion pour classifier chaque nouveau message."""
    return {p["partner_id"]: p["partner_type"] for p in list_partners(active_only=True)}


def recompute_partner_types() -> int:
    """Ré-applique la classification actuelle (table partners) à tous les
    messages déjà en base. Utile après avoir corrigé/ajouté un partenaire
    dans l'admin, pour que l'historique reflète le bon type sans tout
    réingérer. Retourne le nombre de lignes mises à jour."""
    mapping = partner_type_map()
    updated = 0
    with transaction() as conn:
        for partner_id, ptype in mapping.items():
            cur = conn.execute(
                "UPDATE messages SET partner_type = ? WHERE partner_id = ? AND partner_type != ?",
                (ptype, partner_id, ptype),
            )
            updated += cur.rowcount
    return updated


# ------------------------------------------------------------------
# Paramètres (seuils d'alerte, etc.)
# ------------------------------------------------------------------
def get_setting(key: str) -> str | None:
    conn = get_connection()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(key: str, value: str) -> None:
    with transaction() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )


def get_settings() -> dict[str, str]:
    conn = get_connection()
    return {r["key"]: r["value"] for r in conn.execute("SELECT * FROM settings").fetchall()}


# ------------------------------------------------------------------
# Statut de traitement des alertes
# ------------------------------------------------------------------
def get_alert_statuses() -> dict[str, dict[str, Any]]:
    """Tous les statuts en une seule requête (évite N requêtes pour N alertes)."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM alert_status").fetchall()
    return {r["alert_key"]: dict(r) for r in rows}


def set_alert_status(alert_key: str, status: str, username: str, note: str = "") -> None:
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO alert_status (alert_key, status, note, updated_by, updated_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(alert_key) DO UPDATE SET
                status=excluded.status, note=excluded.note,
                updated_by=excluded.updated_by, updated_at=excluded.updated_at
            """,
            (alert_key, status, note, username, datetime.now(timezone.utc).isoformat()),
        )


# ------------------------------------------------------------------
# Audit
# ------------------------------------------------------------------
def log_audit(username: str, action: str, detail: str = "") -> None:
    with transaction() as conn:
        conn.execute(
            "INSERT INTO audit_log (username, action, detail, created_at) VALUES (?,?,?,?)",
            (username, action, detail, datetime.now(timezone.utc).isoformat()),
        )


def get_audit_log(limit: int = 200) -> list[dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]
