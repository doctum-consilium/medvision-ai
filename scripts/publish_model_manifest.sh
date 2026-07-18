#!/usr/bin/env bash
# Purpose  : Publier le dvc.lock frais dans S3 après un `dvc push`, pour que
#            le watcher de l'API prod détecte et tire les nouveaux modèles
#            SANS rebuild d'image ni redéploiement.
#
#            Chaîne complète : entraînement local → convert_to_onnx →
#            dvc push → CE SCRIPT → (≤ 60 s plus tard) le pod fait dvc pull
#            → l'UI Angular reçoit l'événement SSE « models_updated ».
#
# Usage    : bash scripts/publish_model_manifest.sh
#            (à lancer depuis la racine du repo, après chaque dvc push)
# Arguments: aucun.
# Exit codes: 0 = manifeste publié ; 1 = prérequis manquant ou upload échoué.
set -euo pipefail

MANIFEST_S3_URI="${MEDVISION_MANIFEST_S3_URI:-s3://platform-medvision-dvc-artifacts/models/.meta/dvc.lock}"

if [ ! -f dvc.lock ]; then
  echo "[ERREUR] dvc.lock introuvable — lancer depuis la racine du repo." >&2
  exit 1
fi

if ! aws sts get-caller-identity >/dev/null 2>&1; then
  echo "[ERREUR] Session AWS expirée — configurer les credentials (aws configure / sso login)." >&2
  exit 1
fi

echo "Publication du manifeste DVC → ${MANIFEST_S3_URI}"
aws s3 cp dvc.lock "${MANIFEST_S3_URI}"
echo "OK — le watcher de l'API le détectera au prochain cycle (≤ 60 s)."
