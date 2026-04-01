#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_manifest(jobs_dir: Path) -> Path:
    manifests = sorted(jobs_dir.glob("*.json"))
    if not manifests:
        raise FileNotFoundError(f"No fine-tune job manifests found in {jobs_dir}")
    return manifests[-1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job-id", default="")
    ap.add_argument("--manifest", default="")
    ap.add_argument("--jobs-dir", default="data/finetune/jobs")
    ap.add_argument("--limit-events", type=int, default=20)
    args = ap.parse_args()

    root = project_root()
    load_dotenv(root / ".env")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found. Put it in .env or export it.")

    manifest_payload = None
    job_id = args.job_id.strip()
    if args.manifest:
        manifest_path = root / args.manifest
        manifest_payload = load_manifest(manifest_path)
        job_id = manifest_payload.get("fine_tuning_job_id", "").strip()
    elif not job_id:
        manifest_path = latest_manifest(root / args.jobs_dir)
        manifest_payload = load_manifest(manifest_path)
        job_id = manifest_payload.get("fine_tuning_job_id", "").strip()

    if not job_id:
        raise ValueError("No fine-tuning job id found. Pass --job-id or --manifest.")

    client = OpenAI(api_key=api_key)
    job = client.fine_tuning.jobs.retrieve(job_id)
    events = client.fine_tuning.jobs.list_events(job_id, limit=args.limit_events)

    payload = {
        "job_id": job.id,
        "status": job.status,
        "model": job.model,
        "fine_tuned_model": getattr(job, "fine_tuned_model", None),
        "trained_tokens": getattr(job, "trained_tokens", None),
        "training_file": getattr(job, "training_file", None),
        "validation_file": getattr(job, "validation_file", None),
        "result_files": getattr(job, "result_files", None),
        "created_at": getattr(job, "created_at", None),
        "finished_at": getattr(job, "finished_at", None),
        "manifest": manifest_payload,
        "events": [event.to_dict() for event in events.data],
    }

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
