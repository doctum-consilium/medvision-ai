#!/usr/bin/env bash
# Purpose  : Rejouer EN LOCAL tous les checks de la CI GitHub Actions
#            (.github/workflows/ci.yml) AVANT de pousser, pour ne plus
#            découvrir un échec rouge sur la PR.
#
# Usage    : bash scripts/ci_local.sh
#            (appelé automatiquement par .githooks/pre-push)
#
# Checks   : 1) Ruff (src/ + tests/)
#            2) Pytest smoke (sans TF — rapide)
#            3) shellcheck -x (tous les .sh du projet)
#
# Notes    : Les tests TF (test_api.py) ne sont PAS joués ici car ils
#            nécessitent TF + 30 s de chargement. Ils tournent sur GitHub
#            Actions (job test-tf). Pour les jouer localement :
#            conda activate GPUMachineLearning && pytest tests/ -v
#
# Arguments : aucun.
# Exit codes: 0 = tout vert ; 1 = au moins un check a échoué.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
cd "$REPO_ROOT" || exit 1

# shellcheck source=.githooks/_lib.sh
. "$REPO_ROOT/.githooks/_lib.sh"

RUFF="$(hook_ruff)"
PY="$(hook_python)"
SHCHECK=""
hook_has shellcheck && SHCHECK="shellcheck"

# ── 1) Ruff ───────────────────────────────────────────────────────────────
hook_title "Ruff (src/ tests/)"
if [ -z "$RUFF" ]; then
  hook_fail "ruff absent — pip install ruff (la CI le lancera aussi)"
else
  if "$RUFF" check src/ tests/; then
    hook_ok "code propre"
  else
    hook_fail "problèmes ruff (ruff check --fix src/ tests/)"
  fi
fi

# ── 2) Tests smoke (sans TF) + couverture XML ─────────────────────────────
hook_title "Pytest smoke (sans TF)"
if [ -z "$PY" ]; then
  hook_fail "aucun python avec pytest — pip install pytest dans ton venv"
else
  if "$PY" -m pytest tests/smoke/ -q --tb=short \
      --cov=src --cov-report=xml:coverage-smoke.xml; then
    hook_ok "smoke tests verts"
  else
    hook_fail "smoke tests échoués"
  fi
fi

# ── 2bis) Couverture du diff ≥ 80 % (MIROIR du gate CI) ────────────────────
# C'est le gate qui échouait sans être joué en local. BLOQUANT : on récupère
# origin/main au besoin ; l'absence d'outil/branche fait échouer (pas de skip).
hook_title "Couverture du diff (diff-cover ≥ 80 % vs origin/main)"
if [ -z "$PY" ]; then
  hook_fail "python absent (voir ci-dessus)"
elif ! "$PY" -c "import diff_cover" >/dev/null 2>&1; then
  hook_fail "diff-cover absent — pip install diff-cover (la CI l'exige)"
elif [ ! -f coverage-smoke.xml ]; then
  hook_fail "coverage-smoke.xml absent (pytest a échoué avant)"
else
  git rev-parse --verify --quiet origin/main >/dev/null 2>&1 || git fetch -q origin main 2>/dev/null || true
  if ! git rev-parse --verify --quiet origin/main >/dev/null 2>&1; then
    hook_fail "origin/main introuvable même après fetch (git fetch origin main)"
  # --exclude '*/models/*' : src/models et src/segmentation/models importent TensorFlow
  # au niveau module → inatteignables par le smoke (sans TF), donc comptés à 0 % par
  # --cov=src. Leur couverture est assurée par le job test-tf (tests/test_model_builders.py).
  # On les sort de CE gate sans rabaisser le seuil. Le motif '*/models/*' est requis car
  # diff-cover préfixe les chemins. Doit rester aligné avec .github/workflows/ci.yml.
  # --exclude '*/segmentation/*' '*/training/*' : même logique — tous les modules de
  # src/segmentation et src/training importent TensorFlow au niveau module (0 % sans TF) ;
  # leur couverture est exigée par le gate diff-cover du job test-tf (sans exclusion).
  # --ignore-staged --ignore-unstaged : ne juger que le code commité (origin/main...HEAD),
  # pour ne pas ramasser les différences EOL du working tree (.gitattributes eol=lf vs CRLF).
  elif "$PY" -m diff_cover.diff_cover_tool coverage-smoke.xml \
      --compare-branch=origin/main --fail-under=80 \
      --exclude '*/models/*' '*/segmentation/*' '*/training/*' \
      --ignore-staged --ignore-unstaged; then
    hook_ok "lignes du diff couvertes ≥ 80 %"
  else
    hook_fail "des lignes ajoutées par la PR ne sont pas couvertes (< 80 %)"
  fi
