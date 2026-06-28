# Guide d'entraînement local — MedVision AI

Ce guide t'explique, étape par étape, comment :
1. Préparer ton environnement Python
2. Télécharger les données médicales (depuis Kaggle)
3. Lancer l'entraînement d'un modèle sur ton PC
4. Vérifier que ça a bien fonctionné (métriques MLflow)
5. Envoyer le modèle vers le stockage cloud (S3 via DVC)
6. Redéployer l'application en production (Docker → ECR → K3s)

**Tu n'as pas besoin d'être expert** pour suivre ce guide. Chaque commande est expliquée.

---

## Glossaire (à lire en premier)

| Terme | Ce que ça veut dire en pratique |
|-------|--------------------------------|
| **DVC** | Outil qui versionne les gros fichiers (modèles, datasets) sur S3, comme Git versionne le code. |
| **S3** | Stockage cloud Amazon (comme un disque dur dans le cloud). On stocke les modèles entraînés ici. |
| **ECR** | Registre Amazon pour les images Docker (comme Docker Hub mais privé). |
| **K3s** | Notre serveur Kubernetes (hébergé chez OVH). Il fait tourner l'application en production. |
| **Kaggle** | Plateforme de datasets médicaux. On y télécharge les radiographies et IRM. |
| **MLflow** | Tableau de bord pour voir les résultats de chaque entraînement (accuracy, loss, courbes). |
| **conda** | Gestionnaire d'environnements Python. On utilise l'env `GPUMachineLearning` déjà configuré. |
| **`dvc push`** | Envoie les modèles entraînés vers S3. |
| **`dvc pull`** | Récupère les modèles depuis S3 (fait automatiquement au démarrage du pod K3s). |

---

## Prérequis (à faire une seule fois)

### 1. Kaggle API token

Pour télécharger les datasets médicaux, il faut un compte Kaggle et un token API.

