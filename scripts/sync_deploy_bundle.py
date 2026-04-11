from __future__ import annotations

import shutil
from pathlib import Path


def copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    source_kb = root / "data" / "processed" / "kb_json"
    source_index = root / "data" / "rag" / "kb_index.jsonl"

    if not source_kb.exists():
        raise FileNotFoundError(f"Missing processed KB directory: {source_kb}")
    if not source_index.exists():
        raise FileNotFoundError(f"Missing RAG index: {source_index}")

    target_kb = root / "deploy_data" / "processed" / "kb_json"
    target_index = root / "deploy_data" / "rag" / "kb_index.jsonl"
    target_index.parent.mkdir(parents=True, exist_ok=True)

    copy_tree(source_kb, target_kb)
    shutil.copy2(source_index, target_index)

    print(f"Copied KB corpus to {target_kb}")
    print(f"Copied RAG index to {target_index}")


if __name__ == "__main__":
    main()
