from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent


def load_prompt(name: str) -> str:
    """Read a prompt template from prompts/<name>.txt."""
    return (_PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8")
