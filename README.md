# IKAP – Intelligent Knowledge Assistant Platform

**IKAP** (Intelligent Knowledge Assistant Platform) is an AI-powered knowledge assistant designed to improve access to institutional knowledge bases.

## Overview

The system aims to:

1. Provide natural-language search over knowledge base articles  
2. Deliver structured, step-by-step troubleshooting guidance  
3. Reduce ticket resolution time  
4. Improve consistency of support responses  

This repository contains the foundational work for **prompt engineering**, experimentation, and future **RAG-based system development**.

---

## Current Module: Prompt Engineering

The `prompt_engineering/` module is responsible for:

- System prompt experimentation  
- Evaluation of prompting techniques  
- Measuring consistency and reliability  
- Preparing prompts for future RAG integration  

This module serves as a controlled environment to test and compare different prompt strategies **before integrating them into the full IKAP architecture**.

---

## Repository Structure

```
IKAP/
│
├── prompt_engineering/
│   ├── run.py                 # Main entry point for running prompt experiments
│   ├── prompts/               # Prompt templates (for future separation of techniques)
│   ├── experiments/           # Experiment configurations and technique definitions
│   └── results/               # Automatically generated JSON outputs from runs
│
├── .env                       # Environment variables (API key)
├── .gitignore
└── README.md
```

---

### prompt_engineering/

Contains all **prompt experimentation logic**:

- `run.py` → Main entry point for running prompt experiments  
- `prompts/` → Prompt templates  
- `experiments/` → Experiment configurations and technique definitions  
- `results/` → Automatically generated JSON outputs from runs  

---

## Setup Instructions

1. **Clone the Repository**

```bash
git clone <repo_url>
cd IKAP
```

2. **Create Virtual Environment**

```bash
python -m venv .venv
source .venv/bin/activate        # mac/linux
# .venv\Scripts\activate         # windows
```

3. **Install Dependencies**

You can install dependencies either via `pip` for individual packages or using `requirements.txt`:

**Option 1: Install manually**
```bash
pip install openai python-dotenv
```

**Option 2: Install from `requirements.txt`**
```bash
pip install -r requirements.txt
```

4. **Configure API Key**

Create a `.env` file at the repository root:

```
OPENAI_API_KEY=your_api_key_here
```

⚠️ **Do not commit `.env` to GitHub.**

---

## Running Prompt Experiments

To run the baseline experiment:

```bash
python prompt_engineering/run.py
```

This will:

- Execute the configured prompt technique  
- Call the selected model  
- Save output as a timestamped JSON file inside `prompt_engineering/results/`  

Example output:

```
prompt_engineering/results/zero_shot.json
```

---

## Development Roadmap

Future enhancements will include:

- Advanced prompt engineering techniques  
- Self-consistency and evaluation strategies  
- Retrieval-Augmented Generation (RAG) pipeline  
- Backend service layer  
- Frontend interface  

The current focus is **establishing a rigorous and reproducible prompt experimentation framework**.

---

## Collaboration Guidelines

1. Keep modules clean and modular  
2. Do not hardcode API keys  
3. Store experiment outputs only in `results/`  
4. Use clear naming conventions for new experiments  
5. Keep model and temperature constants consistent during comparisons

