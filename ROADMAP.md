# ROADMAP

## Last Update
2026-07-28 (interface reprise pour la vitrine : libellés et état de connexion corrigés)

## Active Phase
Phase 3 — Nouvelle interface (Angular) et portail de documentation

## Execution Log — 2026-07-28

### Phase 3c — Ce que la photographie de l'interface a révélé

**Point de départ.** L'interface était en ligne depuis la veille. Il fallait la
photographier pour la vitrine `doctumconsilium.com` — donc la regarder comme un visiteur
la voit, et non comme on relit du code. Deux défauts sont apparus immédiatement.

**Ce qui a été corrigé.**

1. **La pastille de connexion mentait au premier chargement.** Elle affichait
   « reconnexion… » avant même qu'une connexion ait été tentée : sur une page qui vient
   de s'ouvrir, cela laisse croire à un incident. Elle distingue désormais trois états et
   annonce « connexion… » tant qu'il ne s'est rien passé.
2. **Deux catégories restaient en anglais** au milieu d'une interface française :
   `pituitary tumor` — que le jeu de données de segmentation écrit autrement que celui de
   classification — et `ABNORMAL`. Les étiquettes ont été **relevées sur l'API de
   production** plutôt que devinées, et un test les fige, y compris le cas d'une étiquette
   inconnue qui doit ressortir telle quelle plutôt que de disparaître.

**Vérifications.** Trente tests unitaires verts ; captures prises sur le site public avec
Playwright — le mode capture de Chrome ne produisait rien, car il attend l'inactivité du
réseau alors que l'application garde ouvert un flux temps réel qui, par nature, ne se
termine jamais.

**Images.** `medvision-web:2026-07-28` en production. `medvision-ai` reste en
`2026-07-18f`, inchangée.

**Commandes de déploiement effectivement utilisées.**

```bash
# Publication de l'image du front (le script rafraîchit lui-même le jeton ECR)
cd medvision-ai && ./scripts/build-and-push-web.sh 2026-07-28

# Le jeton du secret de tirage vit 12 h : sans ce renouvellement, tout NOUVEAU tag
# échoue en 403 alors que les pods déjà démarrés continuent de tourner. On PATCHE,
# on ne supprime pas — un delete/create ouvre une fenêtre où le secret n'existe plus.
T=$(aws ecr get-login-password --region eu-west-3)
CFG=$(printf '{"auths":{"113301685315.dkr.ecr.eu-west-3.amazonaws.com":{"username":"AWS","password":"%s","auth":"%s"}}}' \
  "$T" "$(printf 'AWS:%s' "$T" | base64 -w0)" | base64 -w0)
kubectl -n medvision patch secret ecr-pull-secret --type merge \
  -p "{\"data\":{\".dockerconfigjson\":\"$CFG\"}}"
unset T CFG

kubectl -n medvision set image deploy/medvision-web \
  web=113301685315.dkr.ecr.eu-west-3.amazonaws.com/platform/medvision-web:2026-07-28
kubectl -n medvision rollout status deploy/medvision-web --timeout=180s
```

**Note de suivi des versions.** Ce dépôt n'a volontairement pas de
`docs/IMAGE-VERSIONS.md` (décision du 2026-07-18) : les tags sont consignés ici et en
tête de `docs/SESSION-STATE.md`. Le tableau `IMG` de `doctum-trading-platform` ne suit
que les images de cette plateforme-là et ne concerne pas MedVision.

**Hors scope.** La vitrine `doctumconsilium.com` a été mise à jour dans son propre dépôt
(`doctumconsilium-html5-css3-portfolio`), où le déploiement est consigné.

## Execution Log — 2026-07-27

### Phase 3b — L'interface web Angular, de bout en bout

**Point de départ.** Depuis le 18 juillet, les dix-sept modèles tournaient en production
et l'API v2 était complète — mais aucune interface moderne ne les montrait. Le front
s'était arrêté au squelette généré par l'outil, sur une branche locale jamais poussée :
liste de routes vide, page d'accueil de démonstration d'Angular. Accessoirement, le
`.gitignore` du dépôt ne connaissait ni Node ni Angular, si bien que 394 Mo de
dépendances traînaient en fichiers non suivis, à un `git add -A` distrait de finir dans
l'historique.

