# -*- coding: utf-8 -*-
import json
from pathlib import Path

from server import collect

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATA_FILE = DATA_DIR / "hotspots.json"

if __name__ == "__main__":
    DATA_DIR.mkdir(exist_ok=True)
    payload = collect()
    DATA_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(DATA_FILE)
