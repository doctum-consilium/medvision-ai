"""Tests smoke du navigateur d'images partagé (src/datasets/sample_browser.py).

Sans TensorFlow ni Streamlit : la logique est pure (pathlib + pandas + PIL),
c'est précisément la raison de son extraction depuis streamlit_app.py — elle
doit servir à l'identique l'UI Streamlit ET l'API FastAPI du front Angular.
"""
from __future__ import annotations

import csv
from pathlib import Path

from PIL import Image

from src.datasets.sample_browser import (
    SampleIndex,
    build_problem_image_database,
    canonical_label,
    collect_images_from_dirs,
    collect_images_from_manifest,
    filter_samples,
    infer_label_from_path,
    is_supported_image,
    looks_like_generated_sample,
    looks_like_mask_path,
    recommended_samples,
    sample_public_id,
    samples_with_expected_labels,
)


def _write_png(path: Path) -> Path:
    """Écrit une vraie image PNG 8×8 (is_supported_image exige un fichier réel)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), color=(10, 20, 30)).save(path)
    return path


# ── Helpers unitaires ──────────────────────────────────────────────────────


def test_is_supported_image_by_extension(tmp_path: Path) -> None:
    """Seules les extensions d'images connues passent, et le fichier doit exister."""
    png = _write_png(tmp_path / "a.png")
    assert is_supported_image(png)
    assert not is_supported_image(tmp_path / "absent.png")
    text = tmp_path / "notes.txt"
    text.write_text("hello")
    assert not is_supported_image(text)


def test_looks_like_mask_path_conventions() -> None:
    """Les conventions de nommage des masques sont détectées, pas les images."""
    assert looks_like_mask_path(Path("data/raw/x/masks/img1.png"))
    assert looks_like_mask_path(Path("data/raw/x/img1_mask.png"))
    assert looks_like_mask_path(Path("data/raw/x/img1_seg.png"))
    assert looks_like_mask_path(Path("data/raw/labels/img1.png"))
    assert not looks_like_mask_path(Path("data/raw/NORMAL/img1.png"))


def test_sample_public_id_is_stable_and_opaque() -> None:
    """L'identifiant est stable pour un même chemin et n'expose pas le chemin."""
    p = Path("data/raw/chest_xray/NORMAL/img1.png")
    sid = sample_public_id(p)
    assert sid == sample_public_id(p)
    assert sid.startswith("sample-")
    assert "NORMAL" not in sid and "img1" not in sid
    assert sid != sample_public_id(Path("data/raw/chest_xray/NORMAL/img2.png"))


def test_canonical_label_rapproche_les_variantes() -> None:
    """Labels libres du disque rapprochés des class_names du registre."""
    expected = ["NORMAL", "PNEUMONIA"]
    assert canonical_label("normal", expected) == "NORMAL"
    assert canonical_label("Pneumonia cases", expected) == "PNEUMONIA"
    assert canonical_label("inconnu", expected) == "inconnu"
    assert canonical_label("whatever", None) == "whatever"


def test_infer_label_from_path_prefers_parent_dir() -> None:
    """Le dossier parent est la source de label la plus fiable."""
    expected = ["NORMAL", "PNEUMONIA"]
    assert infer_label_from_path(Path("data/x/NORMAL/img.png"), expected) == "NORMAL"
    assert infer_label_from_path(Path("data/x/pneumonia/img.png"), expected) == "PNEUMONIA"
    assert infer_label_from_path(Path("data/x/misc/img.png"), None) == "misc"


# ── Collecte disque ────────────────────────────────────────────────────────


def test_collect_images_from_dirs_balances_classes(tmp_path: Path) -> None:
    """L'équilibrage round-robin montre chaque classe, même très déséquilibrée."""
    for i in range(6):
        _write_png(tmp_path / "NORMAL" / f"n{i}.png")
    for i in range(2):
        _write_png(tmp_path / "PNEUMONIA" / f"p{i}.png")

    samples = collect_images_from_dirs(
        [tmp_path], root=tmp_path, limit=4, expected_labels=["NORMAL", "PNEUMONIA"]
    )
    labels = [s["label"] for s in samples]
    # 4 demandés / 2 classes → 2 par classe maximum, les deux classes présentes.
    assert labels.count("NORMAL") == 2
    assert labels.count("PNEUMONIA") == 2


def test_collect_images_from_dirs_excludes_masks(tmp_path: Path) -> None:
    """exclude_masks écarte les fichiers de masques du navigateur."""
    _write_png(tmp_path / "imgs" / "scan1.png")
    _write_png(tmp_path / "masks" / "scan1.png")

    samples = collect_images_from_dirs([tmp_path], root=tmp_path, limit=10, exclude_masks=True)
    assert len(samples) == 1
    assert "masks" not in str(samples[0]["path"])


