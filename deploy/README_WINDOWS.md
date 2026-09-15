# Déploiement Windows — démarrage automatique du dashboard

Les fichiers `edi-dashboard.service` / `edi-watcher.service` de ce dossier
sont pour Linux (systemd). Sur Windows, voici l'équivalent : faire
démarrer `deploy\start_dashboard.bat` automatiquement à l'ouverture de
session ou au démarrage du PC, avec redémarrage automatique en cas de
plantage — pour que le watcher tourne en continu sans intervention
manuelle, même après une coupure de courant.

## 1. Auto-redémarrage en cas de plantage

C'est déjà géré par `start_dashboard.bat` lui-même : il relance
automatiquement `streamlit run app.py` 5 secondes après tout arrêt
(plantage, erreur, etc.), en boucle infinie. Vous n'avez rien à
configurer pour ça.

## 2. Démarrage automatique après un redémarrage du PC / une coupure

### Option A — Planificateur de tâches Windows (recommandé)

1. Ouvrez **Planificateur de tâches** (recherchez "Planificateur de tâches"
   dans le menu Démarrer).
2. **Action → Créer une tâche...** (pas "tâche de base", pour avoir plus
   d'options).
3. Onglet **Général** :
   - Nom : `EDI Dashboard`
   - Cochez **Exécuter même si l'utilisateur n'est pas connecté** (si
     vous voulez que ça tourne même sans être connecté à Windows), ou
     laissez "Exécuter uniquement si l'utilisateur est connecté" pour la
     simplicité.
4. Onglet **Déclencheurs → Nouveau...** :
   - Commencer la tâche : **Au démarrage de l'ordinateur**
   - (optionnel) Ajoutez aussi un déclencheur **À l'ouverture de session**
5. Onglet **Actions → Nouveau...** :
   - Action : **Démarrer un programme**
   - Programme/script : chemin complet vers `start_dashboard.bat`
     (ex : `C:\Users\pc\Downloads\edi_dashboard\edi_dashboard\deploy\start_dashboard.bat`)
   - Commencer dans : le dossier du projet
     (ex : `C:\Users\pc\Downloads\edi_dashboard\edi_dashboard`)
6. Onglet **Conditions** : décochez "Ne démarrer la tâche que si
   l'ordinateur est branché sur secteur" si c'est un poste fixe.
7. **OK**, puis clic droit sur la tâche créée → **Exécuter**, pour tester
   immédiatement sans attendre un redémarrage.

Résultat : que le PC redémarre suite à une coupure de courant, une mise à
jour Windows, ou un plantage, le dashboard (et son watcher intégré) se
relance tout seul, sans que personne n'ait à ouvrir un terminal.

### Option B — Dossier de démarrage (plus simple, moins robuste)

Créez un raccourci vers `start_dashboard.bat` et placez-le dans :
```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
```
Il se lancera à chaque ouverture de session Windows. Moins fiable que
l'Option A si le PC est configuré pour ne pas ouvrir de session
automatiquement après une coupure de courant.

## 3. Vérifier que ça fonctionne

Après avoir configuré l'une des deux options, redémarrez le PC (un vrai
redémarrage, pas juste une veille) et, sans rien ouvrir manuellement,
attendez ~30 secondes puis allez sur `http://localhost:8501` dans un
navigateur. Si le dashboard s'affiche, c'est configuré correctement.
