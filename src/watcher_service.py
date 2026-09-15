"""
watcher_service.py - Surveillance automatique des dossiers EDI
==================================================================
Avant : le watcher devait être lancé à la main dans un terminal séparé
(`python watcher.py --mode watch`). Si ce terminal était fermé, ou en cas
de coupure de courant / redémarrage, plus rien n'était ingéré et personne
ne le savait.

Maintenant : ce module démarre un thread d'arrière-plan directement dans
le process de l'application Streamlit. Il est lancé automatiquement au
premier chargement de la page (voir app.py) via st.cache_resource, ce qui
garantit qu'il n'existe qu'UNE seule instance par process, même si
Streamlit ré-exécute le script à chaque interaction utilisateur.

Pour un déploiement de production robuste face aux coupures de courant,
`run_watcher.py` (à la racine) permet aussi de lancer ce même service comme
un processus système autonome (via systemd/supervisor), qui redémarre
automatiquement le service après une panne. Voir README.md.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from . import config, ingestion

logger = logging.getLogger("edi.watcher")


class _EdiFileHandler(FileSystemEventHandler):
    """Ingère un fichier dès qu'il apparaît dans inbound/ ou outbound/."""

    def on_created(self, event):
        if event.is_directory:
            return
        self._handle(event.src_path)

    def on_moved(self, event):
        # certains outils écrivent un fichier temporaire puis le renomment
        if event.is_directory:
            return
        self._handle(event.dest_path)

    def _handle(self, path: str) -> None:
        if not path.lower().endswith(config.WATCHER_ALLOWED_EXT):
            return

        # Laisse le temps à l'écriture du fichier de se terminer complètement
        time.sleep(0.3)

        ok, result = ingestion.ingest_file(path)
        name = Path(path).name
        if ok:
            logger.info("Ingéré : %s", name)
        elif result == "duplicate":
            logger.debug("Ignoré (déjà ingéré) : %s", name)
        else:
            logger.error("Échec ingestion %s : %s", name, result)


class EdiWatcherService:
    """Enveloppe le watchdog Observer + un thread de supervision auto-restart."""

    def __init__(self) -> None:
        self._observer: Observer | None = None
        self._stop_event = threading.Event()
        self._supervisor_thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def _start_observer(self) -> Observer:
        observer = Observer()
        handler = _EdiFileHandler()
        for folder in (config.EDI_INBOUND_DIR, config.EDI_OUTBOUND_DIR):
            folder.mkdir(parents=True, exist_ok=True)
            observer.schedule(handler, str(folder), recursive=False)
        observer.start()
        logger.info(
            "Watcher actif sur %s et %s", config.EDI_INBOUND_DIR, config.EDI_OUTBOUND_DIR
        )
        return observer

    def _supervise(self) -> None:
        """Redémarre automatiquement l'observer s'il meurt (résilience)."""
        while not self._stop_event.is_set():
            with self._lock:
                if self._observer is None or not self._observer.is_alive():
                    logger.warning("Observer inactif détecté, redémarrage...")
                    try:
                        self._observer = self._start_observer()
                    except Exception:
                        logger.exception("Échec du redémarrage de l'observer")
            self._stop_event.wait(5)

    def start(self) -> "EdiWatcherService":
        # Ingestion immédiate des fichiers déjà présents au démarrage
        logger.info("Ingestion initiale des fichiers existants...")
        counts = ingestion.run_batch()
        logger.info(
            "Ingestion initiale terminée : %(ok)d nouveaux, %(duplicate)d déjà connus, %(failed)d échecs",
            counts,
        )

        with self._lock:
            self._observer = self._start_observer()

        self._supervisor_thread = threading.Thread(
            target=self._supervise, name="edi-watcher-supervisor", daemon=True
        )
        self._supervisor_thread.start()
        return self

    def stop(self) -> None:
        self._stop_event.set()
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)

    @property
    def is_running(self) -> bool:
        return self._observer is not None and self._observer.is_alive()


def run_forever() -> None:
    """Point d'entrée pour un déploiement en processus système autonome (systemd)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    service = EdiWatcherService().start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Arrêt demandé (Ctrl+C)")
        service.stop()
