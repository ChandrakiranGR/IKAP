"""
evaluate_sensitivity.py
------------------------
Reads sensitivity_results.json, scores each response on evaluation criteria,
and produces sensitivity_report.md with summary tables.
"""

import json
import re
from collections import defaultdict
from datetime import datetime

INPUT_FILE = "sensitivity_results.json"
OUTPUT_FILE = "sensitivity_report.md"

# =============================================================================
# EVALUATION CRITERIA (AUTOMATED CHECKS)
# =============================================================================

# Expected category keywords for each query category
EXPECTED_CATEGORIES = {
    "mfa_enrollment": ["mfa", "multi-factor", "authentication", "duo"],
    "password_reset": ["password", "account", "lockout", "access"],
    "wifi_connectivity": ["wifi", "wi-fi", "wireless", "network", "connectivity"],
}

# Known fabricated patterns to flag as hallucinations
HALLUCINATION_PATTERNS = [
    r"https?://\S+",                          # Any URL
    r"\d{3}[-.\s]?\d{3}[-.\s]?\d{4}",        # Phone numbers
    r"myNortheastern",                         # Specific portal name
    r"ServiceNow",                             # Specific system name
    r"sail\.northeastern\.edu",                # Specific portal
    r"my\.northeastern\.edu",                  # Specific portal
    r"Room \w+\d+",                            # Specific office locations
]


def check_format_compliance(response):
    """
    Check if the response follows the required output format.
    Returns a score: 1.0 (perfect), 0.5 (partial), 0.0 (non-compliant).
    """
    checks = {
        "has_category": bool(re.search(r"Category:", response, re.IGNORECASE)),
        "has_clarifying": bool(re.search(r"Clarifying question:", response, re.IGNORECASE)),
        "has_steps_label": bool(re.search(r"Steps.*:", response, re.IGNORECASE)),
        "has_numbered_steps": bool(re.search(r"\n\s*\d+\.", response)),
        "has_escalation": bool(re.search(r"(does not resolve|contact.*IT|support)", response, re.IGNORECASE)),
    }
    score = sum(checks.values()) / len(checks)
    return score, checks


def check_category_accuracy(response, expected_category):
    """
    Check if the detected category in the response matches the expected category.
    Returns 1 if correct, 0 if wrong.
    """
    cat_match = re.search(r"Category:\s*(.+?)(?:\n|$)", response, re.IGNORECASE)
    if not cat_match:
        return 0

    detected = cat_match.group(1).strip().lower()
    expected_keywords = EXPECTED_CATEGORIES.get(expected_category, [])

    for keyword in expected_keywords:
        if keyword in detected:
            return 1
    return 0


def check_safety(response):
    """
    Check for hallucinated URLs, phone numbers, or Northeastern-specific system names.
    Returns 1 if safe (no hallucinations), 0 if violations found.
    """
    violations = []
    for pattern in HALLUCINATION_PATTERNS:
        matches = re.findall(pattern, response, re.IGNORECASE)
        if matches:
            violations.extend(matches)
    return (1 if not violations else 0), violations


def check_general_guidance_label(response):
    """
    Check if steps are labeled as general guidance (required in no-KB setting).
    Returns 1 if present, 0 if missing.
    """
    return int(bool(re.search(r"general guidance", response, re.IGNORECASE)))


def count_steps(response):
    """Count the number of numbered steps in the response."""
    steps = re.findall(r"\n\s*\d+\.\s", response)
    return len(steps)


def evaluate_single_response(result):
    """Evaluate a single response across all criteria."""
    response = result["response"]
    category = result["category"]

    format_score, format_details = check_format_compliance(response)
    category_score = check_category_accuracy(response, category)
    safety_score, safety_violations = check_safety(response)
    guidance_label = check_general_guidance_label(response)
    step_count = count_steps(response)

    return {
        "prompt_variant": result["prompt_variant"],
        "temperature": result["temperature"],
        "category": result["category"],
        "user_query": result["user_query"],
        "format_score": format_score,
        "format_details": format_details,
        "category_accuracy": category_score,
        "safety_score": safety_score,
        "safety_violations": safety_violations,
        "guidance_label": guidance_label,
        "step_count": step_count,
    }


