# ROADMAP

## Last Update
2026-06-28 (portabilité poste-à-poste : envs, CUDA, install script)

## Active Phase
Phase 2 — Pipeline DVC+S3 + entraînement local reproductible

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
