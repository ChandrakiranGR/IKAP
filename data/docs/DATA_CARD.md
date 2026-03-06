# IKAP Dataset Data Card (Assignment 4 – Step 2)

## Purpose
This dataset supports IKAP, a Northeastern IT helpdesk assistant prototype, by providing structured examples across multiple IT support use cases. It is designed for:
- prompt-only baseline evaluation (consistency and safety)
- fine-tuning/evaluation experiments
- future grounding/RAG integration

## Scope and Use Cases
The dataset covers the following use cases:
- student_portal (Student Hub / profile tasks)
- mfa (Duo and authentication-related issues)
- vpn (remote access/VPN issues)
- canvas (LMS-related support)
- account_access (username/login/access topics)
- software (licensed software install/access issues)
- password (password reset/change topics)
- wifi (connectivity basics)

## Dataset Size and Composition
**Total examples:** 138  
**Case types:**
- Typical: 110
- Edge: 17
- Adversarial: 11

**Use-case distribution:**
| Use Case | Count |
|---|---:|
| student_portal | 29 |
| mfa | 26 |
| vpn | 19 |
| canvas | 14 |
| account_access | 13 |
| software | 13 |
| password | 12 |
| wifi | 12 |

## Data Sources
**Typical examples (KB-derived):**
- Generated from ServiceNow KB articles exported as HTML and converted to structured JSON.
- Steps were extracted and normalized; raw URLs were removed or replaced with placeholders (e.g., `[URL]`).

**Edge examples (incident-inspired + realistic constraints):**
- Built using redacted ServiceNow incident exports for selected use cases:
  - `incident_mfa_redacted.csv`
  - `incident_account_access_redacted.csv`
  - `incident_software_redacted.csv`
  - `incident_student_hub_redacted.csv`
  - `incident_vpn_redacted.csv`
- Wi-Fi incidents were intentionally skipped due to highly repetitive connectivity-only patterns; Wi-Fi edge coverage can be expanded later if needed.

**Adversarial examples (synthetic):**
- Added to test guardrails (e.g., requests for bypassing security, requests for internal-only procedures, prompt-injection attempts).
- Intended to verify safe refusal + correct escalation behavior.

## Data Format
Stored as JSONL with one record per line. Key fields include:
- `id`, `use_case`, `case_type`, `user_query`
- `expected_output`:
  - `category`
  - `steps` (list of step strings)
  - `escalation` (what to do if unresolved)
- `guardrails` (e.g., no URLs, no portal assumptions, no policy claims)
- `source` (KB IDs and/or incident reference filenames)
- `tags` (optional)

Primary compiled file:
- `data/dataset/all.jsonl`

Draft components:
- `data/dataset/draft/*_typical.jsonl`
- `data/dataset/draft/*_edge_adv.jsonl`

## Privacy and PII Handling
Incident exports were processed using regex-based redaction across all columns to remove or mask:
- emails (including partial forms), phone numbers, IP/MAC, ticket IDs (INC/RITM/REQ/TASK/CHG), IDs (NUID/student IDs), dates of birth patterns
- personal names in greetings, signatures, and inline self-introductions (e.g., “My name is …”)
Redacted placeholders are used (e.g., `[REDACTED_EMAIL]`, `[REDACTED_PHONE]`, `[REDACTED_NAME]`, `[REDACTED_TICKET]`).

## Quality Checks
- JSONL validation: schema completeness, duplicate IDs, minimum steps, and URL removal in `expected_output`
- Manual spot checks on redacted incident text to confirm removal of common name/signature patterns
- Consistent labeling across use cases via KB mapping rules

## Train/Dev/Test Split
A stratified split (by `use_case` and `case_type`) was created using a fixed random seed:
- Train: 84
- Dev: 18
- Test: 36

Files:
- `data/dataset/splits/train.jsonl`
- `data/dataset/splits/dev.jsonl`
- `data/dataset/splits/test.jsonl`

## Limitations and Next Improvements
- Some edge/adversarial cases are synthetic (by design) and will be strengthened by exporting additional incident sets (e.g., Canvas/Wi-Fi) if needed.
- Some KB-derived steps may still contain institution-specific wording; URLs are removed, but future RAG grounding will allow safer, more accurate referencing.
- Future work: integrate retrieval grounding (RAG) so responses can cite KB content directly and reduce reliance on generalized guidance.