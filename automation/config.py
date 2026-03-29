"""설정 저장/불러오기"""

import json
from pathlib import Path

SETTINGS_FILE = Path(__file__).parent.parent / "settings.json"

DEFAULT_SETTINGS = {
    "input_folder": "",
    "processing_folder": "",
    "output_folder": "",
}


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        settings = {**DEFAULT_SETTINGS, **saved}
        return settings
    return dict(DEFAULT_SETTINGS)


def save_settings(settings: dict):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
