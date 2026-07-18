#!/usr/bin/env bash
set -euo pipefail
python -m src.segmentation.train_segmentation --config configs/chest_xray_segmentation.yaml
