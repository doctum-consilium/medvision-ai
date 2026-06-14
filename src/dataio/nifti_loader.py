from __future__ import annotations

from pathlib import Path

import numpy as np

SUPPORTED_SUFFIXES = {".nii", ".gz", ".npy"}


def load_volume(path: str | Path) -> np.ndarray:
    """Load a medical volume.

    Supported formats in this demo:
    - .npy: synthetic/demo data and fast local experiments
    - .nii/.nii.gz: real MRI volumes when nibabel is installed
    """
    path = Path(path)
    if path.suffix == ".npy":
        volume = np.load(path)
    elif path.suffix == ".nii" or path.name.endswith(".nii.gz"):
        try:
            import nibabel as nib  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "nibabel is required to read NIfTI files. Install it with `pip install nibabel`."
            ) from exc
        nii = nib.load(str(path))
        volume = np.asarray(nii.get_fdata(), dtype=np.float32)
    else:
        raise ValueError(f"Unsupported volume format for {path}")

    if volume.ndim != 3:
        raise ValueError(f"Expected a 3D volume, got shape {volume.shape} for {path}")

    return volume.astype(np.float32)
