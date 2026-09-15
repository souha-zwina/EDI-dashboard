#!/usr/bin/env python3
"""
run_watcher.py - Lance le watcher comme processus autonome
==============================================================
Le watcher tourne déjà automatiquement à l'intérieur de `streamlit run app.py`
(voir src/watcher_service.py) : dans la majorité des cas, vous n'avez PAS
besoin de ce script.

Il reste utile pour un déploiement de production où l'ingestion doit
continuer même si le dashboard Streamlit est redémarré/arrêté séparément.
Dans ce cas, faites tourner CE script comme un service système (systemd,
supervisor, docker...) qui redémarre automatiquement après une coupure de
courant ou un crash. Voir README.md, section "Déploiement production".
"""

from src.database import init_db
from src.watcher_service import run_forever

if __name__ == "__main__":
    init_db()
    run_forever()
