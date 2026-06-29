"""驗證解析結果正確性 — 輸出到檔案避免 console 編碼問題"""
import json, re
from pathlib import Path
from mgz.fast.header import parse as parse_hdr

folder = Path(__file__).parent.parent

# Load civilization mapping from JSON
_civ_data = json.loads((folder / "data" / "civilizations.json").read_text(encoding="utf-8"))
CIVS = {c["id"]: f"{c['en']} ({c['tw']})" for c in _civ_data["civilizations"]}

# color_id 是 0-indexed 玩家槽位，直接對應顏色與槽位號
# color_id 0 = P1 Blue, 1 = P2 Red, ... 7 = P8 Orange
COLOR_ID_MAP = {
    0: ("P1", "Blue (藍)"),   1: ("P2", "Red (紅)"),
    2: ("P3", "Green (綠)"),  3: ("P4", "Yellow (黃)"),
    4: ("P5", "Teal (青)"),   5: ("P6", "Purple (紫)"),
    6: ("P7", "Gray (灰)"),   7: ("P8", "Orange (橙)"),
}

replay_path = list(folder.glob("*.aoe2record"))[0]

with open(replay_path, "rb") as f:
    raw = parse_hdr(f)

# Extract map name from scenario instructions
instructions = raw["scenario"].get("instructions", b"")
if isinstance(instructions, bytes):
    instructions = instructions.decode("utf-8", errors="replace")

map_name = "Unknown"
for pattern in [r"位置[：:]\s*(.+)", r"Location[：:]\s*(.+)"]:
    m = re.search(pattern, instructions)
    if m:
        map_name = m.group(1).strip()
        break

# Build verification report
lines = []
lines.append("=" * 65)
lines.append("  AOE2 DE REPLAY — VERIFICATION REPORT")
lines.append("=" * 65)
lines.append(f"  File    : {replay_path.name}")
lines.append(f"  Version : {raw.get('version')}  ({raw.get('game_version')})")
lines.append(f"  Map     : {map_name}  (dim:{raw['map']['dimension']})")
lines.append(f"  Speed   : {raw['metadata'].get('speed', '?'):.2f}  (Normal=1.7)")
lines.append(f"  Pop Lim : {raw['lobby'].get('population', '?')}")
lines.append("")
lines.append("  PLAYERS")
lines.append("  " + "-" * 61)
lines.append(f"  {'#':<3} {'Name':<28} {'Civilization':<25} {'Team':<6} {'Color'}")
lines.append("  " + "-" * 61)

for p in raw["de"]["players"]:
    name_raw = p["name"]
    name = name_raw.decode("utf-8", errors="replace") if isinstance(name_raw, bytes) else str(name_raw)
    civ_id = p.get("civilization_id", 0)
    civ_name = CIVS.get(civ_id, f"ID:{civ_id}")
    color_id = p.get("color_id", -1)
    slot, color_name = COLOR_ID_MAP.get(color_id, (f"?{color_id}", "Unknown"))
    team = p.get("team_id", "?")
    lines.append(f"  {slot:<3} {name:<28} {civ_name:<25} T{team:<5} {color_name}")

lines.append("  " + "-" * 61)

# Teams
teams = {}
for p in raw["de"]["players"]:
    tid = p.get("team_id")
    name_raw = p["name"]
    name = name_raw.decode("utf-8", errors="replace") if isinstance(name_raw, bytes) else str(name_raw)
    teams.setdefault(tid, []).append(name)

lines.append("")
for tid, members in sorted(teams.items()):
    lines.append(f"  Team {tid}: {', '.join(members)}")

lines.append("")
lines.append("  NOTE: Duration & Winner require body parsing (next step)")
lines.append("=" * 65)

report = "\n".join(lines)
out_path = folder / "verification_report.txt"
out_path.write_text(report, encoding="utf-8")
print(f"Saved: {out_path}")
print(report)
