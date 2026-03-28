from pathlib import Path


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_v4_prompt_path() -> Path:
    return (
        get_project_root() / "prompt_engineering" / "prompts" / "v4_system_prompt.txt"
    )


def load_v4_system_prompt() -> str:
    prompt_path = get_v4_prompt_path()

    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

    return prompt_path.read_text(encoding="utf-8").strip()
