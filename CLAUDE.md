# CLAUDE.md

This file defines Claude Code execution rules for `medvision-ai`.

## 🤝 Handoff 2026-06-16 — Migration ONNX (branche feat/ci-quality-2026-06-15)

> **Image à construire : `medvision-ai:2026-06-16a`** — après conversion des modèles.
> Branche `feat/ci-quality-2026-06-15` — 4 commits, non encore poussés.
>
> **Ce qui a été livré :**
> - `src/registry/model_registry.py` : `load_onnx_model()` remplace `load_tf_model()`. Tous les
>   `model_candidates` dans `PROBLEMS` pointent vers des `.onnx`.
> - `streamlit_app.py` : `_predict()` utilise `session.run()` via onnxruntime, gestion multi-têtes
>   (U-Net) par nom de sortie. Message d'erreur capé à 300 chars (plus de JSON Keras en clair).
> - `requirements.txt` : tensorflow/keras/torch supprimés → `onnxruntime==1.20.1`. Image -600 MB.
> - `requirements/base.txt` : `onnxruntime==1.20.1` ajouté pour les smoke tests CI.
> - `requirements-train.txt` : nouveau fichier pour la machine ML (TF 2.16.1 + Keras 3.13.2 + PyTorch).
> - `scripts/convert_to_onnx.py` : script de conversion .keras/.pt → .onnx pour la machine ML.
> - `README_ONNX_UPDATE.md` : guide complet pas-à-pas.
> - `tests/smoke/test_core.py` : adapté à ONNX (25 tests verts, sans mock TF).
>
> **ÉTAPE SUIVANTE BLOQUANTE (action utilisateur — machine ML, conda GPUMachineLearning) :**
> ```bash
> pip install tf2onnx>=1.16 onnx>=1.16
> git pull
> dvc pull artifacts/
> python scripts/convert_to_onnx.py
> dvc add artifacts/models/ && dvc push
> git commit -m "feat(models): convertit tous les modèles en ONNX"
> git push
> bash scripts/redeploy-k3s.sh 2026-06-16a
> ```
>
> **Règles ONNX (remplacent les règles Keras) :**
> - `PROBLEMS` dans `model_registry.py` → extensions `.onnx`. Plus de `.keras` ni `.pt` pour l'inférence.
> - La règle `keras==3.3.3` est **OBSOLÈTE** — remplacée par ONNX.
> - Pour l'entraînement : `pip install -r requirements-train.txt` (inclut TF + Keras 3.13.2 + PyTorch + tf2onnx).

## 🤝 Handoff 2026-06-15 — Architecture DVC+S3 + fixes déploiement (DÉPLOYÉ)

> **Image prod active : `medvision-ai:2026-06-15f`** — namespace `medvision`, cluster k3s OVH.
>
> **Ce qui a été livré :**
> - **Architecture DVC+S3** : modèles et rapports hors image Docker, versionnés via DVC sur `s3://platform-medvision-dvc-artifacts/`. L'image ne contient que du code. Les pods font `dvc pull` au démarrage via `docker/entrypoint.sh`.
> - **Entrypoint corrigé** : `git init -q` si absent (DVC requiert un repo git) ; `dvc pull train_chest_xray train_brain_mri train_brain_tumor_segmentation` (stages spécifiques, évite le conflit avec data/raw/ non pushée).
> - **MLflow fix** : `--backend-store-uri=sqlite:////mlflow/mlflow.db` (préfixe `sqlite://` manquant → NotADirectoryError).
> - **Keras version pin** : `keras==3.3.3` dans `requirements.txt` (modèles sauvés avec 3.3.3, pip installait 3.12.2 → AttributeError au chargement).
> - **Images dataset dans les PVCs** : `brain_tumor_mri` (7 212 images Kaggle) + `brain_tumor_segmentation` (12 PNGs synthétiques) copiées via `kubectl cp`.
> - **Secret AWS** `medvision-aws-creds` créé en K3s pour le `dvc pull` au démarrage.
>
> **3 modèles en S3 (stubs — vrais modèles après `dvc repro`)** :
> - `optimized_model.keras` (12 Mo) — chest X-ray classification
> - `brain_mri_optimized.keras` (17 Mo) — brain MRI classification
> - `brain_tumor_segmentation_unet.keras` (90 Mo) — U-Net segmentation
>
> **Règles critiques rappelées :**
> - **`keras==3.3.3`** : toujours pinner explicitement dans `requirements.txt`. Pip installe 3.12.x sans pin → incompatibilité de chargement avec les modèles existants.
> - **DVC pull par stage** : `dvc pull <stage1> <stage2>` (pas `dvc pull` seul) pour éviter le conflit avec `data/raw/` non présente en S3.
> - **Entrypoint bypass** : le champ `command:` K8s écrase le ENTRYPOINT Docker. Si un Deployment a `command: ["mlflow", "server"]`, l'entrypoint.sh est ignoré — c'est voulu pour MLflow.
> - **PVC `medvision-raw-data`** : monté sur `/app/data/raw`, persistant sur `worker-ovh-094`. Copier les données via `kubectl cp`, elles survivent aux restarts.
>
> **Prochaines étapes :**
> 1. Entraîner de vrais modèles : `conda activate GPUMachineLearning && dvc repro`
> 2. `dvc push` → rebuild ECR → redeploy (les pods feront `dvc pull` automatiquement)
> 3. Voir `ONBOARDING_perso_inspiron_ubuntu.md` pour les commandes propres à la machine locale.

