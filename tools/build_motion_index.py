# tools/build_motion_index.py
import sys, json
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else "animation/motions")
items = []
root.mkdir(parents=True, exist_ok=True)
for p in sorted(root.glob("*.json")):
  items.append({"file": p.name, "label": p.stem})
print(json.dumps({"items": items}, ensure_ascii=False, indent=2))
