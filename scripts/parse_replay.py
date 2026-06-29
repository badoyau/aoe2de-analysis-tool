"""
AOE2 DE replay parser using mgz-fast.
Extracts header data: players, map, settings.
Duration and winner require body parsing (future step).

Usage: python parse_replay.py [path_to_replay.aoe2record] [output.json]

Key finding: color_id (0-indexed) is the authoritative player slot.
  color_id 0 = Slot P1 Blue, 1 = P2 Red, ... 7 = P8 Orange
  The 'number' field in de.players is lobby order, NOT game slot.
"""

import sys
import json
import os
import re
import subprocess
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SLOT_COLORS = {
    1: "Blue (藍)",   2: "Red (紅)",    3: "Green (綠)",  4: "Yellow (黃)",
    5: "Teal (青)",   6: "Purple (紫)", 7: "Gray (灰)",   8: "Orange (橙)",
}


def ensure_mgz_fast():
    try:
        import mgz.fast.header  # noqa
    except ImportError:
        print("Installing mgz-fast...", flush=True)
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "git+https://github.com/AoEInsights/mgz-fast.git", "--quiet"
        ])
        print("mgz-fast installed.", flush=True)


def find_replay(directory: str):
    for f in Path(directory).glob("*.aoe2record"):
        return str(f)
    return None


def _decode(raw) -> str:
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace").strip("\x00")
    s = str(raw)
    if s.startswith("b'") or s.startswith('b"'):
        try:
            inner = eval(s)  # noqa: S307
            if isinstance(inner, bytes):
                return inner.decode("utf-8", errors="replace").strip("\x00")
        except Exception:
            pass
        return s[2:-1]
    return s.strip("\x00")


def _extract_map_name(scenario: dict) -> str:
    instructions = scenario.get("instructions", b"")
    if isinstance(instructions, bytes):
        instructions = instructions.decode("utf-8", errors="replace")
    for pattern in [r"位置[：:]\s*(.+)", r"Location[：:]\s*(.+)"]:
        m = re.search(pattern, instructions)
        if m:
            return m.group(1).strip()
    return "Unknown"


def _load_civs(replay_path: str) -> dict:
    """Load civ id->name mapping from data/civilizations.json."""
    data_dir = Path(replay_path).parent / "data" / "civilizations.json"
    if not data_dir.exists():
        # fallback: search relative to this script
        data_dir = Path(__file__).parent.parent / "data" / "civilizations.json"
    if data_dir.exists():
        civ_list = json.loads(data_dir.read_text(encoding="utf-8"))["civilizations"]
        return {c["id"]: {"en": c["en"], "tw": c["tw"]} for c in civ_list}
    return {}


def parse_header(replay_path: str) -> dict:
    from mgz.fast.header import parse as parse_hdr  # type: ignore

    civs = _load_civs(replay_path)

    with open(replay_path, "rb") as f:
        raw = parse_hdr(f)

    result = {}
    result["version"] = str(raw.get("version", ""))
    result["game_version"] = raw.get("game_version")
    result["save_version"] = raw.get("save_version")

    metadata = raw.get("metadata") or {}
    result["speed"] = round(metadata.get("speed", 0), 2)

    lobby = raw.get("lobby") or {}
    result["lock_teams"] = lobby.get("lock_teams")

    scenario = raw.get("scenario") or {}
    result["map_id"] = scenario.get("map_id")
    result["map_name"] = _extract_map_name(scenario)
    result["map_dimension"] = (raw.get("map") or {}).get("dimension")

    # Build player list — sorted by slot (color_id + 1)
    de_players = (raw.get("de") or {}).get("players") or []
    players = []
    for dp in de_players:
        color_id = dp.get("color_id", -1)
        slot = color_id + 1  # 1-indexed game slot
        civ_id = dp.get("civilization_id")
        civ_info = civs.get(civ_id, {})
        player = {
            "slot":            slot,
            "color":           SLOT_COLORS.get(slot, f"P{slot}"),
            "name":            _decode(dp.get("name", b"")),
            "civilization_id": civ_id,
            "civilization_en": civ_info.get("en", f"ID:{civ_id}"),
            "civilization_tw": civ_info.get("tw", ""),
            "team_id":         dp.get("team_id"),
            "color_id":        color_id,
            "profile_id":      dp.get("profile_id"),
            "prefer_random":   dp.get("prefer_random", False),
            "is_human":        dp.get("type") == 2,
        }
        players.append(player)

    players.sort(key=lambda p: p["slot"])
    result["players"] = players
    result["player_count"] = len(players)

    # Teams: keyed by team_id, value = list of slots
    teams: dict = {}
    for p in players:
        tid = str(p["team_id"])
        teams.setdefault(tid, []).append(p["slot"])
    result["teams"] = teams

    result["source_file"] = os.path.basename(replay_path)
    result["source_path"] = os.path.abspath(replay_path)
    result["duration_seconds"] = None  # requires body parsing
    result["winner_team"] = None       # requires postgame parsing

    return result


def format_duration(seconds):
    if seconds is None:
        return "N/A"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m {s:02d}s" if h else f"{m}m {s:02d}s"


def print_summary(data: dict):
    SEP = "=" * 65
    print(f"\n{SEP}")
    print("  AOE2 DE REPLAY — PARSE RESULT")
    print(SEP)
    print(f"  檔案    : {data['source_file']}")
    print(f"  版本    : {data.get('version', 'N/A')}  ({data.get('game_version', '')})")
    print(f"  地圖    : {data.get('map_name', 'N/A')}  ({data.get('map_dimension', '?')}x{data.get('map_dimension', '?')})")
    print(f"  速度    : {data.get('speed', 'N/A')}  (正常=1.7)")
    print(f"  時長    : {format_duration(data.get('duration_seconds'))}")
    print(f"  玩家數  : {data.get('player_count', 0)}")
    print()

    # Team groups
    teams = data.get("teams", {})
    team_slot_to_name = {}
    for p in data.get("players", []):
        team_slot_to_name[p["slot"]] = (p["name"], str(p["team_id"]))

    for tid, slots in sorted(teams.items()):
        names = [team_slot_to_name[s][0] for s in slots if s in team_slot_to_name]
        print(f"  隊伍 {tid}: {', '.join(names)}")

    print()
    print(f"  {'槽位':<4} {'顏色':<12} {'名稱':<28} {'文明ID':<6} {'隊伍'}")
    print("  " + "-" * 61)
    for p in data.get("players", []):
        slot_str = f"P{p['slot']}"
        civ = f"{p['civilization_en']} ({p['civilization_tw']})" if p.get('civilization_tw') else p.get('civilization_en', '')
        print(f"  {slot_str:<4} {p['color']:<12} {p['name']:<28} {civ:<22} T{p['team_id']}")
    print(SEP)


def main():
    ensure_mgz_fast()

    if len(sys.argv) < 2:
        replay_path = find_replay(".")
        if not replay_path:
            print("ERROR: No .aoe2record found.", file=sys.stderr)
            sys.exit(1)
        print(f"Found: {replay_path}")
    else:
        replay_path = sys.argv[1]

    if not os.path.exists(replay_path):
        print(f"ERROR: File not found: {replay_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing: {os.path.basename(replay_path)} ...", flush=True)
    data = parse_header(replay_path)

    output_path = sys.argv[2] if len(sys.argv) >= 3 else os.path.splitext(replay_path)[0] + "_parsed.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    print_summary(data)
    print(f"\n  Saved: {output_path}\n")


if __name__ == "__main__":
    main()
