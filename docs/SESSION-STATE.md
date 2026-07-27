# SESSION-STATE — MedVision AI

Point de reprise canonique. Mis à jour à chaque session significative.
**Lire ce fichier en premier, puis `ROADMAP.md`, puis `CLAUDE.md`.**

---

## 🤝 HANDOFF 2026-07-27 — L'interface web Angular, complète et prête à déployer (NON DÉPLOYÉE)

> **Rien n'est en production côté interface.** Tout le code est écrit, testé et commité en
> local ; **aucune branche n'est poussée**, aucune image n'est construite, aucun DNS créé.
> La production reste exactement telle qu'elle était : `medvision-ai:2026-07-18f`,
> Streamlit sur `app.medvision`, API sur `api.medvision`.
> Plan suivi : **`docs/plans/2026-07-27-medvision-front-angular-b1.md`**.

### Où en est-on exactement

| Élément | État |
|---|---|
| Écrans accueil / analyse / comparaison | Écrits, compilés, 18 tests verts |
| Image nginx `medvision-web` | Dockerfile écrit, **construite et essayée en local** |
| Manifests k3s (`medvision-web`, hôte `ui.medvision`) | Écrits et validés, **non appliqués** |
| Dépôt ECR `platform/medvision-web` | **N'existe pas encore** — à créer |
| Enregistrement DNS `ui.medvision` | **N'existe pas encore** |

### Les six branches, dans l'ordre de fusion

Chaînées : chacune est construite sur la précédente, donc elles se fusionnent d'affilée
sans le moindre conflit — **mais dans cet ordre**, et en vérifiant que la base de chaque
PR est bien `main` avant de la fusionner.

Dépôt `medvision-ai` :

1. `chore/gitignore-node-angular` — les 394 Mo de `node_modules` cessent d'être suivis
2. `feat/front-socle-angular` — outillage, services, flux temps réel, écran d'accueil, CI front
3. `feat/front-studio-prediction` — écran d'analyse et superpositions de segmentation
4. `feat/front-comparaison-metriques` — écran de comparaison
5. `build/docker-frontend` — image nginx et script de publication
6. `docs/handoff-front-angular` — cette documentation

Indépendante (aucun fichier commun, fusionnable quand on veut) :

- `chore/tag-redeploiement-a-jour` — le tag par défaut du script de redéploiement était
  resté sur `2026-07-18b` : le lancer sans argument après un incident aurait redéployé
  une image antérieure aux correctifs du 18 juillet.

Dépôt `k3s-fromOVHVps`, branche `deploy/medvision-web` (deux commits) :

- la remise en phase du gabarit de déploiement avec la production ;
- l'ajout du déploiement `medvision-web` et de l'hôte `ui.medvision`.

### Pour mettre en ligne (dans cet ordre)

```bash
# 1. Créer le dépôt d'images (une seule fois)
aws ecr create-repository --repository-name platform/medvision-web --region eu-west-3

# 2. Construire et publier l'image
cd medvision-ai && ./scripts/build-and-push-web.sh 2026-07-27

# 3. Appliquer les manifests (jamais le fichier entier : il contient des secrets)
kubectl -n medvision apply -f <(…)   # ou laisser passer par la voie habituelle du dépôt k3s

# 4. Créer l'enregistrement DNS — TOUJOURS en simulation d'abord
cd k3s-fromOVHVps
DNS_SYNC_DRY_RUN=true scripts/ovh_dns_sync_k3s_zone.sh   # doit ne proposer QUE la création de ui.medvision
```

Le script de synchronisation DNS **supprime les enregistrements A qui divergent** et il
n'y a pas de joker sur la zone : la simulation n'est pas facultative.

### Trois choses à savoir avant de toucher à ce code

1. **La segmentation ne pose aucun diagnostic.** Sur un type d'analyse dont le
   `task_type` vaut `segmentation`, l'interface n'affiche ni classe prédite, ni confiance,
   ni probabilités. Ces modèles annonçaient « NORMAL » avec une confiance de 1,000 sur des
   pneumonies manifestes. Un test le verrouille
   (`frontend/src/app/pages/studio/studio.component.spec.ts`) — s'il tombe un jour, c'est
   une régression médicale, pas un détail d'affichage.
