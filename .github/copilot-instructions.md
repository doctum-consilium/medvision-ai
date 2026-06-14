# Copilot Instructions

These rules are mandatory for all coding tasks in medvision-ai.

## 🤝 Handoff 2026-06-16 — Migration ONNX (branche feat/ci-quality-2026-06-15)

> **Image à construire : `medvision-ai:2026-06-16a`** — après conversion des modèles sur machine ML.
>
> **Ce qui a été livré :**
> - `load_onnx_model()` dans `model_registry.py` remplace `load_tf_model()`. Tous les modèles → `.onnx`.
> - `_predict()` dans `streamlit_app.py` utilise `onnxruntime` + gestion sorties multi-têtes (U-Net).
> - `requirements.txt` allégé : tensorflow/keras/torch → `onnxruntime==1.20.1`. Image -600 MB.
> - `scripts/convert_to_onnx.py` + `README_ONNX_UPDATE.md` : outils pour la conversion sur machine ML.
> - 25 smoke tests verts, ruff propre, shellcheck propre.
>
> **Règle ONNX :** la règle `keras==3.3.3` est **OBSOLÈTE**. Pour l'inférence → `onnxruntime`.
> Pour l'entraînement → `pip install -r requirements-train.txt` (TF 2.16.1 + Keras 3.13.2).
>
> **Action requise (machine ML) :** voir `README_ONNX_UPDATE.md`.

## 🤝 Handoff 2026-06-15 — Architecture DVC+S3 + fixes déploiement (DÉPLOYÉ)

