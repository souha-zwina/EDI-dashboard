#!/usr/bin/env python3
"""
manage_users.py - Gestion des comptes utilisateurs
=====================================================
Aucun mot de passe n'est jamais écrit en clair dans le code source ou les
logs. Ce script les demande de manière interactive (saisie masquée) et ne
stocke que leur hash bcrypt en base.

Usage :
    python manage_users.py create   customer_service "Customer Service" 👤
    python manage_users.py create   logistics        "Logistics"        📦
    python manage_users.py create   admin            "Administrateur"   🔧
    python manage_users.py list
    python manage_users.py reset-password admin
"""

from __future__ import annotations

import getpass
import sys

from src import auth, database


def cmd_create(username: str, display_name: str, icon: str = "👤", role: str | None = None) -> None:
    role = role or display_name
    password = getpass.getpass(f"Mot de passe pour '{username}' : ")
    confirm = getpass.getpass("Confirmez le mot de passe : ")
    if password != confirm:
        print("❌ Les mots de passe ne correspondent pas.")
        sys.exit(1)
    if len(password) < 8:
        print("❌ Le mot de passe doit faire au moins 8 caractères.")
        sys.exit(1)

    database.upsert_user(
        username=username,
        password_hash=auth.hash_password(password),
        role=role,
        display_name=display_name,
        icon=icon,
    )
    print(f"✅ Utilisateur '{username}' créé/mis à jour (rôle : {role}).")


def cmd_list() -> None:
    users = database.list_users()
    if not users:
        print("Aucun utilisateur enregistré. Créez-en un avec : python manage_users.py create ...")
        return
    for u in users:
        print(f"  {u['icon']}  {u['username']:20s} role={u['role']}")


def cmd_reset_password(username: str) -> None:
    if database.get_user(username) is None:
        print(f"❌ Utilisateur '{username}' introuvable.")
        sys.exit(1)
    password = getpass.getpass(f"Nouveau mot de passe pour '{username}' : ")
    confirm = getpass.getpass("Confirmez : ")
    if password != confirm:
        print("❌ Les mots de passe ne correspondent pas.")
        sys.exit(1)
    user = database.get_user(username)
    database.upsert_user(username, auth.hash_password(password), user["role"], user["display_name"], user["icon"])
    database.reset_failed_login(username)
    print(f"✅ Mot de passe de '{username}' mis à jour.")


def main() -> None:
    database.init_db()

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    if command == "create":
        if len(sys.argv) < 4:
            print("Usage: python manage_users.py create <username> <role_affiche> [icone]")
            sys.exit(1)
        icon = sys.argv[4] if len(sys.argv) > 4 else "👤"
        cmd_create(sys.argv[2], sys.argv[3], icon)
    elif command == "list":
        cmd_list()
    elif command == "reset-password":
        if len(sys.argv) < 3:
            print("Usage: python manage_users.py reset-password <username>")
            sys.exit(1)
        cmd_reset_password(sys.argv[2])
    else:
        print(f"Commande inconnue : {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