2. **nginx résout l'adresse de l'API à chaque requête, et c'est voulu.** Écrite en dur,
   elle est résolue une seule fois au démarrage : le pod refusait alors de démarrer si
   l'API n'était pas encore joignable, et repartait en boucle. D'où le gabarit
   `docker/nginx-frontend.conf.template` et sa variable — ne pas « simplifier » en
   remettant l'adresse en dur.
3. **Le pod de l'API monte désormais le volume des jeux d'images.** Il ne le faisait pas ;
   seul Streamlit l'avait. Sans ce montage, la banque d'exemples de l'interface affiche
   « aucune image » alors que les données sont bien sur le nœud.

### Ce qui reste ouvert

- Six brouillons de documentation non suivis traînent dans `docs/` (`handbook/`,
  `manual/`, `04-`, `10-`, `15-`, `16-`). Ce sont des versions antérieures des chapitres
  qui vivent maintenant dans `k3s-fromOVHVps/docs-portal/content/medvision/` — à
  supprimer, la suppression ayant été refusée par le contrôle de permissions ce jour-là.
- `medvision-ai` n'a **pas de projet Jira** (absent de `~/.claude/hooks/jira-repos.tsv`) :
  aucun ticket n'a été créé pour ce chantier.
- Le détecteur d'écarts du dépôt k3s signale encore trois divergences **sans rapport avec
  MedVision** : `70-keycloak`, `80-products`, `90-monitoring`.

---

## 🤝 HANDOFF 2026-07-18 — Les 17 modèles en production + API v2 + segmentation pure (DÉPLOYÉ)

> **Image prod : `medvision-ai:2026-07-18f`** (api, streamlit et mlflow).
> Plan détaillé de reprise : **`docs/plans/2026-07-18-handoff-medvision.md`** — le lire
> avant de reprendre le chantier.

### État vérifié en production à la clôture

| Problème | Type de tâche | Modèles disponibles |
|---|---|---|
| Chest X-ray Pneumonia Classification | binary | 5/5 |
| Brain MRI Tumor Classification | multiclass | 8/8 |
| Brain Tumor Segmentation | segmentation | 1/1 |
| Chest X-ray Lung Segmentation | segmentation | 1/1 |

17 modèles ONNX sur PVC persistant, aucun pod en erreur.

### Documentation

La documentation technique de MedVision vit désormais sur le portail interne
**<https://docs.doctumconsilium.com/>** (gaté Keycloak, accessible depuis le portail
produits) : dix-sept chapitres écrits comme un manuel, environ soixante-dix mille mots —
architecture, pipeline de données, entraînement, mathématiques de la vision et de la
segmentation, Grad-CAM, inférence en production, infrastructure, exploitation, incidents
vécus, qualité, sécurité, limites. Les sources sont dans `k3s-fromOVHVps/docs-portal/`.

### Le fil de la session

Le point de départ était simple : les 17 modèles entraînés et poussés dans S3 via DVC
n'apparaissaient pas dans l'interface. Le diagnostic a mis au jour **cinq causes racines
enchaînées**, toutes corrigées et déployées.

1. **Zéro modèle en production.** L'extra `dvc[gdrive]` tirait PyDrive2, qui fige
   pyOpenSSL en 22.0.0 ; le rebuild ayant résolu cryptography 49, tout accès S3 de DVC
   plantait (`module 'lib' has no attribute 'GEN_EMAIL'`). Le remote du projet est S3
   seul : l'extra a été retiré. C'est la différence d'environnement entre le PC
   d'entraînement et l'image Docker qui avait déclenché la panne.
2. **Pods évincés en boucle.** Les 17 modèles plus le cache DVC pèsent environ 2,4 Go,
   au-delà de la limite de stockage éphémère de 2 Gi. Limite portée à 6 Gi, **et**
   surtout les modèles déménagés sur le PVC `medvision-model-artifacts` : ils survivent
   désormais à un crash de pod au lieu d'être re-téléchargés à chaque démarrage.
