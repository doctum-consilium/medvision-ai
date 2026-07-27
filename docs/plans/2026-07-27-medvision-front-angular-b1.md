# MedVision AI — reprise du chantier front Angular (B1) jusqu'au déploiement

## Context

Le dépôt `medvision-ai` est propre côté serveur : les 17 modèles ONNX tournent en
production (`medvision-ai:2026-07-18f`) et **l'API v2 est intégralement livrée et
déployée** — `src/api/routes/{problems,models,predict,images,reports,events}.py`,
montées sous le préfixe `/api` par `src/api/main.py:109`. Rien n'est à réécrire côté
serveur.

Ce qui manque, c'est **l'interface**. Le chantier s'était arrêté au socle, sur une
branche locale **jamais poussée** (`feat/front-socle-angular`, commit `ae34461`) :
Angular 19 standalone, design system maison (`frontend/src/styles.css`, thème clair /
sombre par `data-theme`), libellés français des trois écrans déjà rédigés
(`frontend/src/app/core/i18n/libelles.fr.ts`), types miroir de l'API
(`frontend/src/app/core/api/api.types.ts`). Aucun écran n'est branché :
`app.routes.ts` est un tableau vide et `app.component.ts` est encore le squelette
généré par `ng new`.

Deux conséquences fâcheuses de cet arrêt en plein vol :

1. Comme le répertoire de travail est resté sur une branche déjà fusionnée, `frontend/`
   ne contient plus sur le disque que `node_modules` (**394 Mo**) et `.vscode` — et le
   `.gitignore` de `main` **ne connaît ni Node ni Angular**. Un `git add -A` distrait
   committerait 394 Mo de dépendances. C'est le point que tu m'as signalé en premier.
2. Six fichiers de documentation traînent non suivis dans `docs/` (`handbook/`,
   `manual/`, `04-`, `10-`, `15-`, `16-`). Vérification faite : ce sont des **brouillons
   antérieurs** des chapitres qui vivent désormais dans
   `k3s-fromOVHVps/docs-portal/content/medvision/` (versions portail égales ou plus
   longues). Ils polluent le `git status` sans rien apporter.

Résultat visé : `ui.medvision.doctumconsilium.com` en ligne, cohabitant avec le
Streamlit historique (`app.medvision…`), avec les trois écrans (accueil, studio,
comparaison), les superpositions de segmentation réglables sans ré-inférence, et la
mise à jour temps réel par SSE quand un modèle arrive.

> **Note d'honnêteté** : avant que le mode plan ne s'active, la section Node/Angular
> a **déjà été écrite** dans `.gitignore` (branche locale `chore/gitignore-node-angular`,
> **non commitée**). Rien d'autre n'a été modifié. Si le plan est validé, cette édition
> devient la première étape ; sinon, `git checkout .gitignore` l'annule.

---

## Principe directeur

- **Zéro réécriture serveur.** Le front consomme l'API v2 telle qu'elle est. Toute
  divergence de schéma se corrige dans `api.types.ts`, pas dans FastAPI.
- **Outillage front assumé : Tailwind CSS v4 + Chart.js + `@ngrx/signals`.** Ces
  bibliothèques coûtent au bundle envoyé au navigateur, pas au nœud `apps-b` qui ne
  sert que des fichiers statiques via nginx — l'ordre de grandeur (Tailwind purgé à la
  compilation, Chart.js tree-shaké ≈ 70-80 Ko gzip, `@ngrx/signals` ≈ 15 Ko gzip) est
  sans commune mesure avec les 2 Gi du pod d'inférence.
- **Le design system existant n'est pas jeté.** `frontend/src/styles.css` reste la
  **source des tokens** (couleurs, rayons, ombres, thème clair/sombre par
  `data-theme`) ; Tailwind les consomme via `@theme inline { --color-accent:
  var(--accent); … }`, ce qui fait que les utilitaires (`bg-accent`, `text-ink`)
  changent de valeur **au runtime** quand on bascule le thème, sans recompilation.
  Tailwind apporte la mise en page et l'état de survol/focus ; les tokens restent
  définis en un seul endroit.
- **Le canvas fait le travail, pas le serveur.** `mask_prob_png` revient en
  probabilités (jamais binarisé) : le curseur de sensibilité re-seuille côté client,
  instantanément, sans ré-inférence.
- **Règle produit non négociable** : sur un problème `task_type === 'segmentation'`,
  n'afficher **ni prédiction, ni confiance, ni probabilités** — seulement le masque, la
  superposition, la carte de probabilité, la surface détectée, et la phrase de renvoi
  (`FR.studio.pasDeDiagnostic`). La tête de classification des U-Net annonçait NORMAL à
  1,000 de confiance sur des pneumonies manifestes ; la décision produit est tranchée.
