# Plan — Pipeline DVC+S3 + entraînement local + ECR

**Statut : livré 2026-06-15**

## Context

L'app K3s (`app.medvision.doctumconsilium.com`) était vide : pas de modèles visibles, pas d'images. Les modèles existaient localement mais n'étaient pas référencés dans le registry (migration multi-backbones avait laissé les anciens noms orphelins). Les données n'avaient jamais été téléchargées. Et il n'existait pas de pipeline reproductible pour entraîner de nouveaux modèles et les déployer.

## Architecture cible

```
[local] download Kaggle → train → dvc push → S3
[ECR]   git push → docker build (code only) → push ECR
[K3s]   pod démarre → entrypoint: dvc pull (S3) → modèles + rapports disponibles
```

## Surface des changements

| Fichier | Action |
|---------|--------|
| `src/registry/model_registry.py` | +`optimized` dans chest_xray et brain_mri |
| `.dockerignore` | +`artifacts/` (modèles plus baked) |
| `docker/entrypoint.sh` | Nouveau — dvc pull au démarrage |
| `docker/Dockerfile` | +ENTRYPOINT + CMD |
| `scripts/redeploy-k3s.sh` | +Secret AWS medvision-aws-creds + envFrom |
| `dvc.yaml` | Suppression deps `src/models/` et `src/segmentation/models/unet.py` |
| `dvc.lock` | Généré par `dvc commit -f` |
| `artifacts/reports/` | Stubs créés pour tous les outputs de stage |
| `docs/LOCAL_TRAINING_GUIDE.md` | Nouveau — guide complet niveau débutant |
| `docs/DVC_GUIDE.md` | +sections 11 et 12 |
| `ONBOARDING.md` | +bloc "Entraîner ton premier modèle" |
| `ROADMAP.md` | +Phase 2 |

## Vérification

```bash
# DVC : modèles en S3
dvc status   # "up to date" pour les 3 stages entraînés

# Docker local
docker build -f docker/Dockerfile -t medvision-test .
docker run -e AWS_ACCESS_KEY_ID=... -e AWS_SECRET_ACCESS_KEY=... \
           -e AWS_DEFAULT_REGION=eu-west-3 \
           -p 8501:8501 medvision-test
# → "[entrypoint] Artefacts récupérés depuis S3"
# → streamlit accessible sur localhost:8501 avec modèles visibles

# K3s
kubectl logs -n medvision deploy/medvision-streamlit | grep entrypoint
kubectl exec -n medvision deploy/medvision-streamlit -- ls /app/artifacts/models/
```

## Prochaines étapes

1. Télécharger les données Kaggle : `bash scripts/download_dataset.sh`
2. Lancer entraînement complet : `dvc repro`
3. `dvc push` → métriques réelles en S3
4. Build + push ECR : `docker build ... && docker push ...`
5. Redéploiement : `bash scripts/redeploy-k3s.sh 2026-06-15a`
