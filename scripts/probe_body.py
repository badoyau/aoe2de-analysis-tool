"""Probe mgz-fast body parsing API to understand structure."""
import sys, json
from pathlib import Path
from mgz.fast.header import parse as parse_hdr
from mgz.fast import Operation, sync, viewlock, parse_action, unpack, start, chat, save
import mgz.fast as fast

folder = Path(__file__).parent.parent
replay_path = list(folder.glob("MP Replay*001232*.aoe2record"))[0]
print(f"File: {replay_path.name}\n")

# Step 1: parse header, get file position
with open(replay_path, "rb") as f:
    hdr = parse_hdr(f)
    body_start = f.tell()
    print(f"Header ends at byte: {body_start}")
    print(f"File size: {replay_path.stat().st_size}")

    # Step 2: read first few operations to understand structure
    op_counts = {}
    last_time_ms = 0
    action_count = 0
    error_count = 0
    ops_read = 0

    while True:
        try:
            op_type, = unpack('<I', f)
            ops_read += 1
            op_name = op_type

            try:
                op_enum = Operation(op_type)
                op_name = op_enum.name
            except ValueError:
                op_name = f"UNKNOWN({op_type})"

            op_counts[op_name] = op_counts.get(op_name, 0) + 1

            if op_type == Operation.SYNC:
                increment, checksum, payload = sync(f)
                if "current_time" in payload:
                    last_time_ms = payload["current_time"]

            elif op_type == Operation.VIEWLOCK:
                viewlock(f)

            elif op_type == Operation.CHAT:
                chat(f)

            elif op_type == Operation.SAVE:
                save(f)

            elif op_type == Operation.ACTION:
                action_type, = unpack('<I', f)
                length, = unpack('<I', f)
                f.read(length)
                action_count += 1

            elif op_type == Operation.START:
                start(f)

            else:
                # Unknown: stop here for now
                print(f"Unknown op {op_type} at byte {f.tell()}, stopping.")
                break

            if ops_read % 50000 == 0:
                secs = last_time_ms // 1000
                print(f"  {ops_read} ops read, time={secs//60}m{secs%60:02d}s ...")

        except Exception as e:
            error_count += 1
            if error_count == 1:
                print(f"\nFirst error at op {ops_read}: {e}")
            if error_count > 5:
                break

    duration_s = last_time_ms // 1000
    print(f"\n=== BODY SUMMARY ===")
    print(f"Operations read : {ops_read}")
    print(f"Last time       : {duration_s//60}m {duration_s%60:02d}s  ({last_time_ms} ms)")
    print(f"Action ops      : {action_count}")
    print(f"Errors          : {error_count}")
    print(f"\nOp type counts:")
    for k, v in sorted(op_counts.items(), key=lambda x: -x[1]):
        print(f"  {k:<20} {v}")
