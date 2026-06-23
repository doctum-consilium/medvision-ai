#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${ROOT_DIR}" ]]; then
  echo "[guardrails] Not inside a git repository."
  exit 1
fi

CONFIG_FILE="${ROOT_DIR}/.guardrails/config.env"
if [[ ! -f "${CONFIG_FILE}" ]]; then
  echo "[guardrails] Missing config file: .guardrails/config.env"
  echo "[guardrails] Run guardrails installer first."
  exit 1
fi

# shellcheck source=/dev/null
source "${CONFIG_FILE}"

REQUIRED_DOCS="${REQUIRED_DOCS:-README.md}"
REQUIRE_DOC_UPDATE_ON_CODE_CHANGE="${REQUIRE_DOC_UPDATE_ON_CODE_CHANGE:-1}"
TEST_CMD="${TEST_CMD:-}"
LINT_CMD="${LINT_CMD:-}"
BUILD_CMD="${BUILD_CMD:-}"

mapfile -t STAGED_FILES < <(git diff --cached --name-only)
if [[ ${#STAGED_FILES[@]} -eq 0 ]]; then
  echo "[guardrails] No staged files. Nothing to validate."
  exit 0
fi

for doc in ${REQUIRED_DOCS}; do
  if [[ ! -f "${ROOT_DIR}/${doc}" ]]; then
    echo "[guardrails] Missing required documentation file: ${doc}"
    exit 1
  fi
done

if [[ "${REQUIRE_DOC_UPDATE_ON_CODE_CHANGE}" == "1" ]]; then
  CODE_CHANGED=0
  DOC_CHANGED=0
  for file in "${STAGED_FILES[@]}"; do
    if [[ "${file}" =~ ^docs/|\.md$ ]]; then
      DOC_CHANGED=1
    fi
    if [[ "${file}" =~ \.(py|js|ts|tsx|jsx|go|rs|java|cs|cpp|c|h|hpp|rb|php|sh|yml|yaml)$ ]]; then
      CODE_CHANGED=1
    fi
  done

  if [[ "${CODE_CHANGED}" -eq 1 && "${DOC_CHANGED}" -eq 0 ]]; then
    echo "[guardrails] Code changed but no docs update detected."
    echo "[guardrails] Update docs/ or at least one .md file in this commit."
    exit 1
  fi
fi

if [[ -n "${LINT_CMD}" ]]; then
  echo "[guardrails] Running lint command..."
  bash -lc "${LINT_CMD}"
fi

if [[ -n "${TEST_CMD}" ]]; then
  echo "[guardrails] Running test command..."
  bash -lc "${TEST_CMD}"
fi

if [[ -n "${BUILD_CMD}" ]]; then
  echo "[guardrails] Running build command..."
  bash -lc "${BUILD_CMD}"
fi

echo "[guardrails] Validation passed."
