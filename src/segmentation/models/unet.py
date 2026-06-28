"""U-Net architectures for medical image segmentation.

Two variants:
- build_unet: segmentation mask only.
- build_multitask_unet: segmentation mask + classification head (shared encoder).
"""
from __future__ import annotations

import tensorflow as tf


def _conv_block(x: tf.Tensor, filters: int) -> tf.Tensor:
    """Two 3×3 Conv → BN → ReLU layers (standard U-Net block)."""
    x = tf.keras.layers.Conv2D(filters, 3, padding="same", use_bias=False)(x)
    x = tf.keras.layers.BatchNormalization()(x)
    x = tf.keras.layers.ReLU()(x)
    x = tf.keras.layers.Conv2D(filters, 3, padding="same", use_bias=False)(x)
    x = tf.keras.layers.BatchNormalization()(x)
    x = tf.keras.layers.ReLU()(x)
    return x


def _encoder_block(x: tf.Tensor, filters: int) -> tuple[tf.Tensor, tf.Tensor]:
    """Conv block + 2×2 max-pool. Returns (skip, pooled)."""
    skip = _conv_block(x, filters)
    pooled = tf.keras.layers.MaxPooling2D(2)(skip)
    return skip, pooled


def _decoder_block(x: tf.Tensor, skip: tf.Tensor, filters: int) -> tf.Tensor:
    """Bilinear upsample × 2 + concat skip + conv block."""
    x = tf.keras.layers.UpSampling2D(2, interpolation="bilinear")(x)
    x = tf.keras.layers.Concatenate()([x, skip])
    return _conv_block(x, filters)


def _build_encoder(inputs: tf.Tensor) -> tuple[list[tf.Tensor], tf.Tensor]:
    """Returns (skips, bottleneck) for a 4-level encoder."""
    skips: list[tf.Tensor] = []
    x = inputs
    for filters in (64, 128, 256, 512):
        skip, x = _encoder_block(x, filters)
        skips.append(skip)
    bottleneck = _conv_block(x, 1024)
    return skips, bottleneck


def build_unet(image_size: int = 256, num_mask_classes: int = 1) -> tf.keras.Model:
    """Standard U-Net for binary/multi-class semantic segmentation.

    Args:
        image_size: Spatial dimension of the input (image_size × image_size × 3).
        num_mask_classes: 1 → sigmoid binary mask; >1 → softmax per-pixel.

    Returns:
        Compiled-ready Keras Model with a single output named 'segmentation_output'.
    """
    inputs = tf.keras.Input(shape=(image_size, image_size, 3), name="image")
    skips, bottleneck = _build_encoder(inputs)

    x = bottleneck
    for skip, filters in zip(reversed(skips), (512, 256, 128, 64), strict=False):
        x = _decoder_block(x, skip, filters)

    activation = "sigmoid" if num_mask_classes == 1 else "softmax"
    out_channels = 1 if num_mask_classes == 1 else num_mask_classes
    seg_out = tf.keras.layers.Conv2D(
        out_channels, 1, activation=activation, name="segmentation_output"
    )(x)

    return tf.keras.Model(inputs=inputs, outputs=seg_out, name="unet")


def build_multitask_unet(
    image_size: int = 256,
    num_classes: int = 2,
) -> tf.keras.Model:
    """U-Net with shared encoder + dual heads: segmentation mask + image classification.

    The segmentation decoder produces a binary mask (sigmoid).
    The classification head applies global average pooling on the bottleneck
    and outputs a sigmoid (binary) or softmax (multiclass) vector.

    Args:
        image_size: Spatial dimension of the input (image_size × image_size × 3).
        num_classes: Number of classification classes.
                     2 → binary sigmoid (single logit).
                     >2 → softmax over num_classes units.

    Returns:
        Keras Model with two named outputs:
          - 'segmentation_output': (B, H, W, 1) float32 in [0, 1].
          - 'classification_output': (B, 1) for binary or (B, num_classes) for multiclass.
    """
    inputs = tf.keras.Input(shape=(image_size, image_size, 3), name="image")
    skips, bottleneck = _build_encoder(inputs)

    # ── Segmentation decoder ──────────────────────────────────────────────────
    x = bottleneck
    for skip, filters in zip(reversed(skips), (512, 256, 128, 64), strict=False):
        x = _decoder_block(x, skip, filters)
    seg_out = tf.keras.layers.Conv2D(
        1, 1, activation="sigmoid", name="segmentation_output"
    )(x)

    # ── Classification head (from bottleneck) ─────────────────────────────────
    cls_x = tf.keras.layers.GlobalAveragePooling2D()(bottleneck)
    cls_x = tf.keras.layers.Dense(256, activation="relu")(cls_x)
    cls_x = tf.keras.layers.Dropout(0.4)(cls_x)
    if num_classes <= 2:
        cls_out = tf.keras.layers.Dense(1, activation="sigmoid", name="classification_output")(cls_x)
    else:
        cls_out = tf.keras.layers.Dense(num_classes, activation="softmax", name="classification_output")(cls_x)

    return tf.keras.Model(
        inputs=inputs,
        outputs={"segmentation_output": seg_out, "classification_output": cls_out},
        name="multitask_unet",
    )