fi

# ── 3) shellcheck — scripts maintenus (pas la dette legacy Windows) ───────
hook_title "shellcheck (hooks + scripts maintenus)"
# On ne check QUE les scripts sous notre contrôle actuel, pas la dette legacy
# (scripts deploy/*.sh, scripts/*_segmentation_*.sh créés sous Windows avec CRLF).
MAINTAINED_SCRIPTS=(
  ".githooks/_lib.sh"
  ".githooks/pre-commit"
  ".githooks/pre-push"
  "scripts/ci_local.sh"
  "scripts/build-and-push-web.sh"
  "docker/entrypoint.sh"
)
if [ -z "$SHCHECK" ]; then
  hook_skip "shellcheck absent (sudo apt install shellcheck)"
else
  FAIL=0
  for f in "${MAINTAINED_SCRIPTS[@]}"; do
    if [ -f "$REPO_ROOT/$f" ]; then
      shellcheck -x "$REPO_ROOT/$f" || FAIL=1
    fi
  done
  if [ "$FAIL" -eq 0 ]; then
    hook_ok "${#MAINTAINED_SCRIPTS[@]} scripts maintenus propres"
  else
    hook_fail "shellcheck a trouvé des problèmes dans les scripts maintenus"
  fi
fi

# ── 4) Guardrails — MIROIR du job CI « validate » (guardrails.yml) ─────────
# La CI exige .guardrails/config.env présent ET bin/validate_guardrails.sh
# exécutable (test -x). Un bit +x perdu (fichier recréé sous Windows/CRLF) ou
# un config.env oublié faisait échouer la CI sans qu'on le voie en local.
hook_title "Guardrails (assets + validateur)"
if [ ! -d .guardrails ]; then
  hook_skip "pas de .guardrails dans ce repo"
elif [ ! -f .guardrails/config.env ]; then
  hook_fail "guardrails : .guardrails/config.env manquant"
elif [ ! -x .guardrails/bin/validate_guardrails.sh ]; then
  hook_fail "guardrails : bin/validate_guardrails.sh non exécutable (git update-index --chmod=+x ...)"
elif ./.guardrails/bin/validate_guardrails.sh >/dev/null 2>&1; then
  hook_ok "guardrails validés"
else
  hook_fail "guardrails validator a échoué"
fi

# ── 5) Front Angular — MIROIR du job CI « build-and-test » (ci-front.yml) ─
# On ne lance rien si le front n'a pas bougé par rapport à origin/main : une
# session purement Python ne doit pas attendre une compilation Angular.
hook_title "Front Angular (build + tests)"
if [ ! -d "$REPO_ROOT/frontend" ]; then
  hook_skip "pas de front dans ce repo"
elif ! command -v npm >/dev/null 2>&1; then
  hook_skip "npm absent (installer Node 22)"
elif git diff --quiet origin/main -- frontend 2>/dev/null; then
  hook_skip "front inchangé vs origin/main"
elif [ ! -d "$REPO_ROOT/frontend/node_modules" ]; then
  hook_fail "front : dépendances absentes (cd frontend && npm ci)"
else
  FRONT_FAIL=0
  ( cd "$REPO_ROOT/frontend" && npm run build >/dev/null 2>&1 ) || FRONT_FAIL=1
  if [ "$FRONT_FAIL" -eq 0 ]; then
    # Karma a besoin d'un Chrome : sans lui on ne fait PAS échouer la CI
    # locale, on le signale — le job GitHub, lui, en a toujours un.
    FRONT_CHROME="${CHROME_BIN:-$(command -v google-chrome || command -v chromium || true)}"
    if [ -z "$FRONT_CHROME" ]; then
      hook_skip "front : build OK, tests sautés (aucun Chrome trouvé)"
    elif ( cd "$REPO_ROOT/frontend" \
        && CHROME_BIN="$FRONT_CHROME" npx ng test --watch=false --browsers=ChromeHeadless >/dev/null 2>&1 ); then
      hook_ok "front : build et tests verts"
    else
      hook_fail "front : des tests unitaires échouent (cd frontend && npx ng test --watch=false --browsers=ChromeHeadless)"
    fi
  else
    hook_fail "front : la compilation échoue (cd frontend && npm run build)"
  fi
fi

hook_summary
