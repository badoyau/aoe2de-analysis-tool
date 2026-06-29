"""Deeper probe - map, metadata, lobby, player names."""
import sys
import json
from pathlib import Path
from mgz.fast import header as hdr

folder = Path(__file__).parent.parent
replay_path = list(folder.glob("*.aoe2record"))[0]

with open(replay_path, "rb") as f:
    result = hdr.parse(f)

# Print selective sections
for section in ["map", "metadata", "lobby", "de", "scenario"]:
    print(f"\n=== {section} ===")
    val = result.get(section)
    if val:
        try:
            print(json.dumps(val, indent=2, default=str)[:1500])
        except Exception as e:
            print(f"  [error: {e}] raw: {str(val)[:300]}")
    else:
        print("  (empty/None)")

# Print players (non-Gaia)
print("\n=== players (non-Gaia) ===")
for p in result.get("players", []):
    if p.get("number", 0) == 0:
        continue
    p_clean = {k: v for k, v in p.items() if k != "objects"}
    print(json.dumps(p_clean, indent=2, default=str))
    print()