3. **Quatre modèles au lieu de dix-sept.** Sur le PVC, `dvc pull` refusait d'écraser des
   fichiers qu'il considérait comme « non sauvegardés ». `--force` ajouté dans
   l'entrypoint et dans le watcher : le pod est une copie jetable de la vérité S3.
4. **Les trois modèles PyTorch en erreur.** `torch.onnx` exporte en canaux-d'abord
   (NCHW) alors que l'application envoyait systématiquement du NHWC. Nouveau helper
   `format_model_input()` : il lit la forme d'entrée déclarée par la session ONNX et
   transpose si besoin.
5. **503 et OOMKilled en cascade.** Le cache de sessions ONNX de Streamlit était borné à
   16 entrées (~350 Mo chacune) dans un pod à 2 Gi. Ramené à 3, aligné sur le cache LRU
   de l'API.

### Livré en plus des correctifs

- **PR #10 débloquée** : les quatre vérifications rouges de la chaîne d'intégration
  (guardrails, registre des backbones, couverture) réparées, puis fusionnée — c'est elle
  qui apportait le pipeline des 17 modèles.
- **API v2 (préfixe `/api`)** : registre versionné et enrichi, navigateur d'images par
  identifiants opaques (aucun chemin disque n'est jamais exposé ni interprété),
  `POST /api/predict` multi-modèles avec masques en PNG base64 (le seuil se change côté
  client sans ré-inférence), rapports. Les endpoints historiques restent inchangés.
- **Watcher DVC + flux temps réel (SSE)** : `scripts/publish_model_manifest.sh` publie le
  `dvc.lock` frais après un `dvc push` ; le serveur le détecte (ETag S3 toutes les 60 s),
  tire les modèles et prévient l'interface. **Désactivé par défaut**
  (`MEDVISION_WATCH_ENABLED`), à activer quand tu le décides.
- **`convnexttiny` (les 2 variantes) désactivés** : leur ONNX est invalide dès l'export
  (bug tf2onnx/ConvNeXt). Réactivation = décommenter 3 lignes dans
  `src/registry/model_registry.py`, après ré-export sur le PC ML.
- **Segmentation pure** : la tête de classification des U-Net annonçait NORMAL avec une
  confiance de 1,000 sur des pneumonies manifestes. Décision produit : ces deux écrans
  délimitent des zones et ne posent **aucun** diagnostic. Type de tâche passé à
  `segmentation`, libellés sans mention de classification, tête ni exécutée ni affichée.

### Ce qui est en cours (non poussé)

Le **socle du front Angular** est commité sur la branche locale
`feat/front-socle-angular` (commit `ae34461`) : Angular 19, design system maison,
libellés français centralisés, types miroir de l'API. Rien n'est branché ni déployé —
Streamlit reste la seule interface en service.

### Dettes ouvertes (ce ne sont pas des régressions)

- **`convnexttiny` à ré-exporter** sur le PC ML puis `dvc push`. **Jamais d'entraînement
  sur les VPS k3s** (consigne : ils font tourner toute la production).
- ~~Images du dataset de segmentation cérébrale~~ — **RÉSOLU** (image `2026-07-18f`).
  Les 12 fichiers du dossier venaient tous de `scripts/generate_sample_images.py`
  (bouche-trous de développement copiés sur le volume en juin) ; trois autres traînaient
  dans chaque classe du dossier des IRM. Ils sont désormais reconnus à leur nom et
  écartés du navigateur, et la segmentation cérébrale se rabat sur les IRM du problème
  frère — même corpus, déjà présentes sur le volume (400 vraies IRM par classe).
- **Rapports de classification absents du pod** : seul le stage ONNX est tiré au
  démarrage, donc `/api/reports` renvoie `classification_report: null`.
- **34 fichiers encore en CRLF** dans l'historique git (les 4 qui bloquaient les
  changements de branche ont été normalisés). À traiter dans un commit dédié, sinon
  diff-cover comptera chaque ligne comme ajoutée.

### Règles apprises cette session

