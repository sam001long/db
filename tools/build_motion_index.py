#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
掃描 docs/animation/motions/*.json 建立 index.json
"""
from __future__ import annotations
import json
from pathlib import Path

MOT_DIR = Path(__file__).resolve().parents[1] / "docs" / "animation" / "motions"
IDX_PATH = MOT_DIR / "index.json"

def main():
    MOT_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    for p in sorted(MOT_DIR.glob("motion_*.json")):
        items.append({"file": p.name, "label": p.stem.replace("motion_","")})
    with open(IDX_PATH, "w", encoding="utf-8") as f:
        json.dump({"items": items}, f, ensure_ascii=False, indent=2)
    print(f"[OK] wrote {IDX_PATH} with {len(items)} items")

if __name__ == "__main__":
    main()
