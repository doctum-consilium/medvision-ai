# Passer le serveur MLflow de 2.20.3 à 3.18.0

> Rédigé le **2026-11-13** avec la montée de sécurité des dépendances (MLflow 2.20.3 était visé
> par 58 identifiants OSV). Image actuelle : `medvision-ai:2026-07-18f`.
> Image cible : celle construite depuis cette branche, notée `<NOUVEAU_TAG>` ci-dessous.

## Ce qui change pour le serveur

Le Deployment `medvision-mlflow` utilise la même image que l'API et l'UI. Il lance
`mlflow server` sur une base SQLite posée sur le PVC `medvision-mlflow-store`
(`/app/mlflow/mlflow.db`). Un client extérieur y écrit : l'agent RL de
`doctum-trading-platform` (`RL_AGENT_MLFLOW_TRACKING_URI=http://medvision-mlflow.medvision.svc.cluster.local:5000`,
client `mlflow==2.18.0`). Le portail `products` affiche l'UI sous `/tools/mlflow`.

Vérifié au poste (Python 3.11, base créée par 2.20.3, client 2.18.0) :

| Point | Constat |
|---|---|
| Options actuelles (`--host`, `--port`, `--backend-store-uri`, `--default-artifact-root`, `--serve-artifacts`) | toujours valides en 3.18 |
| Schéma de la base | 3.18 le migre **tout seul au démarrage** (même chaîne alembic que `mlflow db upgrade`) |
| Retour arrière | 2.20.3 **refuse** une base migrée (`Can't locate revision identified by 'f4a9b2c7d1e6'`) : il faut restaurer le fichier |
| Données | expérience, run, métrique, artefact et modèle enregistré créés en 2.20.3 relus en 3.18 ; le client 2.18.0 écrit un nouveau run et une version de modèle |
| **En-tête Host** | 3.18 filtre l'en-tête Host. Sans `--allowed-hosts`, l'API répond **403** à `medvision-mlflow.medvision.svc.cluster.local:5000` (agent RL) et à `products.doctumconsilium.com` (portail) ; `/health` reste à 200, la sonde ne voit rien |
| **Mémoire** | 3.18 lance 8 processus `huey_consumer` (exécution de jobs GenAI, inutile ici) : 2,5 Gio de PSS contre 783 Mio en 2.20.3. La limite du pod est 768 Mi. Avec `MLFLOW_SERVER_ENABLE_JOB_EXECUTION=false` et `--workers 2` : 600 Mio |

Il faut donc changer le Deployment en plus de l'image : ajouter l'option `--allowed-hosts`,
l'option `--workers 2` et la variable `MLFLOW_SERVER_ENABLE_JOB_EXECUTION=false`. Mettre à jour le gabarit **et** le
rendu dans `k3s-fromOVHVps` (`deploy/platform/30-medvision.template.yaml`,
`rendered-k3s-manifests/30-medvision.yaml`) :

```yaml
          args:
            - mlflow
            - server
            - --host
            - "0.0.0.0"
            - --port
            - "5000"
            - --backend-store-uri
            - sqlite:////app/mlflow/mlflow.db
            - --default-artifact-root
            - /app/artifacts/models/mlflow
            - --serve-artifacts
            - --workers
            - "2"
            - --allowed-hosts
            - "medvision-mlflow.medvision.svc.cluster.local:5000,medvision-mlflow.medvision:5000,medvision-mlflow:5000,products.doctumconsilium.com,localhost:*,127.0.0.1:*"
          env:
            - name: MLFLOW_SERVER_ENABLE_JOB_EXECUTION
              value: "false"
```

`localhost:*` garde le `kubectl port-forward` utilisé depuis le poste d'entraînement.

## Attention à `scripts/redeploy-k3s.sh`

Le script change l'image des **trois** Deployments d'un coup, MLflow compris. Le pod 3.18
migrerait alors la base sans sauvegarde, pendant que l'ancien pod 2.20.3 tourne encore sur
le même fichier (RollingUpdate). Faire **d'abord** les étapes 1 à 4 ci-dessous, puis
seulement le script (ou `kubectl set image` sur l'API et l'UI).

## Migration

```bash
NS=medvision
OLD=113301685315.dkr.ecr.eu-west-3.amazonaws.com/platform/medvision-ai:2026-07-18f
NEW=113301685315.dkr.ecr.eu-west-3.amazonaws.com/platform/medvision-ai:<NOUVEAU_TAG>
SAUV=mlflow.db.bak-2.20.3-$(date +%Y%m%d-%H%M)
```

**1. Sauvegarde à chaud**, dans le pod 2.20.3 qui tourne (l'API de sauvegarde de SQLite donne
une copie cohérente même pendant des écritures), puis copie sur le poste :

```bash
kubectl -n $NS exec deploy/medvision-mlflow -- python -c \
  "import sqlite3; s=sqlite3.connect('/app/mlflow/mlflow.db'); d=sqlite3.connect('/app/mlflow/$SAUV'); s.backup(d); d.close()"
POD=$(kubectl -n $NS get pod -l app=medvision-mlflow -o jsonpath='{.items[0].metadata.name}')
kubectl -n $NS cp "$POD:/app/mlflow/$SAUV" "./$SAUV"
python3 -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); print(c.execute('pragma integrity_check').fetchone(), c.execute('select count(*) from runs').fetchone())" "./$SAUV"
```

