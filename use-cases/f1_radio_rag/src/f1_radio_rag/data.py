import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load_radio_messages() -> list[dict]:
    return json.loads((DATA_DIR / "radio_messages.json").read_text())


def load_eval_cases() -> list[dict]:
    return json.loads((DATA_DIR / "eval_cases.json").read_text())