**Ce qui a été livré.**

1. **Hygiène du dépôt.** Deux sections dans le `.gitignore` racine — les dépendances
   installées par npm et les sorties de l'outillage Angular. Le trou de 394 Mo est fermé.
2. **Le socle.** Une seule source de vérité, le registre des modèles, chargée au
   démarrage puis tenue à jour par le flux temps réel du serveur : quand un modèle arrive
   dans S3, l'interface se rafraîchit sans rechargement de page. Si le flux tombe, la
   pastille de l'en-tête le dit et la reconnexion espace ses tentatives ; au retour, on
   demande d'abord la version du registre et on ne retélécharge que si elle a changé.
3. **L'écran d'analyse.** Choix du type d'analyse, image déposée ou prise dans la banque
   d'exemples, plusieurs modèles interrogés **en une seule requête**, résultats côte à
   côte. Une erreur sur un modèle reste dans sa carte sans faire tomber les autres.
   Sur les analyses de segmentation, **aucune prédiction ni confiance n'est affichée** :
   ces modèles annonçaient « NORMAL » avec une confiance de 1,000 sur des pneumonies
   manifestes. Un test verrouille cette règle — s'il tombe, c'est qu'une régression
   médicalement trompeuse est revenue.
4. **Les zones réglables sans le serveur.** Le masque arrive en probabilités, pas en noir
   et blanc : le curseur de sensibilité se contente de re-comparer ces valeurs à un seuil
   dans le navigateur. Bouger le curseur est instantané et ne coûte aucune inférence.
5. **L'écran de comparaison.** Tableau triable et graphe en barres. Une mesure absente
   s'affiche en tiret, jamais en zéro, et son modèle reste en fin de classement quel que
   soit le sens du tri — les rapports d'entraînement ne sont pas toujours tirés sur le
   pod, et un excellent modèle sans rapport ne doit pas passer pour le pire du lot.
6. **L'image et le déploiement.** Une image nginx autonome de 49 Mo, séparée de l'image
   d'inférence pour que retoucher un bouton n'oblige pas à reconstruire PyTorch. Manifests
   k3s : déploiement `medvision-web`, hôte `ui.medvision`, Streamlit conservé sur
   `app.medvision`.

**Deux défauts trouvés en essayant, pas en relisant.**

- **nginx serait parti en boucle de redémarrage.** Il résout l'adresse de l'API une seule
  fois, au démarrage : écrite en dur, elle faisait refuser le lancement dès que l'API
  n'était pas encore joignable. La configuration est devenue un gabarit, l'adresse passe
  par une variable et un résolveur DNS, donc elle est relue à chaque requête. Vérifié
  sans aucune API joignable : le conteneur démarre, sert l'application, et répond 502 sur
  `/api` au lieu de mourir.
- **Le pod de l'API ne montait pas les jeux d'images.** Seul Streamlit le faisait. La
  banque d'exemples de la nouvelle interface aurait affiché « aucune image » alors que
  les données sont bien sur le nœud. Corrigé dans les manifests.

**Une dérive corrigée au passage.** Le gabarit de déploiement de MedVision était resté à
l'état d'avant le 18 juillet : reconstruire le cluster à partir de lui aurait rejoué les
incidents déjà corrigés — évictions de pods faute de stockage éphémère, `ImagePullBackOff`
faute de secret de tirage, MLflow en attente sur le mauvais nœud. Vérifié contre le
cluster réel, puis régénéré depuis le manifeste rendu.

**Choix d'outillage assumé.** Tailwind CSS, Chart.js et `@ngrx/signals` sont utilisés :
ils pèsent sur le bundle envoyé au navigateur, pas sur le nœud qui ne sert que des
fichiers statiques. Le design system maison reste la source des couleurs — Tailwind les
consomme, si bien que la bascule clair/sombre repeint aussi les classes utilitaires, au
runtime et sans recompilation.

