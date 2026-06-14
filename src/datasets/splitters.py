from __future__ import annotations

from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

from src.utils.paths import ensure_dir

REQUIRED_COLUMNS = {"patient_id", "path", "label"}


def create_patient_level_splits(
    metadata_csv: str | Path,
    output_dir: str | Path,
    seed: int = 42,
    val_size: float = 0.2,
    test_size: float = 0.2,
) -> tuple[Path, Path, Path, Path]:
    """Create patient-level splits from a metadata CSV.

    The CSV must contain at least: patient_id, path, label.
    """
    metadata_csv = Path(metadata_csv)
    output_dir = ensure_dir(output_dir)
    df = pd.read_csv(metadata_csv)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Metadata CSV missing columns: {sorted(missing)}")

    patient_df = df[["patient_id", "label"]].drop_duplicates().reset_index(drop=True)

    train_patients, temp_patients = train_test_split(
        patient_df,
        test_size=val_size + test_size,
        random_state=seed,
        stratify=patient_df["label"],
    )

    relative_test_size = test_size / (val_size + test_size)
    val_patients, test_patients = train_test_split(
        temp_patients,
        test_size=relative_test_size,
        random_state=seed,
        stratify=temp_patients["label"],
    )

    split_frames = {
        "train": train_patients,
        "val": val_patients,
        "test": test_patients,
    }

    merged_frames: dict[str, pd.DataFrame] = {}
    for split_name, patient_split in split_frames.items():
        merged = df.merge(patient_split[["patient_id"]], on="patient_id", how="inner").copy()
        merged["split"] = split_name
        merged_frames[split_name] = merged

    split_csv = output_dir / "splits.csv"
    pd.concat(merged_frames.values(), ignore_index=True).to_csv(split_csv, index=False)

    train_csv = output_dir / "train.csv"
    val_csv = output_dir / "val.csv"
    test_csv = output_dir / "test.csv"
    merged_frames["train"].to_csv(train_csv, index=False)
    merged_frames["val"].to_csv(val_csv, index=False)
    merged_frames["test"].to_csv(test_csv, index=False)
    return split_csv, train_csv, val_csv, test_csv