def test_collect_images_from_dirs_ignores_missing_dirs(tmp_path: Path) -> None:
    """Un dossier absent est ignoré silencieusement (déploiements sans data)."""
    assert collect_images_from_dirs([tmp_path / "nope"], root=tmp_path, limit=5) == []


# ── Collecte manifeste ─────────────────────────────────────────────────────


def _write_manifest(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    manifest = tmp_path / "manifest.csv"
    with manifest.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["image_path", "mask_path", "label", "split"])
        writer.writeheader()
        writer.writerows(rows)
    return manifest


def test_collect_images_from_manifest_resolves_relative_paths(tmp_path: Path) -> None:
    """Les chemins relatifs du manifeste sont résolus contre root."""
    _write_png(tmp_path / "imgs" / "a.png")
    manifest = _write_manifest(
        tmp_path,
        [{"image_path": "imgs/a.png", "mask_path": "", "label": "tumor", "split": "train"}],
    )
    samples = collect_images_from_manifest(manifest, root=tmp_path, limit=5)
    assert len(samples) == 1
    assert samples[0]["label"] == "tumor"
    assert samples[0]["path"] == tmp_path / "imgs" / "a.png"


def test_collect_images_from_manifest_missing_or_invalid(tmp_path: Path) -> None:
    """Manifeste absent, vide ou sans colonne image_path → liste vide, pas d'erreur."""
    assert collect_images_from_manifest(tmp_path / "nope.csv", root=tmp_path, limit=5) == []
    bad = tmp_path / "bad.csv"
    bad.write_text("colonne_inconnue\nvaleur\n")
    assert collect_images_from_manifest(bad, root=tmp_path, limit=5) == []
    empty = tmp_path / "empty.csv"
    empty.touch()
    assert collect_images_from_manifest(empty, root=tmp_path, limit=5) == []


# ── Filtres / recommandations ──────────────────────────────────────────────


def _fake_samples() -> list[dict[str, str]]:
    return [
        {"path": "p1", "label": "NORMAL", "sample_id": "sample-01", "display": "NORMAL | sample-01"},
        {"path": "p2", "label": "PNEUMONIA", "sample_id": "sample-02", "display": "PNEUMONIA | sample-02"},
        {"path": "p3", "label": "NORMAL", "sample_id": "sample-03", "display": "NORMAL | sample-03"},
    ]


def test_filter_samples_by_label_and_query() -> None:
    """Filtre par classe (insensible à la casse) et recherche libre."""
    samples = _fake_samples()
    assert len(filter_samples(samples, labels=["normal"], query="")) == 2
    assert len(filter_samples(samples, labels=[], query="sample-02")) == 1
    assert filter_samples(samples, labels=["NORMAL"], query="sample-02") == []


def test_samples_with_expected_labels_filters_unknown() -> None:
    """Les labels hors class_names sont écartés."""
    samples = _fake_samples() + [
        {"path": "p4", "label": "autre", "sample_id": "sample-04", "display": "autre | sample-04"}
    ]
    kept = samples_with_expected_labels(samples, ["NORMAL", "PNEUMONIA"])
    assert {s["label"] for s in kept} == {"NORMAL", "PNEUMONIA"}
    assert samples_with_expected_labels(samples, None) == samples


def test_recommended_samples_one_per_class_then_fill() -> None:
    """Une recommandation par classe d'abord, puis complément jusqu'au max."""
    samples = _fake_samples()
    recs = recommended_samples(samples, max_items=3)
    assert len(recs) == 3
    # Les deux premières recommandations couvrent les deux classes.
    assert {recs[0]["label"], recs[1]["label"]} == {"NORMAL", "PNEUMONIA"}
    assert recommended_samples([], max_items=3) == []


# ── Base par problème + index ──────────────────────────────────────────────


def test_build_problem_image_database_chest_xray(tmp_path: Path) -> None:
    """Le problème chest_xray balaye data/raw/chest_xray/{test,val,train}."""
    _write_png(tmp_path / "data/raw/chest_xray/test/NORMAL/n1.png")
    _write_png(tmp_path / "data/raw/chest_xray/test/PNEUMONIA/p1.png")
    samples = build_problem_image_database(
        "chest_xray", expected_labels=["NORMAL", "PNEUMONIA"], limit=10, root=tmp_path
    )
    assert {s["label"] for s in samples} == {"NORMAL", "PNEUMONIA"}


