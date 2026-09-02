# -*- coding: utf-8 -*-
import json
from pathlib import Path

from server import collect

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "hotspots.json"
TEMP_FILE = ROOT / "hotspots.json.tmp"

if __name__ == "__main__":
    payload = collect()
    items = payload.get("items", [])
    successful_sources = [source for source in payload.get("sources", []) if source.get("status") == "ok"]
    if len(items) < 20 or not successful_sources:
        raise RuntimeError("Insufficient hotspot data; keeping the previous snapshot")
    TEMP_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    TEMP_FILE.replace(DATA_FILE)
    print(f"{DATA_FILE} ({len(items)} items, {len(successful_sources)} sources)")
