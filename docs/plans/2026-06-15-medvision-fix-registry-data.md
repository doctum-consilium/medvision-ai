# Plan — MedVision AI : corriger l'app vide (modèles + données)

**Statut : livré 2026-06-15**

## Context

L'app Streamlit affichait "No trained models found" et "No local image samples were found" pour tous les problèmes. Deux causes racines :

1. **Désynchronisation registry / fichiers réels** : `optimized_model.keras` et `brain_mri_optimized.keras` sont les sorties officielles du pipeline DVC (stages `train_chest_xray` et `train_brain_mri`), mais le registry (`src/registry/model_registry.py`) avait été mis à jour après pour le plan multi-backbones (MLflow Experiment Plan 2026-04-07) sans inclure les anciennes clés `"optimized"`.

2. **Données jamais présentes localement** : `data/raw/` ne contenait que des `.gitkeep`. Les datasets Kaggle sont trackés par DVC mais jamais téléchargés en local.

## Architecture (invariants)

- **Registry = source de vérité** pour l'API FastAPI et Streamlit simultanément.
- **DVC = pipeline reproductible** : ne pas casser `dvc repro`.
- **`artifacts/reports/`** : métriques JSON lus par l'onglet "Model Compare".

## Surface des changements

| Fichier | Action |
|---------|--------|
| `src/registry/model_registry.py` | Ajout de `"optimized"` dans `chest_xray` et `brain_mri` |
| `artifacts/reports/optimized_metrics.json` | Stub métriques (en attente de `dvc repro`) |
| `artifacts/reports/brain_mri_metrics.json` | Stub métriques (en attente de `dvc repro`) |
| `scripts/generate_sample_images.py` | Nouveau script : génère des PNG synthétiques 224×224 |
| `data/raw/chest_xray/test/{NORMAL,PNEUMONIA}/` | 3 PNG synthétiques par classe |
| `data/raw/brain_tumor_mri/Testing/{4 classes}/` | 3 PNG synthétiques par classe |
| `data/processed/brain_tumor_segmentation/manifest.csv` | Manifest minimal (12 lignes) |

## Vérification

```bash
conda run -n GPUMachineLearning streamlit run streamlit_app.py
```

- Onglet **Registry** : chest_xray=2 modèles, brain_mri=1, brain_tumor_seg=1.
- Onglet **Prediction Studio** : images disponibles pour chest_xray et brain_mri.
- Onglet **Model Compare** : métriques stubs visibles (toutes à `null`).

Pour obtenir les vraies métriques :
```bash
bash scripts/download_dataset.sh   # requiert ~/.kaggle/kaggle.json
dvc repro train_chest_xray train_brain_mri
```

## Hors scope

- Entraînement des modèles multi-backbones (densenet121, efficientnetv2b0, etc.)
- PyTorch inference path (`brain_mri_2d_demo.pt`)
- Déploiement K3s / sync PVC
