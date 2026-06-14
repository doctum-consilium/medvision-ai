
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.segmentation.datasets.manifest import build_manifest
from src.utils.config import load_config

DEFAULT_LABELS = {
    'brain': ['glioma', 'meningioma', 'pituitary', 'notumor'],
    'chest': ['NORMAL', 'ABNORMAL', 'normal', 'abnormal'],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Prepare a segmentation manifest from a raw dataset tree')
    parser.add_argument('--config', required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    raw_dir = Path(cfg['raw_dataset_dir'])
    manifest_path = Path(cfg['manifest_path'])
    known_labels = cfg.get('class_names') or DEFAULT_LABELS['brain']
    df = build_manifest(raw_dir=raw_dir, output_csv=manifest_path, known_labels=known_labels)
    summary = {
        'rows': int(len(df)),
        'labels': sorted(df['label'].dropna().unique().tolist()) if not df.empty else [],
        'manifest_path': str(manifest_path),
    }
    summary_path = Path(cfg.get('dataset_summary_path', manifest_path.with_name('dataset_summary.json')))
    summary_path.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