**Vérifications.** Compilation stricte verte ; dix-huit tests unitaires verts ; image
Docker construite et lancée en local (accueil, analyse et comparaison répondent 200,
en-têtes de cache conformes) ; manifests analysés sans erreur, détecteur d'écarts du
dépôt silencieux sur MedVision. Premier affichage : 296 ko bruts, 86 ko transférés —
Chart.js et les écrans lourds sont chargés à la demande.

**Mise en ligne, le jour même.** Dépôt ECR créé, image publiée, manifests appliqués de
façon ciblée (création des objets neufs, patchs pour l'API et le point d'entrée — jamais
le fichier entier, qui pourrait écraser un secret), enregistrement DNS créé, certificat
émis pour les trois noms. Vérifié sur l'adresse publique : les trois écrans répondent, le
registre annonce quinze modèles disponibles, la banque d'exemples sert 176 radiographies
et 200 IRM, une prédiction réelle sur trois modèles renvoie des résultats cohérents, la
segmentation ne renvoie aucune classe, et le flux temps réel bat. Streamlit et l'API
historiques sont intacts.

**Deux défauts trouvés pendant la mise en ligne.** Le relais vers l'API répondait 502 :
depuis que l'adresse passe par une variable, c'est nginx qui résout le nom, et il
n'applique pas les domaines de recherche de Kubernetes — il lui faut le nom complet du
service. Et le cache DVC de l'API, présent en production depuis le 18 juillet, n'était
décrit dans aucun manifeste : un redéploiement l'aurait supprimé en silence. Les deux
sont corrigés dans le dépôt.

**Une découverte d'exploitation.** Le nouvel hôte n'a pas été créé automatiquement par
la synchronisation DNS : la configuration de la plateforme tient une liste d'adresses
écrite à la main, qui court-circuite la lecture des manifests. L'adresse y a été ajoutée.
Le script ne touchant que les sous-domaines de cette liste, il n'y avait aucun risque de
suppression ailleurs.

**Images.** `medvision-web:2026-07-27b` en production (refonte visuelle incluse). `medvision-ai` reste en
`2026-07-18f`, inchangée.

**Hors scope.** Le retrait de Streamlit (il reste en ligne tant que la parité n'est pas
constatée), l'authentification Keycloak sur l'interface, l'activation du surveillant DVC,
la réactivation des deux `convnexttiny` (leur ONNX est invalide dès l'export) et
l'anglais.

## Execution Log — 2026-07-18

### Phase 3a — Les 17 modèles en production, API v2 et segmentation pure

**Point de départ.** Les 17 modèles entraînés et poussés dans S3 via DVC n'apparaissaient
pas dans l'interface : elle n'en proposait que 4. Le diagnostic a mis au jour cinq causes
racines enchaînées, toutes corrigées et déployées dans la journée.

**Ce qui bloquait, et pourquoi.**

1. L'extra `dvc[gdrive]` tirait PyDrive2, qui fige pyOpenSSL en 22.0.0. Le rebuild ayant
   résolu un cryptography récent, tout accès S3 de DVC plantait et les pods démarraient
   sans aucun modèle. Le remote du projet étant S3 seul, l'extra a été retiré.
2. Les 17 modèles plus le cache DVC dépassent les 2 Gi de stockage éphémère alloués : les
   pods étaient évincés en boucle. La limite passe à 6 Gi et, surtout, les modèles
   déménagent sur un volume persistant — ils survivent désormais à un crash au lieu
   d'être re-téléchargés à chaque démarrage.
3. Sur ce volume, `dvc pull` refusait d'écraser des fichiers qu'il jugeait non
   sauvegardés, d'où quatre modèles seulement. L'option `--force` a été ajoutée : le pod
   est une copie jetable de la vérité S3.
4. Les trois modèles PyTorch échouaient parce que `torch.onnx` exporte en canaux-d'abord
   quand l'application envoyait toujours du canaux-en-dernier. Un helper lit désormais la
   forme d'entrée déclarée par le modèle et transpose si nécessaire.
5. L'interface tombait en 503 : son cache de sessions ONNX autorisait 16 modèles en
   mémoire (environ 350 Mo chacun) dans un pod limité à 2 Gi. Il est ramené à 3.

**Ce qui a été livré en plus.** La PR #10, bloquée par quatre vérifications rouges, a été
débloquée et fusionnée — c'est elle qui apportait le pipeline des 17 modèles. Une **API v2**
(préfixe `/api`) a été construite pour la future interface : registre versionné, navigateur
d'images par identifiants opaques (aucun chemin disque n'est exposé ni interprété),
prédiction multi-modèles renvoyant les masques en PNG (le seuil se change côté client sans
ré-inférence), rapports. Un **watcher DVC** accompagné d'un flux temps réel permet
désormais qu'un modèle poussé apparaisse sans redéploiement ; il reste désactivé par
défaut, à activer sur décision.

