# Passage de relais — alertes Dependabot de medvision (2026-11-13)

## En une phrase

Ce matin, medvision-ai comptait **778 alertes Dependabot ouvertes**. La PR #44 a réglé tout le Python
et il n'en restait que **99**, toutes dans le front (`frontend/package-lock.json`). La présente PR
traite ces 99 alertes et retire pip de l'image Python.

## Le chemin parcouru

```text
 778 alertes ouvertes (matin du 2026-11-13)
   │
   │  PR #44 — dépendances Python + MLflow 3 (déployée le 2026-11-13)
   ▼
  99 alertes ouvertes, toutes dans frontend/package-lock.json
     (3 critiques, 43 hautes, 42 moyennes, 11 basses)
   │
   │  cette PR — npm audit fix, puis Angular 19 → 20.3
   ▼
  npm audit : 63 vulnérabilités → 21 moyennes, plus aucune haute ni critique
  osv-scanner sur le lock : 122 → 3 (glob, minimatch, uuid : outils de build)
```

Au total, GitHub a vu passer 824 alertes sur ce dépôt : 697 sont corrigées, 28 ont été fermées
automatiquement par Dependabot et 99 étaient encore ouvertes avant cette PR.

## Ce qu'a fait la PR #44 (Python, MLflow 3)

- Les dépendances Python de l'image et des environnements d'entraînement ont été montées jusqu'aux
  versions corrigées : Python 3.11, streamlit 1.67, fastapi 0.162, starlette 1.10, mlflow 3.18.
- **Le serveur MLflow est passé de 2.20.3 à 3.18.0.** La procédure complète, retour arrière compris,
  est dans `docs/MLFLOW-3-MIGRATION.md`.
- Déployée le 2026-11-13. En production, le serveur MLflow tourne avec :
  - **1 worker et une limite mémoire de 1 Gio.** Avec 2 workers et 768 Mi, comme le prévoyait la
    doc de migration, le pod mourait au démarrage, faute de mémoire.
  - `--allowed-hosts` : sans cette option, MLflow 3 répond 403 à l'agent RL et au portail.
  - `MLFLOW_SERVER_ENABLE_JOB_EXECUTION=false` : MLflow 3 lancerait sinon 8 processus de jobs
    inutiles ici.

## Ce que fait cette PR

### 1. Le front : de 99 alertes à presque rien

Le front est une application Angular. Elle est compilée dans l'image `medvision-web`, puis servie
en fichiers statiques par nginx. Seuls les paquets `@angular/*` partent dans le navigateur. Tout le
reste (node-forge, tar, vite, webpack-dev-server…) ne sert qu'à construire.

1. **`npm audit fix`, sans `--force`.** Seules les dépendances indirectes montent, dans les plages
   déjà permises : node-forge, fast-uri, ip-address, follow-redirects, js-yaml… npm audit passe de
   63 vulnérabilités (4 critiques, 27 hautes) à 47 (2 critiques, 14 hautes).
2. **Angular 19 → 20.3.** Le dernier Angular 19 publié, 19.2.25, est encore concerné par
   11 avis sur `@angular/core`, `common`, `compiler` et `router`, dont 7 hauts. Aucune version 19.x
   ne les corrige : la branche 19 n'est plus maintenue. Exemples d'avis hauts :
   - GHSA-jj27-h5hq-8x99 : XSS via les attributs d'événement en i18n ;
   - GHSA-rgjc-h3x7-9mwg : DOM clobbering à l'hydratation ;
   - GHSA-48r7-hpm6-gfxm : déni de service par `formatDate` ;
   - GHSA-62vg-58rm-qff7 : déni de service du routeur côté serveur.

   `ng update` passe le framework en 20.3.35, la CLI en 20.3.43, TypeScript en 5.9.3 et
   `@ngrx/signals` en 20.1.0. Les migrations automatiques n'ont modifié aucun fichier source.

Il reste **21 vulnérabilités moyennes** selon npm audit, soit 3 selon osv-scanner : glob,
minimatch et uuid. Elles sont tirées par la CLI Angular et le serveur de développement, et
n'existent pas dans l'image servie. Pour les supprimer, il faudrait passer à Angular 22.

Vérifié :
- `npm run build` passe ;
- les 30 tests du front sont verts (`npx ng test --watch=false --browsers=ChromeHeadless`) ;
- l'image `docker/frontend.Dockerfile` se construit (`npm ci` sous node:22) ;
- nginx sert `index.html`, un fichier JS et une route profonde (`/studio`) ;
- dans Chromium, l'application démarre avec `ng-version="20.3.35"`.