> **Image prod active : `medvision-ai:2026-06-15f`** — namespace `medvision`.
>
> **Architecture courante** : code dans image ECR, modèles/rapports dans S3 via DVC. Pod → `dvc pull` au démarrage via `docker/entrypoint.sh`. Secret `medvision-aws-creds` fournit les credentials.
>
> **Bugs fixés dans cette session :**
> - `keras==3.3.3` pinné dans `requirements.txt` (3.12.x → AttributeError au load)
> - `dvc pull` avec stages spécifiques (évite conflit avec data/raw/ non pushée)
> - `git` installé dans le Dockerfile (`python:3.10-slim` ne l'inclut pas)
> - MLflow : préfixe `sqlite://` ajouté dans `--backend-store-uri`
>
> **Règle keras** : toujours pinner `keras==3.3.3`. Sans pin, pip installe 3.12.x → incompatibilité.
> **Règle DVC pull** : `dvc pull train_chest_xray train_brain_mri train_brain_tumor_segmentation --no-run-cache` (jamais `dvc pull` seul en prod).
> **Règle PVC** : données dans `/app/data/raw` via PVC `medvision-raw-data` (persistent). Copier via `kubectl cp`, pas rebuild image.
>
> Pour reprendre : lire `CLAUDE.md` (handoff) + `ROADMAP.md` + `ONBOARDING_perso_inspiron_ubuntu.md`.

## CI Workflow (Mandatory)

Avant tout push ou PR :
```bash
bash scripts/ci_local.sh   # ruff + smoke tests + shellcheck
```

Hooks actifs dans `.githooks/` (activer : `git config core.hooksPath .githooks`).
Ne jamais passer `--no-verify`. Ne jamais pousser avec la CI rouge.

## PR Workflow (Mandatory)

Toute session significative se termine par une PR. Après `git push` :
```bash
gh pr create --title "..." --body "..."
```
Ajouter le lien PR dans le handoff de **tous** les fichiers agentiques
(`CLAUDE.md`, `copilot-instructions.md`, `GEMINI.md`) afin que la session suivante
puisse reprendre avec le contexte complet.

## Chat Guardrails
- On the first chat of a session, read project documentation before any significant action (at minimum the `doc` or `docs` folder when present, plus `README.md`, `INFRASTRUCTURE.md` if present, `SKILLS.md` if present, and `ROADMAP.md` if present).
- Read `SKILLS.md`, `ROADMAP.md`, and `INFRASTRUCTURE.md` (when present) before any substantial task.
- Align the execution plan with the active phase in `ROADMAP.md` when it exists.
- Apply a mandatory Plan -> Analyze -> Read relevant code -> Act workflow for any non-trivial task.
- For any non-trivial action plan, use the standard format (`templates/ACTION_PLAN.template.md`):
	- Sections: Objectives, Steps, Validation, Expected Results, Progress
	- Checkmarks for traceability (✅, ⏳, ⏹️)
	- Before/after comparison tables when applicable
	- Clear, verified, and easy to scan
- Before any edits, briefly summarize assumptions and verify they match observed code.
- Provide short, actionable progress updates during execution.
- Prefer minimal, verifiable changes.

## Technical Guardrails
- Fix root causes rather than patching symptoms.
- Preserve repository style and avoid out-of-scope refactors.
- Maintain Ubuntu + Windows compatibility for automation scripts.
- Never hardcode secrets in files, scripts, or logs.
- When behavior changes, update related documentation.

## Quality
- Validate changes (targeted validation script, dry-run, or equivalent checks).
- Reduce speculative actions: prefer fewer high-confidence actions over many low-confidence attempts.
- If a blocker persists, document the cause and propose the simplest practical alternative.

## Execution Contract (Mandatory)
- Treat each user request as an end-to-end execution task until the explicit done criteria are met.
- Do not stop at analysis or planning only: execute code changes, validation, and deployment steps when requested.
- Provide factual progress updates every 3 to 5 meaningful actions, with the next concrete step.
- On blocker, report: root cause, what was attempted, one practical workaround, then continue unless explicit approval is required.
- A task is done only when results are verifiable: changed files, validations run, deployment status (if requested), and rollback steps documented in ROADMAP.md.
- Prefer deterministic actions over speculative iterations; keep changes minimal and reversible.

## Code Documentation Standard (Mandatory)
- Every public function, class, and module MUST have a docstring/JSDoc/XMLDoc in the language's canonical format:
  - Python: Google-style or NumPy-style docstrings (Args, Returns, Raises, Example sections).
  - TypeScript/JavaScript: JSDoc with `@param`, `@returns`, `@throws`, `@example`.
  - C#: XML summary with `<summary>`, `<param>`, `<returns>`, `<exception>`.
  - Shell scripts: header block with Purpose, Usage, Arguments, Exit codes.
- When modifying a function, update its docstring to reflect the new behavior.
- New modules must include a module-level docstring describing purpose, dependencies, and usage example.
- Run `pydoc`, `typedoc`, or equivalent after doc changes to verify output is valid.

## Secret Management Protocol (Mandatory)
- Never hardcode secrets, tokens, or credentials in any file, script, log, or commit.
- Use environment variables or a secrets manager (Vault, AWS Secrets Manager, k8s Secret) for all sensitive values.
- **ECR / Docker Registry tokens rotate every 12 hours.** Before any Docker pull/push or k8s image operation:
  1. Refresh the token: `aws ecr get-login-password --region <region>`.
  2. Recreate the k8s pull secret: `kubectl delete secret <name> --ignore-not-found && kubectl create secret docker-registry <name> ...`.
  3. Restart affected pods if already in `ImagePullBackOff`.
- Document token rotation commands in `INFRASTRUCTURE.md` under the **Operations** section.
- If a secret is accidentally committed, rotate it immediately and document the incident.

## Terminal Sessions (Mandatory for Critical Operations)
- **Always use a named tmux session** for long-running, deployment, or destructive operations:
  ```bash
  # Start / reattach
  tmux new-session -A -s <task-name>
  # Detach safely: Ctrl+B D
  # Reattach: tmux attach -t <task-name>
  ```
- Naming convention: `deploy-<service>`, `build-<tag>`, `k3s-ops`, `ecr-refresh`.
- This prevents work loss on SSH disconnection and provides a recoverable audit trail.
- On Windows (PowerShell): use Windows Terminal tabs or `Start-Process` with logging to a file as equivalent.
