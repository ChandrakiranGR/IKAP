import json
from pathlib import Path
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

META = Path("data/finetune/ft_job_meta.json")


def main():
    if not META.exists():
        raise FileNotFoundError(
            "Missing data/finetune/ft_job_meta.json. Run start_finetune_job.py first."
        )

    meta = json.loads(META.read_text(encoding="utf-8"))
    job_id = meta["job_id"]

    job = client.fine_tuning.jobs.retrieve(job_id)

    meta["status"] = job.status
    meta["fine_tuned_model"] = job.fine_tuned_model  # becomes non-null when succeeded
    META.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print("job_id:", job.id)
    print("status:", job.status)
    print("fine_tuned_model:", job.fine_tuned_model)

    if job.status == "failed" and job.error:
        print("\nJob failed:")
        print(job.error)


if __name__ == "__main__":
    main()
