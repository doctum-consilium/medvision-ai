from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image

from src.preprocessing.image_loader import load_and_preprocess_image
from src.registry.model_registry import compare_models, get_model_entry, load_onnx_model, load_registry

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def _is_supported_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def _looks_like_mask_path(path: Path) -> bool:
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


def _sample_public_id(path: Path) -> str:
    digest = hashlib.blake2s(str(path).encode("utf-8"), digest_size=5).hexdigest()
    return f"sample-{digest}"


def _load_preview_image(path: Path) -> np.ndarray | None:
    try:
        with Image.open(path) as img:
            return np.array(img.convert("RGB"))
    except Exception:
        return None


def _normalize_label(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _canonical_label(raw_label: str, expected_labels: list[str] | None) -> str:
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


def _infer_label_from_path(path: Path, expected_labels: list[str] | None) -> str:
    if not expected_labels:
        return path.parent.name
    parts = [part for part in path.parts if part]
    candidates = [path.parent.name, path.stem]
    candidates.extend(parts[::-1])
    for candidate in candidates:
        canonical = _canonical_label(candidate, expected_labels)
        if canonical in expected_labels:
            return canonical
    return _canonical_label(path.parent.name, expected_labels)


def _collect_images_from_dirs(
    directories: list[Path],
    root: Path,
    limit: int,
    expected_labels: list[str] | None = None,
    exclude_masks: bool = False,
) -> list[dict[str, Any]]:
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
            if not _is_supported_image(path):
                continue
            if exclude_masks and _looks_like_mask_path(path):
                continue
            label_hint = _infer_label_from_path(path, expected_labels)
            sample_id = _sample_public_id(path)
            sample = {
                "path": path,
                "label": label_hint,
                "sample_id": sample_id,
                "display": f"{label_hint} | {sample_id}",
            }
            if expected_labels and per_label_limit is not None and label_hint in buckets:
                if len(buckets[label_hint]) < per_label_limit:
                    buckets[label_hint].append(sample)
                if all(len(buckets[label]) >= per_label_limit for label in expected_labels):
                    break
            else:
                samples.append(sample)
                if len(samples) >= limit:
                    return samples
        if expected_labels and per_label_limit is not None and all(len(buckets[label]) >= per_label_limit for label in expected_labels):
            break

    if expected_labels and per_label_limit is not None:
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

    return samples


def _collect_images_from_manifest(
    manifest_path: Path,
    root: Path,
    limit: int,
    expected_labels: list[str] | None = None,
) -> list[dict[str, Any]]:
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
        if not _is_supported_image(candidate):
            continue
        raw_label = str(row.get("label", candidate.parent.name))
        label_hint = _canonical_label(raw_label, expected_labels)
        sample_id = _sample_public_id(candidate)
        sample = {
            "path": candidate,
            "label": label_hint,
            "sample_id": sample_id,
            "display": f"{label_hint} | {sample_id}",
        }
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

    return samples


def _filter_samples(samples: list[dict[str, Any]], labels: list[str], query: str) -> list[dict[str, Any]]:
    filtered = samples
    if labels:
        label_set = {label.lower() for label in labels}
        filtered = [sample for sample in filtered if str(sample.get("label", "")).lower() in label_set]
    q = query.strip().lower()
    if q:
        filtered = [
            sample
            for sample in filtered
            if q in str(sample.get("sample_id", "")).lower()
            or q in str(sample.get("display", "")).lower()
            or q in str(sample.get("label", "")).lower()
        ]
    return filtered


def _samples_with_expected_labels(samples: list[dict[str, Any]], expected_labels: list[str] | None) -> list[dict[str, Any]]:
    if not expected_labels:
        return samples
    expected = {str(label).lower() for label in expected_labels}
    return [sample for sample in samples if str(sample.get("label", "")).lower() in expected]


def _recommended_samples(samples: list[dict[str, Any]], max_items: int = 4) -> list[dict[str, Any]]:
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


def _render_fixed_label_filters(problem: str, labels: list[str]) -> list[str]:
    state_key = f"label_filters_{problem}"
    saved = st.session_state.get(state_key)

    if not isinstance(saved, list):
        selected_set = set(labels)
    else:
        selected_set = set(saved).intersection(labels)
        if not selected_set and labels:
            selected_set = set(labels)

    st.caption("Class filters")
    c_all, c_none = st.columns(2)
    if c_all.button("All", key=f"{state_key}_all", use_container_width=True):
        selected_set = set(labels)
    if c_none.button("None", key=f"{state_key}_none", use_container_width=True):
        selected_set = set()

    if labels:
        buttons_per_row = 4
        row_cols = st.columns(buttons_per_row)
        for idx, label in enumerate(labels):
            if idx > 0 and idx % buttons_per_row == 0:
                row_cols = st.columns(buttons_per_row)
            is_selected = label in selected_set
            pressed = row_cols[idx % buttons_per_row].button(
                label,
                key=f"{state_key}_btn_{idx}",
                type="primary" if is_selected else "secondary",
                use_container_width=True,
            )
            if pressed:
                if label in selected_set:
                    selected_set.remove(label)
                else:
                    selected_set.add(label)

    selected_labels = [label for label in labels if label in selected_set]
    st.session_state[state_key] = selected_labels
    return selected_labels


@st.cache_data(show_spinner=False)
def _build_problem_image_database(problem: str, expected_labels: list[str] | None = None, limit: int = 60) -> list[dict[str, Any]]:
    root = Path(".").resolve()
    if problem == "chest_xray":
        return _collect_images_from_dirs(
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
        return _collect_images_from_dirs(
            [
                root / "data/raw/brain_tumor_mri/Testing",
                root / "data/raw/brain_tumor_mri/Training",
            ],
            root=root,
            limit=limit,
            expected_labels=expected_labels,
        )
    if problem == "brain_tumor_segmentation":
        samples = _collect_images_from_manifest(
            root / "data/processed/brain_tumor_segmentation/manifest.csv",
            root=root,
            limit=limit,
            expected_labels=expected_labels,
        )
        if samples:
            return samples
        return _collect_images_from_dirs(
            [root / "data/raw/brain_tumor_segmentation"],
            root=root,
            limit=limit,
            expected_labels=expected_labels,
            exclude_masks=True,
        )
    if problem == "chest_xray_segmentation":
        samples = _collect_images_from_manifest(
            root / "data/processed/chest_xray_segmentation/manifest.csv",
            root=root,
            limit=limit,
            expected_labels=expected_labels,
        )
        if samples:
            return samples
        samples = _collect_images_from_dirs(
            [root / "data/raw/chest_xray_segmentation"],
            root=root,
            limit=limit,
            expected_labels=expected_labels,
            exclude_masks=True,
        )
        samples = _samples_with_expected_labels(samples, expected_labels)
        if samples:
            return samples
        return _collect_images_from_dirs(
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


def _run_onnx(session: Any, image: np.ndarray) -> dict[str, np.ndarray]:
    """Exécute l'inférence ONNX et retourne un dict {nom_sortie: valeur}.

    Args:
        session: onnxruntime.InferenceSession chargée par load_onnx_model().
        image: Image prétraitée (H, W, C), float32 ou float64.

    Returns:
        Dict {nom_de_sortie: array numpy} — fonctionne pour les modèles
        mono-tête (classification) comme multi-têtes (segmentation + classification).
    """
    input_name = session.get_inputs()[0].name
    x = image.astype(np.float32)[np.newaxis, ...]  # (1, H, W, C)
    out_names = [o.name for o in session.get_outputs()]
    outputs = session.run(None, {input_name: x})
    return dict(zip(out_names, outputs, strict=True))


def _predict(problem: str, model_name: str, image_path: Path, mask_threshold: float = 0.5) -> dict:
    model_entry = get_model_entry(problem, model_name)
    session = load_onnx_model(str(Path(model_entry["model_path"]).resolve()))

    image_size = 256 if "segmentation" in problem else 224
    image = load_and_preprocess_image(image_path, image_size=image_size)
    raw = _run_onnx(session, image)

    class_names = model_entry["class_names"]
    out_names = list(raw.keys())

    if model_entry["task_type"] == "segmentation_multitask":
        # tf2onnx préserve les noms de couches Keras ; fallback sur l'index si absent.
        seg_key = next((k for k in out_names if "seg" in k.lower()), out_names[0])
        cls_key = next(
            (k for k in out_names if "class" in k.lower() or "cls" in k.lower()),
            out_names[-1],
        )
        seg = raw[seg_key][0, ..., 0]
        cls = raw[cls_key][0]
        if len(class_names) == 2:
            probs = {class_names[0]: float(1 - cls[0]), class_names[1]: float(cls[0])}
        else:
            probs = {name: float(cls[i]) for i, name in enumerate(class_names)}
        pred = max(probs.items(), key=lambda item: item[1])[0]
        confidence = float(max(probs.values()))
        mask = (seg >= mask_threshold).astype(np.float32)
        return {
            "predicted_class": pred,
            "confidence": confidence,
            "probabilities": probs,
            "metrics": model_entry.get("metrics", {}),
            "mask_prob": seg.astype(np.float32),
            "mask": mask,
            "mask_foreground_ratio": float(mask.mean()),
            "mask_prob_mean": float(np.mean(seg)),
            "mask_prob_max": float(np.max(seg)),
            "mask_prob_min": float(np.min(seg)),
            "image": image,
        }

    # Classification (binary ou multiclass) — une seule sortie
    logits = raw[out_names[0]][0]
    if model_entry["task_type"] == "binary":
        p1 = float(logits[0]) if logits.ndim > 0 else float(logits)
        probs = {class_names[0]: float(1 - p1), class_names[1]: p1}
    else:
        probs = {name: float(logits[i]) for i, name in enumerate(class_names)}
    pred = max(probs.items(), key=lambda item: item[1])[0]
    confidence = float(max(probs.values()))
    return {"predicted_class": pred, "confidence": confidence, "probabilities": probs, "metrics": model_entry.get("metrics", {})}


def _inject_styles() -> None:
    st.markdown(
        """
<style>
:root {
  --bg-soft: #f4f6f2;
  --ink-main: #1e2a24;
  --ink-muted: #55645a;
  --card: #ffffff;
  --line: #d8ded7;
  --accent: #0f7a66;
  --accent-2: #c65d2f;
}

.stApp {
  background: radial-gradient(circle at 8% 8%, #eef6f1 0%, #f7f5ee 45%, #fbfaf7 100%);
}

.hero {
  background: linear-gradient(120deg, #133f35 0%, #0f7a66 55%, #2a8d70 100%);
  color: #f4fff9;
  border-radius: 18px;
  padding: 1.3rem 1.4rem;
  margin-bottom: 1rem;
  border: 1px solid rgba(255,255,255,0.2);
  box-shadow: 0 8px 24px rgba(16, 45, 38, 0.18);
}

.hero h2 {
  margin: 0;
  font-size: 1.65rem;
  line-height: 1.15;
}

.hero p {
  margin: 0.45rem 0 0;
  color: #d7f2e8;
  font-size: 0.96rem;
}

.kpi-card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 0.75rem 0.9rem;
}

.kpi-title {
  color: var(--ink-muted);
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.kpi-value {
  color: var(--ink-main);
  font-size: 1.35rem;
  font-weight: 700;
  margin-top: 0.2rem;
}

.pred-card {
  background: #ffffff;
  border: 1px solid #d8ded7;
  border-left: 5px solid var(--accent);
  border-radius: 12px;
  padding: 0.8rem;
  margin-bottom: 0.7rem;
}

.pred-card h4 {
  margin: 0;
  color: #1e2a24;
  font-size: 1rem;
}

.pred-meta {
  margin-top: 0.35rem;
  color: #4a5a51;
  font-size: 0.92rem;
}

[data-testid="stTabs"] button {
  font-weight: 600;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def _blend_overlay(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
    overlay = np.clip(image.copy(), 0.0, 1.0)
    alpha = np.clip(mask, 0.0, 1.0) * 0.7
    overlay[..., 1] = np.maximum(overlay[..., 1], alpha)
    overlay[..., 0] = overlay[..., 0] * (1.0 - 0.35 * alpha)
    overlay[..., 2] = overlay[..., 2] * (1.0 - 0.15 * alpha)
    return overlay


def _render_kpi(label: str, value: str) -> None:
    st.markdown(
        f"""
<div class="kpi-card">
  <div class="kpi-title">{label}</div>
  <div class="kpi-value">{value}</div>
</div>
        """,
        unsafe_allow_html=True,
    )


st.set_page_config(page_title="MedVision AI", layout="wide")
_inject_styles()

st.markdown(
    """
<section class="hero">
  <h2>MedVision AI: Model Comparison Studio</h2>
  <p>Evaluate classification and segmentation models side-by-side with shared registry metadata, prediction confidence, and visual overlays.</p>
</section>
    """,
    unsafe_allow_html=True,
)

registry = load_registry()
problems = registry["problems"]

with st.sidebar:
    st.header("Control Panel")
    problem = st.selectbox("Problem", options=list(problems.keys()), format_func=lambda key: problems[key]["label"])

problem_meta = problems[problem]
is_segmentation_problem = problem_meta["task_type"] == "segmentation_multitask"

with st.sidebar:
    if is_segmentation_problem:
        st.markdown("---")
        st.subheader("Segmentation")
        mask_threshold = st.slider("Mask threshold", min_value=0.10, max_value=0.90, value=0.50, step=0.05)
    else:
        mask_threshold = 0.5

all_models = problem_meta["models"]
available_models = [name for name, meta in all_models.items() if meta["available"]]

k1, k2, k3, k4 = st.columns(4)
with k1:
    _render_kpi("Problem", problem_meta["label"])
with k2:
    _render_kpi("Task Type", problem_meta["task_type"])
with k3:
    _render_kpi("Models Available", str(len(available_models)))
with k4:
    _render_kpi("Classes", str(len(problem_meta.get("class_names", []))))

tab_compare, tab_predict, tab_registry = st.tabs(["Model Compare", "Prediction Studio", "Registry"])

with tab_compare:
    st.subheader("Model Benchmarks")
    rows = compare_models(problem)
    benchmark_df = pd.DataFrame(rows)
    if benchmark_df.empty:
        st.info("No benchmark rows are currently available.")
    else:
        st.dataframe(benchmark_df, use_container_width=True)
        numeric_cols = [col for col in benchmark_df.columns if col not in {"model_name", "available"}]
        numeric_cols = [c for c in numeric_cols if pd.api.types.is_numeric_dtype(benchmark_df[c])]
        if numeric_cols:
            chart_metric = st.selectbox("Benchmark metric to visualize", options=numeric_cols)
            chart_df = benchmark_df[["model_name", chart_metric]].set_index("model_name")
            st.bar_chart(chart_df, use_container_width=True)

with tab_predict:
    st.subheader("Prediction Studio")
    if not available_models:
        st.warning("No trained models found for this problem in artifacts/models.")
    else:
        selected_models = st.multiselect("Select models", options=available_models, default=available_models)
        input_mode = st.radio(
            "Image source",
            options=["Upload image", "Dataset image database"],
            index=1,
            horizontal=True,
        )
        selected_image_path: Path | None = None
        uploaded = None
        sample_state_key = f"prediction_selected_sample_{problem}"

        if input_mode == "Upload image":
            uploaded = st.file_uploader("Upload an image", type=["png", "jpg", "jpeg", "bmp", "webp"])
            if uploaded is not None:
                selected_image_path = Path(uploaded.name)
        else:
            db_samples = _build_problem_image_database(
                problem,
                expected_labels=problem_meta.get("class_names", []),
                limit=48,
            )
            if not db_samples:
                st.warning("No local image samples were found for this problem. You can still upload an image manually.")
            else:
                st.caption(f"{len(db_samples)} local samples available for this problem.")
                base_labels = [str(label) for label in problem_meta.get("class_names", [])]
                sample_labels = [str(sample["label"]) for sample in db_samples]
                available_labels = list(dict.fromkeys(base_labels + sorted(set(sample_labels))))
                c_filter1, c_filter2 = st.columns([1.15, 1])
                with c_filter1:
                    chosen_labels = _render_fixed_label_filters(problem=problem, labels=available_labels)
                with c_filter2:
                    path_query = st.text_input("Search sample id/label", value="")

                filtered_samples = _filter_samples(db_samples, labels=chosen_labels, query=path_query)
                if not filtered_samples:
                    st.warning("No image matches these filters.")
                else:
                    current_sample_id = st.session_state.get(sample_state_key)
                    if current_sample_id not in {str(s["sample_id"]) for s in filtered_samples}:
                        current_sample_id = str(filtered_samples[0]["sample_id"])
                        st.session_state[sample_state_key] = current_sample_id

                    recs = _recommended_samples(filtered_samples, max_items=4)
                    if recs:
                        st.markdown("#### Recommended samples")
                        rec_cols = st.columns(len(recs))
                        for idx, sample in enumerate(recs):
                            with rec_cols[idx]:
                                preview = _load_preview_image(Path(sample["path"]))
                                if preview is not None:
                                    st.image(preview, caption=sample["label"], use_container_width=True)
                                if st.button(
                                    "Select",
                                    key=f"rec_select_{problem}_{sample['sample_id']}",
                                    use_container_width=True,
                                ):
                                    st.session_state[sample_state_key] = str(sample["sample_id"])
                                    current_sample_id = str(sample["sample_id"])

                    page_size = st.select_slider("Samples per page", options=[6, 12, 18, 24], value=12)
                    total_pages = max(1, (len(filtered_samples) + page_size - 1) // page_size)
                    page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1)
                    page_start = (int(page) - 1) * page_size
                    page_samples = filtered_samples[page_start : page_start + page_size]

                    st.caption(f"Showing {len(page_samples)} / {len(filtered_samples)} filtered samples.")
                    default_index = 0
                    for idx, sample in enumerate(filtered_samples):
                        if str(sample["sample_id"]) == str(current_sample_id):
                            default_index = idx
                            break
                    selected_index = st.selectbox(
                        "Choose a dataset image",
                        options=list(range(len(filtered_samples))),
                        index=default_index,
                        format_func=lambda idx: filtered_samples[idx]["display"],
                    )
                    selected_sample = filtered_samples[selected_index]
                    st.session_state[sample_state_key] = str(selected_sample["sample_id"])
                    selected_image_path = Path(selected_sample["path"])

                    preview_cols = st.columns(3)
                    for idx, sample in enumerate(page_samples[:6]):
                        with preview_cols[idx % 3]:
                            preview = _load_preview_image(Path(sample["path"]))
                            if preview is not None:
                                st.image(preview, caption=sample["label"], use_container_width=True)
                            if st.button(
                                "Select",
                                key=f"page_select_{problem}_{sample['sample_id']}",
                                use_container_width=True,
                            ):
                                st.session_state[sample_state_key] = str(sample["sample_id"])

        if uploaded is not None or selected_image_path is not None:
            left_col, right_col = st.columns([1.1, 1.4])
            with left_col:
                if uploaded is not None:
                    st.image(uploaded, caption="Input image", use_container_width=True)
                else:
                    selected_preview = _load_preview_image(Path(selected_image_path)) if selected_image_path else None
                    if selected_preview is not None:
                        st.image(selected_preview, caption="Dataset image", use_container_width=True)

            tmp_path: Path | None = None
            predict_path: Path | None = selected_image_path

            if uploaded is not None:
                with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded.name).suffix or ".png") as tmp:
                    tmp.write(uploaded.getvalue())
                    tmp_path = Path(tmp.name)
                    predict_path = tmp_path

            try:
                prediction_rows = []
                prob_rows = []
                overlays = []
                seg_debug_rows = []
                prediction_errors = []

                with st.spinner("Calcul des prédictions..."):
                    for model_name in selected_models:
                        if predict_path is None:
                            continue
                        try:
                            result = _predict(problem, model_name, predict_path, mask_threshold=mask_threshold)
                        except FileNotFoundError:
                            prediction_errors.append(
                                f"**{model_name}** — modèle introuvable. "
                                "Entraîner le modèle et faire `dvc push`, puis redéployer."
                            )
                            continue
                        except Exception as exc:
                            # Limiter la longueur : str(exc) peut contenir des milliers de
                            # caractères (ex. config JSON Keras) si le modèle n'est pas chargé.
                            msg = str(exc)
                            if len(msg) > 300:
                                msg = msg[:300] + "…"
                            prediction_errors.append(
                                f"**{model_name}** — {type(exc).__name__}: {msg}"
                            )
                            continue
                        prediction_rows.append(
                            {
                                "model": model_name,
                                "predicted_class": result["predicted_class"],
                                "confidence": float(result.get("confidence", 0.0)),
                                "mask_foreground_ratio": float(result.get("mask_foreground_ratio", 0.0)),
                                **{f"metric_{k}": v for k, v in result["metrics"].items() if isinstance(v, (int, float))},
                            }
                        )
                        prob_row = {"model": model_name}
                        prob_row.update(result["probabilities"])
                        prob_rows.append(prob_row)
                        if "mask" in result:
                            overlays.append((model_name, result["image"], result["mask"], result["mask_prob"]))
                            seg_debug_rows.append(
                                {
                                    "model": model_name,
                                    "threshold": float(mask_threshold),
                                    "mask_foreground_ratio": float(result.get("mask_foreground_ratio", 0.0)),
                                    "prob_mean": float(result.get("mask_prob_mean", 0.0)),
                                    "prob_max": float(result.get("mask_prob_max", 0.0)),
                                    "prob_min": float(result.get("mask_prob_min", 0.0)),
                                }
                            )

                for err_msg in prediction_errors:
                    st.error(err_msg)

                if prediction_rows:
                    with right_col:
                        st.markdown("#### Résultats")
                        for row in prediction_rows:
                            st.markdown(
                                f"""
<div class="pred-card">
  <h4>{row['model']}</h4>
  <div class="pred-meta">Prédiction : <strong>{row['predicted_class']}</strong></div>
  <div class="pred-meta">Confiance : <strong>{row['confidence']:.3f}</strong></div>
</div>
                                """,
                                unsafe_allow_html=True,
                            )

                    st.markdown("#### Tableau de prédictions")
                    st.dataframe(pd.DataFrame(prediction_rows), use_container_width=True)

                    if prob_rows:
                        st.markdown("#### Probabilités par classe")
                        prob_df = pd.DataFrame(prob_rows)
                        st.dataframe(prob_df, use_container_width=True)
                        prob_chart = prob_df.set_index("model")
                        st.bar_chart(prob_chart, use_container_width=True)

                    if overlays:
                        st.markdown("#### Segmentation")
                        st.dataframe(pd.DataFrame(seg_debug_rows), use_container_width=True)

                        if all(row["mask_foreground_ratio"] == 0.0 for row in seg_debug_rows):
                            st.warning(
                                "Tous les masques sont vides au seuil actuel. "
                                "Essayer un seuil plus bas (0.30 ou 0.20) et inspecter la carte de probabilité."
                            )

                        for model_name, image, mask, mask_prob in overlays:
                            st.markdown(f"##### {model_name}")
                            c1, c2, c3, c4 = st.columns([1, 1, 1.2, 1])
                            with c1:
                                st.caption("Image prétraitée")
                                st.image(image, use_container_width=True)
                            with c2:
                                st.caption("Masque binaire")
                                st.image(mask, clamp=True, use_container_width=True)
                            with c3:
                                st.caption("Superposition")
                                st.image(_blend_overlay(image, mask), use_container_width=True)
                            with c4:
                                st.caption("Carte de probabilité")
                                st.image(mask_prob, clamp=True, use_container_width=True)

            finally:
                if tmp_path is not None:
                    tmp_path.unlink(missing_ok=True)

with tab_registry:
    st.subheader("Registry")
    st.json(registry)
