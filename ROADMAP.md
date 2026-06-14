# ROADMAP

## Last Update
2026-06-15 (session complète DVC+S3+ECR+K3s)

## Active Phase
Phase 2 — Pipeline DVC+S3 + entraînement local reproductible

## Goals
- Maintain service availability
- Keep dependencies and documentation up to date
- Enforce guardrails (code documentation, secret management, deployment standards)

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
