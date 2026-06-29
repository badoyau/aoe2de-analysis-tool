"""
AOE2 DE body parser using mgz-fast.
Parses game body to extract:
  - duration (from final SYNC current_time)
  - resigned players (from RESIGN actions)
  - age-up events (from RESEARCH actions matching age tech IDs)
  - postgame leaderboard data

Usage: python parse_body.py [path_to_replay.aoe2record] [output.json]
Requires: parse_replay.py already run (header JSON must exist)
"""

import sys
import json
import struct
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Age-up research IDs (standard + DE)
AGE_TECH_IDS = {
    101: "Feudal Age",
    102: "Castle Age",
    103: "Imperial Age",
    # Chinese starts in Dark Age but researches differently — covered by same IDs
}

SLOT_COLORS = {
    1: "Blue(藍)", 2: "Red(紅)", 3: "Green(綠)", 4: "Yellow(黃)",
    5: "Teal(青)", 6: "Purple(紫)", 7: "Gray(灰)", 8: "Orange(橙)",
}


def find_replay(directory: str):
    candidates = sorted(Path(directory).glob("*.aoe2record"), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(candidates[0]) if candidates else None


def ms_to_str(ms: int) -> str:
    s = ms // 1000
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m {s:02d}s" if h else f"{m}m {s:02d}s"


def parse_body(replay_path: str) -> dict:
    from mgz.fast.header import parse as parse_hdr
    from mgz.fast import operation, meta, Operation, Action

    result = {
        "duration_ms": None,
        "duration_str": None,
        "resigned_color_ids": [],   # color_id (0-indexed slot) of resigned players
        "age_ups": [],              # {time_ms, time_str, color_id, age_name}
        "postgame": None,
        "sync_count": 0,
        "action_count": 0,
    }

    with open(replay_path, "rb") as f:
        # 1. Parse header to advance file pointer
        hdr = parse_hdr(f)

        # Build color_id lookup: de.players number -> color_id
        # (action player_id uses de.players 'number', not slot)
        de_players = (hdr.get("de") or {}).get("players") or []
        number_to_color_id = {p["number"]: p["color_id"] for p in de_players}

        # 2. Read body meta (preamble before operations)
        try:
            meta(f)
        except Exception as e:
            print(f"  [warn] meta() failed: {e}", file=sys.stderr)

        # 3. Main operation loop
        last_time_ms = 0
        errors = 0

        while True:
            try:
                op_type, payload = operation(f)

                if op_type == Operation.SYNC:
                    result["sync_count"] += 1
                    # payload = (increment, checksum, detail_dict)
                    if isinstance(payload, tuple) and len(payload) >= 3:
                        detail = payload[2]
                        if "current_time" in detail:
                            last_time_ms = detail["current_time"]

                elif op_type == Operation.ACTION:
                    result["action_count"] += 1
                    # payload = (action_type, action_data_dict)
                    if isinstance(payload, tuple) and len(payload) >= 2:
                        action_type, action_data = payload[0], payload[1]

                        if action_type == Action.RESIGN:
                            # player_id is the 'number' from de.players (lobby order)
                            pid = action_data.get("player_id") if isinstance(action_data, dict) else None
                            if pid is not None:
                                cid = number_to_color_id.get(pid, pid)
                                result["resigned_color_ids"].append({
                                    "color_id": cid,
                                    "slot": cid + 1,
                                    "time_ms": last_time_ms,
                                    "time_str": ms_to_str(last_time_ms),
                                })

                        elif action_type == Action.RESEARCH:
                            if isinstance(action_data, dict):
                                tech_id = action_data.get("technology_id") or action_data.get("tech_id")
                                pid = action_data.get("player_id")
                                if tech_id in AGE_TECH_IDS:
                                    cid = number_to_color_id.get(pid, pid) if pid is not None else None
                                    slot = (cid + 1) if cid is not None else None
                                    age_name = AGE_TECH_IDS[tech_id]
                                    # Deduplicate: same slot+age within 5s window
                                    seen_key = (slot, age_name)
                                    existing = next((a for a in result["age_ups"] if (a["slot"], a["age"]) == seen_key), None)
                                    if existing is None:
                                        result["age_ups"].append({
                                            "color_id": cid,
                                            "slot": slot,
                                            "age": age_name,
                                            "tech_id": tech_id,
                                            "time_ms": last_time_ms,
                                            "time_str": ms_to_str(last_time_ms),
                                        })

                elif op_type == Operation.POSTGAME:
                    result["postgame"] = payload

            except EOFError:
                break
            except Exception as e:
                errors += 1
                if errors <= 3:
                    print(f"  [warn] op error: {e}", file=sys.stderr)
                if errors > 20:
                    print("  [warn] too many errors, stopping.", file=sys.stderr)
                    break

    result["duration_ms"] = last_time_ms
    result["duration_str"] = ms_to_str(last_time_ms)
    result["parse_errors"] = errors
    return result


def determine_winner(hdr_data: dict, body: dict) -> dict:
    """Determine winning team from resign events."""
    if not hdr_data:
        return {}

    # Map slot -> team_id
    slot_to_team = {p["slot"]: p["team_id"] for p in hdr_data.get("players", [])}
    slot_to_name = {p["slot"]: p["name"] for p in hdr_data.get("players", [])}

    resigned_slots = {r["slot"] for r in body.get("resigned_color_ids", [])}
    early_resign_threshold_ms = 5 * 60 * 1000  # 5 minutes

    early_leaves = [r for r in body.get("resigned_color_ids", []) if r["time_ms"] < early_resign_threshold_ms]
    late_resigns = [r for r in body.get("resigned_color_ids", []) if r["time_ms"] >= early_resign_threshold_ms]

    # Teams that had late resignations
    losing_teams = {slot_to_team.get(r["slot"]) for r in late_resigns if slot_to_team.get(r["slot"])}

    all_teams = set(slot_to_team.values())
    winning_teams = all_teams - losing_teams

    return {
        "winning_team": list(winning_teams)[0] if len(winning_teams) == 1 else None,
        "losing_teams": list(losing_teams),
        "early_leaves": [{"slot": r["slot"], "name": slot_to_name.get(r["slot"], "?"), "time_str": r["time_str"]} for r in early_leaves],
        "resigned_at_end": [{"slot": r["slot"], "name": slot_to_name.get(r["slot"], "?"), "time_str": r["time_str"]} for r in late_resigns],
    }


def print_body_summary(hdr_data: dict, body: dict):
    SEP = "=" * 65
    print(f"\n{SEP}")
    print("  BODY PARSE RESULT")
    print(SEP)
    print(f"  時長       : {body.get('duration_str', 'N/A')}  ({body.get('duration_ms', 0):,} ms)")
    print(f"  SYNC 數    : {body.get('sync_count', 0):,}")
    print(f"  ACTION 數  : {body.get('action_count', 0):,}")
    print(f"  解析錯誤   : {body.get('parse_errors', 0)}")
    print()

    # Winner determination
    winner_info = determine_winner(hdr_data, body)
    if winner_info.get("winning_team"):
        print(f"  勝利隊伍   : Team {winner_info['winning_team']}")
        print(f"  敗北隊伍   : Team {winner_info['losing_teams']}")
    if winner_info.get("early_leaves"):
        print()
        print("  早期離開 (<5min — 可能斷線):")
        for e in winner_info["early_leaves"]:
            print(f"    P{e['slot']} {e['name']:<28} @ {e['time_str']}")
    print()
    print("  RESIGN 事件 (正常投降):")
    if winner_info.get("resigned_at_end"):
        for r in winner_info["resigned_at_end"]:
            slot = r.get("slot", "?")
            color = SLOT_COLORS.get(slot, f"P{slot}")
            print(f"    P{slot} {color:<12} {r.get('name','?'):<28} @ {r.get('time_str', '?')}")
    else:
        print("    (none)")

    # Age-ups
    age_ups = body.get("age_ups", [])
    if age_ups:
        print()
        print("  AGE-UP 事件:")
        for a in sorted(age_ups, key=lambda x: x.get("time_ms", 0)):
            slot = a.get("slot", "?")
            color = SLOT_COLORS.get(slot, f"P{slot}")
            print(f"    P{slot} {color:<12} → {a.get('age', '?'):<14} @ {a.get('time_str', '?')}")
    else:
        print("  AGE-UP 事件: (none detected — check tech ID mapping)")

    # Postgame
    pg = body.get("postgame")
    if pg:
        print()
        print(f"  POSTGAME world_time: {pg.get('world_time', 'N/A')} ms")
    print(SEP)


def main():
    import sys

    if len(sys.argv) < 2:
        replay_path = find_replay(".")
        if not replay_path:
            print("ERROR: No .aoe2record found.", file=sys.stderr)
            sys.exit(1)
        print(f"Found: {replay_path}")
    else:
        replay_path = sys.argv[1]

    from mgz.fast.header import parse as parse_hdr
    with open(replay_path, "rb") as f:
        hdr_raw = parse_hdr(f)

    # Load header JSON if exists
    base = Path(replay_path).with_suffix("")
    hdr_json_path = Path(str(base) + "_parsed.json")
    hdr_data = {}
    if hdr_json_path.exists():
        hdr_data = json.loads(hdr_json_path.read_text(encoding="utf-8"))

    print(f"Parsing body: {Path(replay_path).name} ...", flush=True)
    body = parse_body(replay_path)

    print_body_summary(hdr_data, body)

    # Merge into header JSON if available
    if hdr_data:
        winner_info = determine_winner(hdr_data, body)
        hdr_data["duration_seconds"] = body["duration_ms"] // 1000 if body["duration_ms"] else None
        hdr_data["duration_str"] = body["duration_str"]
        hdr_data["duration_ms"] = body["duration_ms"]
        hdr_data["winner_team"] = winner_info.get("winning_team")
        hdr_data["loser_teams"] = winner_info.get("losing_teams")
        hdr_data["early_leaves"] = winner_info.get("early_leaves", [])
        hdr_data["resigned_players"] = body["resigned_color_ids"]
        hdr_data["age_ups"] = body["age_ups"]
        hdr_data["postgame"] = body["postgame"]

        out_path = Path(str(base) + "_parsed.json")
        out_path.write_text(json.dumps(hdr_data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"\n  Updated: {out_path}")
    else:
        out_path = Path(str(base) + "_body.json")
        out_path.write_text(json.dumps(body, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"\n  Saved: {out_path}")


if __name__ == "__main__":
    main()
