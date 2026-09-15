"""Tests d'authentification : hachage, vérification, verrouillage après
échecs répétés (protection anti brute-force)."""

from __future__ import annotations

from src import auth


def test_hash_password_never_returns_plaintext():
    hashed = auth.hash_password("MonMotDePasse123")
    assert hashed != "MonMotDePasse123"
    assert hashed.startswith("$2b$")  # préfixe bcrypt


def test_verify_login_success(db):
    db.upsert_user("alice", auth.hash_password("Password123"), "Administrateur", "Alice", "👤")
    ok, error, info = auth.verify_login("alice", "Password123")
    assert ok is True
    assert error == ""
    assert info["username"] == "alice"


def test_verify_login_wrong_password(db):
    db.upsert_user("alice", auth.hash_password("Password123"), "Administrateur", "Alice", "👤")
    ok, error, info = auth.verify_login("alice", "MauvaisMotDePasse")
    assert ok is False
    assert info is None


def test_verify_login_unknown_user_gives_generic_error(db):
    """Le message d'erreur ne doit pas révéler si le compte existe ou
    non (protection contre l'énumération de comptes)."""
    ok, error, info = auth.verify_login("inconnu", "peu importe")
    assert ok is False
    assert "incorrects" in error.lower()


def test_account_locks_after_max_failed_attempts(db):
    db.upsert_user("bob", auth.hash_password("Password123"), "Administrateur", "Bob", "👤")

    for _ in range(auth.MAX_FAILED_ATTEMPTS):
        auth.verify_login("bob", "mauvais")

    ok, error, info = auth.verify_login("bob", "Password123")  # même avec le bon mdp
    assert ok is False
    assert "verrouillé" in error.lower()


def test_successful_login_resets_failed_attempts(db):
    db.upsert_user("carol", auth.hash_password("Password123"), "Administrateur", "Carol", "👤")
    auth.verify_login("carol", "mauvais")
    auth.verify_login("carol", "mauvais")
    auth.verify_login("carol", "Password123")  # succès -> reset

    user = db.get_user("carol")
    assert user["failed_attempts"] == 0
