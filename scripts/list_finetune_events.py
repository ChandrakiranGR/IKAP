import json
from pathlib import Path
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

META = Path("data/finetune/ft_job_meta.json")


def main():
    meta = json.loads(META.read_text(encoding="utf-8"))
    job_id = meta["job_id"]

    # Retrieve job
    job = client.fine_tuning.jobs.retrieve(job_id)
    print("job_id:", job.id)
    print("status:", job.status)
    print("fine_tuned_model:", job.fine_tuned_model)
    print()

    # List recent events (logs)
    events = client.fine_tuning.jobs.list_events(job_id, limit=50)

    # events.data is newest-first in most SDKs; print in reverse chronological for readability
    data = list(events.data)
    data.reverse()

    for e in data:
        # e.level: info/warn/error, e.message: text
        print(f"[{e.level}] {e.message}")


if __name__ == "__main__":
    main()
