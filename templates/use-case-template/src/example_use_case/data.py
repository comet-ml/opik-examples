import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load_cases() -> list[dict]:
    return json.loads((DATA_DIR / "cases.json").read_text())
