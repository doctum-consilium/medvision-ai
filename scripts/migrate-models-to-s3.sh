#!/usr/bin/env bash
# Purpose  : Crée le bucket S3 DVC (Terraform) et y pousse les modèles .keras depuis l'image ECR.
# Usage    : ./scripts/migrate-models-to-s3.sh
# Exit codes:
#   0  Migration réussie
#   1  Erreur (voir message)
#
# Ce script fait exactement ceci :
#   1. Vérifie que AWS CLI est authentifié
#   2. Crée le bucket S3 via Terraform (idempotent — ne recrée pas si existant)
#   3. Extrait les modèles depuis l'image ECR vers un dossier local temporaire
#   4. Configure DVC avec le bucket S3 comme remote
#   5. Fait dvc add + dvc push pour envoyer les modèles sur S3
#   6. Commit le .dvc file dans git (optionnel)
#
# Après cette migration, les modèles sont disponibles sur S3 et toute machine
# qui a les credentials AWS peut faire : dvc pull
set -euo pipefail

REGISTRY="113301685315.dkr.ecr.eu-west-3.amazonaws.com/platform"
REGION="eu-west-3"
ECR_IMAGE_TAG="${1:-2026-04-16}"
BUCKET_NAME="platform-medvision-dvc-artifacts"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR=$(mktemp -d)

log() { echo "[$(date +%H:%M:%S)] $*"; }
die() { echo "[ERREUR] $*" >&2; exit 1; }

cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

# ─── 1. Vérifications ───────────────────────────────────────────────────────
log "Vérification AWS credentials…"
aws sts get-caller-identity --query Account --output text >/dev/null 2>&1 \
  || die "AWS session expirée. Lancez : aws sso login (ou aws login)"

command -v terraform >/dev/null 2>&1 || die "Terraform non installé. Voir : https://developer.hashicorp.com/terraform/install"
command -v dvc >/dev/null 2>&1 || die "DVC non installé. Lancez : pip install dvc[s3]"
command -v docker >/dev/null 2>&1 || die "Docker non installé."

# ─── 2. Terraform — création du bucket S3 ────────────────────────────────────
log "Terraform init + apply (bucket S3 DVC)…"
TF_DIR="${REPO_ROOT}/terraform/aws_dvc_remote"
cd "$TF_DIR"
terraform init -upgrade -input=false
terraform apply -auto-approve -input=false
cd "$REPO_ROOT"
log "Bucket S3 créé/vérifié : s3://${BUCKET_NAME}"

# ─── 3. Extraction des modèles depuis l'image ECR ────────────────────────────
log "Refresh token ECR…"
ECR_TOKEN=$(aws ecr get-login-password --region "$REGION")
echo "$ECR_TOKEN" | docker login --username AWS --password-stdin "${REGISTRY%/platform}"

log "Pull de l'image ECR ${REGISTRY}/medvision-ai:${ECR_IMAGE_TAG}…"
docker pull "${REGISTRY}/medvision-ai:${ECR_IMAGE_TAG}"

log "Extraction des modèles vers ${TMP_DIR}/models …"
docker run --rm \
  -v "${TMP_DIR}:/export" \
  "${REGISTRY}/medvision-ai:${ECR_IMAGE_TAG}" \
  sh -c "cp -r /app/artifacts/models /export/ && echo 'Extraction OK'"

if [[ ! -d "${TMP_DIR}/models" ]] || [[ -z "$(ls -A "${TMP_DIR}/models")" ]]; then
  die "Aucun modèle trouvé dans /app/artifacts/models de l'image ECR."
fi

log "Modèles extraits :"
ls "${TMP_DIR}/models/"

# ─── 4. Copier les modèles dans le repo local ────────────────────────────────
mkdir -p "${REPO_ROOT}/artifacts/models"
cp -r "${TMP_DIR}/models/." "${REPO_ROOT}/artifacts/models/"
log "Modèles copiés dans artifacts/models/"

# ─── 5. Configuration DVC remote S3 ─────────────────────────────────────────
cd "$REPO_ROOT"
log "Configuration DVC remote S3…"
dvc remote add -d s3remote "s3://${BUCKET_NAME}/models" 2>/dev/null \
  || dvc remote modify s3remote url "s3://${BUCKET_NAME}/models"
dvc remote modify s3remote region "$REGION"

# ─── 6. DVC add + push ───────────────────────────────────────────────────────
log "dvc add artifacts/models/ …"
dvc add artifacts/models/

log "dvc push vers s3://${BUCKET_NAME}/models …"
dvc push

log ""
log "=== MIGRATION TERMINÉE ==="
log "Modèles disponibles sur : s3://${BUCKET_NAME}/models"
log ""
log "Pour récupérer les modèles sur une autre machine :"
log "  dvc remote add -d s3remote s3://${BUCKET_NAME}/models"
log "  dvc remote modify s3remote region ${REGION}"
log "  dvc pull"
log ""
log "Pour committer le fichier .dvc dans git :"
log "  git add artifacts/models.dvc .dvc/config"
log "  git commit -m 'feat(dvc): ajoute remote S3 pour les modèles medvision'"
