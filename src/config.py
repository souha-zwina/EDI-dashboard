"""
config.py - Configuration centrale de l'application
======================================================
Toutes les valeurs sensibles ou dépendantes de l'environnement viennent
d'un fichier .env (jamais commité) ou de variables d'environnement système.
Rien n'est codé en dur ici -> un seul fichier à modifier pour changer
d'environnement (dev / prod).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Racine du projet = deux niveaux au-dessus de ce fichier (src/config.py -> project/)
BASE_DIR = Path(__file__).resolve().parent.parent

# Charge le fichier .env s'il existe (ne fait rien en prod si les variables
# sont déjà injectées par le système / le conteneur / systemd)
load_dotenv(BASE_DIR / ".env")


def _get(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(
            f"Variable d'environnement manquante : {name}. "
            f"Copiez .env.example vers .env et complétez-le."
        )
    return value


# ------------------------------------------------------------------
# Chemins
# ------------------------------------------------------------------
DATA_DIR = BASE_DIR / "data"
EDI_INBOUND_DIR = DATA_DIR / "edi_messages" / "inbound"
EDI_OUTBOUND_DIR = DATA_DIR / "edi_messages" / "outbound"
MODEL_PATH = DATA_DIR / "models" / "xgboost_model.pkl"
DB_PATH = Path(_get("EDI_DB_PATH", str(DATA_DIR / "edi.db")))
LOG_PATH = DATA_DIR / "logs" / "edi_app.log"
ASSETS_DIR = BASE_DIR / "assets"
LOGO_PATH = ASSETS_DIR / "lear_logo.png"

for d in (EDI_INBOUND_DIR, EDI_OUTBOUND_DIR, MODEL_PATH.parent, LOG_PATH.parent):
    d.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------------
# Entreprise / partenaires (métier)
# ------------------------------------------------------------------
OWN_PARTNER_ID = _get("EDI_OWN_PARTNER_ID", "LEARX88")
CLIENTS = [c.strip() for c in _get(
    "EDI_CLIENTS", "RENAULTFR,VOLVOSE01,TESLAUS01,BMWDEU01,MERCEDESDE"
).split(",") if c.strip()]
SUPPLIERS = [s.strip() for s in _get(
    "EDI_SUPPLIERS", "FRANSERV01,CABLEX0022,WIREPRO014,TERMILEC09,PLASTIK01"
).split(",") if s.strip()]

# ------------------------------------------------------------------
# Watcher (surveillance de dossier)
# ------------------------------------------------------------------
AUTO_START_WATCHER = _get("EDI_AUTO_START_WATCHER", "true").lower() == "true"
WATCHER_ALLOWED_EXT = (".x12", ".edifact", ".edi", ".txt")

# ------------------------------------------------------------------
# Cache Streamlit
# ------------------------------------------------------------------
DATA_CACHE_TTL_SECONDS = int(_get("EDI_DATA_CACHE_TTL", "15"))

# ------------------------------------------------------------------
# Authentification
# ------------------------------------------------------------------
# Format attendu dans .env :
#   EDI_USERS=customer_service:CS,logistics:Logistics,admin:Administrateur
#   EDI_PASSWORD_HASH_customer_service=$2b$12$....   (hash bcrypt)
# Voir auth.py::bootstrap_default_users() pour la génération initiale.
SESSION_TIMEOUT_MINUTES = int(_get("EDI_SESSION_TIMEOUT_MINUTES", "120"))
