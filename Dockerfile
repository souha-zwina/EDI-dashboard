# Dockerfile - EDI Dashboard
# =============================
# Image légère basée sur python:3.11-slim. Le watcher tourne DANS le même
# conteneur que le dashboard (thread intégré, voir src/watcher_service.py) :
# un seul conteneur à faire tourner, pas d'orchestration complexe requise.

FROM python:3.11-slim

# Dépendances système minimales (certificats pour les appels HTTPS de
# Prophet/cmdstanpy, build-essential pour compiler certaines roues Python
# si aucun wheel précompilé n'est disponible pour l'architecture cible)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Étape séparée pour les dépendances : le cache Docker évite de tout
# réinstaller à chaque modification du code source
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# L'utilisateur "app" (non-root) exécute l'application : bonne pratique de
# sécurité, un conteneur compromis n'a pas les droits root sur l'hôte
RUN useradd --create-home --shell /bin/bash app \
    && mkdir -p /app/data/edi_messages/inbound /app/data/edi_messages/outbound \
               /app/data/models /app/data/logs \
    && chown -R app:app /app
USER app

EXPOSE 8501

# Vérifie périodiquement que Streamlit répond, pour que Docker/Compose
# puisse détecter et relancer un conteneur bloqué
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