# =============================================================================
# AGGREGATION HELPERS
# =============================================================================

def aggregate_by_key(evaluations, key):
    """Aggregate scores grouped by a given key (e.g., prompt_variant, temperature)."""
    groups = defaultdict(list)
    for e in evaluations:
        groups[e[key]].append(e)

    summary = {}
    for group_name, evals in groups.items():
        n = len(evals)
        summary[group_name] = {
            "count": n,
            "avg_format": round(sum(e["format_score"] for e in evals) / n, 3),
            "avg_category": round(sum(e["category_accuracy"] for e in evals) / n, 3),
            "avg_safety": round(sum(e["safety_score"] for e in evals) / n, 3),
            "avg_guidance_label": round(sum(e["guidance_label"] for e in evals) / n, 3),
            "avg_step_count": round(sum(e["step_count"] for e in evals) / n, 1),
        }
    return summary


def aggregate_by_two_keys(evaluations, key1, key2):
    """Aggregate scores grouped by two keys (e.g., prompt_variant × temperature)."""
    groups = defaultdict(list)
    for e in evaluations:
        groups[(e[key1], e[key2])].append(e)

    summary = {}
    for (k1, k2), evals in groups.items():
        n = len(evals)
        summary[(k1, k2)] = {
            "count": n,
            "avg_format": round(sum(e["format_score"] for e in evals) / n, 3),
            "avg_category": round(sum(e["category_accuracy"] for e in evals) / n, 3),
            "avg_safety": round(sum(e["safety_score"] for e in evals) / n, 3),
        }
    return summary


# =============================================================================
# REPORT GENERATION
# =============================================================================

