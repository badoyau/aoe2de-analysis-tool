"""Probe the mgz-fast API to find the right way to parse .aoe2record files."""
import sys
import glob
import json
from pathlib import Path

# Find replay
folder = Path(__file__).parent.parent
replays = list(folder.glob("*.aoe2record"))
if not replays:
    print("No .aoe2record found in", folder)
    sys.exit(1)
replay_path = replays[0]
print(f"Using: {replay_path}")

# Try header.parse
from mgz.fast import header as hdr
from mgz.util import get_version

with open(replay_path, "rb") as f:
    result = hdr.parse(f)

print("Type:", type(result))
if isinstance(result, dict):
    print("Keys:", list(result.keys()))
    print(json.dumps(result, indent=2, default=str)[:3000])
else:
    print("Attrs:", [a for a in dir(result) if not a.startswith("_")])
