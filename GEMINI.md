# GEMINI.md

This file defines execution rules for Google's AI assistants and IDEs in `medvision-ai`:

## 🤝 Handoff 2026-06-15 — Architecture DVC+S3 + fixes déploiement (DÉPLOYÉ)

> **Image prod : `medvision-ai:2026-06-15f`** — namespace `medvision`, k3s OVH.
>
> **À lire en premier** : `CLAUDE.md` (handoff complet) + `ROADMAP.md` + `ONBOARDING_perso_inspiron_ubuntu.md`.
>
> **Règles critiques** :
> - `keras==3.3.3` obligatoire dans requirements.txt (sinon AttributeError au chargement des modèles)
> - `dvc pull train_chest_xray train_brain_mri train_brain_tumor_segmentation` (stages, pas `dvc pull` seul)
> - Modèles dans S3, pas dans l'image Docker (`artifacts/` exclu de `.dockerignore`)
> - Données dataset dans PVC `medvision-raw-data` → `kubectl cp` pour ajouter, pas rebuild
> - `git` doit être dans le Dockerfile (`apt-get install git`) — `python:3.10-slim` ne l'inclut pas


- **Gemini CLI** (`gemini` command)
- **Gemini Assistant** (VS Code extension)
- **Antigravity IDE** (Google AI development platform)

## Mandatory Sources of Truth
- `README.md` (MANDATORY: Must exist, create if missing)
- `INFRASTRUCTURE.md` (MANDATORY: Must exist, create if missing)
- `SKILLS.md` (if present)
- `ROADMAP.md` (MANDATORY: Must exist, create if missing)
- `.github/copilot-instructions.md`

## Project Context
medvision-ai — [Add project description here]

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
- On macOS: same tmux convention applies.

## Environment Policy
- Use a single standard environment per repo when possible.
- Parallel environments allowed only if technically unavoidable — document reason, limits, naming, activation.

## Platform Compatibility
- Critical automation scripts must support Ubuntu (Bash), Windows (PowerShell), and macOS (zsh/bash).
- Any exception must be documented with an operational alternative.

## Gemini CLI Configuration
```bash
# Add repository context to Gemini CLI
gemini context add . --name medvision-ai
gemini context add README.md --priority high
gemini context add INFRASTRUCTURE.md --priority high
gemini context add ROADMAP.md --priority high

# Run tasks with Gemini CLI
gemini run "Explain the project architecture"
gemini run "Generate documentation"
```

## Gemini Assistant (VS Code Extension)
- **Extension**: `google.gemini-assistant` (install from VS Code Marketplace)
- **Context**: Automatically reads `README.md`, `ROADMAP.md`, `.github/copilot-instructions.md`, and this file
- **Slash Commands**: `/check`, `/explain`, `/improve`, `/generate`, `/review`, `/test`
- **Triggering**: Highlight code, press `Cmd+.` (macOS) or `Ctrl+.` (Linux/Windows) to open AI commands

## Antigravity IDE Integration
Start the repository in Antigravity IDE:
```bash
antigravity /path/to/medvision-ai
```

Antigravity will automatically:
1. Load all folders and context from this repository
2. Index documentation (`README.md`, `INFRASTRUCTURE.md`, `ROADMAP.md`)
3. Enable built-in AI copilot via `Cmd+K` (macOS) or `Ctrl+K` (Linux/Windows)

### Common Antigravity AI Queries
- "Explain the README"
- "Generate unit tests for this module"
- "Review this code change"
- "Document this function"
- "Fix linting errors"

## Multi-AI Compatibility
This repository is compatible with all major AI development tools:
- **Claude Code** (via `CLAUDE.md`)
- **GitHub Copilot** (via `.github/copilot-instructions.md`)
- **Gemini CLI** (via `gemini context add`)
- **Gemini Assistant** (VS Code extension, this file)
- **Antigravity IDE** (native support)

All instructions follow vendor-neutral standards focused on reproducible, high-quality outcomes.