def generate_report(evaluations, config):
    """Generate a markdown report with summary tables."""
    lines = []
    lines.append("# IKAP Prompt Sensitivity Report")
    lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"\nModel: {config['model']} | Max tokens: {config['max_tokens']}")
    lines.append(f"Total runs: {config['total_runs']}")
    lines.append(f"Prompt variants: {', '.join(config['prompt_variants'])}")
    lines.append(f"Temperatures: {config['temperatures']}")
    lines.append(f"Categories: {', '.join(config['categories'])}")

    # ----- Overall Summary -----
    lines.append("\n## 1. Overall Summary")
    n = len(evaluations)
    lines.append(f"\n| Metric | Average Score |")
    lines.append(f"|--------|--------------|")
    lines.append(f"| Format compliance | {sum(e['format_score'] for e in evaluations)/n:.3f} |")
    lines.append(f"| Category accuracy | {sum(e['category_accuracy'] for e in evaluations)/n:.3f} |")
    lines.append(f"| Safety (no hallucination) | {sum(e['safety_score'] for e in evaluations)/n:.3f} |")
    lines.append(f"| General guidance label | {sum(e['guidance_label'] for e in evaluations)/n:.3f} |")
    lines.append(f"| Avg step count | {sum(e['step_count'] for e in evaluations)/n:.1f} |")

    # ----- By Prompt Variant -----
    lines.append("\n## 2. Scores by Prompt Variant")
    by_prompt = aggregate_by_key(evaluations, "prompt_variant")
    lines.append(f"\n| Prompt Variant | Format | Category | Safety | Guidance Label | Avg Steps |")
    lines.append(f"|---------------|--------|----------|--------|---------------|-----------|")
    for name, scores in sorted(by_prompt.items()):
        lines.append(
            f"| {name} | {scores['avg_format']} | {scores['avg_category']} | "
            f"{scores['avg_safety']} | {scores['avg_guidance_label']} | {scores['avg_step_count']} |"
        )

    # ----- By Temperature -----
    lines.append("\n## 3. Scores by Temperature")
    by_temp = aggregate_by_key(evaluations, "temperature")
    lines.append(f"\n| Temperature | Format | Category | Safety | Guidance Label | Avg Steps |")
    lines.append(f"|------------|--------|----------|--------|---------------|-----------|")
    for temp, scores in sorted(by_temp.items()):
        lines.append(
            f"| {temp} | {scores['avg_format']} | {scores['avg_category']} | "
            f"{scores['avg_safety']} | {scores['avg_guidance_label']} | {scores['avg_step_count']} |"
        )

    # ----- By Category -----
    lines.append("\n## 4. Scores by Query Category")
    by_cat = aggregate_by_key(evaluations, "category")
    lines.append(f"\n| Category | Format | Category Acc. | Safety | Guidance Label | Avg Steps |")
    lines.append(f"|----------|--------|-------------|--------|---------------|-----------|")
    for cat, scores in sorted(by_cat.items()):
        lines.append(
            f"| {cat} | {scores['avg_format']} | {scores['avg_category']} | "
            f"{scores['avg_safety']} | {scores['avg_guidance_label']} | {scores['avg_step_count']} |"
        )

    # ----- Prompt × Temperature Cross-Tab -----
    lines.append("\n## 5. Prompt Variant × Temperature (Format Compliance)")
    by_cross = aggregate_by_two_keys(evaluations, "prompt_variant", "temperature")
    temps = sorted(set(e["temperature"] for e in evaluations))
    prompts = sorted(set(e["prompt_variant"] for e in evaluations))
    header = "| Prompt / Temp | " + " | ".join(str(t) for t in temps) + " |"
    sep = "|" + "---|" * (len(temps) + 1)
    lines.append(f"\n{header}")
    lines.append(sep)
    for p in prompts:
        row = f"| {p} |"
        for t in temps:
            score = by_cross.get((p, t), {}).get("avg_format", "N/A")
            row += f" {score} |"
        lines.append(row)

    # ----- Safety Violations Detail -----
    lines.append("\n## 6. Safety Violations (if any)")
    violations_found = False
    for e in evaluations:
        if e["safety_violations"]:
            violations_found = True
            lines.append(
                f"\n- **{e['prompt_variant']}** | temp={e['temperature']} | "
                f"{e['category']}: `{e['safety_violations']}`"
            )
            lines.append(f"  - Query: \"{e['user_query']}\"")
    if not violations_found:
        lines.append("\nNo safety violations detected across all runs.")

    # ----- Format Failures Detail -----
    lines.append("\n## 7. Format Compliance Failures (score < 1.0)")
    failures_found = False
    for e in evaluations:
        if e["format_score"] < 1.0:
            failures_found = True
            missing = [k for k, v in e["format_details"].items() if not v]
            lines.append(
                f"\n- **{e['prompt_variant']}** | temp={e['temperature']} | "
                f"{e['category']}: missing `{missing}`"
            )
            lines.append(f"  - Query: \"{e['user_query']}\"")
    if not failures_found:
        lines.append("\nAll responses achieved full format compliance.")

    # ----- Recommendations -----
    lines.append("\n## 8. Recommendations for Prompt Hardening")
    lines.append("\nBased on the results above, consider the following:")
    lines.append("\n- If format compliance drops at higher temperatures, add stronger format enforcement or select a lower temperature.")
    lines.append("- If category accuracy is low for specific categories, add category-specific hints or examples.")
    lines.append("- If safety violations appear, tighten grounding constraints in the affected prompt section.")
    lines.append("- If the guidance label is missing in some responses, make the label part of a fixed template string rather than an instruction.")
    lines.append("- Use the best-performing prompt variant and temperature combination as your hardened baseline.")

    return "\n".join(lines)


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    # Load results
    with open(INPUT_FILE, "r") as f:
        data = json.load(f)

    config = data["config"]
    results = data["results"]

    print(f"Loaded {len(results)} results from {INPUT_FILE}")

    # Evaluate each response
    evaluations = [evaluate_single_response(r) for r in results]

    # Generate report
    report = generate_report(evaluations, config)

    # Save report
    with open(OUTPUT_FILE, "w") as f:
        f.write(report)

    print(f"Report saved to {OUTPUT_FILE}")
    print("\n--- Quick Summary ---")
    n = len(evaluations)
    print(f"Avg format compliance: {sum(e['format_score'] for e in evaluations)/n:.3f}")
    print(f"Avg category accuracy: {sum(e['category_accuracy'] for e in evaluations)/n:.3f}")
    print(f"Avg safety score:      {sum(e['safety_score'] for e in evaluations)/n:.3f}")
    print(f"Avg guidance label:    {sum(e['guidance_label'] for e in evaluations)/n:.3f}")