**Deux décisions produit.** Les deux variantes `convnexttiny` sont retirées du registre :
leur fichier ONNX est invalide dès l'export (bug tf2onnx sur ConvNeXt), elles affichaient
une erreur à chaque analyse. Et les deux problèmes de segmentation ne posent plus de
diagnostic : leur tête de classification annonçait NORMAL avec une confiance de 1,000 sur
des pneumonies manifestes. Ces écrans délimitent des zones, un point c'est tout — les
libellés, l'inférence et l'affichage ont été alignés sur cette promesse.

**Vérifications.** Intégration locale verte à chaque étape (ruff, tests smoke, couverture
du diff supérieure à 80 %, shellcheck, guardrails) ; état de production contrôlé
directement dans les pods après chaque déploiement.

**Images déployées** : `medvision-ai:2026-07-18e` (api, streamlit, mlflow).

**Fusions** : medvision-ai #10 à #17 ; k3s-fromOVHVps #30 et #32.

**Hors périmètre.** L'interface Angular s'arrête au socle (branche locale
`feat/front-socle-angular`, rien de déployé) ; le portail de documentation privé n'est pas
commencé ; aucun modèle n'a été ré-entraîné. Détail complet et marche à suivre :
`docs/plans/2026-07-18-handoff-medvision.md`.

## Goals
- Maintain service availability
- Keep dependencies and documentation up to date
- Enforce guardrails (code documentation, secret management, deployment standards)
- **Reproductibilité d'un poste à l'autre** (Ubuntu natif & WSL2) : install scriptée, environnements déterministes, GPU.

## Execution Log — 2026-06-28

### Phase 2c — Portabilité « d'un poste à l'autre » (Ubuntu & WSL2)

**Objectif** : qu'un clone neuf sur n'importe quel poste Ubuntu/WSL2 arrive à `dvc repro`
(entraîne les 4 modèles + conversion ONNX) sur GPU, sans étape implicite propre à une machine.

**Cause racine traitée — collision CUDA TensorFlow ↔ PyTorch.** TF 2.16 (`nvidia-nccl-cu12`
2.19.3) et torch (`nvidia-nccl-cu13` 2.29.7) fournissent le **même** `libnccl.so.2` → dans un
seul env, torch charge le NCCL de TF (trop vieux) → `undefined symbol: ncclCommResume`, torch
inutilisable. cuDNN/cuBLAS ne collisionnent pas (packages cu12 vs cu13 distincts).

**Architecture retenue — deux environnements séparés :**
- `.venv` (`requirements-train.txt`) : **TensorFlow 2.16.1 [and-cuda]** — pipeline `dvc repro`.
- `.venv-torch` (`requirements-torch.txt`) : **torch 2.6.0+cu124 / torchvision 0.21.0** — modèles PyTorch/vision.

**Livrés :**
- `scripts/install_prereqs.sh` : installe TOUT (paquets système, Python 3.10–12, les 2 envs,
  CUDA via wheels pip, contrôle AWS/Kaggle). Idempotent, détecte WSL2 (driver côté Windows).
