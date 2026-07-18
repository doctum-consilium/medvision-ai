"""Découverte et indexation des images de datasets pour la navigation UI.

Ce module regroupe la logique PURE (sans Streamlit, sans FastAPI) qui
alimente le « navigateur d'images dataset » : balayage des dossiers
d'images brutes, lecture des manifest.csv produits par la préparation de
données, équilibrage par classe, filtres, recommandations, et index
sample_id → chemin.

POURQUOI ce module existe : cette logique vivait dans streamlit_app.py.
L'API FastAPI (front Angular) doit exposer exactement le même navigateur
d'images — une seule source de vérité évite que Streamlit et Angular
divergent pendant leur coexistence.

Sécurité : l'UI ne manipule JAMAIS de chemins de fichiers, uniquement des
`sample_id` opaques (hash blake2s). `SampleIndex.resolve()` ne sert que
des chemins découverts par NOS balayages — aucun chemin fourni par un
client n'est jamais ouvert (pas de traversée de répertoires possible).
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pandas as pd

# Extensions d'images supportées par le navigateur (alignées sur ce que
# PIL sait ouvrir et ce que les datasets contiennent réellement).
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def is_supported_image(path: Path) -> bool:
    """Vrai si `path` est un fichier image d'extension supportée.

    Args:
        path: Chemin à tester.

    Returns:
        True si le fichier existe et porte une extension d'image connue.
    """
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def looks_like_mask_path(path: Path) -> bool:
    """Détecte heuristiquement les masques de segmentation à exclure.

    Les datasets de segmentation mélangent images ET masques dans la même
    arborescence ; proposer un masque comme « image à prédire » n'a aucun
    sens pour l'utilisateur — on les filtre par convention de nommage.

    Args:
        path: Chemin du fichier image candidat.

    Returns:
        True si le chemin ressemble à un masque (nom ou dossier parent).
    """
    parts = [part.lower() for part in path.parts]
    stem = path.stem.lower()
    parent = path.parent.name.lower()
    return (
        "mask" in stem
        or stem.endswith("_seg")
        or "label" in stem
        or parent in {"mask", "masks", "seg", "segs", "labels"}
        or any(part in {"mask", "masks", "seg", "segs", "labels"} for part in parts)
    )


def sample_public_id(path: Path) -> str:
    """Construit l'identifiant public opaque d'un échantillon.

    Le hash (blake2s tronqué) remplace le chemin dans TOUTES les
    interfaces : l'UI ne voit jamais l'arborescence disque.

    Args:
        path: Chemin réel de l'image.

    Returns:
        Identifiant stable de la forme ``sample-<10 hex>``.
    """
    digest = hashlib.blake2s(str(path).encode("utf-8"), digest_size=5).hexdigest()
    return f"sample-{digest}"


def _normalize_label(value: str) -> str:
    """Normalise un label pour comparaison (minuscules, alphanumérique)."""
    return "".join(ch for ch in value.lower() if ch.isalnum())


def canonical_label(raw_label: str, expected_labels: list[str] | None) -> str:
    """Rapproche un label brut du label canonique du problème.

    Les datasets nomment leurs classes librement (« NORMAL », « normal »,
    « Normal cases »…) ; on les rabat sur les `class_names` du registre
    pour que filtres et affichage restent cohérents.

    Args:
        raw_label: Label lu depuis le disque ou le manifeste.
        expected_labels: Labels canoniques du problème (None = pas de rapprochement).

    Returns:
        Le label canonique correspondant, ou `raw_label` si aucun ne matche.
    """
    if not expected_labels:
        return raw_label
    raw_norm = _normalize_label(raw_label)
    for label in expected_labels:
        label_norm = _normalize_label(label)
        if raw_norm == label_norm:
            return label
        if raw_norm and label_norm and (raw_norm in label_norm or label_norm in raw_norm):
            return label
    return raw_label


def infer_label_from_path(path: Path, expected_labels: list[str] | None) -> str:
    """Déduit le label d'une image depuis son chemin (dossier parent, nom…).

    Args:
        path: Chemin de l'image.
        expected_labels: Labels canoniques du problème.

    Returns:
        Le label canonique le plus plausible (au pire, le nom du dossier parent).
    """
    if not expected_labels:
        return path.parent.name
    parts = [part for part in path.parts if part]
    candidates = [path.parent.name, path.stem]
    candidates.extend(parts[::-1])
    for candidate in candidates:
        canonical = canonical_label(candidate, expected_labels)
        if canonical in expected_labels:
            return canonical
    return canonical_label(path.parent.name, expected_labels)


def _make_sample(path: Path, label: str) -> dict[str, Any]:
    """Construit le dict standard d'un échantillon (path, label, id, display)."""
    sid = sample_public_id(path)
    return {"path": path, "label": label, "sample_id": sid, "display": f"{label} | {sid}"}


