# Mise à jour des modèles vers ONNX

Ce document décrit les étapes à effectuer **une seule fois** sur la machine
d'entraînement (là où Keras 3.13.2 et PyTorch sont installés) pour convertir
les modèles `.keras`/`.pt` en format `.onnx`.

---

## Pourquoi ONNX ?

Les modèles ont été sauvegardés avec **Keras 3.13.2** (mars 2026).
L'image de déploiement installait `keras==3.3.3` — un écart de 10 versions mineures
qui rend la désérialisation impossible et cause l'erreur :

```
TypeError: <class 'keras.src.models.functional.Functional'> could not be deserialized
```

**ONNX (Open Neural Network Exchange)** résout ce problème définitivement :
un modèle converti en ONNX se charge avec `onnxruntime`, sans dépendance à Keras,
TensorFlow ou PyTorch. Le format est stable entre les versions depuis 2017.

Bénéfices supplémentaires :
- Image Docker allégée : `tensorflow-cpu` (600 MB) → `onnxruntime-cpu` (10 MB)
- Démarrage du pod : ~30 s → ~3 s
- Inférence CPU plus rapide

---

## Prérequis

- **Machine avec GPU/ML** : `conda activate GPUMachineLearning` (Keras 3.13.2, PyTorch)
- **AWS CLI** configuré (accès au bucket S3 utilisé par DVC)
- **Git** configuré avec accès en écriture au repo

---

## Étapes

### 1. Préparer l'environnement

```bash
conda activate GPUMachineLearning
pip install tf2onnx>=1.16 onnx>=1.16
git pull origin feat/ci-quality-2026-06-15
```

Vérifier les versions :
```bash
python -c "import keras; print('Keras:', keras.__version__)"
# → Keras: 3.13.2 (ou supérieur)
python -c "import tf2onnx; print('tf2onnx:', tf2onnx.__version__)"
```

### 2. Récupérer tous les modèles depuis S3

```bash
dvc pull artifacts/
```

Vérifier que les modèles sont présents :
```bash
ls -lh artifacts/models/*.keras artifacts/models/*.pt 2>/dev/null
```

Attendu : au moins `baseline_model.keras`, `optimized_model.keras`,
`brain_mri_optimized.keras`, `brain_tumor_segmentation_unet.keras`.

### 3. Voir ce qui sera converti (dry-run)

```bash
python scripts/convert_to_onnx.py --dry-run
```

### 4. Lancer la conversion

```bash
python scripts/convert_to_onnx.py
```

Le script affiche la progression. Résumé final :
- `✓ N converti(s) : [...]` → succès
- `→ N déjà présent(s) : [...]` → déjà convertis lors d'une session précédente
- `✗ N échec(s) : [...]` → voir la section [Erreurs fréquentes](#erreurs-fréquentes)

### 5. Vérifier les fichiers produits

```bash
ls -lh artifacts/models/*.onnx
```

Attendu : un `.onnx` pour chaque `.keras` et `.pt` présent.

### 6. Tester un modèle converti

```bash
pip install onnxruntime
python - <<'EOF'
import onnxruntime as ort, numpy as np

sess = ort.InferenceSession(
    "artifacts/models/optimized_model.onnx",
    providers=["CPUExecutionProvider"],
)
inp = sess.get_inputs()[0]
print("Input :", inp.name, inp.shape)

out_names = [o.name for o in sess.get_outputs()]
print("Outputs:", out_names)

dummy = np.random.rand(1, 224, 224, 3).astype(np.float32)
result = sess.run(None, {inp.name: dummy})
print("Output shape:", result[0].shape)
print("OK — inférence ONNX fonctionne correctement")
EOF
```

Pour le modèle U-Net de segmentation (sorties multiples) :
```bash
python - <<'EOF'
import onnxruntime as ort, numpy as np

sess = ort.InferenceSession(
    "artifacts/models/brain_tumor_segmentation_unet.onnx",
    providers=["CPUExecutionProvider"],
)
print("Inputs :", [(i.name, i.shape) for i in sess.get_inputs()])
print("Outputs:", [(o.name, o.shape) for o in sess.get_outputs()])

dummy = np.random.rand(1, 256, 256, 3).astype(np.float32)
result = sess.run(None, {sess.get_inputs()[0].name: dummy})
for i, out in enumerate(result):
    print(f"  output[{i}] shape: {out.shape}")
print("OK")
EOF
```

### 7. Enregistrer dans DVC et pousser vers S3

```bash
dvc add artifacts/models/
dvc push
```

### 8. Commiter et pousser

```bash
git add artifacts/models/
git commit -m "feat(models): convertit tous les modèles en ONNX (version-stable)"
git push
```

### 9. Déclencher le build de la nouvelle image

Depuis n'importe quelle machine avec Docker + AWS CLI :

```bash
bash scripts/redeploy-k3s.sh 2026-06-16a
```

---

## Erreurs fréquentes

### `ModuleNotFoundError: No module named 'tf2onnx'`

```bash
pip install tf2onnx>=1.16 onnx>=1.16
```

### `TypeError: could not be deserialized` lors de la conversion

L'environnement actif n'a pas Keras 3.13.2 :
```bash
python -c "import keras; print(keras.__version__)"
# Doit afficher 3.13.x — sinon activer GPUMachineLearning
```

### `RuntimeError: ONNX export failed` pour un modèle PyTorch

Le fichier `.pt` est peut-être un **state_dict** et non un modèle complet.

Diagnostic :
```bash
python - <<'EOF'
import torch
obj = torch.load("artifacts/models/brain_mri_2d_demo.pt", map_location="cpu", weights_only=False)
print(type(obj))
# torch.nn.Module → modèle complet (OK)
# OrderedDict / dict → state_dict (nécessite reconstruction de l'architecture)
EOF
```

Si c'est un state_dict, il faut reconstruire l'architecture avant l'export.
Contacter le responsable du modèle ou consulter le notebook d'entraînement correspondant.

### `dvc push` échoue avec `403 Forbidden`

```bash
aws sts get-caller-identity   # vérifier les credentials
aws sso login                 # si expiré
```

---

## Structure après conversion

```
artifacts/models/
  baseline_model.keras               → baseline_model.onnx
  optimized_model.keras              → optimized_model.onnx
  brain_mri_optimized.keras          → brain_mri_optimized.onnx
  brain_tumor_segmentation_unet.keras → brain_tumor_segmentation_unet.onnx
  chest_xray_segmentation_unet.keras → chest_xray_segmentation_unet.onnx
  brain_mri_densenet121.keras        → brain_mri_densenet121.onnx
  brain_mri_efficientnetv2b0.keras   → brain_mri_efficientnetv2b0.onnx
  brain_mri_convnexttiny.keras       → brain_mri_convnexttiny.onnx
  brain_mri_resnet50v2.keras         → brain_mri_resnet50v2.onnx
  brain_mri_2d_demo.pt               → brain_mri_2d_demo.onnx
  brain_mri_densenet121_torch.pt     → brain_mri_densenet121_torch.onnx
  brain_mri_resnet50_torch.pt        → brain_mri_resnet50_torch.onnx
  brain_mri_swin_v2_s_torch.pt       → brain_mri_swin_v2_s_torch.onnx
```

Les fichiers `.keras` et `.pt` sont conservés (ils restent dans DVC pour
les notebooks d'entraînement), mais l'application de déploiement utilise
uniquement les `.onnx`.