- `scripts/gpu_env.sh` : à sourcer avant `dvc repro` — contourne le bug TF 2.16.1 (wheels pip
  qui ne déclarent pas leurs libs CUDA) en ajoutant `nvidia/*/lib` à `LD_LIBRARY_PATH`. Portable.
- `requirements-train.txt` réécrit (TF only, **plus de torch**) ; `requirements-torch.txt` créé.
- **onnx épinglé `<1.18`** : les ≥1.18 exigent `ml_dtypes ≥ 0.4` (float4_e2m1fn), incompatible
  avec le `ml_dtypes 0.3.x` de TF 2.16 → cassait l'étape `convert_to_onnx`.
- `src/models/backbones.py` : ajout de la clé **`optimized`** (→ EfficientNetV2B0) attendue par
  `dvc.yaml` (`--model optimized`) et par les artefacts S3 (`optimized_model.keras`, `brain_mri_optimized.keras`).
- Docs dé-machinifiées (`ONBOARDING.md`, `START.md`, `README_ONNX_UPDATE.md`,
  `docs/LOCAL_TRAINING_GUIDE.md`, `requirements-train.txt`) : suppression des `conda activate
  GPUMachineLearning`, chemins absolus et `aws sso` imposés ; ajout setup AWS (clés statiques **ou**
  SSO) + Kaggle ; commandes d'entraînement alignées sur `dvc.yaml`.

**Validé :** TF voit le GPU (`GPU:0`) après `gpu_env.sh` ; `torch.cuda.is_available()` = True
dans `.venv-torch` ; imports de toutes les étapes du pipeline OK.

**Pipeline « tout entraîner » :** `scripts/train_all.sh` entraîne les **17 modèles** du registry
(6 chest + 6 brain_mri Keras + 3 PyTorch + 2 segmentations) en gérant les 2 envs, puis convertit
en ONNX. Idempotent (`--skip-existing`). Plan : `docs/plans/2026-06-28-train-all-models.md`.

### Phase 2d — Câblage prod des 17 modèles via DVC `foreach` (2026-06-28)

**Objectif** : `dvc repro` entraîne+convertit+versionne les 17, et la prod les sert tous.

**Livrés :**
- `dvc.yaml` réécrit en `foreach` (24 stages) : `train_chest_xray`/`train_brain_mri` × 6 backbones,
  `train_brain_mri_torch` × 3 (env torch), `convert_to_onnx` étendu à **17 deps / 17 outs**.
- Wrappers d'environnement `scripts/_dvc_tf.sh` (`.venv` + gpu_env), `scripts/_dvc_torch.sh`
  (`.venv-torch`, `LD_LIBRARY_PATH` isolé), `scripts/_dvc_convert.sh` (2 passes keras+pt).
- `docker/entrypoint.sh` : `dvc pull convert_to_onnx` inchangé → récupère désormais les 17.
- 2 incohérences pré-existantes corrigées : `brain_mri_${item}_metrics.json` (vs `brain_mri_metrics.json`),
  et `baseline` désormais entraîné (était une dép orpheline de `convert_to_onnx`).
- Validé statiquement : `dvc stage list` (24 stages) + `dvc dag` (DAG sans cycle).
- Plan : `docs/plans/2026-06-28-prod-all-models-et-spa.md` (inclut le chantier SPA suivant).

**Hors scope / étape suivante :** entraînement complet (`dvc repro`, GPU multi-heures — utilisateur),
puis `dvc push` + `redeploy-k3s.sh` ; ensuite migration du front Streamlit → SPA (POC React + Angular).

## Execution Log — 2026-06-15 (session 2)

### Phase 2b — Fixes déploiement + images dataset + documentation (2026-06-15)

**Image active : `medvision-ai:2026-06-15f`**

