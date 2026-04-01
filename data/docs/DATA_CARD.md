# IKAP Data Card (KB-Only MVP)

## Current Scope
The current IKAP MVP uses Northeastern IT knowledge base (KB) articles only.

This repository no longer treats incident exports as part of the active MVP data path. The latest KB exports in `data/raw/` are the source of truth for ingestion, cleaning, retrieval, and downstream response grounding.

## Active Use Cases
The KB corpus currently supports these working use-case groups:
- `account_access`
- `mfa`
- `vpn`
- `wifi`
- `student_portal`
- `canvas`
- `software`
- `other`

Password-related flows such as reset, change, or forgotten-password guidance are handled under `account_access` or the relevant product-specific KB area rather than a standalone MVP use case.

## Data Sources
KB articles are collected from Northeastern ServiceNow knowledge base pages through raw exports such as:
- structured KB JSON exports placed in `data/raw/*_kb.json`

## Raw and Processed Layout
Raw KB inputs:
- `data/raw/*_kb.json`

Processed KB artifacts:
- `data/processed/kb_json/` for one-article-per-file normalized KB records
- `data/manifests/kb_index.csv` for the generated KB manifest

## Expected KB Record Shape
Each normalized KB article should preserve:
- `article_id`
- `title`
- `article_url`
- `source_url`
- `doc_type`
- `source_system`
- `updated_at`
- `plain_text`
- `body_html`
- `sections`
- `links`
- `related_articles`
- `categories`

Each section should preserve:
- `heading`
- `text`
- `steps`
- `links`

## Quality Goals
The KB cleaning pipeline should:
- keep canonical KB article URLs
- preserve embedded links with visible anchor text
- extract actionable steps from procedural sections
- remove navigation/page chrome noise such as table-of-contents duplication, profile menus, and footer content
- deduplicate repeated article exports
- keep raw exports separate from normalized processed files

## Exclusions
The current MVP excludes:
- ServiceNow incident exports
- incident-inspired edge-case generation
- incident redaction workflows
- any retrieval or evaluation path that depends on incident data

## Notes
Some historical coursework scripts and experiments may still remain in the repository, but the active MVP data path is KB-only.
