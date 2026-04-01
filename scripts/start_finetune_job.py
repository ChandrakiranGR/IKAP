#!/usr/bin/env python3
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


DEFAULT_MODEL = "gpt-4o-mini-2024-07-18"
DEFAULT_SUFFIX = "ikap-kb-assistant"


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def count_jsonl_rows(path: Path) -> int:
    count = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                count += 1
    return count


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")
    if path.stat().st_size == 0:
        raise ValueError(f"{label} is empty: {path}")


def slugify_suffix(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned[:40] or DEFAULT_SUFFIX


def write_manifest(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", default="data/finetune/gold_train.jsonl")
    ap.add_argument("--dev", default="data/finetune/gold_dev.jsonl")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--suffix", default=DEFAULT_SUFFIX)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--n-epochs", type=int, default=3)
    ap.add_argument("--batch-size", default="auto")
    ap.add_argument("--learning-rate-multiplier", default="auto")
    ap.add_argument("--jobs-dir", default="data/finetune/jobs")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root = project_root()
    load_dotenv(root / ".env")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found. Put it in .env or export it.")

    train_path = root / args.train
    dev_path = root / args.dev
    require_file(train_path, "Training dataset")
    require_file(dev_path, "Validation dataset")

    train_rows = count_jsonl_rows(train_path)
    dev_rows = count_jsonl_rows(dev_path)
    if train_rows == 0:
        raise ValueError(f"Training dataset has 0 rows: {train_path}")
    if dev_rows == 0:
        raise ValueError(f"Validation dataset has 0 rows: {dev_path}")

    suffix = slugify_suffix(args.suffix)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    jobs_dir = root / args.jobs_dir
    manifest_path = jobs_dir / f"{timestamp}_{suffix}.json"

    payload = {
        "created_at": timestamp,
        "status": "dry_run" if args.dry_run else "launching",
        "base_model": args.model,
        "suffix": suffix,
        "seed": args.seed,
        "hyperparameters": {
            "n_epochs": args.n_epochs,
            "batch_size": args.batch_size,
            "learning_rate_multiplier": args.learning_rate_multiplier,
        },
        "datasets": {
            "train_path": str(train_path),
            "train_rows": train_rows,
            "dev_path": str(dev_path),
            "dev_rows": dev_rows,
        },
    }

    if args.dry_run:
        write_manifest(manifest_path, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print(f"Dry run manifest written to {manifest_path}")
        return 0

    client = OpenAI(api_key=api_key)

    with train_path.open("rb") as fh:
        train_file = client.files.create(file=fh, purpose="fine-tune")
    client.files.wait_for_processing(train_file.id)

    with dev_path.open("rb") as fh:
        dev_file = client.files.create(file=fh, purpose="fine-tune")
    client.files.wait_for_processing(dev_file.id)

    hyperparameters = {
        "n_epochs": args.n_epochs,
        "batch_size": args.batch_size,
        "learning_rate_multiplier": args.learning_rate_multiplier,
    }

    job = client.fine_tuning.jobs.create(
        model=args.model,
        training_file=train_file.id,
        validation_file=dev_file.id,
        suffix=suffix,
        seed=args.seed,
        hyperparameters=hyperparameters,
        metadata={
            "project": "IKAP",
            "dataset": "gold",
            "train_rows": str(train_rows),
            "dev_rows": str(dev_rows),
        },
    )

    payload.update(
        {
            "status": job.status,
            "training_file_id": train_file.id,
            "validation_file_id": dev_file.id,
            "fine_tuning_job_id": job.id,
            "job": job.to_dict(),
        }
    )
    write_manifest(manifest_path, payload)

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"Job manifest written to {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