**Étapes :**
1. Va sur [kaggle.com](https://www.kaggle.com) → ton profil → Settings → API → **Create New Token**
2. Ça télécharge un fichier `kaggle.json`
3. Copie ce fichier dans `~/.kaggle/` :

```bash
mkdir -p ~/.kaggle
cp /chemin/vers/kaggle.json ~/.kaggle/kaggle.json
chmod 600 ~/.kaggle/kaggle.json   # important : restreindre les permissions
```

**Vérification :**
```bash
kaggle datasets list --search "chest xray"
# Doit afficher une liste de datasets, pas une erreur
```

**Erreur fréquente :** `401 Unauthorized` → ton token est expiré. Retourne sur Kaggle → Settings → API → Create New Token pour en créer un nouveau.

---

### 2. AWS CLI configuré

Pour envoyer les modèles vers S3, l'AWS CLI doit être connecté.

**Vérification :**
```bash
aws sts get-caller-identity
# Doit afficher ton Account ID (113301685315)
```

Si ça retourne une erreur, demande à Yann les credentials ou renouvelle la session SSO.

---

### 3. Espace disque disponible

| Dataset | Taille approximative |
|---------|---------------------|
| Chest X-ray (pneumonie) | ~2 Go |
| Brain MRI (tumeurs) | ~1 Go |
| Brain Tumor Segmentation | ~2 Go |
| **Total** | **~5 Go** pour les données + ~500 Mo pour les modèles |

---

## Étape 1 — Activer l'environnement Python

```bash
cd <chemin-vers-votre-clone>/medvision-ai     # ex. ~/medvision-ai
# Activez votre environnement Python 3.10–3.12 :
source .venv/bin/activate                       # venv
# ou : conda activate <votre-env>               # conda
```

**Cet environnement doit contenir les deps d'entraînement** (`pip install -r requirements-train.txt` : TensorFlow, PyTorch, etc.). Sinon `import tensorflow` échoue.

**Vérification :**
```bash
python -c "import tensorflow as tf; print('TF:', tf.__version__)"
# Doit afficher : TF: 2.x.x
```

---

## Étape 2 — Télécharger les données

Les données viennent de Kaggle. Un script les télécharge automatiquement.

### Option A — Tout télécharger d'un coup (~15-30 min selon la connexion)

```bash
bash scripts/download_dataset.sh
```

Ce script télécharge dans l'ordre :
1. Chest X-ray (pneumonie vs normal)
2. Brain MRI (4 types de tumeurs)
3. Brain Tumor Segmentation (images + masques)

### Option B — Télécharger un seul dataset

```bash
# Chest X-ray uniquement (~2 Go)
python -m src.data.download_dataset

# Brain MRI uniquement (~1 Go)
python -m src.data.download_brain_mri_dataset --config configs/brain_tumor_mri.yaml

# Brain Tumor Segmentation (~2 Go)
python -m src.data.download_segmentation_dataset --problem brain_tumor_seg
python -m src.data.prepare_segmentation_dataset --config configs/brain_tumor_segmentation.yaml
```

**Résultat attendu :**
```
data/raw/
├── chest_xray/
│   ├── train/NORMAL/    (~1300 images)
│   ├── train/PNEUMONIA/ (~3875 images)
│   └── test/NORMAL/ test/PNEUMONIA/
├── brain_tumor_mri/
│   ├── Training/glioma/ meningioma/ notumor/ pituitary/
│   └── Testing/...
└── brain_tumor_segmentation/
    └── BraTS2020_TrainingData/...
```

**Erreur fréquente :** `403 Forbidden` sur Kaggle → tu n'as pas accepté les règles d'utilisation du dataset. Va sur la page Kaggle du dataset, clique "I Understand and Accept" puis relance.

---

## Étape 3 — Test rapide (smoke test, 2-3 minutes)

Avant de lancer un entraînement complet (qui peut prendre des heures), **teste d'abord avec 1 seule époque** pour vérifier que tout fonctionne :

```bash
# Test Chest X-ray (1 époque = ~2 min sur CPU, ~30 sec sur GPU)
python -m src.training.train --config configs/config.yaml --model optimized --epochs 1

# Test Brain MRI
python -m src.training.train_brain_mri --config configs/brain_tumor_mri.yaml --model optimized --epochs 1
```

**Si c'est vert (aucune erreur), tu peux passer à l'étape 4.**

**Erreur fréquente :** `OOM (Out of Memory)` → le batch size est trop grand pour ta RAM/VRAM. Réduis dans le config :
```yaml
# configs/config.yaml
batch_size: 8   # au lieu de 16
```

---

## Étape 4 — Entraînement complet

### Chest X-ray — Classification pneumonie

```bash
python -m src.training.train \
    --config configs/config.yaml \
    --model optimized
# Durée : ~30 min sur GPU, ~2-3h sur CPU
# Sortie : artifacts/models/optimized_model.keras
```

### Brain MRI — Classification tumeurs (4 classes)

```bash
# Modèle principal (optimized = EfficientNet)
python -m src.training.train_brain_mri \
    --config configs/brain_tumor_mri.yaml \
    --model optimized
# Durée : ~1h sur GPU, ~4-5h sur CPU
# Sortie : artifacts/models/brain_mri_optimized.keras

# Alternatives (si tu veux comparer les backbones)
python -m src.training.train_brain_mri --config configs/brain_tumor_mri.yaml --model densenet121
python -m src.training.train_brain_mri --config configs/brain_tumor_mri.yaml --model convnexttiny
```

### Brain MRI — PyTorch (benchmark alternatif)

```bash
python -m src.training.train_brain_mri_torch \
    --config configs/brain_tumor_mri.yaml \
    --model densenet121_torch
# Sortie : artifacts/models/brain_mri_densenet121_torch.pt
```

### Brain Tumor Segmentation — U-Net multitâche

```bash
# 1. Préparer le manifest CSV (liste des images + masques)
python -m src.data.prepare_segmentation_dataset \
    --config configs/brain_tumor_segmentation.yaml

# 2. Entraîner le U-Net
python -m src.segmentation.train_segmentation \
    --config configs/brain_tumor_segmentation.yaml
# Durée : ~2h sur GPU, très long sur CPU (non recommandé sans GPU)
# Sortie : artifacts/models/brain_tumor_segmentation_unet.keras
```

### Tout entraîner via DVC (pipeline complet)

DVC permet de reproduire toute la chaîne : download → train → rapports. Il ne relance que ce qui a changé.

```bash
dvc repro
# Rejoue les stages dans l'ordre correct
# Si les données sont déjà présentes, saute le download
```

---

## Étape 5 — Vérifier les résultats

### Voir les métriques dans MLflow

```bash
mlflow ui --backend-store-uri ./mlruns
# Ouvre http://localhost:5000 dans ton navigateur
```

Tu verras l'accuracy, la loss, les courbes d'apprentissage pour chaque run.

### Vérifier les fichiers créés

```bash
ls artifacts/models/          # → fichiers .keras et .pt
ls artifacts/reports/         # → metrics.json, classification_report.txt, confusion_matrix.png
```

**Vérification rapide des métriques :**
```bash
cat artifacts/reports/optimized_metrics.json
# Doit afficher accuracy > 0.8 pour un bon modèle chest X-ray
```

### Tester une prédiction rapide

```bash
# Lancer le serveur FastAPI localement
uvicorn src.api.main:app --reload

# Dans un autre terminal, tester une image :
curl -X POST http://localhost:8000/predict/chest_xray \
     -F "file=@data/raw/chest_xray/test/NORMAL/IM-0001-0001.jpeg"
```

---

## Étape 6 — Envoyer les modèles vers S3 (DVC push)

Une fois l'entraînement validé, on envoie les modèles vers S3 pour que le pod K3s puisse les récupérer.

```bash
# Enregistre l'état actuel des modèles dans DVC
dvc commit -f

# Envoie vers S3
dvc push

# Vérification
dvc status   # Doit afficher "Data and pipelines are up to date" pour les stages entraînés
```

**Ce qui se passe en coulisses :** DVC calcule une empreinte (hash SHA256) de chaque modèle et l'envoie vers `s3://platform-medvision-dvc-artifacts/models/`.

---

## Étape 7 — Reconstruire l'image Docker et déployer

### A. Refresh du token ECR (expire toutes les 12h)

```bash
aws ecr get-login-password --region eu-west-3 \
    | docker login --username AWS --password-stdin \
    113301685315.dkr.ecr.eu-west-3.amazonaws.com
```

### B. Build de l'image (code uniquement — les modèles viennent de S3)

```bash
TAG="2026-06-15a"   # Convention : YYYY-MM-DD + lettre si rebuild le même jour
REGISTRY="113301685315.dkr.ecr.eu-west-3.amazonaws.com/platform"

docker build \
    -f docker/Dockerfile \
    -t $REGISTRY/medvision-ai:$TAG \
    .
```

**Note :** L'image ne contient PAS les modèles (exclus par `.dockerignore`). Le pod les récupère depuis S3 au démarrage via `docker/entrypoint.sh`.

### C. Push vers ECR

```bash
docker push $REGISTRY/medvision-ai:$TAG
```

### D. Redéployer sur K3s

```bash
bash scripts/redeploy-k3s.sh $TAG
```

Ce script :
1. Crée/met à jour le Secret `medvision-aws-creds` dans K3s (pour que les pods puissent faire `dvc pull`)
2. Met à jour les Deployments avec le nouveau tag
3. Attend que les pods soient en état Running
4. Vérifie que les modèles ont été récupérés depuis S3

### E. Vérifier le déploiement

```bash
# État des pods
kubectl get pods -n medvision

# Logs du pod streamlit (cherche la ligne [entrypoint])
kubectl logs -n medvision deploy/medvision-streamlit | grep -E "entrypoint|Artefacts|dvc"

# Test de l'app
curl https://api.medvision.doctumconsilium.com/health
```

---

## Résumé des commandes (cheatsheet)

```bash
# ── Setup (une seule fois) ────────────────────────────────────────────────────
cd <chemin-vers-votre-clone>/medvision-ai      # ex. ~/medvision-ai
source .venv/bin/activate                       # ou : conda activate <votre-env>
pip install -r requirements-train.txt           # deps entraînement (TF, torch, kaggle…)

# ── Données ──────────────────────────────────────────────────────────────────
bash scripts/download_dataset.sh           # Télécharge tout depuis Kaggle

# ── Smoke test (valider l'environnement) ─────────────────────────────────────
python -m src.training.train --config configs/config.yaml --model optimized --epochs 1

# ── Entraînement complet ─────────────────────────────────────────────────────
python -m src.training.train --config configs/config.yaml --model optimized
python -m src.training.train_brain_mri --config configs/brain_tumor_mri.yaml --model optimized
python -m src.segmentation.train_segmentation --config configs/brain_tumor_segmentation.yaml

# ── Résultats ────────────────────────────────────────────────────────────────
mlflow ui --backend-store-uri ./mlruns    # Dashboard métriques → localhost:5000
cat artifacts/reports/optimized_metrics.json

# ── DVC push vers S3 ─────────────────────────────────────────────────────────
dvc commit -f && dvc push

# ── Deploy prod ──────────────────────────────────────────────────────────────
TAG="2026-06-15a"
REGISTRY="113301685315.dkr.ecr.eu-west-3.amazonaws.com/platform"
aws ecr get-login-password --region eu-west-3 | docker login --username AWS --password-stdin $REGISTRY
docker build -f docker/Dockerfile -t $REGISTRY/medvision-ai:$TAG . && docker push $REGISTRY/medvision-ai:$TAG
bash scripts/redeploy-k3s.sh $TAG
```

---

## Dépannage

| Erreur | Cause probable | Solution |
|--------|---------------|---------|
| `401 Unauthorized` (Kaggle) | Token expiré | Regénérer `kaggle.json` sur kaggle.com |
| `403 Forbidden` (Kaggle) | Règles dataset non acceptées | Aller sur la page Kaggle du dataset et cliquer "Accept" |
| `OOM` pendant l'entraînement | Pas assez de RAM/VRAM | Réduire `batch_size` dans le config YAML |
| `ModuleNotFoundError` (ex. `tensorflow`) | Env. non activé ou deps train absentes | Activer l'env. puis `pip install -r requirements-train.txt` |
| `dvc push` échoue | Session AWS expirée | `aws sts get-caller-identity` pour vérifier |
| `ImagePullBackOff` en K3s | Token ECR expiré (12h) | Relancer `bash scripts/redeploy-k3s.sh $TAG` (recrée le token) |
| Pod démarre mais sans modèles | `dvc pull` a échoué | Voir `/tmp/dvc-pull.log` dans le pod : `kubectl exec -n medvision deploy/medvision-streamlit -- cat /tmp/dvc-pull.log` |
| GPU non détecté | Drivers CUDA | `nvidia-smi` pour vérifier, ou enlever `--extra-index-url` PyTorch CUDA de requirements.txt |

---

## Prochaines étapes (cloud training)

L'entraînement local convient pour des runs de quelques heures. Pour des entraînements plus longs ou avec plus de données, consulter `docs/DEPLOYMENT_OPTIONS.md` (section AWS SageMaker / spot instances).
