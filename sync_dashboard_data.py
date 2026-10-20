"""
Synchronize Life_mean data into the dashboard Docker volume.

The dashboard container deliberately has NO host bind mounts (see
docker-compose.yml: "No host bind mounts. These are Docker-managed
volumes, not C: paths."). To keep that isolation while feeding the
Compare tab real data, this script copies the relevant data folders
host -> container volume before the dashboard starts, then asks the
dashboard to rebuild its index from RAW.

Folders copied:
  data/subjects/    -> /app/data/subjects   (tree markers, topic folders)
  data/raw_debates/ -> /app/data/raw_debates (RAW .jsonl evidence -> index)

Idempotent and safe: only copies, never deletes container-side files it
does not own. Run after `docker compose up -d` and before using the UI.

Usage:
  python sync_dashboard_data.py [--container NAME]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_CONTAINER = "life_mean-dashboard-1"
DASHBOARD_PORT = int(os.environ.get("LIFE_MEAN_PORT", "8080"))
DASHBOARD_URL = f"http://127.0.0.1:{DASHBOARD_PORT}"

# (host relative dir, container absolute dir)
SYNC_DIRS = [
    ("subjects", "/app/data/subjects"),
    ("raw_debates", "/app/data/raw_debates"),
]


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, capture_output=True, text=True)


def sync_folder(container: str, host_rel: str, container_dir: str) -> int:
    """Copy one folder host -> container volume. Returns file count copied."""
    host_dir = DATA_DIR / host_rel
    if not host_dir.is_dir():
        print(f"  [skip] {host_rel}: host folder missing")
        return 0

    # Ensure the target exists inside the container (volume may be fresh).
    _run(["docker", "exec", container, "mkdir", "-p", container_dir])

    # Copy contents into the target directory.
    result = _run([
        "docker", "cp", f"{host_dir}/.", f"{container}:{container_dir}/",
    ])
    if result.returncode != 0:
        print(f"  [error] docker cp failed for {host_rel}: {result.stderr.strip()}")
        return 0

    # Count what landed in the container.
    count = _run([
        "docker", "exec", container, "sh", "-c",
        f"find {container_dir} -type f | wc -l",
    ])
    n = int(count.stdout.strip() or 0)
    print(f"  [ok] {host_rel}: {n} files -> {container_dir}")
    return n


def rebuild_index(container: str, url: str = DASHBOARD_URL) -> bool:
    """Ask the dashboard to rebuild its compare index from RAW."""
    # The container name lets us read where it actually writes the index.
    time.sleep(1)
    try:
        req = urllib.request.urlopen(
            f"{url}/api/compare/browser?refresh=true", timeout=30
        )
        payload = json.load(req)
        count = payload.get("count")
        fresh = payload.get("fresh")
        generated = payload.get("generated_at")
        print(f"  [ok] index rebuilt: count={count}, fresh={fresh}, "
              f"generated_at={generated}")
        return True
    except Exception as e:
        print(f"  [warn] could not rebuild index: {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    args = parser.parse_args()

    print(f"Synchronizing Life_mean data into container {args.container} ...")

    # 1) Make sure the container is running (compose may have just started).
    status = _run(["docker", "inspect", "-f", "{{.State.Running}}", args.container])
    if status.returncode != 0 or status.stdout.strip() != "true":
        print("[error] container is not running — run `docker compose up -d` first")
        return 1

    # 2) Copy the data folders.
    total = 0
    for host_rel, container_dir in SYNC_DIRS:
        total += sync_folder(args.container, host_rel, container_dir)

    # 3) Rebuild the compare index so the UI shows fresh data immediately.
    rebuild_index(args.container)

    print(f"Sync complete ({total} files copied).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