- **Le manifeste k3s doit suivre la production.** Les correctifs ont d'abord été appliqués
  au cluster par bumps ciblés ; le manifeste a divergé, et un redéploiement depuis le
  fichier aurait tout recassé. Toujours consigner dans
  `k3s-fromOVHVps/rendered-k3s-manifests/30-medvision.yaml`.
- **Les PV `local-path` sont ancrés à un nœud.** Tout pod qui monte
  `medvision-model-artifacts` doit rester sur `apps-b` — mlflow était sur `apps-a` et
  restait bloqué en attente.

---

## État au 2026-06-15 (fin de session)

### Image ECR active

```
113301685315.dkr.ecr.eu-west-3.amazonaws.com/platform/medvision-ai:2026-06-15f
```

Contient : code uniquement (modèles exclus via `.dockerignore`). Les modèles sont tirés depuis S3 via DVC au démarrage du pod.

### Pods K3s (namespace `medvision`)

| Pod | État | Notes |
|---|---|---|
| `medvision-api` | Running | Port 8000 — FastAPI |
| `medvision-streamlit` | Running | Port 8501 — UI |
| `medvision-mlflow` | Running | Port 5000 — tracking (accès interne) |

### URLs

| Service | URL |
|---|---|
| API | https://api.medvision.doctumconsilium.com |
| Streamlit | https://app.medvision.doctumconsilium.com |
| MLflow | `kubectl port-forward -n medvision svc/medvision-mlflow 5000:5000` |

### Modèles disponibles (tirés depuis S3 via DVC)

| Fichier | Taille | État |
|---|---|---|
| `optimized_model.keras` | 12 Mo | Stub (à ré-entraîner) |
| `brain_mri_optimized.keras` | 17 Mo | Stub (à ré-entraîner) |
| `brain_tumor_segmentation_unet.keras` | 90 Mo | Stub (à ré-entraîner) |

### Données dans les PVCs

| PVC | Contenu actuel |
|---|---|
| `medvision-raw-data` (worker-ovh-094) | chest_xray/ (samples) + brain_tumor_mri/ (7 212 images Kaggle) + brain_tumor_segmentation/images/ (12 PNGs synthétiques) |
| `medvision-mlflow-store` (worker-ovh-233) | mlflow.db (historique entraînements) |
| `medvision-model-artifacts` (worker-ovh-233) | Vide — modèles via DVC/S3 |

---

## Architecture (résumé)

```
[Local Inspiron Ubuntu]
  conda activate GPUMachineLearning
  dvc repro       → entraîne les modèles
  dvc push        → pousse vers s3://platform-medvision-dvc-artifacts/

[ECR]
  docker build (code only, artifacts/ exclu)
  docker push → 113301685315.dkr.ecr.eu-west-3.amazonaws.com/platform/medvision-ai:TAG

[K3s pod au démarrage]
  docker/entrypoint.sh:
    git init -q   (DVC requiert un repo git)
    dvc pull train_chest_xray train_brain_mri train_brain_tumor_segmentation
    → artifacts/models/ peuplé depuis S3
  streamlit run streamlit_app.py
```

---

## Prochaines étapes prioritaires

1. **Entraîner de vrais modèles** (la plus importante)
   ```bash
   conda activate GPUMachineLearning
   bash scripts/download_dataset.sh   # si données pas encore là
   dvc repro
   dvc push
   ```

2. **Rebuild ECR avec les vrais modèles** → redeploy (voir `ONBOARDING_perso_inspiron_ubuntu.md`)

3. **Valider les prédictions** : ouvrir l'app, tester predict sur brain_mri et chest_xray

---

## Règles critiques

- **`keras==3.3.3`** obligatoire dans `requirements.txt` (modèles sauvés avec 3.3.3, pip installe 3.12.x sans pin → AttributeError)
- **`dvc pull <stages>`** (jamais `dvc pull` seul — conflit avec data/raw/ non pushée)
- **`git` dans le Dockerfile** (`apt-get install git` — `python:3.10-slim` ne l'inclut pas)
- **PVC `medvision-raw-data`** : ajouter des images via `kubectl cp`, pas rebuild
- **MLflow** : `--backend-store-uri=sqlite:////mlflow/mlflow.db` (4 slashes pour chemin absolu)
