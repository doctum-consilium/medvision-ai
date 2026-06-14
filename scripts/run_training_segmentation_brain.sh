#!/usr/bin/env bash
set -euo pipefail
python -m src.segmentation.train_segmentation --config configs/brain_tumor_segmentation.yaml