## CI Workflow (Mandatory — s'applique à Claude, Copilot, Gemini, tout agent)

Avant tout push ou PR, exécuter la CI locale :
```bash
bash scripts/ci_local.sh
```

Ce script est le miroir exact de `.github/workflows/ci.yml` :
1. `ruff check src/ tests/` — lint Python
2. `pytest tests/smoke/ -q` — tests sans TF (~5 s)
3. `shellcheck -x` — 5 scripts shell maintenus

Les hooks sont dans `.githooks/` (activer avec `git config core.hooksPath .githooks`) :
- `pre-commit` : ruff + shellcheck + détection de secrets (sur les fichiers staged)
- `pre-push` : délègue à `scripts/ci_local.sh` automatiquement

**Ne jamais pousser avec la CI rouge.** Corriger la vraie cause — jamais `--no-verify`.

## PR Workflow (Mandatory — s'applique à tout agent)

Toute session de travail significative DOIT se terminer par une PR :
1. Commits propres (un sujet par commit, conventionnel, lisible à voix haute)
2. CI locale verte (`bash scripts/ci_local.sh`)
3. Demander confirmation push à l'utilisateur
4. `git push` puis `gh pr create`
5. **Ajouter le lien de la PR dans le handoff du fichier agentique** (CLAUDE.md, copilot-instructions.md, GEMINI.md)

Le lien PR permet à tout agent de reprendre en contexte lors de la session suivante.

## Mandatory Sources of Truth
- `README.md` (MANDATORY: Must exist, create if missing)
- `INFRASTRUCTURE.md` (MANDATORY: Must exist, create if missing)
- `SKILLS.md` (if present)
- `ROADMAP.md` (MANDATORY: Must exist, create if missing)
- `.github/copilot-instructions.md`

## Execution Principles
1. Read sources of truth before any non-trivial task.
2. Align every change with the active phase in `ROADMAP.md`.
3. Fix root causes before any workaround.
4. Keep changes minimal, targeted, and verifiable.
5. Update documentation when behavior changes.
6. MISSING CORE DOCUMENTS: If README.md, INFRASTRUCTURE.md, or ROADMAP.md are missing, your VERY FIRST task is to create them before writing any code.

## Code Documentation Standard (Mandatory)
- Every public function, class, and module MUST have a docstring in the language's canonical format:
  - Python: Google-style docstrings (Args, Returns, Raises, Example).
  - TypeScript/JavaScript: JSDoc with @param, @returns, @throws, @example.
  - C#: XML summary with <summary>, <param>, <returns>.
  - Shell: header block with Purpose, Usage, Arguments, Exit codes.
- When modifying a function, update its docstring to reflect the new behavior.
- Run `pydoc`, `typedoc`, or equivalent after doc changes to verify output.

## Secret Management Protocol (Mandatory)
- Never hardcode secrets, tokens, or credentials in any file, script, log, or commit.
- ECR / Docker Registry tokens rotate every 12 hours. Before any image operation:
  1. `aws ecr get-login-password --region <region>` to refresh.
  2. Recreate the k8s pull secret via `kubectl delete/create secret`.
  3. Restart pods stuck in `ImagePullBackOff`.
- Document rotation commands in `INFRASTRUCTURE.md` under Operations.

## Terminal Sessions (Mandatory for Critical Operations)
- Always use a named tmux session for long-running, deployment, or destructive operations:
  ```bash
  tmux new-session -A -s <task-name>   # start or reattach
  # Naming: deploy-<service>, build-<tag>, k3s-ops, ecr-refresh
  ```
- On Windows: use Windows Terminal tabs or Start-Process with file logging.

## Environment Policy
- Use a single standard environment per repo when possible.
- Use GPU if available and compatible; otherwise CPU in the same environment.
- Parallel environments allowed only if technically unavoidable — document reason, limits, naming, activation.

## Platform Compatibility
- Critical automation scripts must provide Ubuntu (Bash) and Windows (PowerShell) execution.
- macOS (zsh/bash) compatibility is required when the script uses only POSIX-standard commands.
- Any exception must be documented with an operational alternative.

## Hooks (if present)
- Preflight: `.claude/hooks/preflight.ps1` and `.claude/hooks/preflight.sh`
- Post-task check: `.claude/hooks/post-task.ps1` and `.claude/hooks/post-task.sh`
- Usage details: `.claude/hooks/README.md`
