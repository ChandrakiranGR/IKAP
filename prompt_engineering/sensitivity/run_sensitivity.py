"""
run_sensitivity.py
-------------------
Runs all combinations of prompt variants × temperatures × user query paraphrases
through the OpenAI API and saves raw results to sensitivity_results.json.

Test matrix: 3 prompt variants × 3 temperatures × 6 queries = 54 API calls
"""

import json
import os
import time
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
from prompts import PROMPT_VARIANTS

# Load .env file from project root
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

MODEL = "gpt-4o-mini"
MAX_TOKENS = 500
TEMPERATURES = [0.0, 0.3, 0.7]
OUTPUT_FILE = "sensitivity_results.json"

# Initialize OpenAI client
client = OpenAI()

# =============================================================================
# USER QUERY PARAPHRASES
# =============================================================================
# 3 categories × 2 paraphrases each = 6 unique queries

USER_QUERIES = {
    "mfa_enrollment": [
        "How do I enroll in Duo multi-factor authentication?",
        "I'm a new student and I need to set up MFA. What are the steps?",
    ],
    "password_reset": [
        "I forgot my Northeastern password. How do I reset it?",
        "I can't log in to my account. I think my password is wrong.",
    ],
    "wifi_connectivity": [
        "How do I connect to campus WiFi on my laptop?",
        "WiFi keeps asking for credentials and then failing. What should I do?",
    ],
}

# =============================================================================
# RUN EXPERIMENT
# =============================================================================

def run_single_query(system_prompt, user_query, temperature):
    """Send a single query to the API and return the response text."""
    try:
        response = client.chat.completions.create(
            model=MODEL,
            temperature=temperature,
            max_tokens=MAX_TOKENS,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query},
            ],
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"ERROR: {str(e)}"


def run_all_experiments():
    """Run all combinations and collect results."""
    results = []
    total_combinations = (
        len(PROMPT_VARIANTS) * len(TEMPERATURES) * sum(len(q) for q in USER_QUERIES.values())
    )
    current = 0

    print(f"Starting sensitivity test: {total_combinations} total API calls")
    print(f"Prompt variants: {list(PROMPT_VARIANTS.keys())}")
    print(f"Temperatures: {TEMPERATURES}")
    print(f"Categories: {list(USER_QUERIES.keys())}")
    print("-" * 60)

    for prompt_name, system_prompt in PROMPT_VARIANTS.items():
        for temp in TEMPERATURES:
            for category, queries in USER_QUERIES.items():
                for query in queries:
                    current += 1
                    print(f"[{current}/{total_combinations}] {prompt_name} | temp={temp} | {category}")

                    response_text = run_single_query(system_prompt, query, temp)

                    results.append({
                        "prompt_variant": prompt_name,
                        "temperature": temp,
                        "category": category,
                        "user_query": query,
                        "response": response_text,
                        "model": MODEL,
                        "max_tokens": MAX_TOKENS,
                        "timestamp": datetime.now().isoformat(),
                    })

                    # Small delay to avoid rate limiting
                    time.sleep(0.5)

    return results


def save_results(results):
    """Save results to JSON file."""
    output = {
        "experiment": "IKAP Prompt Sensitivity Testing",
        "date": datetime.now().isoformat(),
        "config": {
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "temperatures": TEMPERATURES,
            "prompt_variants": list(PROMPT_VARIANTS.keys()),
            "categories": list(USER_QUERIES.keys()),
            "total_runs": len(results),
        },
        "results": results,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nResults saved to {OUTPUT_FILE}")
    print(f"Total runs: {len(results)}")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    results = run_all_experiments()
    save_results(results)