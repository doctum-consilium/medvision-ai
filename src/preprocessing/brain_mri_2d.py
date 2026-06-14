from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import torch
import torch.nn.functional as F


class BrainMRI2DPreprocessor:
    def __init__(self, image_size: int = 128, normalization: str = "zscore_nonzero") -> None:
        self.image_size = image_size
        self.normalization = normalization

    def normalize(self, volume: np.ndarray) -> np.ndarray:
        volume = volume.astype(np.float32)
        if self.normalization == "zscore_nonzero":
            mask = volume != 0
            if np.any(mask):
                values = volume[mask]
                mean = float(values.mean())
                std = float(values.std())
                std = std if std > 1e-6 else 1.0
                volume = np.where(mask, (volume - mean) / std, 0.0)
        elif self.normalization == "minmax":
            vmin = float(volume.min())
            vmax = float(volume.max())
            if vmax - vmin > 1e-6:
                volume = (volume - vmin) / (vmax - vmin)
        return volume

    def select_slices(self, volume: np.ndarray, strategy: str = "central_k", k: int = 5) -> Sequence[np.ndarray]:
        depth = volume.shape[2]
        if strategy != "central_k":
            raise ValueError(f"Unsupported slice strategy: {strategy}")
        center = depth // 2
        half = max(1, k // 2)
        indices = [min(max(i, 0), depth - 1) for i in range(center - half, center + half + 1)]
        return [volume[:, :, idx] for idx in indices]

    def resize_slice(self, slice_2d: np.ndarray) -> np.ndarray:
        tensor = torch.from_numpy(slice_2d).float().unsqueeze(0).unsqueeze(0)
        tensor = F.interpolate(tensor, size=(self.image_size, self.image_size), mode="bilinear", align_corners=False)
        return tensor.squeeze(0).numpy()

    def preprocess_volume(self, volume: np.ndarray, strategy: str = "central_k", k: int = 5) -> list[np.ndarray]:
        volume = self.normalize(volume)
        slices = self.select_slices(volume, strategy=strategy, k=k)
        return [self.resize_slice(slice_2d) for slice_2d in slices]