- **Une branche par sujet, chaînées** (règle projet) : chaque PR se construit sur la
  précédente, jamais deux PR parallèles sur les mêmes fichiers.

---

## Surface des changements

### Étape 0 — remise d'aplomb (avant tout code)

- Copier ce plan dans `docs/plans/2026-07-27-medvision-front-angular-b1.md` (règle
  « Plan files » de `CLAUDE.md`) et l'inscrire dans `docs/plans/README.md`.
- Supprimer les six brouillons non suivis : `docs/handbook/`, `docs/manual/`,
  `docs/04-pipeline-ml-dvc.md`, `docs/10-inference-production.md`,
  `docs/15-securite-donnees.md`, `docs/16-limites-et-suite.md`.
  *Irréversible* (jamais commités) — mais superseded par le portail, vérifié fichier
  par fichier.

### PR 1 — `chore/gitignore-node-angular` (base `main`)

Un seul fichier : `.gitignore`. Section **Node / npm** (`node_modules/`, caches npm /
pnpm / yarn, journaux de debug, `.eslintcache`) et section **Angular** (`.angular/`,
`frontend/dist/`, `frontend/out-tsc/`, `frontend/tmp/`, `frontend/coverage/`,
`*.tsbuildinfo`), placées après la section des environnements virtuels, chacune
commentée sur le *pourquoi* (`npm ci` réinstalle à l'identique, ~400 Mo).
`build/` et `dist/` sont déjà couverts par la section Python — pas de doublon.

Mergeable seule et immédiatement : elle referme le trou de 394 Mo.

### PR 2 — `feat/front-socle-angular` (base : PR 1)

La branche existante, **rebasée** sur PR 1 (son hunk `.gitignore` de 5 lignes devient
redondant : le laisser tomber pendant le rebase), puis complétée.

**Mise en place de l'outillage** (`package.json` + `package-lock.json`) :

- `npm i -D tailwindcss @tailwindcss/postcss postcss` ; `.postcssrc.json` =
  `{"plugins": {"@tailwindcss/postcss": {}}}` (le CLI Angular le détecte seul) ;
  en tête de `styles.css` : `@import "tailwindcss";`, puis
  `@custom-variant dark (&:where([data-theme="dark"], [data-theme="dark"] *));` pour
  que `dark:` suive l'attribut déjà utilisé par le design system, et le bloc
  `@theme inline` qui expose les tokens existants aux utilitaires.
- `npm i @ngrx/signals` (version alignée sur Angular 19 → NgRx 19).
- `npm i chart.js` (v4, appelée directement — pas de wrapper à réaligner à chaque
  montée de version d'Angular).

**Code** :

- `app.config.ts` : ajouter `provideHttpClient(withFetch())`.
- `core/api/registre.service.ts`, `images.service.ts`, `prediction.service.ts`,
  `comparaison.service.ts` — clients `HttpClient` typés par `api.types.ts`, `baseUrl`
  relatif (`/api`) pour que nginx proxifie sans configuration d'environnement.
- `core/realtime/sse.service.ts` — `EventSource` sur `/api/events`, gestion du
  `heartbeat` (25 s), reconnexion à backoff exponentiel plafonné, et **resynchronisation
  par `GET /api/models/version`** à la reconnexion (on ne recharge le registre que si la
  version a bougé). Zéro polling.
- `core/state/registre.store.ts` — **SignalStore** `@ngrx/signals` en
  `{ providedIn: 'root' }` : `withState` (version, problèmes, chargement, erreur),
  `withComputed` (compteurs de modèles disponibles, liste triée pour l'accueil),
  `withMethods` (`recharger()`, appelé au démarrage et sur événement SSE
  `models_updated`).
- `shared/graphe-barres.component.ts` — composant `canvas` autonome pilotant Chart.js,
  n'enregistrant que ce qu'il utilise (`BarController`, `BarElement`, `CategoryScale`,
  `LinearScale`, `Tooltip`) pour garder le tree-shaking efficace ; couleurs lues dans
  les tokens CSS pour suivre le thème.
- `core/theme/theme.service.ts` — `data-theme` sur `<html>`, préférence système au
  premier chargement puis choix mémorisé (`localStorage`) ; il notifie les graphes
  pour qu'ils relisent leurs couleurs.
- Coquille applicative : en-tête (titre, sous-titre, pastille temps réel
  connecté/reconnexion, bouton thème), navigation trois onglets, bandeau
  `FR.app.disclaimer` permanent.
- Écran **accueil** : une carte par problème (libellé, `models_available / models_total`,
  nombre de catégories, mention « délimite des zones » sur les segmentations), boutons
  *Analyser* / *Comparer*, toast `FR.app.nouveauxModeles` sur événement SSE.
- `app.routes.ts` : routes `''` (accueil), `'studio'`, `'comparaison'` en `loadComponent`.
- `.github/workflows/ci-front.yml` — déclenché sur `frontend/**` : Node 22, `npm ci`,
  `ng build` (le mode strict TypeScript **est** le garde-fou), `ng test --watch=false
  --browsers=ChromeHeadless` (Karma/Jasmine déjà en devDependencies, Chrome préinstallé
  sur `ubuntu-latest`). Ajouter le même build dans `scripts/ci_local.sh` pour que le
  hook `pre-push` l'attrape.
- **Budgets de bundle** (`angular.json`) : les seuils générés par `ng new` (500 Ko
  d'avertissement) seront dépassés une fois Chart.js et le store embarqués. Les relever
  **consciemment** — 900 Ko d'avertissement / 1,4 Mo d'erreur sur le bundle initial — et
  consigner la taille réelle mesurée après le premier `ng build` dans le compte rendu.
  Un budget qu'on relève sans regarder le chiffre ne protège plus de rien.

### PR 3 — `feat/front-studio-prediction` (base : PR 2)

- Sélecteur de type d'analyse, puis deux sources d'image exclusives : dépôt par
  glisser-déposer, ou banque d'exemples (`GET /api/images` : filtres par classe,
  recherche, pagination 12/page, quatre « recommandés » mis en avant ; vignettes via
  `GET /api/images/{id}/file?thumb=true`).
- Sélection multi-modèles (cases à cocher, tout sélectionner / désélectionner), appel
  `POST /api/predict` en **une seule requête** (multipart `file` **ou** `sample_id`,
  `model_names` répété).
- Rendu des résultats **par modèle**, avec le champ `error` affiché en carte dégradée
  sans faire tomber les autres (l'API rapporte les erreurs par modèle exprès).
- Classification : classe prédite, jauge de confiance, et **graphe de probabilités par
  catégorie** (`<app-graphe-barres>`, Chart.js).
  **Segmentation : aucun de ces trois blocs** — masque, superposition, carte de
  probabilité, surface détectée (`mask_foreground_ratio`), phrase de renvoi.
- `shared/overlay-canvas.component.ts` — deux `<canvas>` superposés : image
  prétraitée (`preprocessed_png`) dessous, masque re-seuillé dessus à partir de
  `mask_prob_png` décodé en `ImageData` ; curseurs **sensibilité** (0→1) et **opacité**
  purement client. Trois vues : Superposition / Masque / Probabilités.

### PR 4 — `feat/front-comparaison-metriques` (base : PR 3)

Écran comparaison sur `GET /api/compare?problem=…` : tableau triable par colonne
(modèle, état prêt/absent, taille, date de mise à jour, métriques), doublé d'un
**graphe Chart.js** (barres groupées, une série par métrique) pour lire les écarts
d'un coup d'œil, et message `FR.comparaison.aucuneMesure` quand le problème n'expose
pas de métriques.

### PR 5 — `build/docker-frontend` (base : PR 4)

- `docker/frontend.Dockerfile` — multi-étapes `node:22-alpine` (`npm ci` + `ng build`)
  → `nginx:1.27-alpine` ne recevant que `dist/`.
- `docker/nginx-frontend.conf` — `try_files $uri $uri/ /index.html` (SPA),
  proxy `/api` → `medvision-api:8000`, et **bloc dédié `/api/events`** avec
  `proxy_buffering off` + `proxy_read_timeout 3600` + `proxy_http_version 1.1`
  (sans quoi le SSE est bufferisé et l'interface paraît figée).
- `scripts/build-and-push-web.sh` — connexion ECR, build, push. **Prérequis à
  exécuter une fois** : `aws ecr create-repository --repository-name platform/medvision-web`
  (les dépôts ECR ne sont pas gérés par Terraform ici, vérifié).
- Tag `2026-07-27` (suffixes `b`, `c`… seulement après un vrai échec de déploiement).

### PR 6 — dépôt `k3s-fromOVHVps`, branche `deploy/medvision-web`

Modifier **le template ET le rendu** (la source de vérité est le template) :
`deploy/platform/30-medvision.template.yaml` et
`rendered-k3s-manifests/30-medvision.yaml`.

- Deployment + Service `medvision-web` (nginx, `nodeSelector: apps-b`, requests
  50m/64Mi, `ecr-pull-secret`).
- Ingress : nouvel hôte `ui.medvision.__ROOT_DOMAIN__` dans `tls.hosts` et `rules`,
  plus l'annotation `nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"` pour que
  le SSE survive à l'ingress.
- **Correctif indispensable** : le pod `medvision-api` ne monte **que**
  `medvision-model-artifacts` — le PVC `medvision-raw-data` lui manque, donc
  `GET /api/images` ne verrait aucun exemple en production. Ajouter le montage
  `/app/data/raw` sur l'API (RWO, même nœud `apps-b` que le Streamlit qui le monte
  déjà — contrainte respectée).
- DNS : `scripts/ovh_dns_sync_k3s_zone.sh` découvre les hôtes depuis les manifests
  rendus. Lancer d'abord en `DNS_SYNC_DRY_RUN=true`, vérifier qu'il ne propose que la
  **création** de `ui.medvision`, puis appliquer. *(Il n'y a pas de wildcard DNS et le
  script supprime les enregistrements A divergents : le dry-run n'est pas optionnel.)*
- Rappel de script à honorer : mettre à jour le `TAG` par défaut de
  `scripts/redeploy-k3s.sh` (`medvision-ai`) — il est resté à `2026-07-18b` alors que la
  production tourne en `2026-07-18f`.

---

## Vérification

**En local, avant tout push** (règle CI locale verte) :

```bash
cd frontend && npm ci && npm run build && npx ng test --watch=false --browsers=ChromeHeadless
cd .. && bash scripts/ci_local.sh
```

**Bout en bout, contre l'API de production** (le front en dev, l'API distante) : lancer
`ng serve` avec un proxy `/api` → `https://api.medvision.doctumconsilium.com`, puis
vérifier dans l'ordre :

1. L'accueil affiche **4 problèmes** et **17 modèles disponibles** au total
   (5 + 8 + 1 + 1) ; la pastille temps réel passe à « connecté ».
2. Studio, chest X-ray : une image de la banque + trois modèles cochés → trois cartes de
   résultat, probabilités cohérentes.
3. Studio, `brain_tumor_segmentation` : **aucune** prédiction ni confiance affichée ;
   le curseur de sensibilité modifie le masque **instantanément**, sans requête réseau
   (à confirmer dans l'onglet Réseau du navigateur : zéro appel pendant le glissement).
4. Un modèle volontairement absent du PVC → carte d'erreur isolée, les autres résultats
   restent lisibles.
5. Comparaison : tri par colonne, cohérent avec `GET /api/compare`.
6. Coupure réseau simulée → la pastille passe en « reconnexion… », puis le registre se
   resynchronise sans rechargement de page.

**Après déploiement** :

```bash
kubectl -n medvision get pods -o wide
kubectl -n medvision exec deploy/medvision-api -- ls /app/data/raw   # le PVC est bien monté
curl -sI https://ui.medvision.doctumconsilium.com | head -3          # 200 + certificat valide
curl -sN https://ui.medvision.doctumconsilium.com/api/events | head -2  # heartbeat SSE non bufferisé
```

Puis contrôle visuel sur `ui.medvision.doctumconsilium.com`, et vérification que
`app.medvision…` (Streamlit) fonctionne toujours.

**Rollback** : `kubectl -n medvision delete deploy/svc medvision-web` + retirer l'hôte
de l'ingress. Le Streamlit et l'API ne sont pas touchés (hors ajout du montage PVC, qui
est un correctif indépendant et sans risque).

**Documentation de fin** (gros chantier → doc lourde en fin de session) : entrée datée
en tête du journal de `ROADMAP.md`, bloc handoff en tête de `docs/SESSION-STATE.md`
(tags d'images inclus), note de complétion dans
`docs/plans/2026-07-18-handoff-medvision.md`, chapitres du portail
(`k3s-fromOVHVps/docs-portal/content/medvision/03-architecture-logicielle.md` et
`10-inference-production.md`) mis à jour avec l'existence du front.

---

## Hors scope

- **Retrait de Streamlit** — il reste en ligne sur `app.medvision…` tant que la parité
  n'est pas validée par toi.
- **Authentification Keycloak / oauth2-proxy** sur `ui.medvision…` — l'interface reste
  publique comme l'actuelle.
- **Activation du watcher DVC** (`MEDVISION_WATCH_ENABLED=1`) — livré mais désactivé ;
  l'interface sait déjà réagir au SSE, l'activation reste ta décision.
- **Réactivation des deux `convnexttiny`** — leur ONNX est invalide dès l'export
  (bug tf2onnx/ConvNeXt), il faut un ré-export sur le PC ML.
- **Métriques absentes en pod** (le stage DVC `reports` n'est pas tiré) — connu, non
  traité ici ; l'écran comparaison affichera simplement les métriques disponibles.
- **Anglais / i18n** — la v1 est francophone, `libelles.fr.ts` est prêt pour une
  traduction ultérieure.
- **Dette d'un autre dépôt** (signalée au démarrage, hors de ce chantier) :
  `doctum-trading-platform` n'a pas d'entrée `ROADMAP.md` depuis le 2026-07-21 et trois
  plans du 26-27 juillet n'existent que sur cette machine. À traiter dans une session
  dédiée à ce dépôt.
