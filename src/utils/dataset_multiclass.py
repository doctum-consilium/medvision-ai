from __future__ import annotations

from pathlib import Path

import tensorflow as tf

AUTOTUNE = tf.data.AUTOTUNE


def _normalize(images, labels):
    return tf.cast(images, tf.float32) / 255.0, labels


def build_multiclass_datasets(
    dataset_dir: str | Path,
    image_size: int,
    batch_size: int,
    validation_split: float = 0.15,
    seed: int = 42,
    training_subdir: str = "Training",
    testing_subdir: str = "Testing",
) -> tuple[tf.data.Dataset, tf.data.Dataset, tf.data.Dataset, list[str]]:
    dataset_dir = Path(dataset_dir)
    train_root = dataset_dir / training_subdir
    test_root = dataset_dir / testing_subdir

    if not train_root.exists() or not test_root.exists():
        raise FileNotFoundError(
            f"Expected `{train_root}` and `{test_root}` to exist. Check dataset_dir and Kaggle extraction."
        )

    train_ds = tf.keras.utils.image_dataset_from_directory(
        train_root,
        image_size=(image_size, image_size),
        batch_size=batch_size,
        shuffle=True,
        seed=seed,
        validation_split=validation_split,
        subset="training",
        label_mode="int",
    )
    val_ds = tf.keras.utils.image_dataset_from_directory(
        train_root,
        image_size=(image_size, image_size),
        batch_size=batch_size,
        shuffle=True,
        seed=seed,
        validation_split=validation_split,
        subset="validation",
        label_mode="int",
    )
    test_ds = tf.keras.utils.image_dataset_from_directory(
        test_root,
        image_size=(image_size, image_size),
        batch_size=batch_size,
        shuffle=False,
        label_mode="int",
    )

    class_names = train_ds.class_names

    train_ds = train_ds.map(_normalize, num_parallel_calls=AUTOTUNE).prefetch(AUTOTUNE)
    val_ds = val_ds.map(_normalize, num_parallel_calls=AUTOTUNE).prefetch(AUTOTUNE)
    test_ds = test_ds.map(_normalize, num_parallel_calls=AUTOTUNE).prefetch(AUTOTUNE)
    return train_ds, val_ds, test_ds, class_names
