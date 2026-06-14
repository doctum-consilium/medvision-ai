#!/usr/bin/env bash
set -euo pipefail
python -m src.data.download_segmentation_dataset --problem brain_tumor_seg
