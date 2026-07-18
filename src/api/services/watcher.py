"""Watcher DVC : détecte les nouveaux modèles poussés dans S3 et les tire.

Problème résolu : le `dvc.lock` du pod est FIGÉ dans l'image Docker — un
`dvc push` depuis le poste d'entraînement ne rendait les nouveaux modèles
visibles qu'après un rebuild + redéploiement complet. Ce watcher rend la
chaîne réactive :

1. le poste d'entraînement publie son dvc.lock frais dans S3 après chaque
   push (scripts/publish_model_manifest.sh) ;
2. toutes les `MEDVISION_WATCH_INTERVAL_S` secondes, le watcher fait un
   HEAD S3 de ce manifeste (1 requête légère) et compare l'ETag ;
3. si l'ETag a changé : télécharge le lock, remplace celui du pod, lance
   `dvc pull convert_to_onnx`, vide le cache de sessions ONNX, rafraîchit
   le registre versionné et diffuse `models_updated` en SSE ;
4. en cas d'échec : backoff exponentiel, l'API continue de servir les
   modèles déjà présents (jamais de crash).
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("medvision.watcher")


@dataclass
class WatcherConfig:
    """Configuration du watcher, lue depuis l'environnement (ConfigMap k8s).

    Attributes:
        enabled: Interrupteur global (OFF en CI et dans les tests).
        interval_s: Période du HEAD S3 (60 s = négligeable pour le VPS).
        manifest_s3_uri: URI S3 du dvc.lock publié par l'entraînement.
        dvc_lock_path: Emplacement du dvc.lock DANS le pod.
        pull_timeout_s: Garde-fou sur la durée d'un dvc pull.
    """

    enabled: bool = True
    interval_s: float = 60.0
    manifest_s3_uri: str = "s3://platform-medvision-dvc-artifacts/models/.meta/dvc.lock"
    dvc_lock_path: Path = Path("dvc.lock")
    pull_timeout_s: float = 600.0

    @classmethod
    def from_env(cls) -> WatcherConfig:
        """Construit la config depuis les variables d'environnement."""
        return cls(
            enabled=os.getenv("MEDVISION_WATCH_ENABLED", "0") == "1",
            interval_s=float(os.getenv("MEDVISION_WATCH_INTERVAL_S", "60")),
            manifest_s3_uri=os.getenv(
                "MEDVISION_MANIFEST_S3_URI",
                "s3://platform-medvision-dvc-artifacts/models/.meta/dvc.lock",
            ),
            dvc_lock_path=Path(os.getenv("MEDVISION_DVC_LOCK_PATH", "dvc.lock")),
            pull_timeout_s=float(os.getenv("MEDVISION_PULL_TIMEOUT_S", "600")),
        )


def _split_s3_uri(uri: str) -> tuple[str, str]:
    """Découpe s3://bucket/clé en (bucket, clé).

    Raises:
        ValueError: URI mal formée (pas de schéma s3:// ou clé vide).
    """
    if not uri.startswith("s3://"):
        raise ValueError(f"URI S3 invalide : {uri}")
    bucket, _, key = uri[len("s3://") :].partition("/")
    if not bucket or not key:
        raise ValueError(f"URI S3 invalide : {uri}")
    return bucket, key