Attendu : `('ok',)` et le nombre de runs. La copie reste aussi sur le PVC, à côté de la base.
La sauvegarde hebdomadaire `volumes-backup` (91-backups) couvre aussi ce PVC, mais elle peut
dater de six jours.

**2. Arrêt du serveur**, pour qu'aucun pod 2.20.3 n'écrive pendant la migration :

```bash
kubectl -n $NS scale deploy/medvision-mlflow --replicas=0
kubectl -n $NS wait --for=delete pod -l app=medvision-mlflow --timeout=120s
```

Pendant la coupure, l'agent RL perd son suivi d'expériences (le tracker est sans effet si
MLflow est désactivé, mais il échoue s'il est activé et que le serveur ne répond pas).
Choisir un moment sans entraînement en cours.

**3. Nouvelle image et nouveaux réglages**, puis redémarrage :

```bash
kubectl -n $NS set image deploy/medvision-mlflow mlflow=$NEW
kubectl -n $NS set env deploy/medvision-mlflow MLFLOW_SERVER_ENABLE_JOB_EXECUTION=false
kubectl -n $NS patch deploy medvision-mlflow --type=json -p='[
  {"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--workers"},
  {"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"2"},
  {"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--allowed-hosts"},
  {"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"medvision-mlflow.medvision.svc.cluster.local:5000,medvision-mlflow.medvision:5000,medvision-mlflow:5000,products.doctumconsilium.com,localhost:*,127.0.0.1:*"}]'
kubectl -n $NS scale deploy/medvision-mlflow --replicas=1
kubectl -n $NS rollout status deploy/medvision-mlflow --timeout=300s
kubectl -n $NS logs deploy/medvision-mlflow | grep -E "Updating database tables|Uvicorn running"
```

**4. Migration explicite du schéma, et vérifications.** Le serveur l'a déjà faite au
démarrage ; la commande la confirme (idempotente, sortie 0) :

```bash
kubectl -n $NS exec deploy/medvision-mlflow -- mlflow db upgrade sqlite:////app/mlflow/mlflow.db
kubectl -n $NS exec deploy/medvision-mlflow -- mlflow --version            # 3.18.0
# Depuis un pod du namespace doctum-trading : même en-tête Host que l'agent RL, attendu 200
kubectl -n doctum-trading run mlflow-check --rm -i --restart=Never --image=curlimages/curl:8.11.1 -- \
  curl -s -o /dev/null -w '%{http_code}\n' \
  'http://medvision-mlflow.medvision.svc.cluster.local:5000/api/2.0/mlflow/experiments/search?max_results=5'
kubectl -n $NS top pod -l app=medvision-mlflow                               # sous 768 Mi
```

Puis ouvrir `https://products.doctumconsilium.com/tools/mlflow/` : les expériences
Medvision et `doctum-trading` doivent s'afficher.

## Retour arrière (vers `2026-07-18f`)

2.20.3 ne lit pas une base migrée et ne connaît pas `--allowed-hosts` : on restaure le
fichier **et** les anciens réglages. Les runs écrits depuis la
migration sont perdus pour 2.20.3 (ils restent dans `mlflow.db.v3`).

```bash
# a. Depuis le pod 3.18 encore en marche : mettre la sauvegarde à la place de la base
kubectl -n $NS exec deploy/medvision-mlflow -- sh -c \
  "cp /app/mlflow/mlflow.db /app/mlflow/mlflow.db.v3 && cp /app/mlflow/$SAUV /app/mlflow/mlflow.db"
#    (si la copie du PVC a disparu : kubectl cp ./$SAUV <pod>:/app/mlflow/mlflow.db)
# b. Arrêter, remettre l'image et les arguments d'avant, redémarrer
kubectl -n $NS scale deploy/medvision-mlflow --replicas=0
kubectl -n $NS wait --for=delete pod -l app=medvision-mlflow --timeout=120s
kubectl -n $NS set image deploy/medvision-mlflow mlflow=$OLD
kubectl -n $NS set env deploy/medvision-mlflow MLFLOW_SERVER_ENABLE_JOB_EXECUTION-
kubectl -n $NS patch deploy medvision-mlflow --type=json -p='[
  {"op":"replace","path":"/spec/template/spec/containers/0/args","value":
   ["mlflow","server","--host","0.0.0.0","--port","5000",
    "--backend-store-uri","sqlite:////app/mlflow/mlflow.db",
    "--default-artifact-root","/app/artifacts/models/mlflow","--serve-artifacts"]}]'
kubectl -n $NS scale deploy/medvision-mlflow --replicas=1
kubectl -n $NS rollout status deploy/medvision-mlflow --timeout=300s
kubectl -n $NS exec deploy/medvision-mlflow -- mlflow --version            # 2.20.3
```

Ce retour arrière a été joué au poste : la sauvegarde 2.20.3 restaurée, le serveur 2.20.3
redémarre et relit le modèle enregistré.

## Après la migration

Suivre la procédure de `docs/IMAGE-VERSIONS.md` (tableau, manifests gabarit et rendu,
`ROADMAP.md`, `docs/SESSION-STATE.md`, tag par défaut de `scripts/redeploy-k3s.sh`).
Garder la sauvegarde au moins jusqu'au prochain `volumes-backup`.
