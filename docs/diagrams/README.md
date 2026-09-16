# Diagrammes du projet

5 diagrammes au format [Mermaid](https://mermaid.js.org/) (texte, versionné
comme du code) couvrant l'architecture, la base de données, le
fonctionnement et le déploiement.

| Fichier | Type | Contenu |
|---|---|---|
| `architecture.mmd` | Diagramme de composants | Vue d'ensemble du système (sources EDI → watcher → parseur → base → interface) |
| `schema_bdd.mmd` | Entité-relation (ERD) | Schéma complet de la base SQLite (messages, partenaires, alertes, utilisateurs, audit) |
| `sequence_ingestion.mmd` | Diagramme de séquence | Ce qui se passe précisément entre le dépôt d'un fichier et son apparition dans le dashboard |
| `cas_utilisation.mmd` | Cas d'utilisation | Actions possibles par rôle (Customer Service / Logistics / Administrateur) |
| `deploiement_docker.mmd` | Diagramme de déploiement | Conteneur, volume persistant, healthcheck |

## Pourquoi Mermaid plutôt qu'un fichier binaire (Visio, draw.io...)

- **Versionné avec le code** : un changement d'architecture se voit dans
  `git diff`, comme n'importe quel fichier source.
- **Rendu natif sur GitHub/GitLab** : ces `.mmd` s'affichent directement
  dans l'interface, sans outil externe.
- **Facile à exporter en image** pour un rapport Word/PDF (voir ci-dessous).

## Exporter en PNG/SVG pour le rapport écrit

Trois options, aucune installation nécessaire pour la première :

1. **[mermaid.live](https://mermaid.live)** (le plus simple) — collez le
   contenu d'un fichier `.mmd`, cliquez sur "Actions → Export PNG/SVG".
2. **Extension VS Code** "Markdown Preview Mermaid Support" — ouvre un
   aperçu et permet d'exporter directement depuis l'éditeur.
3. **En ligne de commande** (si Node.js est installé) :
   ```bash
   npm install -g @mermaid-js/mermaid-cli
   mmdc -i architecture.mmd -o architecture.png -b white -w 1600
   ```