class ModelWatcher:
    """Boucle asyncio qui surveille le manifeste S3 et rafraîchit les modèles.

    Les appels boto3 (bloquants) passent par `run_in_executor` pour ne pas
    geler l'event loop qui sert les requêtes HTTP.
    """

    def __init__(self, app_state, config: WatcherConfig | None = None, s3_client=None) -> None:
        """Initialise le watcher.

        Args:
            app_state: `app.state` FastAPI (registry_state, session_cache,
                image_index, broadcaster).
            config: Configuration (défaut : depuis l'environnement).
            s3_client: Client S3 injecté par les tests (défaut : boto3).
        """
        self._state = app_state
        self._config = config or WatcherConfig.from_env()
        self._s3_client = s3_client
        self._last_etag: str | None = None
        self._task: asyncio.Task | None = None
        self._backoff_s = self._config.interval_s
        self.status = "disabled" if not self._config.enabled else "starting"

    # ── Cycle de vie ───────────────────────────────────────────────────────

    def start(self) -> None:
        """Démarre la boucle en tâche de fond (no-op si désactivé)."""
        if not self._config.enabled:
            logger.info("Watcher DVC désactivé (MEDVISION_WATCH_ENABLED != 1).")
            return
        self._task = asyncio.get_running_loop().create_task(self._run())

    async def stop(self) -> None:
        """Arrête proprement la boucle (shutdown FastAPI)."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    # ── Boucle principale ──────────────────────────────────────────────────

    async def _run(self) -> None:
        """Boucle infinie : HEAD S3 → (si changement) pull + refresh + SSE."""
        self.status = "running"
        while True:
            try:
                await self.check_once()
                self._backoff_s = self._config.interval_s  # succès → cadence normale
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Backoff exponentiel plafonné : S3 indisponible ou pull qui
                # échoue ne doivent PAS spammer ni tuer l'API.
                self._backoff_s = min(self._backoff_s * 2, 300.0)
                logger.warning("Watcher DVC : %s — prochain essai dans %.0f s", exc, self._backoff_s)
            await asyncio.sleep(self._backoff_s)

    async def check_once(self) -> bool:
        """Un cycle de surveillance ; retourne True si des modèles ont été tirés.

        Séparé de la boucle pour être testable sans temporisation.
        """
        etag = await self._head_manifest_etag()
        if etag is None:
            # Manifeste pas encore publié : veille silencieuse (log au 1er tour).
            if self._last_etag is None:
                logger.info("Manifeste S3 absent (%s) — veille.", self._config.manifest_s3_uri)
            return False
        if etag == self._last_etag:
            return False

        first_sync = self._last_etag is None
        logger.info("Nouveau manifeste DVC détecté (ETag %s) — dvc pull…", etag)
        await self._download_manifest()
        await self._dvc_pull()
        self._last_etag = etag

        # Invalidation TOTALE : sessions ONNX (fichiers remplacés) + index
        # d'images (de nouveaux datasets peuvent accompagner les modèles).
        self._state.session_cache.clear()
        self._state.image_index.invalidate()
        version, newly_available = self._state.registry_state.refresh()

        # Au premier tour (démarrage du pod), le pull confirme l'état initial :
        # on ne notifie pas « nouveaux modèles » pour des modèles déjà là.
        if not first_sync or newly_available:
            await self._state.broadcaster.publish(
                "models_updated",
                {
                    "version": version,
                    "changed": newly_available,
                    "at": self._state.registry_state.refreshed_at,
                },
            )
        logger.info("Modèles synchronisés (version %s, nouveaux : %s)", version, newly_available)
        return True

    # ── Primitives S3 / DVC ────────────────────────────────────────────────

    def _client(self):
        """Client S3 (boto3 importé paresseusement : absent des CI légères)."""
        if self._s3_client is None:
            import boto3  # noqa: PLC0415 — lazy import intentionnel

            self._s3_client = boto3.client("s3")
        return self._s3_client

    async def _head_manifest_etag(self) -> str | None:
        """ETag du manifeste S3, None s'il n'existe pas encore."""
        bucket, key = _split_s3_uri(self._config.manifest_s3_uri)
        loop = asyncio.get_running_loop()

        def _head() -> str | None:
            client = self._client()
            try:
                return client.head_object(Bucket=bucket, Key=key)["ETag"]
            except Exception as exc:
                # boto3 lève ClientError 404 si absent — on distingue ce cas
                # (veille normale) des vraies erreurs (propagées).
                code = getattr(getattr(exc, "response", None), "get", lambda *_: None)("Error")
                if code and code.get("Code") in {"404", "NoSuchKey", "NotFound"}:
                    return None
                if "404" in str(exc) or "Not Found" in str(exc):
                    return None
                raise

        return await loop.run_in_executor(None, _head)

    async def _download_manifest(self) -> None:
        """Télécharge le dvc.lock frais par-dessus celui du pod."""
        bucket, key = _split_s3_uri(self._config.manifest_s3_uri)
        loop = asyncio.get_running_loop()
        destination = str(self._config.dvc_lock_path)
        await loop.run_in_executor(
            None, lambda: self._client().download_file(bucket, key, destination)
        )

    async def _dvc_pull(self) -> None:
        """Lance `dvc pull convert_to_onnx --no-run-cache` (mêmes args que l'entrypoint).

        Raises:
            RuntimeError: dvc pull a échoué (code retour non nul).
            TimeoutError: dvc pull a dépassé pull_timeout_s.
        """
        # --force : mêmes arguments que l'entrypoint — les modèles du PVC
        # sont des copies jetables de S3, l'écrasement est toujours voulu
        # (sans lui, DVC refuse de remplacer un fichier au hash changé).
        process = await asyncio.create_subprocess_exec(
            "dvc",
            "pull",
            "convert_to_onnx",
            "--no-run-cache",
            "--force",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            stdout, _ = await asyncio.wait_for(
                process.communicate(), timeout=self._config.pull_timeout_s
            )
        # asyncio.TimeoutError : pas l'alias du builtin en Python 3.10 (prod).
        except asyncio.TimeoutError:  # noqa: UP041
            process.kill()
            raise
        if process.returncode != 0:
            raise RuntimeError(
                f"dvc pull a échoué (code {process.returncode}) : "
                f"{stdout.decode(errors='replace')[-500:]}"
            )
