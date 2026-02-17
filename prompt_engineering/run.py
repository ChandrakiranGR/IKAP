import os
import json
import importlib
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# ---------- Config ----------
MODEL = "gpt-4o-mini"
TEMPERATURE = 0.3
MAX_TOKENS = 500

USER_QUERY = (
    "I am a new Northeastern student. "
    "How do I enroll in Duo multi-factor authentication?"
)
# ---------------------------

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise RuntimeError("OPENAI_API_KEY not found. Put it in .env")

client = OpenAI(api_key=api_key)

BASE_DIR = Path(__file__).parent
RESULTS_DIR = BASE_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def call_llm(system_prompt: str, user_prompt: str) -> str:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt.strip()},
        ],
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
    )
    return resp.choices[0].message.content


def save_result(payload: dict) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"{ts}_{payload['technique']}.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def run_experiment(experiment_module_name: str):
    module = importlib.import_module(f"experiments.{experiment_module_name}")

    technique = module.TECHNIQUE_NAME
    system_prompt = module.SYSTEM_PROMPT

    response = call_llm(system_prompt, USER_QUERY)

    payload = {
        "technique": technique,
        "model": MODEL,
        "temperature": TEMPERATURE,
        "user_query": USER_QUERY,
        "system_prompt": system_prompt.strip(),
        "response": response,
    }

    out_path = save_result(payload)
    print(f"[✓] Saved: {out_path}")


if __name__ == "__main__":
    run_experiment("zero_shot")
