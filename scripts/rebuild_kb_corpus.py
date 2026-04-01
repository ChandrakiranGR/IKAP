#!/usr/bin/env python3
import argparse
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], cwd: Path):
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_dir", default="data/raw")
    ap.add_argument("--out_dir", default="data/processed/kb_json")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    python = sys.executable

    run(
        [
            python,
            "scripts/raw_kb_to_processed.py",
            "--in_dir",
            args.in_dir,
            "--out_dir",
            args.out_dir,
            "--prune",
        ],
        cwd=root,
    )
    run([python, "scripts/validate_kb_corpus.py", "--kb_dir", args.out_dir], cwd=root)
    run([python, "scripts/kb_index.py"], cwd=root)


if __name__ == "__main__":
    main()
