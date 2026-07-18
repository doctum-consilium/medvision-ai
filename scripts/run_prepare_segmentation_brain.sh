#!/usr/bin/env bash
set -euo pipefail
python -m src.data.prepare_segmentation_dataset --config configs/brain_tumor_segmentation.yaml
