# EDI Dashboard — Lear Corporation

Outil de supervision et de traitement des échanges EDI (ANSI X12 /
EDIFACT) pour des agents Customer Service / Logistique : détection
automatique des anomalies (messages mal formés, pics de demande,
partenaires silencieux), prévisions de volume, et suivi du traitement de
chaque problème — pas un simple tableau de bord de courbes, un vrai outil
d'exploitation.

## 🚀 Démarrage rapide

```bash
# 1. Installer les dépendances
python -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements.txt

# 2. Configurer l'environnement
cp .env.example .env                # Windows : copy .env.example .env

# 3. Créer votre premier compte (mot de passe demandé de façon masquée,
#    jamais stocké en clair, jamais codé en dur dans le code source)
python manage_users.py create admin Administrateur 🔧

# 4. Lancer l'application
streamlit run app.py
```

Les comptes Customer Service / Logistics peuvent être créés soit avec
`manage_users.py`, soit directement depuis l'interface (onglet
**⚙️ Administration → Utilisateurs**, réservé au rôle Administrateur).

**Vous n'avez pas besoin d'ouvrir un second terminal pour le watcher** :
il démarre automatiquement avec l'application et surveille en continu
`data/edi_messages/inbound/` et `data/edi_messages/outbound/`. Déposez-y
un fichier `.x12` ou `.edifact` : il est ingéré en moins d'une seconde.

