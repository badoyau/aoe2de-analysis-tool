"""Probe DE_QUEUE and MAKE action data to confirm unit_id/amount fields."""
import json
from pathlib import Path
from mgz.fast.header import parse as parse_hdr
from mgz.fast import operation, meta, Operation, Action

folder = Path(__file__).parent.parent
replay_path = list(folder.glob("*001232*.aoe2record"))[0]

samples = []  # collect first 30 training events

with open(replay_path, "rb") as f:
    hdr = parse_hdr(f)
    de_players = (hdr.get("de") or {}).get("players") or []
    number_to_slot = {p["number"]: p["color_id"] + 1 for p in de_players}

    try: meta(f)
    except: pass

    last_ms = 0
    while len(samples) < 30:
        try:
            op_type, payload = operation(f)
            if op_type == Operation.SYNC:
                if isinstance(payload, tuple) and len(payload) >= 3:
                    d = payload[2]
                    if "current_time" in d:
                        last_ms = d["current_time"]
            elif op_type == Operation.ACTION:
                if isinstance(payload, tuple) and len(payload) >= 2:
                    atype, adata = payload
                    if atype in (Action.DE_QUEUE, Action.MAKE, Action.QUEUE, Action.MULTIQUEUE):
                        samples.append({
                            "action": atype.name,
                            "time_ms": last_ms,
                            "data": adata,
                        })
        except EOFError:
            break
        except Exception:
            pass

print("First 30 training actions:")
for s in samples:
    m, sec = divmod(s["time_ms"]//1000, 60)
    print(f"  [{m:02d}:{sec:02d}] {s['action']}: {s['data']}")
