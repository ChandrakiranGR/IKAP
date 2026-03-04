# IKAP Prompt Sensitivity Report

Generated: 2026-03-04 13:44

Model: gpt-4o-mini | Max tokens: 500
Total runs: 54
Prompt variants: v3_revised, v3_rephrase_a, v3_rephrase_b
Temperatures: [0.0, 0.3, 0.7]
Categories: mfa_enrollment, password_reset, wifi_connectivity

## 1. Overall Summary

| Metric | Average Score |
|--------|--------------|
| Format compliance | 1.000 |
| Category accuracy | 1.000 |
| Safety (no hallucination) | 1.000 |
| General guidance label | 1.000 |
| Avg step count | 5.9 |

## 2. Scores by Prompt Variant

| Prompt Variant | Format | Category | Safety | Guidance Label | Avg Steps |
|---------------|--------|----------|--------|---------------|-----------|
| v3_rephrase_a | 1.0 | 1.0 | 1.0 | 1.0 | 5.8 |
| v3_rephrase_b | 1.0 | 1.0 | 1.0 | 1.0 | 5.9 |
| v3_revised | 1.0 | 1.0 | 1.0 | 1.0 | 5.9 |

## 3. Scores by Temperature

| Temperature | Format | Category | Safety | Guidance Label | Avg Steps |
|------------|--------|----------|--------|---------------|-----------|
| 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 5.9 |
| 0.3 | 1.0 | 1.0 | 1.0 | 1.0 | 5.7 |
| 0.7 | 1.0 | 1.0 | 1.0 | 1.0 | 5.9 |

## 4. Scores by Query Category

| Category | Format | Category Acc. | Safety | Guidance Label | Avg Steps |
|----------|--------|-------------|--------|---------------|-----------|
| mfa_enrollment | 1.0 | 1.0 | 1.0 | 1.0 | 6.0 |
| password_reset | 1.0 | 1.0 | 1.0 | 1.0 | 5.7 |
| wifi_connectivity | 1.0 | 1.0 | 1.0 | 1.0 | 5.9 |

## 5. Prompt Variant × Temperature (Format Compliance)

| Prompt / Temp | 0.0 | 0.3 | 0.7 |
|---|---|---|---|
| v3_rephrase_a | 1.0 | 1.0 | 1.0 |
| v3_rephrase_b | 1.0 | 1.0 | 1.0 |
| v3_revised | 1.0 | 1.0 | 1.0 |

## 6. Safety Violations (if any)

No safety violations detected across all runs.

## 7. Format Compliance Failures (score < 1.0)

All responses achieved full format compliance.

## 8. Recommendations for Prompt Hardening

Based on the results above, consider the following:

- If format compliance drops at higher temperatures, add stronger format enforcement or select a lower temperature.
- If category accuracy is low for specific categories, add category-specific hints or examples.
- If safety violations appear, tighten grounding constraints in the affected prompt section.
- If the guidance label is missing in some responses, make the label part of a fixed template string rather than an instruction.
- Use the best-performing prompt variant and temperature combination as your hardened baseline.