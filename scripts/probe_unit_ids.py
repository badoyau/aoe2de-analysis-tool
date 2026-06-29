"""Find all unit_ids trained in this replay."""
from pathlib import Path
from collections import defaultdict
from mgz.fast.header import parse as parse_hdr
from mgz.fast import operation, meta, Operation, Action

folder = Path(__file__).parent.parent
replay_path = list(folder.glob("*001232*.aoe2record"))[0]

unit_totals = defaultdict(int)  # unit_id -> total amount
unit_by_player = defaultdict(lambda: defaultdict(int))  # player_id -> unit_id -> amount

with open(replay_path, "rb") as f:
    hdr = parse_hdr(f)
    de_players = (hdr.get("de") or {}).get("players") or []
    number_to_slot = {p["number"]: p["color_id"] + 1 for p in de_players}
    try: meta(f)
    except: pass

    while True:
        try:
            op_type, payload = operation(f)
            if op_type == Operation.ACTION:
                if isinstance(payload, tuple) and len(payload) >= 2:
                    atype, adata = payload
                    if atype == Action.DE_QUEUE and isinstance(adata, dict):
                        uid = adata.get("unit_id")
                        amt = adata.get("amount", 1)
                        pid = adata.get("player_id")
                        if uid is not None:
                            unit_totals[uid] += amt
                            if pid is not None:
                                slot = number_to_slot.get(pid, pid)
                                unit_by_player[slot][uid] += amt
        except EOFError:
            break
        except Exception:
            pass

print(f"Unique unit IDs trained: {len(unit_totals)}")
print(f"\nAll unit IDs (sorted by total trained):")
for uid, total in sorted(unit_totals.items(), key=lambda x: -x[1]):
    print(f"  {uid:>5} : {total:>5} total")

print(f"\nPer player (slot -> unit_id: count):")
for slot in sorted(unit_by_player.keys()):
    print(f"  P{slot}: {dict(unit_by_player[slot])}")