def _balance_buckets(
    buckets: dict[str, list[dict[str, Any]]],
    expected_labels: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    """Interleave round-robin des buckets par classe, plafonné à `limit`.

    POURQUOI : sans équilibrage, un dossier « NORMAL » de 5 000 images
    remplirait tout le quota avant qu'une seule image « PNEUMONIA »
    n'apparaisse — le navigateur doit montrer chaque classe.
    """
    balanced: list[dict[str, Any]] = []
    round_idx = 0
    while len(balanced) < limit:
        added_in_round = False
        for label in expected_labels:
            bucket = buckets.get(label, [])
            if round_idx < len(bucket):
                balanced.append(bucket[round_idx])
                added_in_round = True
                if len(balanced) >= limit:
                    break
        if not added_in_round:
            break
        round_idx += 1
    return balanced


def collect_images_from_dirs(
    directories: list[Path],
    root: Path,
    limit: int,
    expected_labels: list[str] | None = None,
    exclude_masks: bool = False,
) -> list[dict[str, Any]]:
    """Balaye récursivement des dossiers d'images et échantillonne par classe.

    Args:
        directories: Dossiers à balayer (les absents sont ignorés).
        root: Racine du projet (réservé aux évolutions ; non utilisé pour le scan).
        limit: Nombre maximal d'échantillons retournés.
        expected_labels: Labels canoniques — active l'équilibrage par classe.
        exclude_masks: Exclut les fichiers ressemblant à des masques.

    Returns:
        Liste de dicts ``{path, label, sample_id, display}``.
    """
    buckets: dict[str, list[dict[str, Any]]] = {}
    per_label_limit = None
    if expected_labels:
        per_label_limit = max(1, limit // max(1, len(expected_labels)))
        buckets = {label: [] for label in expected_labels}

    samples: list[dict[str, Any]] = []
    for directory in directories:
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if not is_supported_image(path):
                continue
            if exclude_masks and looks_like_mask_path(path):
                continue
            label_hint = infer_label_from_path(path, expected_labels)
            sample = _make_sample(path, label_hint)
            if expected_labels and per_label_limit is not None and label_hint in buckets:
                if len(buckets[label_hint]) < per_label_limit:
                    buckets[label_hint].append(sample)
                if all(len(buckets[label]) >= per_label_limit for label in expected_labels):
                    break
            else:
                samples.append(sample)
                if len(samples) >= limit:
                    return samples
        if expected_labels and per_label_limit is not None and all(
            len(buckets[label]) >= per_label_limit for label in expected_labels
        ):
            break

    if expected_labels and per_label_limit is not None:
        return _balance_buckets(buckets, expected_labels, limit)
    return samples


def collect_images_from_manifest(
    manifest_path: Path,
    root: Path,
    limit: int,
    expected_labels: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Charge les échantillons décrits par un manifest.csv de préparation.

    Args:
        manifest_path: Chemin du manifest.csv (colonnes image_path, label…).
        root: Racine pour résoudre les chemins relatifs du manifeste.
        limit: Nombre maximal d'échantillons retournés.
        expected_labels: Labels canoniques — active l'équilibrage par classe.

    Returns:
        Liste de dicts ``{path, label, sample_id, display}`` ; vide si le
        manifeste est absent, illisible ou sans colonne image_path.
    """
    if not manifest_path.exists():
        return []
    try:
        manifest_df = pd.read_csv(manifest_path)
    except Exception:
        return []
    if "image_path" not in manifest_df.columns:
        return []

    buckets: dict[str, list[dict[str, Any]]] = {}
    per_label_limit = None
    if expected_labels:
        per_label_limit = max(1, limit // max(1, len(expected_labels)))
        buckets = {label: [] for label in expected_labels}

    samples: list[dict[str, Any]] = []
    for _, row in manifest_df.iterrows():
        image_path_raw = row.get("image_path")
        if not isinstance(image_path_raw, str) or not image_path_raw.strip():
            continue
        candidate = Path(image_path_raw)
        if not candidate.is_absolute():
            candidate = root / candidate
        if not is_supported_image(candidate):
            continue
        raw_label = str(row.get("label", candidate.parent.name))
        label_hint = canonical_label(raw_label, expected_labels)
        sample = _make_sample(candidate, label_hint)
        if expected_labels and per_label_limit is not None and label_hint in buckets:
            if len(buckets[label_hint]) < per_label_limit:
                buckets[label_hint].append(sample)
            if all(len(buckets[label]) >= per_label_limit for label in expected_labels):
                break
        else:
            samples.append(sample)
            if len(samples) >= limit:
                break

    if expected_labels and per_label_limit is not None:
        return _balance_buckets(buckets, expected_labels, limit)
    return samples


def filter_samples(
    samples: list[dict[str, Any]], labels: list[str], query: str
) -> list[dict[str, Any]]:
    """Filtre les échantillons par labels sélectionnés et recherche libre.

    Args:
        samples: Échantillons à filtrer.
        labels: Labels retenus (liste vide = tous).
        query: Texte cherché dans sample_id, display ou label.

    Returns:
        Sous-liste filtrée, dans l'ordre d'origine.
    """
    filtered = samples
    if labels:
        label_set = {label.lower() for label in labels}
        filtered = [s for s in filtered if str(s.get("label", "")).lower() in label_set]
    q = query.strip().lower()
    if q:
        filtered = [
            s
            for s in filtered
            if q in str(s.get("sample_id", "")).lower()
            or q in str(s.get("display", "")).lower()
            or q in str(s.get("label", "")).lower()
        ]
    return filtered


def samples_with_expected_labels(
    samples: list[dict[str, Any]], expected_labels: list[str] | None
) -> list[dict[str, Any]]:
    """Ne garde que les échantillons dont le label appartient aux classes attendues."""
    if not expected_labels:
        return samples
    expected = {str(label).lower() for label in expected_labels}
    return [s for s in samples if str(s.get("label", "")).lower() in expected]


def recommended_samples(
    samples: list[dict[str, Any]], max_items: int = 4
) -> list[dict[str, Any]]:
    """Choisit des échantillons « recommandés » : un par classe, puis complète.

    Args:
        samples: Échantillons disponibles (déjà filtrés).
        max_items: Nombre maximal de recommandations.

    Returns:
        Jusqu'à `max_items` échantillons couvrant le plus de classes possible.
    """
    if not samples:
        return []

    grouped: dict[str, list[dict[str, Any]]] = {}
    for sample in samples:
        key = str(sample.get("label", "unknown"))
        grouped.setdefault(key, []).append(sample)

    picks: list[dict[str, Any]] = []
    for label in sorted(grouped.keys()):
        if grouped[label]:
            picks.append(grouped[label][0])
        if len(picks) >= max_items:
            return picks

    if len(picks) < max_items:
        existing = {str(item.get("sample_id", item.get("display", ""))) for item in picks}
        for sample in samples:
            key = str(sample.get("sample_id", sample.get("display", "")))
            if key in existing:
                continue
            picks.append(sample)
            if len(picks) >= max_items:
                break
    return picks


def build_problem_image_database(
    problem: str,
    expected_labels: list[str] | None = None,
    limit: int = 60,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Construit la base d'images navigables d'un problème médical.

    Encode la connaissance « où vivent les images de chaque problème » :
    dossiers bruts pour les classifications, manifest.csv (avec replis
    successifs) pour les segmentations.

    Args:
        problem: Identifiant du problème (chest_xray, brain_mri,
            brain_tumor_segmentation, chest_xray_segmentation).
        expected_labels: Labels canoniques du problème (équilibrage).
        limit: Nombre maximal d'échantillons.
        root: Racine du projet (défaut : répertoire courant résolu) —
            paramétrable pour les tests et les déploiements non-standard.

    Returns:
        Liste d'échantillons ``{path, label, sample_id, display}`` ;
        vide si le problème est inconnu ou sans données locales.
    """
    root = Path(".").resolve() if root is None else root
    if problem == "chest_xray":
        return collect_images_from_dirs(
            [
                root / "data/raw/chest_xray/test",
                root / "data/raw/chest_xray/val",
                root / "data/raw/chest_xray/train",
            ],
            root=root,
            limit=limit,
            expected_labels=expected_labels,
        )
    if problem == "brain_mri":
        return collect_images_from_dirs(
            [
                root / "data/raw/brain_tumor_mri/Testing",
                root / "data/raw/brain_tumor_mri/Training",
            ],
            root=root,
            limit=limit,
            expected_labels=expected_labels,
        )
    if problem == "brain_tumor_segmentation":
        samples = collect_images_from_manifest(
            root / "data/processed/brain_tumor_segmentation/manifest.csv",
            root=root,
            limit=limit,
            expected_labels=expected_labels,
        )
        if samples:
            return samples
        return collect_images_from_dirs(
            [root / "data/raw/brain_tumor_segmentation"],
            root=root,
            limit=limit,
            expected_labels=expected_labels,
            exclude_masks=True,
        )
    if problem == "chest_xray_segmentation":
        samples = collect_images_from_manifest(
            root / "data/processed/chest_xray_segmentation/manifest.csv",
            root=root,
            limit=limit,
            expected_labels=expected_labels,
        )
        if samples:
            return samples
        samples = collect_images_from_dirs(
            [root / "data/raw/chest_xray_segmentation"],
            root=root,
            limit=limit,
            expected_labels=expected_labels,
            exclude_masks=True,
        )
        samples = samples_with_expected_labels(samples, expected_labels)
        if samples:
            return samples
        return collect_images_from_dirs(
            [
                root / "data/raw/chest_xray/test",
                root / "data/raw/chest_xray/val",
                root / "data/raw/chest_xray/train",
            ],
            root=root,
            limit=limit,
            expected_labels=expected_labels,
        )
    return []


class SampleIndex:
    """Index sample_id → échantillon, par problème.

    C'est la pièce de sécurité du futur endpoint ``GET /api/images/{id}/file`` :
    l'API ne résout QUE des identifiants issus de nos propres balayages ;
    un identifiant inconnu ne mène nulle part (aucun chemin client n'est
    jamais interprété).
    """

    def __init__(self) -> None:
        self._by_problem: dict[str, dict[str, dict[str, Any]]] = {}

    def put(self, problem: str, samples: list[dict[str, Any]]) -> None:
        """Enregistre (ou remplace) les échantillons indexés d'un problème.

        Args:
            problem: Identifiant du problème.
            samples: Échantillons issus de ``build_problem_image_database``.
        """
        self._by_problem[problem] = {str(s["sample_id"]): s for s in samples}

    def resolve(self, problem: str, sample_id: str) -> dict[str, Any] | None:
        """Retourne l'échantillon correspondant à un identifiant, ou None.

        Args:
            problem: Identifiant du problème.
            sample_id: Identifiant public opaque (``sample-<hex>``).

        Returns:
            Le dict échantillon si connu, sinon None (jamais d'exception :
            un id inconnu est un cas normal côté API → 404).
        """
        return self._by_problem.get(problem, {}).get(str(sample_id))

    def known_problems(self) -> list[str]:
        """Liste les problèmes actuellement indexés."""
        return sorted(self._by_problem)
