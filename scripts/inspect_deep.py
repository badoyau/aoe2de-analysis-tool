import json
from pathlib import Path

f = Path(r"C:\Users\popo5\OneDrive\文件\Claude\0_Claude_Code\Age of Empires II DE_Analysis Tool\MP Replay v101.103.48086.0 @2026.06.28 001232 (8)_deep.json")
data = json.loads(f.read_text(encoding="utf-8"))

print("=== SYNC samples (first 3) ===")
for s in data["samples"][:3]:
    print(f"  {s['time_str']}: {s['players']}")

print("\n=== SYNC samples (last 3) ===")
for s in data["samples"][-3:]:
    print(f"  {s['time_str']}: {s['players']}")

print("\n=== Actions per player (total) ===")
for slot, actions in sorted(data["actions_per_player"].items(), key=lambda x: int(x[0]) if x[0].isdigit() else 99):
    total = sum(actions.values())
    top3 = sorted(actions.items(), key=lambda x: -x[1])[:3]
    print(f"  P{slot}: {total:>5} actions   top: {top3}")

print("\n=== Sample at 30min mark ===")
target = next((s for s in data["samples"] if s["time_ms"] >= 30*60*1000), None)
if target:
    print(json.dumps(target, indent=2))
