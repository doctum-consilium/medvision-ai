# MedVision AI — PR #10 + 17 modèles en prod + refonte Angular réactive

> **État au 2026-07-18 (fin de session) — LIVRÉ EN PARTIE.**
>
> **Chantier 1 (PR #10 → les 17 modèles en production) : livré intégralement**, et
> au-delà du plan initial — cinq causes racines imprévues ont dû être corrigées en
> chemin (dépendance DVC, stockage éphémère, écrasement des modèles, format d'entrée
> PyTorch, saturation mémoire). Voir `2026-07-18-handoff-medvision.md`.
>
> **Chantier 2 (front Angular) : arrêté au socle.** Le squelette, le design system, les
> libellés et les types sont commités sur la branche locale `feat/front-socle-angular`
> (non poussée) ; aucun écran n'est branché, rien n'est déployé.
>
> **Deux décisions produit prises en cours de route, qui modifient ce plan :** les deux
> modèles `convnexttiny` sont désactivés (export ONNX invalide) et les problèmes de
> segmentation ne posent plus aucun diagnostic (leur tête de classification était
> trompeuse). L'écran « studio » du front devra respecter cette seconde règle.
>
> **Pour reprendre : lire `docs/plans/2026-07-18-handoff-medvision.md`**, qui contient
> l'état exact, la marche à suivre et les dettes ouvertes.

> **MISE À JOUR DU 2026-07-27 — chantier 2 (front Angular) TERMINÉ côté code.**
>
> Les trois écrans existent, sont testés et empaquetés dans une image nginx : accueil,
> analyse multi-modèles avec superpositions de segmentation réglables sans ré-inférence,
> et comparaison. Les manifests k3s sont écrits (`medvision-web`, hôte `ui.medvision`,
> Streamlit conservé). **Rien n'est déployé** : l'image reste à publier, les manifests à
> appliquer et le DNS à créer.
>
> Deux écarts par rapport à ce plan, assumés :
> - **Angular 19** (et non 20) — c'est la version du socle déjà installé.
> - **Le design system maison est conservé** et Tailwind le consomme au lieu de le
>   remplacer : la bascule clair/sombre repeint ainsi aussi les classes utilitaires.
>
> Suite et détail : **`docs/plans/2026-07-27-medvision-front-angular-b1.md`** et le bloc
> de reprise en tête de `docs/SESSION-STATE.md`.

## Context

Yann a entraîné 17 modèles ONNX et les a poussés dans S3 via DVC, mais l'UI Streamlit de prod n'en montre que 4. Cause racine vérifiée : la prod (image `medvision-ai:2026-06-16b`) fait `dvc pull convert_to_onnx` au démarrage avec le **`dvc.lock` baked dans l'image**, construit depuis `main` qui ne connaît que 4 ONNX. La PR #10 (`feat/dvc-17-modeles-et-portabilite`) porte le nouveau pipeline 17 modèles mais a **4 checks CI rouges**. Il faut : réparer la CI, merger, rebuild + redéployer. Ensuite, refonte du front en **Angular** (UI professionnelle, coexiste avec Streamlit, parité complète) avec **réactivité SSE** : un nouveau modèle poussé via DVC apparaît dans l'UI sans redéploiement.

Décisions utilisateur : corrige CI + merge PR #10 ✔ · Angular coexiste avec Streamlit ✔ · parité complète v1 ✔ · SSE + watcher backend ✔.

## Diagnostic CI PR #10 (vérifié)

1. **`validate` (guardrails.yml)** : `.guardrails/config.env` absent + validateur en mode 100644 (le job fait `test -f config.env` ET `test -x validate_guardrails.sh`). Le fix existe déjà : commit local `67597a0` (branche `feat/ci-quality-2026-06-15`) — config.env + chmod 755 + étape guardrails dans `ci_local.sh`.
2. **`test-tf` (ci.yml) + `current-test-suite` (ci-suite.yml)** : `tests/test_model_builders.py:111` asserte `set(TF_BACKBONES) == {4 noms}` mais la branche a ajouté l'alias `"optimized"` (EfficientNetV2B0) dans `src/models/backbones.py:58`.
3. **`test-fast` smoke (ci.yml)** : diff-cover < 80 % — `src/segmentation/data.py` (54 lignes, 0 %) + `src/training/train.py` (3 lignes) importent TF au niveau module → inatteignables sans TF.
4. **Échec latent** : une fois le test backbones réparé, le gate diff-cover du job `test-tf` (sans exclusions) échouera car `src/segmentation/data.py` n'a aucun test → il faut un `tests/test_segmentation_data.py`.

Le registre `src/registry/model_registry.py` (PROBLEMS) référence déjà exactement les 17 ONNX du nouveau dvc.lock — aucune modif registre nécessaire.

---

## Chantier 1 — CI PR #10 verte → merge → 17 modèles en prod

### Surface des changements (branche `feat/dvc-17-modeles-et-portabilite`)

4 commits (conventional commits FR, jamais de Co-Authored-By) :

1. **guardrails** : `git cherry-pick 67597a0` (si conflit sur `scripts/ci_local.sh`, réappliquer à la main : `git show 67597a0:.guardrails/config.env` + `git update-index --chmod=+x .guardrails/bin/validate_guardrails.sh`).
2. **test backbones** : `tests/test_model_builders.py:111` — ajouter `"optimized"` au set + assert `TF_BACKBONES["optimized"].cls is EfficientNetV2B0`.
3. **gate smoke** : dans `.github/workflows/ci.yml` (job test-fast, étape diff-cover ~l.108) ET `scripts/ci_local.sh` (bloc miroir ~l.83) : étendre `--exclude` avec `'*/segmentation/*' '*/training/*'` (modules TF-only, couverture exigée par le gate du job test-tf).
4. **tests segmentation** : nouveau `tests/test_segmentation_data.py` (mini PNG 16×16 + manifest.csv en tmp_path) : multitask (shapes + clés seg/classif), binaire, fallback split, erreurs (manifest absent/vide). Vise ~95 % du diff mesurable TF.

### Merge + déploiement

```bash
bash scripts/ci_local.sh                                  # CI locale verte AVANT push (règle)
# + suite TF locale : pytest tests/ --cov=src + diff-cover vs origin/main
git push origin feat/dvc-17-modeles-et-portabilite
gh pr checks 10 --watch && gh pr merge 10 --merge
git checkout main && git pull --ff-only

aws ecr get-login-password --region eu-west-3 | docker login --username AWS --password-stdin 113301685315.dkr.ecr.eu-west-3.amazonaws.com
TAG=2026-07-18a
docker build -f docker/Dockerfile -t .../platform/medvision-ai:$TAG . && docker push ...
bash scripts/redeploy-k3s.sh $TAG          # tmux session deploy-medvision
```

Puis pérenniser le tag : `k3s-fromOVHVps/rendered-k3s-manifests/30-medvision.yaml` (l.73, 134) + défaut `TAG=` de `scripts/redeploy-k3s.sh` + `docs/SESSION-STATE.md`.

### Vérification

```bash
kubectl exec -n medvision deploy/medvision-streamlit -- sh -c "ls /app/artifacts/models/*.onnx | wc -l"   # → 17
kubectl exec -n medvision deploy/medvision-streamlit -- python -c "from src.registry.model_registry import load_registry; r=load_registry(); print(sum(m['available'] for p in r['problems'].values() for m in p['models'].values()))"  # → 17
```
+ contrôle visuel sur `app.medvision.doctumconsilium.com` (6 chest + 9 brain + 2 seg).

**Rollback** : `bash scripts/redeploy-k3s.sh 2026-06-16b`.

**Risque connu (hors périmètre, à signaler)** : l'entrypoint ne tire que le stage ONNX → `artifacts/reports/` absent en pod → modèles disponibles mais métriques vides dans l'UI.

---

## Chantier 2 — Refonte Angular réactive (chaîne de PRs empilées)

### Principe directeur

Angular 20 standalone + signals (pas de NgRx), **Tailwind CSS v4 + composants maison** (rendu médical pro, tokens teal `#0f7a66` / dark-light), Chart.js, libellés **français** centralisés (`libelles.fr.ts`), ton grand public + disclaimer médical. Backend : FastAPI éclaté en routes/services, **watcher asyncio** (HEAD ETag S3 d'un `dvc.lock` manifeste → `dvc pull` → invalidation cache → broadcast **SSE**) → l'UI se met à jour seule. Streamlit reste sur `app.medvision...`, Angular sur **`ui.medvision.doctumconsilium.com`**.

### Backend (fichiers clés)

- `src/datasets/sample_browser.py` — extraction des fonctions pures du browser d'images de `streamlit_app.py` (source de vérité partagée) + `SampleIndex` (sample_id hashé → Path, anti path-traversal).
- `src/api/routes/{problems,models,predict,images,reports,events}.py` + `src/api/services/{registry_state,session_cache,image_index,inference,broadcaster,watcher}.py` ; endpoints historiques conservés, nouveaux sous `/api/*`.
- Endpoints : `GET /api/problems`, `GET /api/models` (enrichi size/mtime/**version**), `GET /api/models/version`, `POST /api/predict` (multipart, multi-modèles, **masque proba en PNG base64** → re-seuillage client sans ré-inférence), `GET /api/images` (+`/{id}/file?thumb=`), `GET /api/reports`, `GET /api/events` (SSE maison ~40 lignes, heartbeat 25 s).
- **Watcher** : `scripts/publish_model_manifest.sh` (`aws s3 cp dvc.lock s3://platform-medvision-dvc-artifacts/models/.meta/dvc.lock` après chaque `dvc push`) ; boucle asyncio 60 s HEAD ETag → si changé : download lock → `dvc pull convert_to_onnx` → clear cache sessions → refresh registre → SSE `models_updated`. Backoff sur échec, env `MEDVISION_WATCH_*`, OFF en CI.
- **RAM** : `OnnxSessionCache` LRU borné à 3 sessions (pod 2 Gi, jamais 17 modèles en mémoire) ; `load_onnx_model()` devient wrapper de compat pour Streamlit.

### Frontend (`frontend/`)

- `core/api/*` (clients HttpClient miroir des schemas), `core/realtime/sse.service.ts` (EventSource + backoff + resync via `/api/models/version` à la reconnexion), `core/state/registry.store.ts` (signals).
- Écrans : **tableau de bord** (cartes problèmes, pastille SSE), **studio** (drag&drop OU navigateur dataset filtres/pagination, multi-modèles, jauges de confiance, graphes probas), **overlays seg** (2 canvas, sliders seuil/opacité 100 % client-side), **comparaison** (tableau triable + graphe), **métriques/rapports**.
- Toast "Nouveau modèle disponible" + badge "Nouveau" sur événement SSE. Zéro polling.

### Build/deploy

- `docker/frontend.Dockerfile` (node:22 build → nginx:1.27, SPA try_files, proxy `/api` → `medvision-api:8000`, `/api/events` avec `proxy_buffering off`).
- `30-medvision.yaml` : Deployment+Service `medvision-web` (requests 50m/64Mi), host `ui.medvision...` dans l'ingress (+ `proxy-read-timeout 3600` pour SSE), **monter le PVC `medvision-raw-data` sur le pod API** (requis par `/api/images` ; RWO OK, même nœud apps-b), env watcher dans le ConfigMap.

### Chaîne de PRs (empilées, base = précédente ; vérifier `base: main` avant chaque merge)

1. `refactor/extraction-index-images` — sample_browser + adaptation streamlit + tests
2. `feat/api-endpoints-v2` — routes/services, session cache, tests
3. `feat/api-watcher-sse` — watcher + broadcaster + `/api/events` + publish_model_manifest.sh + tests
4. `feat/front-socle-angular` — scaffold, Tailwind, core, tableau de bord, `ci-front.yml` (node 22, lint+vitest+build)
5. `feat/front-studio-prediction` — studio + overlays canvas
6. `feat/front-comparaison-metriques` — comparaison + métriques
7. `build/docker-frontend` — Dockerfile + nginx.conf + script build
8. `deploy/k3s-medvision-web` — (repo k3s-fromOVHVps) manifests

**Chaque push de PR = demander confirmation à Yann d'abord** (règle projet) ; CI locale verte avant.

### Tests

- pytest : `tests/api/*` (endpoints, SSE via httpx ASGITransport, watcher avec S3 fake + subprocess mocké, session cache LRU, sample_browser) — gate diff-cover ≥ 80 % existant.
- front : Vitest (`ng test` builder Angular 20), specs SSE/store/overlay ; `ng build` = gate tsc strict.

## Vérification globale

1. Chantier 1 : 17 modèles visibles dans Streamlit prod (commandes ci-dessus).
2. Chantier 2 (fin) : ouvrir `ui.medvision...`, prédire sur upload + image dataset, overlays seg fluides ; puis **test de réactivité de bout en bout** : `dvc push` d'un modèle + `publish_model_manifest.sh` → sous ~60 s le toast "Nouveau modèle" apparaît sans refresh.
3. Docs : plan copié dans `docs/plans/`, entrée `ROADMAP.md`, `docs/SESSION-STATE.md`, tags images consignés.

## Hors scope

- Retrait de Streamlit (après validation de parité, session ultérieure).
- Auth Keycloak/oauth2-proxy sur medvision (évolution possible).
- Métriques manquantes en pod (stage DVC reports non tiré) — signalé, non traité.
- GPU / accélération inférence ; i18n anglais.
