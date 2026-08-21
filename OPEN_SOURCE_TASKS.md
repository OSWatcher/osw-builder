# Open Source Tasks — osw-builder

Liste des tâches pour préparer osw-builder à l'open source.

---

## ✅ #5 Open sourcer le submodule packer-templates

Submodule : `github.com/OSWatcher/packer-templates`

- ✅ `win10_pro` supprimée (branche morte, commits JSON pré-HCL non pertinents)
- ✅ `.gitmodules` mis à jour pour pointer sur `master`
- ✅ Toutes les branches stale supprimées (bug_vboxmanage_template, qemu, ubuntu, packer_fixed)
- ✅ Clé VLK Windows XP retirée (`WINNT.SIF`)
- ✅ Licence Apache 2.0 ajoutée
- ✅ README réécrit (syntaxe HCL, ISOs, prérequis, answer files)
- ✅ Repo rendu public sur GitHub

---

## ✅ #6 Purger les URLs ISO privées de default_settings.yaml

32 entrées `source:` pointent vers un hôte MinIO privé :

- Remplacer toutes les URLs par un placeholder explicite, ex: `source: null  # provide your own ISO path`
- Les vieilles boxes (win95, win98, winME, win2000) méritent une note séparée — non récupérables facilement
- Ajouter un commentaire en tête de fichier expliquant la démarche
- Documenter où trouver les ISOs légalement :
  - Windows 10/11 : Microsoft Evaluation Center
  - Windows XP/7/8 : Internet Archive
  - Ubuntu : ubuntu.com/download
- Garder les checksums ISO comme référence de vérification

---

## #4 Cleanup : API keys, branches mortes, refs privées

- `build.py:158` : `username="oswatcher"` hardcodé → rendre configurable
- Vérifier les workflows CI (`.github/workflows/`) pour refs à infra privée
- Supprimer les branches locales et remote obsolètes (50+ branches stale sur origin)
  - Branches locales à évaluer : `feature/branch-cascade-inheritance`, `feature/os-entry-inheritance`, `feature/vagrant-realtime-logging`
- Fichiers parasites à la racine à supprimer :
  - `capture.log`, `packer-build.log`, `vagrant.log`, `domain.xml`
  - `REPORT.md`, `debug_guestfs.py`
  - `rewrite_commits_nonbusiness.py`, `extract_business_hours_commits.py`
  - `update_windows_release_dates.cypher`

---

## #3 CLI : build et updates sans capture

Le flag `--skip-neogit` existe déjà et fonctionne (`capture.py:38`), mais trop interne :

- Renommer `--skip-neogit` → `--no-capture` (garder l'ancien comme alias)
- Subcommande unique `capture_os` qui fait tout : nom trompeur pour un externe
- Envisager des sous-commandes dédiées : `build`, `update`, `capture`
- Documenter les combinaisons de flags pour chaque cas d'usage :
  - Builder une image sans capture → `--no-capture`
  - Appliquer des updates sans capture → `--no-capture --updates=true`
  - Flow complet → comportement par défaut

---

## #1 Documentation générale

Le README actuel est vide (4 lignes). Écrire une vraie documentation :

- README complet : ce que fait le projet, prérequis, architecture globale
- Documenter les variables d'env nécessaires (`GHCR_TOKEN`, etc.)
- Documenter les fichiers de configuration (`config.yaml`, `default_settings.yaml`)
- Documenter les modules : `image_builder`, `capture`, `updates`, `services`
- Documenter le flux complet : build image → capture → push neo4j

---

## #2 Tutoriel et facilité d'accès *(difficile)*

Rendre le projet accessible à quelqu'un qui découvre :

- Tutorial "getting started" : builder une image Ubuntu minimale de zéro
- Documenter les dépendances système : libguestfs, qemu, vagrant, packer, docker
- Clarifier ce qui est nécessaire côté infra (Neo4j, MinIO) vs optionnel
- Exemples de `config.yaml` pour les cas d'usage courants
- Potentiellement un docker-compose de dev minimal pour lancer sans toute l'infra OSWatcher

---

*Priorité suggérée : #6 → #4 → #3 → #1 → #2*
