"""
auth.py - Authentification
=============================
Corrections par rapport à la version d'origine :
- plus AUCUN mot de passe en clair ni hashé-MD5 dans le code source.
- plus d'affichage des mots de passe sur l'écran de connexion.
- hachage bcrypt (lent par construction -> résiste au brute-force,
  contrairement à MD5 qui se casse en masse en quelques secondes).
- verrouillage temporaire d'un compte après 5 échecs consécutifs.
- les comptes sont gérés via `manage_users.py` (CLI), jamais codés en dur.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import bcrypt

from . import database

logger = logging.getLogger("edi.auth")

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        logger.error("Hash de mot de passe invalide en base")
        return False


def _is_locked(user: dict) -> bool:
    locked_until = user.get("locked_until")
    if not locked_until:
        return False
    try:
        return datetime.fromisoformat(locked_until) > datetime.now(timezone.utc)
    except ValueError:
        return False


def verify_login(username: str, password: str) -> tuple[bool, str, dict | None]:
    """Retourne (succès, message_erreur, infos_utilisateur)."""
    user = database.get_user(username)
    if user is None:
        # Message volontairement générique : ne pas révéler si le compte existe
        return False, "Identifiants incorrects", None

    if _is_locked(user):
        return False, "Compte temporairement verrouillé suite à plusieurs échecs. Réessayez plus tard.", None

    if not _verify_password(password, user["password_hash"]):
        attempts = user["failed_attempts"] + 1
        lock_until = None
        if attempts >= MAX_FAILED_ATTEMPTS:
            lock_until = (datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)).isoformat()
        database.register_failed_login(username, lock_until)
        if lock_until:
            return False, f"Trop d'échecs. Compte verrouillé {LOCKOUT_MINUTES} minutes.", None
        return False, "Identifiants incorrects", None

    database.reset_failed_login(username)
    return True, "", {
        "username": username,
        "role": user["role"],
        "display_name": user["display_name"],
        "icon": user["icon"],
    }
