import os
import json
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

TRAIN_PATH = Path("data/finetune/train_ft.jsonl")
VALID_PATH = Path("data/finetune/valid_ft.jsonl")

# Per OpenAI cookbook example, a common base model for SFT is:
BASE_MODEL = "gpt-4o-mini-2024-07-18"

OUT_META = Path("data/finetune/ft_job_meta.json")
OUT_META.parent.mkdir(parents=True, exist_ok=True)


def upload(path: Path) -> str:
    resp = client.files.create(
        file=path.open("rb"),
        purpose="fine-tune",
    )
    return resp.id


def main():
    if not TRAIN_PATH.exists() or not VALID_PATH.exists():
        raise FileNotFoundError(
            "Missing train_ft.jsonl or valid_ft.jsonl under data/finetune/"
        )

    print("Uploading training file...")
    train_file_id = upload(TRAIN_PATH)
    print("Training file_id:", train_file_id)

    print("Uploading validation file...")
    valid_file_id = upload(VALID_PATH)
    print("Validation file_id:", valid_file_id)

    print("Creating fine-tuning job...")
    job = client.fine_tuning.jobs.create(
        model=BASE_MODEL,
        training_file=train_file_id,
        validation_file=valid_file_id,
    )

    meta = {
        "base_model": BASE_MODEL,
        "train_file": str(TRAIN_PATH),
        "valid_file": str(VALID_PATH),
        "train_file_id": train_file_id,
        "valid_file_id": valid_file_id,
        "job_id": job.id,
        "status": job.status,
    }
    OUT_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print("\n Fine-tune job started")
    print("job_id:", job.id)
    print("status:", job.status)
    print("Saved metadata to:", OUT_META)


if __name__ == "__main__":
    main()