### 2. L'image Python : pip retiré

pip ne sert qu'à construire l'image, mais il y restait deux fois : le paquet installé et la roue
gardée par `ensurepip`. Ce pip 24.0 porte 12 vulnérabilités, donc 24 dans l'image. La dernière
instruction `RUN` de `docker/Dockerfile` désinstalle pip et supprime cette roue.

La même image fait tourner l'API, Streamlit et le serveur MLflow. Vérifié sur la nouvelle image :
- Streamlit (le `CMD` par défaut) répond 200 sur `/_stcore/health` et sur sa page ;
- l'API répond 200 sur `/health`, et son `/openapi.json` est identique à celui d'avant ;
- `mlflow server --workers 1`, avec `MLFLOW_SERVER_ENABLE_JOB_EXECUTION=false`, répond 200 sur
  `/health` et liste ses expériences ;
- `dvc --version` répond 3.59.2. Avec des identifiants AWS factices et sans réseau,
  l'entrypoint fait son `git init` et tente son `dvc pull` : l'échec est le même qu'avec l'ancienne
  image (S3 injoignable), pas une erreur liée à pip.

Vulnérabilités PyPI de l'image : **33 → 9**. Restent setuptools 79.0.1 et ses paquets embarqués
(7), qui viennent de l'image de base, et diskcache 5.6.3 (2).

## Comment mesurer

```bash
# Alertes Dependabot ouvertes, par gravité puis par fichier
gh api --paginate "/repos/doctum-consilium/medvision-ai/dependabot/alerts?state=open&per_page=100" \
  --jq '.[] | [.security_advisory.severity, .dependency.manifest_path, .dependency.package.name] | @tsv' \
  > alertes.tsv
cut -f1 alertes.tsv | sort | uniq -c
cut -f2 alertes.tsv | sort | uniq -c

# Le front, deux avis
(cd frontend && npm audit)
osv-scanner scan source --config osv-scanner.toml -L frontend/package-lock.json

# Une image construite (contexte = racine du dépôt)
podman build -t localhost/medvision-ai:essai -f docker/Dockerfile .
podman save -o ~/.cache/socle/mv.tar localhost/medvision-ai:essai
osv-scanner scan image --archive ~/.cache/socle/mv.tar --format json > mv-osv.json
rm ~/.cache/socle/mv.tar
```

Le `.tar` d'une image pèse plusieurs gigaoctets. Le poser sous `~/.cache`, jamais sous `/tmp` :
`/tmp` est un tmpfs plafonné.

## Ce qui reste sous surveillance

| Sujet | Où | Pourquoi ce n'est pas corrigé |
|---|---|---|
| TensorFlow 2.16.1 → protobuf 4.25.9 (PYSEC-2026-1805 / GHSA-7gcm-g887-7qv7, haute) | `requirements-train.txt`, poste d'entraînement seulement | TF 2.16 exige protobuf < 5, et le correctif est en 5.29.6. Jamais dans l'image servie |
| Couche système Debian de l'image | `python:3.11-slim`, plus build-essential, git, libgl | Le correctif annoncé n'existe que dans Debian testing ou unstable. Un `apt-get upgrade` ne change presque rien (mesuré : 209 → 206 sur la base nue). Un simple rebuild le prendra quand Debian le publiera |
| setuptools 79.0.1, diskcache 5.6.3 | image `medvision-ai` | setuptools vient de l'image de base ; diskcache n'a pas de version corrigée |
| glob, minimatch, uuid (moyennes) | outils de build du front | Correctif seulement dans Angular 22 ; absents de l'image servie |
| **Fin de support d'Angular 20** | front | D'après la politique Angular (18 mois par version majeure), la v20 sort du support long vers la fin novembre 2026, à vérifier sur angular.dev/reference/releases. Après cette date, plus aucun correctif 20.x |

## Prochaines étapes

1. Fusionner cette PR une fois la CI verte.
2. Reconstruire et déployer `medvision-web` (`scripts/build-and-push-web.sh`) et `medvision-ai`,
   puis suivre la procédure de suivi des versions d'images de `CLAUDE.md` : `IMAGE-VERSIONS.md`,
   gabarit **et** rendu k3s, ROADMAP, SESSION-STATE, tag par défaut des scripts.
3. Recompter les alertes Dependabot après la fusion. Attendu : seulement les 3 moyennes du build
   du front.
4. Préparer le passage à Angular 21 ou 22 avant la fin du support de la v20. Cette montée retire
   aussi les 3 dernières alertes.
