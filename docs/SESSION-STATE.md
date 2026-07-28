# SESSION-STATE — MedVision AI

Point de reprise canonique. Mis à jour à chaque session significative.
**Lire ce fichier en premier, puis `ROADMAP.md`, puis `CLAUDE.md`.**

---

## 🤝 HANDOFF 2026-07-27 — L'interface web Angular EN PRODUCTION sur ui.medvision

> **En ligne : <https://ui.medvision.doctumconsilium.com>** — image
> `medvision-web:2026-07-28`. L'interface Streamlit historique reste en service sur
> `app.medvision`, l'API sur `api.medvision` ; `medvision-ai` n'a pas bougé
> (`2026-07-18f`). Plan suivi : `docs/plans/2026-07-27-medvision-front-angular-b1.md`.

### Vérifié en ligne à la clôture

| Contrôle | Résultat |
|---|---|
| Certificat TLS | valide, trois noms, expire le 2026-10-25 |
| Vitrine `doctumconsilium.com` | bascule faite : les deux liens MedVision pointent sur `ui.medvision` |
| Les trois écrans (`/`, `/studio`, `/comparaison`) | 200 |
| Registre des modèles à travers l'interface | 15 disponibles (5 + 8 + 1 + 1) |
| Banque d'exemples | 176 radiographies, 200 IRM de segmentation |
| Prédiction réelle, 3 modèles en une requête | NORMAL 0,597 · PNEUMONIA 0,561 · PNEUMONIA 0,571 |
| Segmentation réelle | surface 0,7 %, masque de probabilités servi ; `predicted_class` = `None` |
| Flux temps réel (SSE) | `event: hello` puis battements de cœur |
| Streamlit et API historiques | 200, intacts |

**Note sur le compte de modèles :** 15 disponibles, pas 17. Les deux `convnexttiny`
restent désactivés (ONNX invalide dès l'export) ; 15 + 2 = les 17 fichiers du pipeline.

### Refonte visuelle (seconde passe du 2026-07-27)

La première mise en ligne fonctionnait mais faisait « panneau
d'administration » : fond blanc, cartes plates, et surtout des libellés restés
en anglais alors que tout le reste parlait français. Repris dans la foulée —
accroche qui dit franchement ce que l'outil ne fait pas, parcours en trois
temps, noms d'analyses et catégories traduits (avec repli sur l'étiquette
d'origine), accord en nombre, identité dessinée déclinée en icône d'onglet
(l'ancienne était encore celle du générateur de projet), palette ivoire chaude
et trois niveaux d'ombre.

Deux fragilités écartées en **regardant** le rendu plutôt qu'en relisant le
code : le titre en dégradé reposait sur `color: transparent` et disparaissait
si le dégradé ne peignait pas ; l'animation d'apparition masquait le contenu
tant qu'elle n'avait pas tourné. Et les en-têtes de tri du tableau comparatif,
utilisables à la souris seulement, sont devenus de vrais boutons annonçant
`aria-sort`.

### Deux défauts trouvés PENDANT la mise en ligne, corrigés

1. **Le relais vers l'API répondait 502.** Journal de nginx :
   `medvision-api could not be resolved (3: Host not found)`. Depuis que l'adresse passe
   par une variable — le correctif contre la boucle de redémarrage — c'est nginx qui
   résout le nom, et **nginx n'applique pas les domaines de recherche** de
   `/etc/resolv.conf`. Le nom court marche depuis un shell du pod mais pas depuis nginx.
   Corrigé par le nom complet `medvision-api.medvision.svc.cluster.local`, dans les
   manifests **et** dans la valeur par défaut de l'image.
2. **Le cache DVC de l'API n'était décrit nulle part.** Il existe en production depuis le
   18 juillet ; un redéploiement depuis le dépôt l'aurait supprimé en silence. Ajouté aux
   manifests ; les montages décrits sont désormais identiques à ceux du cluster.

### Deux découvertes d'infrastructure à traiter

1. **🔴 La synchronisation DNS travaille sur un clone périmé.**
   `scripts/ovh_dns_sync_k3s_zone.sh` lit `RENDERED_MANIFESTS_DIR`, que la configuration
   pointe sur **`/home/yann/Documents/Github/k3s-fromOVHVps/`** (et non `GithubPerso/`) —
   un ancien clone dont `30-medvision.yaml` **date du 26 avril**. Conséquence : tout hôte
   ajouté depuis n'a jamais été créé par ce script, et il pourrait supprimer des
   enregistrements sur la foi d'une description obsolète. `ui.medvision` a dû être créé en
   forçant la liste des hôtes. **À corriger dans la configuration.**
2. **Le secret de tirage ECR était périmé de neuf jours.** Un jeton ECR vit 12 h : les
   pods déjà démarrés ne s'en aperçoivent pas, mais tout nouveau tag échoue en
   `403 Forbidden`. Renouvelé par `kubectl patch` (jamais par delete/create : cela ouvre
   une fenêtre où le secret n'existe pas).

### Commandes de déploiement réellement utilisées

```bash
aws ecr create-repository --repository-name platform/medvision-web --region eu-west-3
./scripts/build-and-push-web.sh 2026-07-27          # depuis medvision-ai
kubectl create -f <deployment+service medvision-web>  # objets NEUFS, extraits du manifeste
kubectl -n medvision patch deploy medvision-api --type strategic -p '<volumeMounts+volumes>'
kubectl -n medvision patch ingress medvision-ingress --type merge -p '<tls+rules+annotations>'
kubectl -n medvision set env deploy/medvision-web MEDVISION_API_UPSTREAM=http://medvision-api.medvision.svc.cluster.local:8000
DNS_RECORDS="ui.medvision.doctumconsilium.com" bash scripts/ovh_dns_sync_k3s_zone.sh <conf>
```

**Jamais `kubectl apply` du fichier entier** : le garde-fou du poste le bloque, et à
raison — un manifeste peut écraser un secret réel par un placeholder.

### Suivi Jira

Le dépôt est désormais mappé sur le projet **MVA « Medical vision AI »**. Épic **MVA-1**,
chantiers **MVA-2** à **MVA-7**, défauts **MVA-8** (dérive du gabarit) et **MVA-9** (tag de
redéploiement périmé).

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

- **Le chemin périmé de la synchronisation DNS** (voir plus haut) : c'est le point le
  plus important, il touche toute la plateforme et pas seulement MedVision.
- **Retrait de Streamlit** : à décider une fois la parité constatée à l'usage.
- **Authentification** : `ui.medvision` est public, comme l'était `app.medvision`.
- **Surveillant DVC** toujours désactivé (`MEDVISION_WATCH_ENABLED`) — l'interface sait
  déjà réagir au flux temps réel, l'activation reste ta décision.
- **Les deux `convnexttiny`** restent désactivés : leur ONNX est invalide dès l'export
  (bug tf2onnx/ConvNeXt), il faut un ré-export sur le PC ML.
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