Le jeu de données fourni (1150 fichiers, 5 clients + 5 fournisseurs,
plusieurs mois d'historique) permet de tester toutes les fonctionnalités
dès le premier lancement, y compris les prévisions et la détection de
pics. Pour en régénérer / en générer davantage :
```bash
cd scripts
python generate_fake_edi.py --n 500
```

## 🗂️ Structure du projet

```
edi_dashboard/
├── app.py                     # Point d'entrée Streamlit
├── run_watcher.py             # Watcher en processus autonome (prod/systemd)
├── manage_users.py            # CLI de gestion des comptes (création, reset mdp)
├── requirements.txt
├── pytest.ini
├── .env.example                # À copier vers .env
├── data/
│   ├── edi.db                  # Base SQLite (persistante, créée au 1er lancement)
│   ├── edi_messages/
│   │   ├── inbound/             # Déposez vos fichiers EDI entrants ici
│   │   └── outbound/            # Déposez vos fichiers EDI sortants ici
│   ├── models/                  # Modèle de prévision entraîné (cache, auto-invalidé)
│   └── logs/                    # Logs applicatifs
├── assets/                     # Logo, images
├── scripts/
│   └── generate_fake_edi.py    # Générateur de données de démonstration
├── deploy/
│   ├── edi-dashboard.service    # Service systemd (Linux)
│   ├── edi-watcher.service       # Service systemd watcher autonome (Linux)
│   ├── start_dashboard.bat       # Lancement + auto-restart (Windows)
│   └── README_WINDOWS.md         # Démarrage automatique au boot (Windows)
├── tests/                      # Suite de tests automatisés (pytest)
│   ├── conftest.py               # Fixtures (base de test isolée)
│   ├── test_parser_edi.py
│   ├── test_database.py
│   ├── test_ingestion.py
│   ├── test_analytics.py
│   └── test_auth.py
└── src/
    ├── config.py                # Configuration centrale (lit .env)
    ├── database.py               # Persistance SQLite (messages, partenaires,
    │                               statuts d'alerte, réglages, audit)
    ├── parser_edi.py             # Parseur ANSI X12 / EDIFACT
    ├── ingestion.py               # Logique métier d'ingestion
    ├── watcher_service.py         # Surveillance de dossier en thread + auto-restart
    ├── auth.py                    # Authentification bcrypt + anti brute-force
    ├── analytics.py               # Dataframes, alertes, prévisions
    └── ui/
        ├── style.py                # CSS des composants custom (le thème vient de .streamlit/config.toml)
        ├── components.py           # Blocs UI réutilisables (carte d'alerte, etc.)
        ├── login.py                # Écran de connexion
        ├── context.py              # Objet de contexte transmis aux pages
        └── pages/                  # Une page = un fichier
            ├── home.py               # Vue d'ensemble
            ├── alerts.py             # Alertes (avec suivi de traitement)
            ├── forecast.py           # Prévisions (moteur masqué, langage métier)
            ├── partners.py           # Détail par partenaire
            ├── data_view.py          # Données brutes / export
            └── admin.py              # Administration (rôle Administrateur uniquement)
```

## 🧭 Navigation (pensée pour un agent métier, pas un data analyst)

| Page | Ce qu'elle répond |
|---|---|
| 🏠 Vue d'ensemble | "Y a-t-il un problème maintenant ?" |
| 🚨 Alertes | "Qu'est-ce qui ne va pas, et où en est le traitement ?" |
| 📈 Prévisions | "Combien vais-je recevoir/livrer, et dois-je m'attendre à un pic ?" |
| 🏢 Partenaires | "Quel est l'historique de tel client/fournisseur ?" |
| 📋 Données | Export brut pour audit / reporting |
| ⚙️ Administration | Partenaires, seuils, utilisateurs, journal d'audit (admin) |

Aucune page ne mentionne un algorithme (XGBoost, Prophet...) : la méthode
de calcul des prévisions est choisie et masquée automatiquement par
`analytics.forecast_demand()`, avec un repli par moyenne mobile garanti
disponible même si aucune librairie de machine learning n'est installée.

## 🚨 Suivi des alertes (pas un simple affichage)

Chaque alerte détectée (erreur de format, pic de volume, silence
partenaire) peut être **prise en charge**, **résolue**, ou **rouverte**,
avec une note optionnelle. Ce statut est persisté en base (table
`alert_status`, clé stable indépendante du recalcul) : contrairement à un
simple indicateur visuel, retraiter la même alerte demain ne perd pas
l'historique de ce qui a déjà été fait.

## 🔒 Sécurité

- Mots de passe hachés avec **bcrypt** (jamais en clair, jamais dans le code).
- Verrouillage automatique d'un compte après 5 échecs de connexion (15 min).
- Aucun identifiant n'est affiché sur l'écran de connexion.
- **Journal d'audit** : chaque connexion, changement de statut d'alerte,
  modification de partenaire/seuil/utilisateur est tracé (qui, quoi,
  quand) — consultable dans Administration → Journal d'audit.

Gestion des comptes en ligne de commande (en plus de l'interface Admin) :
```bash
python manage_users.py list
python manage_users.py create <username> "<Nom affiché>" <icone_optionnelle>
python manage_users.py reset-password <username>
```

Les rôles filtrent automatiquement les données visibles :
- **Customer Service** → uniquement les partenaires de type Client
- **Logistics** → uniquement les partenaires de type Fournisseur
- **Administrateur** → tout, + accès à la page Administration

## 🏢 Gestion des partenaires et seuils (Administration)

Les partenaires (clients/fournisseurs) et les seuils de détection
(sensibilité d'un pic de demande, fenêtre d'analyse en semaines) ne sont
plus codés en dur : ils sont amorcés une première fois depuis `.env` puis
gérés depuis **⚙️ Administration**, sans redéploiement. Un bouton
« Recalculer les types sur l'historique existant » permet d'appliquer un
changement de classification aux messages déjà en base.

## 💾 Pourquoi SQLite et pas mongomock ?

L'ancienne version utilisait `mongomock`, une base **100% en mémoire** :
tout redémarrage du process (crash, coupure de courant, mise à jour) vidait
entièrement les données ingérées, et les rejouait ensuite en double au
prochain batch (les statistiques gonflaient artificiellement à chaque
redémarrage).

SQLite stocke tout dans un seul fichier (`data/edi.db`), avec :
- des transactions ACID (pas de corruption si le process est tué),
- le mode WAL (le watcher peut écrire pendant que le dashboard lit, sans
  se bloquer mutuellement),
- une contrainte `UNIQUE` sur le hash de fichier qui garantit qu'un même
  fichier ne sera **jamais** ingéré deux fois, même après redémarrage,
- un modèle de prévision qui se **réentraîne automatiquement** si le
  volume de données a significativement changé depuis le dernier
  entraînement (évite de servir des prévisions basées sur des données
  périmées).

## 🛰️ Déploiement en production (résilience aux coupures)

**Sur Windows** → voir `deploy/README_WINDOWS.md` (Planificateur de tâches
+ script `deploy/start_dashboard.bat` avec redémarrage automatique en cas
de plantage).

**Sur Linux** → services systemd fournis dans `deploy/` :
```bash
sudo cp deploy/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now edi-dashboard
```
`Restart=always` garantit un redémarrage automatique après un crash ou
une coupure de courant.

## 🧩 Modules de prévision optionnels

`xgboost`, `scikit-learn` et `prophet` sont optionnels. S'ils ne sont pas
installés, `analytics.forecast_demand()` utilise automatiquement un
repli par moyenne mobile pondérée — la page Prévisions reste toujours
fonctionnelle, jamais de message d'erreur technique affiché à l'agent.

## 🧪 Tests automatisés

```bash
pip install -r requirements.txt   # inclut pytest
pytest
```

46 tests couvrant : parseur EDI (formats valides/invalides, encodages),
persistance (déduplication, non-régression sur la perte de données),
ingestion (classification partenaire dynamique), moteur d'alertes
(clé stable, fusion de statut, seuils configurables), authentification
(hachage, verrouillage anti brute-force). Chaque test utilise une base
SQLite temporaire isolée (`tests/conftest.py`), jamais la base réelle.

Pour explorer la logique métier sans lancer Streamlit :
```python
from src import database, ingestion, analytics

database.init_db()
counts = ingestion.run_batch()          # ingère data/edi_messages/{in,out}bound
raw = database.fetch_all_messages()
df_messages, df_forecasts = analytics.prepare_dataframes(raw)
alerts = analytics.build_alerts(raw, df_messages, df_forecasts)
```

## 📐 Limites connues (honnêteté avant tout)

- Le reclassement d'un partenaire (Admin → Partenaires) ne s'applique aux
  messages déjà en base qu'après un clic explicite sur « Recalculer » —
  ce n'est pas automatique, pour éviter une réécriture de masse silencieuse.
- Le modèle de prévision est entraîné globalement (tous partenaires
  confondus) plutôt qu'un modèle par partenaire : suffisant pour ce volume
  de données, mais une vraie mise à l'échelle multi-partenaires demanderait
  un modèle dédié par partenaire ou une feature d'identité partenaire.
- Pas de notification push (email/Slack) quand une alerte critique
  apparaît : l'agent doit consulter le dashboard. C'est la suite logique
  si ce projet est repris au-delà de cette version.
