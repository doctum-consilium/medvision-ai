#!/usr/bin/env bash
set -euo pipefail
python -m src.data.download_segmentation_dataset --problem chest_xray_seg
