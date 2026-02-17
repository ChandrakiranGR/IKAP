IKAP – Intelligent Knowledge Assistant Platform
Overview
IKAP (Intelligent Knowledge Assistant Platform) is an AI-powered knowledge assistant designed to improve access to institutional knowledge bases.

The system aims to:
1) Provide natural-language search over knowledge base articles
2) Deliver structured, step-by-step troubleshooting guidance
3) Reduce ticket resolution time
4) Improve consistency of support responses

This repository contains the foundational work for prompt engineering, experimentation, and future RAG-based system development.

Current Module: Prompt Engineering

The prompt_engineering/ module is responsible for:

1) System prompt experimentation
2) Evaluation of prompting techniques
3) Measuring consistency and reliability
4) Preparing prompts for future RAG integration

This module serves as a controlled environment to test and compare different prompt strategies before integrating them into the full IKAP architecture.

Repository Structure
IKAP/
│
├── prompt_engineering/
│   ├── run.py
│   ├── prompts/
│   ├── experiments/
│   └── results/
│
├── .env
├── .gitignore
└── README.md

prompt_engineering/

Contains all prompt experimentation logic.

run.py → Main entry point for running prompt experiments

prompts/ → Prompt templates (future separation of techniques)

experiments/ → Experiment configurations and technique definitions

results/ → Automatically generated JSON outputs from runs

------Setup Instructions------
1. Clone the Repository
git clone <repo_url>
cd IKAP

2. Create Virtual Environment
python -m venv .venv
source .venv/bin/activate        # mac/linux
# .venv\Scripts\activate         # windows

3. Install Dependencies
pip install openai python-dotenv

4. Configure API Key

Create a .env file at the repository root:
OPENAI_API_KEY=your_api_key_here
⚠️ Do not commit .env to GitHub.

Running Prompt Experiments
To run the baseline experiment:

python prompt_engineering/run.py

This will:

Execute the configured prompt technique

Call the selected model

Save output as a timestamped JSON file inside prompt_engineering/results/

Example output:

prompt_engineering/results/20260217_123045_zero_shot.json

Development Roadmap

This repository will evolve to include:

Advanced prompt engineering techniques

Self-consistency and evaluation strategies

Retrieval-Augmented Generation (RAG) pipeline

Backend service layer

Frontend interface

The current focus is establishing a rigorous and reproducible prompt experimentation framework.

Collaboration Guidelines

1) Keep modules clean and modular
2) Do not hardcode API keys
3) Store experiment outputs only in results/
4) Use clear naming conventions for new experiments
5) Keep model and temperature constants consistent during comparisons