**Bugs fixés :**
- `git: command not found` dans l'entrypoint → `apt-get install git` dans le Dockerfile.
- `dvc pull artifacts/models/` syntaxe invalide → remplacé par `dvc pull <stage1> <stage2>`.
- `AttributeError: 'NoneType' object has no attribute 'pop'` au chargement Keras → `keras==3.3.3` pinné dans `requirements.txt` (pip installait 3.12.x, incompatible avec modèles sauvés en 3.3.3).
- MLflow `NotADirectoryError` → préfixe `sqlite://` ajouté dans `--backend-store-uri`.
- "No local image samples" pour brain_mri et brain_tumor_seg → `kubectl cp` des images dans le PVC + restart pour vider `@st.cache_data`.

**Livrés :**
- `docker/entrypoint.sh` corrigé (git init + dvc pull par stages)
- `requirements.txt` : `keras==3.3.3` ajouté
- PVC `medvision-raw-data` : brain_tumor_mri (7 212 images) + brain_tumor_segmentation (12 PNGs)
- `ONBOARDING_perso_inspiron_ubuntu.md` (notes machine locale)
- `docs/SESSION-STATE.md` (point de reprise canonique)
- `docs/plans/README.md` (index plans)
- Handoffs dans CLAUDE.md, GEMINI.md, .github/copilot-instructions.md
- `ONBOARDING.md` mis à jour

**Hors scope :** entraînement sur vrais datasets Kaggle (étape suivante).

## Execution Log — 2026-06-15

### Phase 2 — Architecture DVC+S3 + pipeline d'entraînement local (2026-06-15)

**Objectif** : rendre l'app deployable avec de vrais modèles entraînés localement, sans dépendre d'artefacts baked dans l'image Docker.

**Livré :**

- **Architecture DVC+S3** : les modèles et rapports ne sont plus baked dans l'image Docker. Ils sont versionnés dans DVC (`dvc.lock` généré) et stockés sur S3 (`s3://platform-medvision-dvc-artifacts/models`). 6 fichiers pushés.
- **Entrypoint Docker** (`docker/entrypoint.sh`) : les pods K3s font automatiquement `dvc pull` au démarrage si les credentials AWS sont présents.
- **Secret AWS en K3s** (`medvision-aws-creds`) : credentials injectés via `envFrom` dans medvision-api et medvision-streamlit, créés par `scripts/redeploy-k3s.sh`.
- **Registry fix** : ajout des modèles `optimized` pour `chest_xray` et `brain_mri` dans `src/registry/model_registry.py` (modèles existants non référencés depuis la migration multi-backbones).
- **dvc.yaml corrigé** : suppression des dépendances `src/models/` et `src/segmentation/models/unet.py` qui n'existent plus.
- **Documentation débutant** (`docs/LOCAL_TRAINING_GUIDE.md`) : guide complet download→train→metrics→DVC push→ECR→K3s, avec glossaire, smoke test, erreurs fréquentes.
- **DVC_GUIDE.md** mis à jour : sections « Ajouter un modèle entraîné » et « Pull dans K3s ».
- **ONBOARDING.md** mis à jour : bloc « Entraîner ton premier modèle » avec renvoi vers LOCAL_TRAINING_GUIDE.md.

**Prochaines étapes :**
- Télécharger les vrais datasets Kaggle et relancer `dvc repro` pour des métriques réelles.
- Reconstruire l'image ECR avec le nouveau Dockerfile et redéployer K3s.
- Phase 3 : entraînement cloud (AWS SageMaker ou GPU spot).

## Execution Log — 2026-05-08

### Guardrails Propagation

- Added `INFRASTRUCTURE.md` with operational runbook
- Added `CLAUDE.md` and `GEMINI.md` for multi-AI assistant compatibility
- Updated `.github/copilot-instructions.md` with:
  - Code documentation standard (pydoc/JSDoc/XML/shell headers)
  - Secret management protocol (ECR 12h rotation, k8s pull secrets)
  - tmux sessions mandatory for critical operations
- ECR secrets agent available at `.github/agents/ecr-secrets-agent.agent.md`

## Rollback
- All changes above are documentation-only and non-breaking.
- Revert any file via `git checkout HEAD~1 -- <file>`.