def test_build_problem_image_database_segmentation_manifest_first(tmp_path: Path) -> None:
    """Pour la segmentation, le manifest.csv est prioritaire sur le scan brut."""
    _write_png(tmp_path / "data/processed/brain_tumor_segmentation/imgs/a.png")
    manifest_dir = tmp_path / "data/processed/brain_tumor_segmentation"
    with (manifest_dir / "manifest.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["image_path", "mask_path", "label", "split"])
        writer.writeheader()
        writer.writerow(
            {
                "image_path": str(manifest_dir / "imgs/a.png"),
                "mask_path": "",
                "label": "tumor",
                "split": "train",
            }
        )
    samples = build_problem_image_database("brain_tumor_segmentation", limit=10, root=tmp_path)
    assert len(samples) == 1
    assert samples[0]["label"] == "tumor"


def test_looks_like_generated_sample_reconnait_le_generateur() -> None:
    """Les PNG factices de scripts/generate_sample_images.py sont reconnus."""
    assert looks_like_generated_sample(Path("data/raw/chest_xray/NORMAL/sample_000.png"))
    assert looks_like_generated_sample(Path("data/raw/x/glioma_sample_012.png"))
    # Une vraie image de dataset ne doit surtout pas être prise pour un faux.
    assert not looks_like_generated_sample(Path("data/raw/x/Te-gl_0010.jpg"))
    assert not looks_like_generated_sample(Path("data/raw/x/person1_bacteria_1.jpeg"))
    assert not looks_like_generated_sample(Path("data/raw/x/sample_patient.png"))


def test_collect_images_exclut_les_images_synthetiques(tmp_path: Path) -> None:
    """Le navigateur ignore les bouche-trous générés, garde les vraies images."""
    _write_png(tmp_path / "IRM" / "sample_000.png")
    _write_png(tmp_path / "IRM" / "glioma_sample_001.png")
    vraie = _write_png(tmp_path / "IRM" / "Te-gl_0042.png")

    samples = collect_images_from_dirs([tmp_path], root=tmp_path, limit=10)
    assert [s["path"] for s in samples] == [vraie]


def test_brain_seg_se_rabat_sur_les_vraies_irm(tmp_path: Path) -> None:
    """Sans données de segmentation réelles, on sert les IRM du problème frère.

    Vécu en production : le dossier de segmentation cérébrale ne contenait que
    12 images synthétiques ; le navigateur n'affichait que du bruit avec un
    carré gris. Les vraies IRM sont déjà présentes sous brain_tumor_mri.
    """
    # Le dossier de segmentation n'a que des images générées → inutilisables.
    _write_png(tmp_path / "data/raw/brain_tumor_segmentation/images/glioma_sample_000.png")
    # Les vraies IRM du corpus frère.
    _write_png(tmp_path / "data/raw/brain_tumor_mri/Testing/glioma/Te-gl_0001.png")
    _write_png(tmp_path / "data/raw/brain_tumor_mri/Testing/meningioma/Te-me_0001.png")

    samples = build_problem_image_database(
        "brain_tumor_segmentation",
        expected_labels=["glioma", "meningioma", "pituitary tumor"],
        limit=10,
        root=tmp_path,
    )
    assert samples, "aucun échantillon : le repli sur les vraies IRM n'a pas joué"
    assert all("brain_tumor_mri" in str(s["path"]) for s in samples)
    assert all("_sample_" not in Path(s["path"]).name for s in samples)


def test_build_problem_image_database_unknown_problem(tmp_path: Path) -> None:
    """Un problème inconnu retourne une liste vide (pas d'exception)."""
    assert build_problem_image_database("inconnu", root=tmp_path) == []


def test_sample_index_resolves_only_known_ids(tmp_path: Path) -> None:
    """SampleIndex ne résout que ses propres ids — jamais un chemin client."""
    png = _write_png(tmp_path / "NORMAL" / "n1.png")
    samples = collect_images_from_dirs([tmp_path], root=tmp_path, limit=5)
    index = SampleIndex()
    index.put("chest_xray", samples)

    sid = samples[0]["sample_id"]
    resolved = index.resolve("chest_xray", sid)
    assert resolved is not None and resolved["path"] == png
    # Un id inconnu ou un chemin déguisé en id ne résolvent rien.
    assert index.resolve("chest_xray", "sample-ffffffffff") is None
    assert index.resolve("chest_xray", "../../etc/passwd") is None
    assert index.resolve("autre_probleme", sid) is None
    assert index.known_problems() == ["chest_xray"]
