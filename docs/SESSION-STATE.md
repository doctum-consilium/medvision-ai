# SESSION-STATE — MedVision AI

Point de reprise canonique. Mis à jour à chaque session significative.
**Lire ce fichier en premier, puis `ROADMAP.md`, puis `CLAUDE.md`.**

---

## État au 2026-06-15 (fin de session)

### Image ECR active

```
113301685315.dkr.ecr.eu-west-3.amazonaws.com/platform/medvision-ai:2026-06-15f
```

Contient : code uniquement (modèles exclus via `.dockerignore`). Les modèles sont tirés depuis S3 via DVC au démarrage du pod.

### Pods K3s (namespace `medvision`)

| Pod | État | Notes |
|---|---|---|
| `medvision-api` | Running | Port 8000 — FastAPI |
| `medvision-streamlit` | Running | Port 8501 — UI |
| `medvision-mlflow` | Running | Port 5000 — tracking (accès interne) |

### URLs

| Service | URL |
|---|---|
| API | https://api.medvision.doctumconsilium.com |
| Streamlit | https://app.medvision.doctumconsilium.com |
| MLflow | `kubectl port-forward -n medvision svc/medvision-mlflow 5000:5000` |

### Modèles disponibles (tirés depuis S3 via DVC)

| Fichier | Taille | État |
|---|---|---|
| `optimized_model.keras` | 12 Mo | Stub (à ré-entraîner) |
| `brain_mri_optimized.keras` | 17 Mo | Stub (à ré-entraîner) |
| `brain_tumor_segmentation_unet.keras` | 90 Mo | Stub (à ré-entraîner) |

### Données dans les PVCs

| PVC | Contenu actuel |
|---|---|
| `medvision-raw-data` (worker-ovh-094) | chest_xray/ (samples) + brain_tumor_mri/ (7 212 images Kaggle) + brain_tumor_segmentation/images/ (12 PNGs synthétiques) |
| `medvision-mlflow-store` (worker-ovh-233) | mlflow.db (historique entraînements) |
| `medvision-model-artifacts` (worker-ovh-233) | Vide — modèles via DVC/S3 |

---

## Architecture (résumé)

```
[Local Inspiron Ubuntu]
  conda activate GPUMachineLearning
  dvc repro       → entraîne les modèles
  dvc push        → pousse vers s3://platform-medvision-dvc-artifacts/

[ECR]
  docker build (code only, artifacts/ exclu)
  docker push → 113301685315.dkr.ecr.eu-west-3.amazonaws.com/platform/medvision-ai:TAG

[K3s pod au démarrage]
  docker/entrypoint.sh:
    git init -q   (DVC requiert un repo git)
    dvc pull train_chest_xray train_brain_mri train_brain_tumor_segmentation
    → artifacts/models/ peuplé depuis S3
  streamlit run streamlit_app.py
```

---

## Prochaines étapes prioritaires

1. **Entraîner de vrais modèles** (la plus importante)
   ```bash
   conda activate GPUMachineLearning
   bash scripts/download_dataset.sh   # si données pas encore là
   dvc repro
   dvc push
   ```

2. **Rebuild ECR avec les vrais modèles** → redeploy (voir `ONBOARDING_perso_inspiron_ubuntu.md`)

3. **Valider les prédictions** : ouvrir l'app, tester predict sur brain_mri et chest_xray

---

## Règles critiques

- **`keras==3.3.3`** obligatoire dans `requirements.txt` (modèles sauvés avec 3.3.3, pip installe 3.12.x sans pin → AttributeError)
- **`dvc pull <stages>`** (jamais `dvc pull` seul — conflit avec data/raw/ non pushée)
- **`git` dans le Dockerfile** (`apt-get install git` — `python:3.10-slim` ne l'inclut pas)
- **PVC `medvision-raw-data`** : ajouter des images via `kubectl cp`, pas rebuild
- **MLflow** : `--backend-store-uri=sqlite:////mlflow/mlflow.db` (4 slashes pour chemin absolu)
