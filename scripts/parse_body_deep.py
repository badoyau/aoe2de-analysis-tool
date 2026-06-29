"""
Deep body parser — samples SYNC data every 30s for per-player economic proxy,
collects per-player action counts, buildings, research events, and training events.

Outputs: <replay>_deep.json
  {
    "samples": [ {time_ms, time_str, players: {slot: {total_res, obj_count}}} ],
    "actions_per_player": {slot: {action_name: count}},
    "build_events":     [ {time_ms, time_str, slot, object_id} ],
    "research_events":  [ {time_ms, time_str, slot, tech_id} ],
    "training_events":  [ {time_ms, time_str, slot, unit_id, amount} ],
  }
"""

import sys, json, struct
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SAMPLE_INTERVAL_MS = 30_000   # sample every 30 seconds


def ms_to_str(ms):
    s = ms // 1000
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"


def parse_deep(replay_path: str) -> dict:
    from mgz.fast.header import parse as parse_hdr
    from mgz.fast import operation, meta, Operation, Action

    result = {
        "samples": [],
        "actions_per_player": {},  # slot -> {action_name: count}
        "build_events": [],
        "research_events": [],
        "training_events": [],    # {time_ms, time_str, slot, unit_id, amount}
    }

    with open(replay_path, "rb") as f:
        hdr = parse_hdr(f)

        # Map de.players number -> color_id (slot = color_id + 1)
        de_players = (hdr.get("de") or {}).get("players") or []
        number_to_color_id = {p["number"]: p["color_id"] for p in de_players}
        number_to_slot = {p["number"]: p["color_id"] + 1 for p in de_players}

        # Init per-player action counters (keyed by slot str for JSON)
        for p in de_players:
            slot = str(p["color_id"] + 1)
            result["actions_per_player"][slot] = {}

        try:
            meta(f)
        except Exception as e:
            print(f"  [warn] meta: {e}", file=sys.stderr)

        last_time_ms = 0
        next_sample_ms = 0
        last_sync_player_data = {}   # player_id -> {total_res, obj_count}
        errors = 0

        while True:
            try:
                op_type, payload = operation(f)

                # ---- SYNC: time + per-player snapshot ----
                if op_type == Operation.SYNC:
                    if isinstance(payload, tuple) and len(payload) >= 3:
                        detail = payload[2]
                        if "current_time" in detail:
                            last_time_ms = detail["current_time"]

                        # Collect per-player data from SYNC
                        for key, val in detail.items():
                            if key == "current_time":
                                continue
                            if isinstance(val, dict):
                                # key = player_id (de.players number)
                                last_sync_player_data[key] = val

                        # Sample every 30s
                        if last_time_ms >= next_sample_ms:
                            sample = {
                                "time_ms": last_time_ms,
                                "time_str": ms_to_str(last_time_ms),
                                "players": {},
                            }
                            for pid, pdata in last_sync_player_data.items():
                                slot = number_to_slot.get(pid, pid)
                                sample["players"][str(slot)] = {
                                    "total_res": pdata.get("total_res", 0),
                                    "obj_count": pdata.get("obj_count", 0),
                                    "dp_obj_count": pdata.get("dp_obj_count", 0),
                                }
                            result["samples"].append(sample)
                            next_sample_ms += SAMPLE_INTERVAL_MS

                # ---- ACTION ----
                elif op_type == Operation.ACTION:
                    if isinstance(payload, tuple) and len(payload) >= 2:
                        action_type, action_data = payload[0], payload[1]
                        pid = None
                        if isinstance(action_data, dict):
                            pid = action_data.get("player_id")

                        slot = number_to_slot.get(pid) if pid is not None else None
                        slot_str = str(slot) if slot else "unknown"
                        aname = action_type.name if hasattr(action_type, "name") else str(action_type)

                        # Count per player
                        if slot_str not in result["actions_per_player"]:
                            result["actions_per_player"][slot_str] = {}
                        cnts = result["actions_per_player"][slot_str]
                        cnts[aname] = cnts.get(aname, 0) + 1

                        # BUILD events
                        if action_type == Action.BUILD and isinstance(action_data, dict):
                            result["build_events"].append({
                                "time_ms": last_time_ms,
                                "time_str": ms_to_str(last_time_ms),
                                "slot": slot,
                                "object_id": action_data.get("object_id"),
                                "x": action_data.get("x"),
                                "y": action_data.get("y"),
                            })

                        # RESEARCH events
                        if action_type == Action.RESEARCH and isinstance(action_data, dict):
                            tech_id = action_data.get("technology_id") or action_data.get("tech_id")
                            result["research_events"].append({
                                "time_ms": last_time_ms,
                                "time_str": ms_to_str(last_time_ms),
                                "slot": slot,
                                "tech_id": tech_id,
                            })

                        # TRAINING events (DE_QUEUE = unit production)
                        if action_type == Action.DE_QUEUE and isinstance(action_data, dict):
                            uid = action_data.get("unit_id")
                            amt = action_data.get("amount", 1)
                            if uid is not None:
                                result["training_events"].append({
                                    "time_ms": last_time_ms,
                                    "time_str": ms_to_str(last_time_ms),
                                    "slot": slot,
                                    "unit_id": uid,
                                    "amount": amt,
                                })

            except EOFError:
                break
            except Exception as e:
                errors += 1
                if errors <= 3:
                    print(f"  [warn] {e}", file=sys.stderr)
                if errors > 20:
                    break

    result["duration_ms"] = last_time_ms
    result["parse_errors"] = errors
    print(f"  Samples collected : {len(result['samples'])}")
    print(f"  Build events      : {len(result['build_events'])}")
    print(f"  Research events   : {len(result['research_events'])}")
    print(f"  Training events   : {len(result['training_events'])}")
    print(f"  Errors            : {errors}")
    return result


def main():
    if len(sys.argv) < 2:
        candidates = sorted(Path(".").glob("*.aoe2record"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            print("ERROR: no .aoe2record found", file=sys.stderr); sys.exit(1)
        replay_path = str(candidates[0])
        print(f"Found: {replay_path}")
    else:
        replay_path = sys.argv[1]

    print(f"Deep parsing body: {Path(replay_path).name} ...", flush=True)
    data = parse_deep(replay_path)

    out = Path(replay_path).with_suffix("")
    out_path = Path(str(out) + "_deep.json")
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
