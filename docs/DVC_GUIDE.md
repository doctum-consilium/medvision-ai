# DVC Guide

This guide is the practical reference for using DVC in MedVision AI.

## 1. Why DVC is central in this repository

DVC is used to make data and training pipelines reproducible across machines and over time.

In this project:

- Git tracks code, configs, and documentation.
- DVC tracks stage dependencies, data/model outputs, and metrics files.
- MLflow tracks run behavior and results.

A simple mental model:

- DVC answers which pipeline produced an artifact.
- MLflow answers how that run performed.

## 2. Repository stage graph

The stage graph is defined in dvc.yaml.

Current stages:

- download_chest_xray
- train_chest_xray
- download_brain_mri
- train_brain_mri
- download_brain_tumor_segmentation
- prepare_brain_tumor_segmentation
- train_brain_tumor_segmentation
- download_chest_xray_segmentation
- prepare_chest_xray_segmentation
- train_chest_xray_segmentation

## 3. Pre-flight checks

Before running DVC commands:

1. Activate your Python virtual environment (uv or legacy venv).
2. Ensure project dependencies are installed.
3. Confirm Kaggle token is configured if download stages are needed.

### 3.1 Do you need dvc init?

Decision rule:

- If the repository already contains a .dvc directory, do not run dvc init again.
- If .dvc is missing, run dvc init once at repository root.

For this repository checkout, dvc.yaml exists but .dvc may be missing on some machines.
In that case, initialize DVC once:

```bash
dvc init
```

Then continue with dvc status and dvc repro.

If dvc init reports that DVC is already initialized, keep existing configuration and do not reinitialize.

## 4. Most useful day-to-day commands

Check what is out of date:

```bash
dvc status
```

Reproduce all outdated stages:

```bash
dvc repro
```

Reproduce one specific stage:

```bash
dvc repro train_brain_tumor_segmentation
```

Run experiments without changing baseline outputs:

```bash
dvc exp run
dvc exp show
```

## 5. Recommended workflows

### 5.1 Quick local smoke workflow

Use this when validating environment setup.

1. Run one download stage.
2. Run one short training stage.
3. Check expected artifacts and metrics exist.

Example:

```bash
dvc repro download_chest_xray
dvc repro train_chest_xray
```

### 5.2 Segmentation workflow

Use this sequence for segmentation tracks.

1. Download segmentation dataset.
2. Prepare segmentation manifest.
3. Train segmentation model.

Example for brain track:

```bash
dvc repro download_brain_tumor_segmentation
dvc repro prepare_brain_tumor_segmentation
dvc repro train_brain_tumor_segmentation
```

### 5.3 Iteration workflow for hyperparameters

1. Edit params.yaml or relevant config files.
2. Run dvc exp run.
3. Compare results with dvc exp show.
4. Keep only the experiments worth promoting.

## 6. Outputs and contracts to verify

After stage execution, verify these contracts:

- Model files under artifacts/models.
- Report and metrics files under artifacts/reports.
- Segmentation overlays under artifacts/overlays when applicable.
- Processed manifests under data/processed for segmentation tracks.

If outputs are missing, inspect the corresponding stage in dvc.yaml first.

## 7. DVC remote usage

For sharing large artifacts across environments, configure a DVC remote.

Typical commands:

```bash
dvc remote add -d storage <remote-url>
dvc push
dvc pull
```

This repository includes Terraform assets for AWS S3 remote provisioning under terraform/aws_dvc_remote.

## 8. Common issues and fixes

### 8.1 dvc init fails

Symptom:

- dvc init returns an error.

Fix:

1. Check whether .dvc directory exists.
2. If it exists, do not reinitialize and continue with dvc status and dvc repro.
3. If it does not exist, verify you are at repository root and retry dvc init.

### 8.2 Stage runs but model does not appear in API/UI

Symptom:

- Training completed, but model is not visible in registry endpoints or Streamlit.

Fix:

1. Verify model artifact filename.
2. Verify report/metrics outputs exist.
3. Verify registry candidate names in src/registry/model_registry.py.

### 8.3 Segmentation metrics are unexpectedly poor

Symptom:

- Overlay quality is low or metrics collapse.

Fix:

1. Inspect generated manifest rows.
2. Validate image and mask pairing manually on sampled entries.
3. Re-run prepare stage and short training.

### 8.4 dvc repro reruns too much or too little

Symptom:

- Unexpected stage invalidation behavior.

Fix:

1. Run dvc status to inspect dependency drift.
2. Check recent edits in configs and params.
3. Check whether outputs were manually modified.

### 8.5 Import error on dvc init (_DIR_MARK)

Symptom:

- cannot import name '_DIR_MARK' from pathspec.patterns.gitwildmatch

Cause:

- pathspec 1.0+ installed with a DVC/scmrepo combination expecting pre-1.0 internals.

Fix:

```bash
uv pip install "pathspec<1.0"
# or, with legacy pip:
# pip install "pathspec<1.0"
```

Then retry:

```bash
dvc init
```

If the next message is ".dvc exists", DVC is already initialized and you can continue with dvc status / dvc repro.

## 9. Team conventions for DVC changes

When a PR changes pipeline behavior:

1. Update dvc.yaml explicitly.
2. Explain stage impact in the PR description.
3. Mention any changed outputs or metrics files.
4. Update docs if stage contracts changed.

## 11. Ajouter un modèle entraîné dans DVC (workflow standard)

Après avoir entraîné un modèle localement :

```bash
# 1. Enregistrer l'état actuel des sorties de stage dans DVC
dvc commit -f

# 2. Envoyer vers S3
dvc push

# 3. Valider que la synchro est OK
dvc status
```

Si tu as entraîné avec un backbone non encore dans dvc.yaml (ex. `densenet121`), ajoute d'abord le fichier produit :
```bash
dvc add artifacts/models/densenet121_model.keras
git add artifacts/models/densenet121_model.keras.dvc .gitignore
dvc push
```

## 12. Pull des artefacts dans K3s (entrypoint automatique)

Chaque pod medvision (API et Streamlit) exécute `docker/entrypoint.sh` au démarrage.
Ce script fait automatiquement :
```bash
dvc pull artifacts/models/ artifacts/reports/
```

Les credentials AWS sont injectés via le Secret K8s `medvision-aws-creds`. Voir `scripts/redeploy-k3s.sh` § 4b.

**Vérifier que le pull a fonctionné dans un pod :**
```bash
kubectl exec -n medvision deploy/medvision-streamlit -- ls /app/artifacts/models/
kubectl exec -n medvision deploy/medvision-streamlit -- cat /tmp/dvc-pull.log
```

## 10. Quick command cheat sheet

```bash
# Inspect pipeline state
dvc status

# Run everything that is out of date
dvc repro

# Run a specific stage
dvc repro train_brain_mri

# Run and compare experiments
dvc exp run
dvc exp show

# Sync artifacts with remote
dvc push
dvc pull
```
