"""conftest.py - Fixtures partagées pour tous les tests.

Chaque test utilise une base SQLite TEMPORAIRE et isolée (jamais la vraie
base data/edi.db) grâce à la fixture `db`, pour que les tests soient
reproductibles et n'interfèrent jamais avec des données réelles.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config, database  # noqa: E402


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Base SQLite vide et isolée, un fichier temporaire par test."""
    db_file = tmp_path / "test_edi.db"
    monkeypatch.setattr(config, "DB_PATH", db_file)

    # Chaque test doit avoir sa PROPRE connexion (le cache thread-local de
    # database.py garderait sinon une connexion vers l'ancien fichier).
    database._local.conn = None
    database.init_db()
    yield database
    database._local.conn = None


@pytest.fixture
def sample_x12_valid() -> str:
    return (
        "ISA*00*          *00*          *ZZ*BMWDEU01       *ZZ*LEARX88        "
        "*260725*0800*U*00401*000009001*0*P*>~\r\n"
        "GS*SH*BMWDEU01*LEARX88*20260725*0800*1*X*004010~\r\n"
        "ST*830*0001~\r\n"
        "BFR*04*9001**20260725*20260725~\r\n"
        "N1*ST*LEARX88~\r\n"
        "LIN*1*BP*1933893-01-D~\r\n"
        "FST*70*C*EA*20260725~\r\n"
        "FST*75*C*EA*20260801~\r\n"
        "SE*8*0001~\r\n"
        "GE*1*1~\r\n"
        "IEA*1*000009001~\r\n"
    )


@pytest.fixture
def sample_x12_bad_quantity() -> str:
    return (
        "ISA*00*          *00*          *ZZ*BMWDEU01       *ZZ*LEARX88        "
        "*260725*0802*U*00401*000009003*0*P*>~\r\n"
        "GS*SH*BMWDEU01*LEARX88*20260725*0802*1*X*004010~\r\n"
        "ST*830*0001~\r\n"
        "BFR*04*9003**20260725*20260725~\r\n"
        "N1*ST*LEARX88~\r\n"
        "LIN*1*BP*1933893-01-D~\r\n"
        "FST*ABC*C*EA*20260725~\r\n"
        "SE*7*0001~\r\n"
        "GE*1*1~\r\n"
        "IEA*1*000009003~\r\n"
    )


@pytest.fixture
def sample_illisible() -> str:
    return "Bonjour,\nVoici la commande de la semaine.\nCordialement\n"
