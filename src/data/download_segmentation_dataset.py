
from __future__ import annotations

import argparse
import shutil
import subprocess
import zipfile
from pathlib import Path

SEGMENTATION_DATASETS = {
    'brain_tumor_seg': {
        'slug': 'indk214/brain-tumor-dataset-segmentation-and-classification',
        'target_dir': 'data/raw/brain_tumor_segmentation',
    },
    'chest_xray_seg': {
        'slug': 'nikhilpandey360/chest-xray-masks-and-labels',
        'target_dir': 'data/raw/chest_xray_segmentation',
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Download segmentation datasets from Kaggle')
    parser.add_argument('--problem', choices=sorted(SEGMENTATION_DATASETS.keys()), required=True)
    parser.add_argument('--output-dir', default=None)
    parser.add_argument('--force', action='store_true')
    return parser.parse_args()


def _extract_all(zip_path: Path, dest: Path) -> None:
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(dest)


def _download_with_cli(slug: str, download_dir: Path) -> Path:
    if shutil.which('kaggle') is None:
        raise FileNotFoundError('Kaggle CLI is not installed')

    cmd = ['kaggle', 'datasets', 'download', '-d', slug, '-p', str(download_dir), '-o']
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise RuntimeError(f'Kaggle CLI download failed with exit code {result.returncode}')

    zip_path = download_dir / f"{slug.split('/')[-1]}.zip"
    if zip_path.exists():
        return zip_path

    candidates = sorted(download_dir.glob('*.zip'), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise RuntimeError('Kaggle CLI reported success but no zip archive was found')
    return candidates[0]


def _download_with_api(slug: str, download_dir: Path) -> Path:
    from kaggle.api.kaggle_api_extended import KaggleApi

    api = KaggleApi()
    api.authenticate()
    api.dataset_download_files(slug, path=str(download_dir), unzip=False)

    zip_path = download_dir / f"{slug.split('/')[-1]}.zip"
    if zip_path.exists():
        return zip_path

    candidates = sorted(download_dir.glob('*.zip'), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise RuntimeError('Kaggle API reported success but no zip archive was found')
    return candidates[0]


def main() -> None:
    args = parse_args()
    spec = SEGMENTATION_DATASETS[args.problem]
    target_dir = Path(args.output_dir or spec['target_dir'])
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    if target_dir.exists() and any(target_dir.iterdir()) and not args.force:
        print(f'{target_dir} already exists and is not empty; skipping download.')
        return
    if target_dir.exists() and args.force:
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    download_dir = target_dir.parent
    try:
        zip_path = _download_with_cli(spec['slug'], download_dir)
    except Exception as cli_err:
        print(f'Kaggle CLI path failed ({cli_err}); falling back to Kaggle API client...')
        try:
            zip_path = _download_with_api(spec['slug'], download_dir)
        except Exception as api_err:
            raise SystemExit(
                f'Failed to download dataset {spec["slug"]}. '
                f'CLI error: {cli_err}. API error: {api_err}.\n'
                'If the process is being killed by the OS, check memory/disk on the host '
                '(e.g. `free -h`, `df -h`, `dmesg -T | grep -Ei "killed process|oom" | tail`).'
            ) from api_err

    _extract_all(zip_path, target_dir)
    print(f'Downloaded and extracted {spec["slug"]} to {target_dir}')


if __name__ == '__main__':
    main()
