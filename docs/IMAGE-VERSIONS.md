# Images Docker — versions courantes

> Mis à jour le **2026-07-28**. Toujours vérifier l'état réel avant un build :
> `kubectl -n medvision get deploy -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.template.spec.containers[0].image}{"\n"}{end}'`
>
> **Règle absolue : jamais `kubectl apply` sur le manifest complet — toujours
> `kubectl set image`.** Un manifest peut écraser un Secret réel par un espace réservé ;
> l'incident est déjà arrivé sur `products.doctumconsilium.com` (500, oauth2 cassé).

## Images déployées en production (k3s OVH, namespace `medvision`)

| Service | Deployment | Image déployée | Rôle |
|---|---|---|---|
| API d'inférence | `medvision-api` | `medvision-ai:2026-07-18f` ✅ | FastAPI, API v2 sous `/api` |
| Interface Streamlit (historique) | `medvision-streamlit` | `medvision-ai:2026-07-18f` ✅ | `app.medvision…` — conservée tant que la parité n'est pas constatée |
| MLflow | `medvision-mlflow` | `medvision-ai:2026-07-18f` ✅ | suivi des expériences |
| **Interface web (Angular + nginx)** | `medvision-web` | `medvision-web:2026-07-28` ✅ | `ui.medvision…` |

**Deux images, deux cycles de vie.** `medvision-ai` pèse plusieurs gigaoctets (PyTorch,
TensorFlow, ONNX Runtime) et bouge rarement. `medvision-web` ne contient que des fichiers
statiques et nginx (~49 Mo) : on la republie à chaque retouche de l'interface. Les forcer
au même tag obligerait à reconstruire l'une pour publier l'autre.

## Registre ECR

```
113301685315.dkr.ecr.eu-west-3.amazonaws.com/platform/medvision-ai
113301685315.dkr.ecr.eu-west-3.amazonaws.com/platform/medvision-web
```

Le jeton ECR **expire au bout de 12 heures**. Les pods déjà démarrés ne s'en aperçoivent
pas — mais tout **nouveau tag** échoue alors en `403 Forbidden`. Renouveler le secret de
tirage AVANT de déployer, par un `patch` et jamais par un `delete` suivi d'un `create`,
qui ouvre une fenêtre pendant laquelle le secret n'existe plus :

```bash
T=$(aws ecr get-login-password --region eu-west-3)
CFG=$(printf '{"auths":{"113301685315.dkr.ecr.eu-west-3.amazonaws.com":{"username":"AWS","password":"%s","auth":"%s"}}}' \
  "$T" "$(printf 'AWS:%s' "$T" | base64 -w0)" | base64 -w0)
kubectl -n medvision patch secret ecr-pull-secret --type merge \
  -p "{\"data\":{\".dockerconfigjson\":\"$CFG\"}}"
unset T CFG
```

## Publier une nouvelle version

### Interface web (`medvision-web`)

```bash
./scripts/build-and-push-web.sh 2026-07-28          # contrôle de compilation, build, push
kubectl -n medvision set image deploy/medvision-web \
  web=113301685315.dkr.ecr.eu-west-3.amazonaws.com/platform/medvision-web:2026-07-28
kubectl -n medvision rollout status deploy/medvision-web --timeout=180s
```

### Image d'inférence (`medvision-ai`)

```bash
./scripts/redeploy-k3s.sh 2026-07-18f               # le tag par défaut suit la production
```

## Après CHAQUE déploiement — la procédure, sans exception

1. Mettre à jour **ce fichier** (tableau + date en tête).
2. Mettre à jour le tag dans `k3s-fromOVHVps` : `deploy/platform/30-medvision.template.yaml`
   **et** `rendered-k3s-manifests/30-medvision.yaml` — le gabarit ET le rendu, sinon une
   reconstruction du cluster repartirait sur l'ancienne version.
3. Ajouter une **entrée datée** en tête du journal de `ROADMAP.md`, avec les **commandes
   exactes rejouables** (elles sont dans `~/.claude/ops-journal/*.tsv`, à ne pas
   reconstituer de mémoire).
4. Reporter le tag en tête de `docs/SESSION-STATE.md`.
5. Mettre à jour le tag par défaut de `scripts/redeploy-k3s.sh` s'il s'agit de
   `medvision-ai` — le laisser périmé fait redéployer une version antérieure aux
   correctifs le jour où on le lance sans argument, c'est-à-dire en pleine panne.

## Historique

| Date | Image | Tag | Motif |
|---|---|---|---|
| 2026-07-28 | `medvision-web` | `2026-07-28` | Étiquettes traduites, état de connexion corrigé au premier chargement |
| 2026-07-27 | `medvision-web` | `2026-07-27b` | Refonte visuelle (identité, palette, accessibilité du tri) |
| 2026-07-27 | `medvision-web` | `2026-07-27` | Première mise en ligne de l'interface Angular |
| 2026-07-18 | `medvision-ai` | `2026-07-18f` | Les 17 modèles en production, API v2, segmentation pure |
