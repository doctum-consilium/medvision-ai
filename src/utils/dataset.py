from __future__ import annotations

from pathlib import Path

import tensorflow as tf

AUTOTUNE = tf.data.AUTOTUNE


def build_datasets(
    dataset_dir: str | Path,
    image_size: int,
    batch_size: int,
    validation_split: float = 0.2,
    seed: int = 42,
) -> tuple[tf.data.Dataset, tf.data.Dataset, tf.data.Dataset]:
    dataset_dir = Path(dataset_dir)
    train_dir = dataset_dir / "train"
    val_dir = dataset_dir / "val"
    test_dir = dataset_dir / "test"

    if train_dir.exists() and val_dir.exists() and test_dir.exists():
        train_ds = tf.keras.utils.image_dataset_from_directory(
            train_dir,
            image_size=(image_size, image_size),
            batch_size=batch_size,
            shuffle=True,
            seed=seed,
            label_mode="binary",
        )
        val_ds = tf.keras.utils.image_dataset_from_directory(
            val_dir,
            image_size=(image_size, image_size),
            batch_size=batch_size,
            shuffle=False,
            label_mode="binary",
        )
        test_ds = tf.keras.utils.image_dataset_from_directory(
            test_dir,
            image_size=(image_size, image_size),
            batch_size=batch_size,
            shuffle=False,
            label_mode="binary",
        )
    else:
        full_ds = tf.keras.utils.image_dataset_from_directory(
            dataset_dir,
            image_size=(image_size, image_size),
            batch_size=batch_size,
            shuffle=True,
            seed=seed,
            label_mode="binary",
            validation_split=validation_split,
            subset="both",
        )
        train_ds, val_ds = full_ds
        test_ds = val_ds

    def prepare(ds: tf.data.Dataset) -> tf.data.Dataset:
        return ds.map(lambda x, y: (tf.cast(x, tf.float32) / 255.0, y), num_parallel_calls=AUTOTUNE).prefetch(AUTOTUNE)

    return prepare(train_ds), prepare(val_ds), prepare(test_ds)
