# ONBOARDING — MedVision AI

Guide complet pour un débutant qui rejoint le projet : de zéro à la première prédiction fonctionnelle, puis au déploiement en production.

---

## Ce que fait l'application

MedVision AI est une plateforme d'aide au diagnostic médical par imagerie.
Elle prend en entrée une image médicale (radiographie, IRM cérébrale) et répond :
- quelle maladie est détectée (pneumonie, tumeur…)
- avec quelle probabilité
- optionnellement, un masque de segmentation (où se trouve la lésion dans l'image)

**Quatre tâches supportées** :
| Tâche | Données | Modèle |
|---|---|---|
| Classification pneumonie | Radiographies pulmonaires (Chest X-ray) | EfficientNetB0 binaire |
| Classification tumeur cérébrale | IRM cérébrales | ResNet50 multiclasse |
| Segmentation + classification cerveau | IRM | U-Net multitâche |
| Segmentation + classification poumon | Radiographies | U-Net multitâche |

---

## Architecture

```
[Image médicale]
       │
       ▼
  FastAPI (port 8000)                ← src/api/main.py
       │  /predict?model_name=...
       │  /registry
       │  /compare
       ▼
  Model Registry                     ← src/registry/model_registry.py
       │  charge le bon .keras
       ▼
  TensorFlow/Keras Inference
       │
       ▼
  JSON { predicted_class, confidence, probabilities }

  Streamlit (port 8501)              ← src/streamlit/app.py
       │  interface visuelle pour comparer les modèles
       ▼
  même Model Registry

  MLflow (port 5000)                 ← suivi des expériences d'entraînement
```

**Stack technique** :
- Python 3.10+, TensorFlow 2.x, FastAPI, Streamlit, MLflow, DVC
- PostgreSQL (via MLflow backend store)
- Docker / k3s (Kubernetes) pour le déploiement
- AWS ECR pour les images Docker
- AWS S3 (via DVC) pour les datasets et artefacts versionnés

---

## Lancer le projet en local (développement)

### Prérequis

```bash
# Python 3.10+, pip, git
python --version  # doit être >= 3.10

# Créer l'environnement virtuel
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
# ou .venv\Scripts\activate      # Windows

pip install -r requirements.txt
```

### Démarrer l'API

```bash
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
# → http://localhost:8000/docs  (Swagger UI)
# → http://localhost:8000/health
```

### Démarrer Streamlit

```bash
streamlit run src/streamlit/app.py
# → http://localhost:8501
```

### Démarrer MLflow (optionnel, pour suivre les entraînements)

```bash
mlflow server \
  --backend-store-uri sqlite:///mlflow.db \
  --default-artifact-root ./artifacts \
  --host 0.0.0.0 --port 5000
# → http://localhost:5000
```

---

## Où sont les modèles ?

### Architecture courante (depuis 2026-06-15) : S3 via DVC

Les modèles **ne sont plus dans l'image Docker**. Ils sont versionnés dans DVC et stockés sur S3. Au démarrage, chaque pod fait automatiquement `dvc pull` via `docker/entrypoint.sh`.

```
Image ECR (code only) : 113301685315.dkr.ecr.eu-west-3.amazonaws.com/platform/medvision-ai:2026-06-15f
Modèles en S3          : s3://platform-medvision-dvc-artifacts/
Pull automatique       : docker/entrypoint.sh → dvc pull au démarrage du pod
```

### Sur S3 via DVC

Un bucket S3 AWS est configuré comme remote DVC :
```
s3://platform-medvision-dvc-artifacts/models
Région : eu-west-3 (Paris)
Terraform : terraform/aws_dvc_remote/
```

Pour synchroniser les modèles vers S3 (une seule fois, puis `dvc push` après chaque entraînement) :
```bash
# Prérequis : aws sso login + terraform installé + dvc[s3] installé
./scripts/migrate-models-to-s3.sh

# Ce script fait : terraform apply → docker pull → extract → dvc add → dvc push
```

Pour récupérer les modèles depuis S3 sur une nouvelle machine :
```bash
pip install dvc[s3]
dvc remote add -d s3remote s3://platform-medvision-dvc-artifacts/models
dvc remote modify s3remote region eu-west-3
dvc pull
```

**En local (développement)** : après entraînement, les modèles apparaissent dans `artifacts/models/`.
Si vous clonez le repo sans entraîner ni faire `dvc pull`, ce dossier est vide — c'est normal.
L'API renvoie alors 404 sur `/predict` jusqu'à ce que vous ayez des modèles.

---

## Entraîner un modèle

### 1. Télécharger les données

```bash
# Radiographies (Chest X-ray — ~1 Go depuis Kaggle)
bash scripts/download_chest_xray_seg.sh

# IRM cérébrales
bash scripts/download_brain_mri_dataset.sh
```

### 2. Lancer l'entraînement

```bash
# Classification pneumonie (chest X-ray)
python -m src.training.train_classification \
  --config configs/chest_xray_classification.yaml

# Classification tumeur cérébrale
python -m src.training.train_classification \
  --config configs/brain_mri_classification.yaml

# Segmentation multitâche (chest)
python -m src.segmentation.train_multitask \
  --config configs/chest_xray_segmentation.yaml
```

MLflow enregistre automatiquement les métriques (accuracy, loss) et les modèles.
Ouvrez http://localhost:5000 pour les voir.

### 3. Déployer un nouveau modèle

Une fois satisfait des métriques :
```bash
# 1. Placer le .keras dans artifacts/models/ (MLflow le fait automatiquement)
# 2. Rebuild l'image Docker
docker build -t medvision-ai:YYYY-MM-DD -f docker/Dockerfile .

# 3. Push ECR (token valide 12h — rafraîchir si nécessaire)
aws ecr get-login-password --region eu-west-3 | docker login --username AWS \
  --password-stdin 113301685315.dkr.ecr.eu-west-3.amazonaws.com
docker tag medvision-ai:YYYY-MM-DD \
  113301685315.dkr.ecr.eu-west-3.amazonaws.com/platform/medvision-ai:YYYY-MM-DD
docker push 113301685315.dkr.ecr.eu-west-3.amazonaws.com/platform/medvision-ai:YYYY-MM-DD

# 4. Redéployer sur k3s
./scripts/redeploy-k3s.sh YYYY-MM-DD
```

---

## Déployer en production (k3s)

### Prérequis

- `kubectl` configuré vers le cluster k3s (fichier `~/.kube/config` à jour)
- AWS CLI connecté : `aws sts get-caller-identity` doit fonctionner
  - Si expiré : `aws sso login` (ou `aws login`)
- SSH sans mot de passe vers `ubuntu@51.38.235.94` (worker-ovh-094)

### Redéploiement complet (disaster recovery)

```bash
./scripts/redeploy-k3s.sh [TAG]
# Exemple : ./scripts/redeploy-k3s.sh 2026-04-16
```

Ce script :
1. Vérifie kubectl et AWS credentials
2. Crée/met à jour le namespace `medvision`
3. Rafraîchit le token ECR (expire toutes les 12h)
4. Applique ConfigMap, PVCs, Deployments, Services, Ingress
5. Attend que les pods soient Running
6. Vérifie la présence des modèles

### Vérification rapide

```bash
kubectl get pods -n medvision
# Attendu : medvision-api, medvision-streamlit, medvision-mlflow → Running

curl https://api.medvision.doctumconsilium.com/health
# Attendu : {"status":"ok"}
```

---

## URLs de production

| Service | URL |
|---|---|
| API FastAPI | https://api.medvision.doctumconsilium.com |
| Swagger (doc API) | https://api.medvision.doctumconsilium.com/docs |
| Interface Streamlit | https://app.medvision.doctumconsilium.com |
| MLflow (accès interne) | `kubectl port-forward -n medvision svc/medvision-mlflow 5000` |

---

## Entraîner ton premier modèle

Pour entraîner un modèle localement et le déployer en production, suis le guide complet :

**→ [`docs/LOCAL_TRAINING_GUIDE.md`](docs/LOCAL_TRAINING_GUIDE.md)**

Ce guide couvre :
- Setup Kaggle API et téléchargement des données
- Lancer l'entraînement (smoke test + entraînement complet)
- Vérifier les résultats avec MLflow
- Pousser les modèles vers S3 avec DVC (`dvc push`)
- Reconstruire l'image Docker et redéployer sur K3s

**Résumé ultra-rapide :**
```bash
# Activer votre environnement Python (conda, venv, etc.)
bash scripts/download_dataset.sh                     # données depuis Kaggle
python -m src.training.train --config configs/config.yaml --model optimized
dvc commit -f && dvc push                            # envoyer vers S3
TAG="$(date +%Y-%m-%d)a" && bash scripts/redeploy-k3s.sh $TAG
```

> Pour les commandes propres à votre machine locale (nom d'env conda, chemins, AWS profile…), voir `ONBOARDING_perso_<machine>.md`.

---

## Données persistées (PVCs k3s)

| PVC | Nœud k3s | Contenu | Taille |
|---|---|---|---|
| `medvision-raw-data` | worker-ovh-094 | Radiographies Chest X-ray brutes | 47 MB |
| `medvision-mlflow-store` | worker-ovh-233 | `mlflow.db` — historique des entraînements | 10 Gi alloués |
| `medvision-model-artifacts` | worker-ovh-233 | Vide (modèles sont dans l'image ECR) | 20 Gi alloués |

⚠ **Important** : les PVCs utilisent `local-path` (stockage local au nœud). Si un nœud est détruit,
les données de ce nœud sont perdues. Pour les radiographies brutes, elles sont re-téléchargeables
depuis Kaggle (`scripts/download_chest_xray_seg.sh`). Pour MLflow, faites une sauvegarde manuelle :
```bash
kubectl exec -n medvision deploy/medvision-mlflow -- \
  cp /mlflow/mlflow.db /tmp/mlflow-backup.db
kubectl cp medvision/$(kubectl get pod -n medvision -l app=medvision-mlflow \
  -o jsonpath='{.items[0].metadata.name}'):/tmp/mlflow-backup.db ./mlflow-backup.db
```

---

## Dépannage courant

### Pod en `ImagePullBackOff`

Le token ECR (12h) est expiré. Sur la machine locale avec AWS CLI :
```bash
aws sso login   # ou  aws login
./scripts/redeploy-k3s.sh  # rafraîchit le token et redéploie
```

### Pod en `Pending` (scheduling impossible)

Vérifier les volumes montés — un PVC sur un mauvais nœud bloque le scheduling :
```bash
kubectl describe pod -n medvision <nom-du-pod> | grep -A5 Events
```
Si "node(s) had volume node affinity conflict" : retirer le volumeMount conflictuel (voir Phase 1 du plan de ce chantier).

### L'API répond `/health` mais `/predict` renvoie 404 (model not found)

Les modèles ne sont pas dans le pod. Depuis 2026-06-15, ils sont tirés depuis S3 via DVC au démarrage.
Vérifier : `kubectl logs -n medvision deployment/medvision-streamlit | grep entrypoint`
Si "dvc pull a échoué" → entraîner un modèle → `dvc push` → redeploy (dvc pull automatique).

### `AttributeError: 'NoneType' object has no attribute 'pop'` lors d'une prédiction

Incompatibilité de version Keras. Les modèles doivent être sauvés avec Keras 3.3.3.
Vérifier que `keras==3.3.3` est bien dans `requirements.txt` et que l'image a été rebuild après ajout.

### Port-forward MLflow

```bash
kubectl port-forward -n medvision svc/medvision-mlflow 5000:5000
# → http://localhost:5000
```

---

## Pipelines DVC (optionnel mais recommandé)

DVC permet de reproduire exactement la chaîne data → modèle.

```bash
# Voir l'état du pipeline
dvc status

# Rejouer le pipeline depuis le début
dvc repro

# Configurer le remote S3 (après avoir appliqué terraform/aws_dvc_remote/)
dvc remote add -d s3remote s3://platform-medvision-artifacts
dvc remote modify s3remote region eu-west-3
dvc push   # envoie les artefacts sur S3
dvc pull   # récupère les artefacts depuis S3
```

---

## Contacts et ressources

- Infrastructure k3s : repo `k3s-fromOVHVps` (templates dans `deploy/platform/30-medvision.template.yaml`)
- ECR registry : `113301685315.dkr.ecr.eu-west-3.amazonaws.com/platform/`
- Région AWS : `eu-west-3` (Paris)
- Cluster k3s : 4 nœuds OVH (cp-ovh-232, worker-ovh-094, worker-ovh-233, vps-7f9dbc3f)
- Nœud des pods medvision-api/streamlit : `worker-ovh-094` (node-pool: apps-b)
- Nœud de MLflow : `worker-ovh-233` (node-pool: apps-a)
