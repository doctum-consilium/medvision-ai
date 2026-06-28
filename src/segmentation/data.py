
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import tensorflow as tf
from PIL import Image
from sklearn.model_selection import train_test_split

AUTOTUNE = tf.data.AUTOTUNE


def _read_image(path: str, image_size: int) -> np.ndarray:
    arr = np.asarray(Image.open(path).convert('RGB').resize((image_size, image_size)), dtype=np.float32) / 255.0
    return arr


def _read_mask(path: str, image_size: int) -> np.ndarray:
    mask = Image.open(path).convert('L').resize((image_size, image_size))
    arr = np.asarray(mask, dtype=np.float32) / 255.0
    arr = (arr > 0.5).astype(np.float32)
    return arr[..., None]


def _make_dataset(df: pd.DataFrame, image_size: int, batch_size: int, class_to_idx: dict[str, int], task_type: str, repeat: bool = True):
    image_paths = df['image_path'].tolist()
    mask_paths = df['mask_path'].tolist()
    labels = [class_to_idx.get(lbl, 0) for lbl in df['label'].tolist()]

    def gen():
        for image_path, mask_path, label in zip(image_paths, mask_paths, labels, strict=False):
            image = _read_image(image_path, image_size)
            mask = _read_mask(mask_path, image_size)
            if task_type == 'multitask':
                yield image, {'segmentation_output': mask, 'classification_output': np.array(label, dtype=np.int32)}
            else:
                yield image, mask

    if task_type == 'multitask':
        output_signature = (
            tf.TensorSpec(shape=(image_size, image_size, 3), dtype=tf.float32),
            {
                'segmentation_output': tf.TensorSpec(shape=(image_size, image_size, 1), dtype=tf.float32),
                'classification_output': tf.TensorSpec(shape=(), dtype=tf.int32),
            },
        )
    else:
        output_signature = (
            tf.TensorSpec(shape=(image_size, image_size, 3), dtype=tf.float32),
            tf.TensorSpec(shape=(image_size, image_size, 1), dtype=tf.float32),
        )
    ds = tf.data.Dataset.from_generator(gen, output_signature=output_signature)
    # Seul le train est répété (couplé à steps_per_epoch). Répéter val/test les rend
    # infinis → validation et boucle d'éval post-fit ne se terminent jamais.
    if repeat:
        ds = ds.repeat()
    return ds.batch(batch_size).prefetch(AUTOTUNE)


def build_segmentation_datasets(manifest_path: str | Path, image_size: int, batch_size: int, validation_split: float = 0.2, seed: int = 42, task_type: str = 'multitask'):
    manifest_path = Path(manifest_path)

    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    if manifest_path.stat().st_size == 0:
        raise ValueError(
            f"Manifest is empty: {manifest_path}. "
            "prepare_segmentation_dataset produced zero rows."
        )

    df = pd.read_csv(manifest_path)

    if df.empty:
        raise ValueError(f'No rows found in manifest {manifest_path}')
    labels = sorted([lbl for lbl in df['label'].dropna().unique().tolist() if lbl != 'unknown'])
    if not labels:
        labels = ['negative', 'positive']
    class_to_idx = {name: idx for idx, name in enumerate(labels)}

    train_df = df[df['split'] != 'test'].copy()
    test_df = df[df['split'] == 'test'].copy()
    if test_df.empty:
        train_df, test_df = train_test_split(train_df, test_size=max(validation_split, 0.15), random_state=seed, stratify=train_df['label'])
    train_df, val_df = train_test_split(train_df, test_size=validation_split, random_state=seed, stratify=train_df['label'])

    train_size = len(train_df)

    return (
        _make_dataset(train_df, image_size, batch_size, class_to_idx, task_type, repeat=True),
        _make_dataset(val_df, image_size, batch_size, class_to_idx, task_type, repeat=False),
        _make_dataset(test_df, image_size, batch_size, class_to_idx, task_type, repeat=False),
        labels,
        train_size,
    )
