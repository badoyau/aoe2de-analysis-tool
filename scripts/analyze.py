"""
AOE2 DE Analysis — produces a structured win/loss report.
Reads: <replay>_parsed.json + <replay>_deep.json

Sections:
  1. Game Overview
  2. Age-up Timeline (per player, per team)
  3. Economic Analysis (total_res + obj_count from SYNC)
  4. APM & Action Breakdown
  5. Win/Loss Key Factors + Recommendations
"""

import json, sys
from pathlib import Path
from statistics import mean
from collections import defaultdict

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SLOT_COLORS = {
    1: "Blue(藍)", 2: "Red(紅)", 3: "Green(綠)", 4: "Yellow(黃)",
    5: "Teal(青)", 6: "Purple(紫)", 7: "Gray(灰)", 8: "Orange(橙)",
}
AGE_TW = {"Feudal Age": "封建時代", "Castle Age": "城堡時代", "Imperial Age": "帝王時代"}


# ── helpers ──────────────────────────────────────────────────────────────────

def ms_to_str(ms):
    if ms is None: return "N/A"
    s = ms // 1000; m, s = divmod(s, 60); h, m = divmod(m, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"


def load(base: Path, suffix: str) -> dict:
    p = Path(str(base) + suffix)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def section(title: str):
    print(f"\n{'─'*65}")
    print(f"  {title}")
    print(f"{'─'*65}")


def build_player_index(hdr: dict) -> dict:
    """slot (int) -> player dict"""
    return {p["slot"]: p for p in hdr.get("players", [])}


# ── 1. Game Overview ──────────────────────────────────────────────────────────

def section_overview(hdr: dict):
    section("① 遊戲概要")
    print(f"  地圖     : {hdr.get('map_name','?')}  ({hdr.get('map_dimension','?')}x{hdr.get('map_dimension','?')})")
    print(f"  版本     : {hdr.get('version','?')}  ({hdr.get('game_version','?')})")
    print(f"  時長     : {hdr.get('duration_str','?')}")
    print(f"  勝利隊伍 : Team {hdr.get('winner_team','?')}")

    pidx = build_player_index(hdr)
    teams = hdr.get("teams", {})
    for tid, slots in sorted(teams.items()):
        label = "★ 勝" if str(tid) == str(hdr.get("winner_team")) else "  敗"
        names = [f"P{s} {pidx[s]['name']}({pidx[s]['civilization_tw']})" for s in slots if s in pidx]
        print(f"\n  Team {tid} {label}")
        for n in names:
            print(f"    {n}")

    el = hdr.get("early_leaves", [])
    if el:
        print(f"\n  ⚠ 早期離開 (<5min):")
        for e in el:
            print(f"    P{e['slot']} {e['name']} @ {e['time_str']}")


# ── 2. Age-up Timeline ────────────────────────────────────────────────────────

def section_ageup(hdr: dict):
    section("② 升代時序")
    pidx = build_player_index(hdr)
    age_ups = hdr.get("age_ups", [])

    # Build: slot -> {age_name -> time_ms}
    slot_ages: dict = {}
    for a in age_ups:
        slot = a["slot"]
        if slot is None: continue
        slot_ages.setdefault(slot, {})[a["age"]] = a["time_ms"]

    ages = ["Feudal Age", "Castle Age", "Imperial Age"]
    col_w = 14

    # Header
    print(f"\n  {'槽位/名稱':<30}", end="")
    for age in ages:
        print(f"  {AGE_TW[age]:<{col_w}}", end="")
    print()
    print(f"  {'─'*28}", end="")
    for _ in ages: print(f"  {'─'*col_w}", end="")
    print()

    teams = hdr.get("teams", {})
    for tid, slots in sorted(teams.items()):
        win_tag = "★" if str(tid) == str(hdr.get("winner_team")) else " "
        print(f"\n  Team {tid} {win_tag}")
        team_times: dict = {a: [] for a in ages}

        for slot in sorted(slots):
            p = pidx.get(slot, {})
            label = f"P{slot} {p.get('name','?')[:18]}"
            ages_for_slot = slot_ages.get(slot, {})
            print(f"  {label:<30}", end="")
            for age in ages:
                t = ages_for_slot.get(age)
                if t:
                    team_times[age].append(t)
                    print(f"  {ms_to_str(t):<{col_w}}", end="")
                else:
                    tag = "DC" if slot == 2 else "—"
                    print(f"  {tag:<{col_w}}", end="")
            print()

        # Team average (exclude missing)
        print(f"  {'  隊伍平均':<30}", end="")
        for age in ages:
            ts = team_times[age]
            print(f"  {ms_to_str(int(mean(ts))) if ts else '—':<{col_w}}", end="")
        print()

    # First to each age
    print(f"\n  最快升代:")
    for age in ages:
        candidates = [(slot, slot_ages[slot][age]) for slot in slot_ages if age in slot_ages[slot]]
        if candidates:
            first_slot, first_ms = min(candidates, key=lambda x: x[1])
            p = pidx.get(first_slot, {})
            print(f"    {AGE_TW[age]}: P{first_slot} {p.get('name','?')} ({p.get('civilization_tw','?')}) @ {ms_to_str(first_ms)}")


# ── 3. Economic Analysis ──────────────────────────────────────────────────────

def section_econ(hdr: dict, deep: dict):
    section("③ 經濟分析 (資源代理指標)")
    pidx = build_player_index(hdr)
    samples = deep.get("samples", [])
    if not samples:
        print("  (no SYNC data)"); return

    # Checkpoints: 10m, 20m, 30m, 40m, end
    checkpoints_ms = [10*60*1000, 20*60*1000, 30*60*1000, 40*60*1000]
    cp_samples = {}
    for cp in checkpoints_ms:
        s = next((x for x in samples if x["time_ms"] >= cp), None)
        if s: cp_samples[cp] = s

    last_sample = samples[-1]

    col_w = 10
    cp_labels = ["10min", "20min", "30min", "40min", "終局"]

    print(f"\n  【累積資源 total_res — 越高=資源堆積多 or 採集強】")
    print(f"  {'槽位':<30}", end="")
    for lbl in cp_labels: print(f"  {lbl:>{col_w}}", end="")
    print()
    print(f"  {'─'*28}", end="")
    for _ in cp_labels: print(f"  {'─'*col_w}", end="")
    print()

    teams = hdr.get("teams", {})
    for tid, slots in sorted(teams.items()):
        win_tag = "★" if str(tid) == str(hdr.get("winner_team")) else " "
        print(f"\n  Team {tid} {win_tag}")
        for slot in sorted(slots):
            p = pidx.get(slot, {})
            label = f"P{slot} {p.get('name','?')[:18]}"
            print(f"  {label:<30}", end="")
            for cp in checkpoints_ms:
                s = cp_samples.get(cp, {})
                val = s.get("players", {}).get(str(slot), {}).get("total_res")
                print(f"  {str(val) if val is not None else '—':>{col_w}}", end="")
            # End
            val = last_sample.get("players", {}).get(str(slot), {}).get("total_res")
            print(f"  {str(val) if val is not None else '—':>{col_w}}", end="")
            print()

    print(f"\n  【物件數 obj_count — 包含建築+單位，反映規模】")
    print(f"  {'槽位':<30}", end="")
    for lbl in cp_labels: print(f"  {lbl:>{col_w}}", end="")
    print()
    print(f"  {'─'*28}", end="")
    for _ in cp_labels: print(f"  {'─'*col_w}", end="")
    print()

    for tid, slots in sorted(teams.items()):
        win_tag = "★" if str(tid) == str(hdr.get("winner_team")) else " "
        print(f"\n  Team {tid} {win_tag}")
        for slot in sorted(slots):
            p = pidx.get(slot, {})
            label = f"P{slot} {p.get('name','?')[:18]}"
            print(f"  {label:<30}", end="")
            for cp in checkpoints_ms:
                s = cp_samples.get(cp, {})
                val = s.get("players", {}).get(str(slot), {}).get("obj_count")
                print(f"  {str(val) if val is not None else '—':>{col_w}}", end="")
            val = last_sample.get("players", {}).get(str(slot), {}).get("obj_count")
            print(f"  {str(val) if val is not None else '—':>{col_w}}", end="")
            print()


# ── 4. APM & Actions ─────────────────────────────────────────────────────────

def section_apm(hdr: dict, deep: dict, duration_ms: int):
    section("④ 操作強度 (APM 代理)")
    pidx = build_player_index(hdr)
    apc = deep.get("actions_per_player", {})
    duration_min = duration_ms / 60000 if duration_ms else 1

    teams = hdr.get("teams", {})
    print(f"\n  {'槽位':<30} {'總操作':>8} {'APM':>6}  前3動作類型")
    print(f"  {'─'*28} {'─'*8} {'─'*6}  {'─'*25}")

    for tid, slots in sorted(teams.items()):
        win_tag = "★" if str(tid) == str(hdr.get("winner_team")) else " "
        print(f"\n  Team {tid} {win_tag}")
        for slot in sorted(slots):
            p = pidx.get(slot, {})
            label = f"P{slot} {p.get('name','?')[:18]}"
            actions = apc.get(str(slot), {})
            total = sum(actions.values())
            apm = total / duration_min
            top3 = sorted(actions.items(), key=lambda x: -x[1])[:3]
            top3_str = ", ".join(f"{k}×{v}" for k, v in top3)
            print(f"  {label:<30} {total:>8} {apm:>6.1f}  {top3_str}")


# ── 5. Win/Loss Key Factors ───────────────────────────────────────────────────

def section_verdict(hdr: dict, deep: dict):
    section("⑤ 勝負關鍵 & 建議")
    pidx = build_player_index(hdr)
    winner_team = hdr.get("winner_team")
    apc = deep.get("actions_per_player", {})
    duration_ms = hdr.get("duration_ms", 1)
    duration_min = duration_ms / 60000

    teams = hdr.get("teams", {})
    # Team stats
    team_stats = {}
    for tid, slots in teams.items():
        total_actions = sum(sum(apc.get(str(s), {}).values()) for s in slots)
        alive_players = [s for s in slots if s != 2]  # exclude DC
        team_stats[tid] = {"total_actions": total_actions, "alive": len(alive_players), "slots": slots}

    samples = deep.get("samples", [])
    last = samples[-1] if samples else {}

    print("\n  【關鍵事件】")
    el = hdr.get("early_leaves", [])
    if el:
        for e in el:
            print(f"  ⚠ P{e['slot']} {e['name']} 在 {e['time_str']} 斷線 → Team {pidx[e['slot']]['team_id']} 以人數劣勢作戰")

    age_ups = hdr.get("age_ups", [])
    # Fastest imperial
    imperial_times = [(a["slot"], a["time_ms"]) for a in age_ups if a["age"] == "Imperial Age"]
    if imperial_times:
        first_imp_slot, first_imp_ms = min(imperial_times, key=lambda x: x[1])
        p = pidx.get(first_imp_slot, {})
        print(f"  ⚡ 最快帝王: P{first_imp_slot} {p.get('name','?')} ({p.get('civilization_tw','?')}) @ {ms_to_str(first_imp_ms)}")
        # Team breakdown
        for tid, slots in sorted(teams.items()):
            team_imp = [ms for slot, ms in imperial_times if slot in slots]
            if team_imp:
                avg_imp = int(mean(team_imp))
                print(f"     Team {tid} 帝王平均: {ms_to_str(avg_imp)}")

    # Economy gap at end
    if last.get("players"):
        print(f"\n  【終局經濟差距 (total_res)】")
        for tid, slots in sorted(teams.items()):
            vals = [last["players"].get(str(s), {}).get("total_res", 0) for s in slots]
            print(f"  Team {tid}: {vals}  合計={sum(vals)}")

    # APM comparison
    print(f"\n  【操作強度對比 (APM)】")
    for tid, slots in sorted(teams.items()):
        apms = [sum(apc.get(str(s), {}).values()) / duration_min for s in slots if str(s) in apc]
        avg_apm = mean(apms) if apms else 0
        print(f"  Team {tid} 平均 APM: {avg_apm:.1f}")

    # Verdict
    print(f"\n  【勝負分析】")
    if winner_team:
        print(f"  ✅ Team {winner_team} 勝利")
        w_slots = teams.get(str(winner_team), [])
        l_teams = [t for t in teams if str(t) != str(winner_team)]
        for lt in l_teams:
            print(f"  ❌ Team {lt} 敗北 → 投降時間 {hdr.get('duration_str','?')}")

    print(f"\n  【改善建議】")
    # DC impact
    if el:
        print(f"  • Team {pidx[el[0]['slot']]['team_id']} 因 P{el[0]['slot']} 斷線以 3v4 完成比賽，建議確認網路穩定性")

    # Age-up pace
    feudal_times = {a["slot"]: a["time_ms"] for a in age_ups if a["age"] == "Feudal Age"}
    if feudal_times:
        slow_feudal = max(feudal_times.items(), key=lambda x: x[1])
        sf_slot, sf_ms = slow_feudal
        if sf_ms > 10 * 60 * 1000:
            p = pidx.get(sf_slot, {})
            print(f"  • P{sf_slot} {p.get('name','?')} 封建升代 {ms_to_str(sf_ms)} 偏慢，目標 <8min30s")

    # High total_res at end (resource hoarding)
    if last.get("players"):
        for slot, pdata in last["players"].items():
            tr = pdata.get("total_res", 0)
            if tr > 10000 and int(slot) != 2:
                p = pidx.get(int(slot), {})
                print(f"  • P{slot} {p.get('name','?')} 終局 total_res={tr:,} 偏高，資源可能未充分使用")

    print()


# ── 6. Unit Analysis ─────────────────────────────────────────────────────────

def _load_unit_map() -> dict:
    """Load data/units.json → {unit_id: {en, tw, class}}"""
    candidates = [
        Path(__file__).parent.parent / "data" / "units.json",
        Path("data/units.json"),
    ]
    for p in candidates:
        if p.exists():
            raw = json.loads(p.read_text(encoding="utf-8"))
            return {u["id"]: u for u in raw.get("units", [])}
    return {}


def _classify_age(time_ms: int, slot_age_times: dict) -> str:
    """Return '帝王'/'城堡'/'封建'/'黑暗' based on per-player age-up times."""
    imp = slot_age_times.get("Imperial Age")
    cas = slot_age_times.get("Castle Age")
    feu = slot_age_times.get("Feudal Age")
    if imp and time_ms >= imp: return "帝王"
    if cas and time_ms >= cas: return "城堡"
    if feu and time_ms >= feu: return "封建"
    return "黑暗"


AGE_ORDER = ["黑暗", "封建", "城堡", "帝王"]
CLASS_ORDER = ["econ", "cavalry", "infantry", "archer", "unique", "siege", "support"]
CLASS_TW = {
    "econ": "經濟", "cavalry": "騎兵", "infantry": "步兵",
    "archer": "弓箭", "unique": "特殊", "siege": "攻城", "support": "輔助",
}


def section_units(hdr: dict, deep: dict):
    section("⑥ 兵種分析 (訓練數量 × 時代)")

    pidx = build_player_index(hdr)
    unit_map = _load_unit_map()
    training_events = deep.get("training_events", [])

    if not training_events:
        print("  (no training_events — re-run parse_body_deep.py to capture unit data)")
        return

    # Build per-player age-up time lookup: slot -> {age_name -> time_ms}
    slot_age_times: dict = {}
    for a in hdr.get("age_ups", []):
        slot = a.get("slot")
        if slot is None: continue
        slot_age_times.setdefault(slot, {})[a["age"]] = a["time_ms"]

    # Aggregate: slot -> age -> unit_id -> total amount
    stats: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for ev in training_events:
        slot = ev.get("slot")
        uid = ev.get("unit_id")
        amt = ev.get("amount", 1)
        if slot is None or uid is None: continue
        age = _classify_age(ev["time_ms"], slot_age_times.get(slot, {}))
        stats[slot][age][uid] += amt

    teams = hdr.get("teams", {})
    for tid, slots in sorted(teams.items()):
        win_tag = "★" if str(tid) == str(hdr.get("winner_team")) else " "
        print(f"\n  ══ Team {tid} {win_tag} ══")

        for slot in sorted(slots):
            p = pidx.get(slot, {})
            name = p.get("name", "?")
            civ  = p.get("civilization_tw", "?")
            print(f"\n  P{slot} {name} ({civ})")

            player_stats = stats.get(slot, {})
            if not player_stats:
                print("    (無訓練紀錄)")
                continue

            # Gather all unit_ids this player trained
            all_uids = set()
            for age_data in player_stats.values():
                all_uids.update(age_data.keys())

            # Sort units by class then total amount
            def sort_key(uid):
                u = unit_map.get(uid, {})
                cls = u.get("class", "z")
                total = sum(player_stats.get(age, {}).get(uid, 0) for age in AGE_ORDER)
                ci = CLASS_ORDER.index(cls) if cls in CLASS_ORDER else len(CLASS_ORDER)
                return (ci, -total)

            sorted_uids = sorted(all_uids, key=sort_key)

            # Header
            col = 8
            print(f"    {'兵種':<22} {'類型':<6}", end="")
            for age in AGE_ORDER:
                print(f"  {age:>{col}}", end="")
            print(f"  {'合計':>{col}}")
            print(f"    {'─'*22} {'─'*6}", end="")
            for _ in AGE_ORDER: print(f"  {'─'*col}", end="")
            print(f"  {'─'*col}")

            for uid in sorted_uids:
                u = unit_map.get(uid, {})
                uname = u.get("tw") or u.get("en") or f"ID:{uid}"
                ucls  = CLASS_TW.get(u.get("class", ""), u.get("class", "—"))
                total = sum(player_stats.get(age, {}).get(uid, 0) for age in AGE_ORDER)
                print(f"    {uname:<22} {ucls:<6}", end="")
                for age in AGE_ORDER:
                    cnt = player_stats.get(age, {}).get(uid, 0)
                    print(f"  {str(cnt) if cnt else '—':>{col}}", end="")
                print(f"  {total:>{col}}")

            # Row totals per age (excluding villagers for military summary)
            mil_uids = [u for u in sorted_uids if unit_map.get(u, {}).get("class") != "econ"]
            if mil_uids:
                print(f"    {'─'*22} {'─'*6}", end="")
                for _ in AGE_ORDER: print(f"  {'─'*col}", end="")
                print(f"  {'─'*col}")
                mil_total = sum(
                    player_stats.get(age, {}).get(uid, 0)
                    for uid in mil_uids for age in AGE_ORDER
                )
                print(f"    {'  軍事合計':<22} {'':6}", end="")
                for age in AGE_ORDER:
                    s = sum(player_stats.get(age, {}).get(uid, 0) for uid in mil_uids)
                    print(f"  {str(s) if s else '—':>{col}}", end="")
                print(f"  {mil_total:>{col}}")

    print()


# ── 7. Player Timeline Snapshots ─────────────────────────────────────────────

def _nearest_sample(samples: list, target_ms: int) -> dict:
    """Return the SYNC sample closest to target_ms."""
    if not samples: return {}
    return min(samples, key=lambda s: abs(s["time_ms"] - target_ms))


def _units_before(training_events: list, slot: int, cutoff_ms: int) -> dict:
    """Sum unit training for a player up to cutoff_ms → {unit_id: count}"""
    totals: dict = defaultdict(int)
    for ev in training_events:
        if ev.get("slot") == slot and ev["time_ms"] <= cutoff_ms:
            totals[ev["unit_id"]] += ev.get("amount", 1)
    return dict(totals)


def section_timeline(hdr: dict, deep: dict):
    section("⑦ 玩家時序快照 (升代瞬間狀態)")

    pidx    = build_player_index(hdr)
    samples = deep.get("samples", [])
    tevents = deep.get("training_events", [])
    unit_map = _load_unit_map()

    # slot -> {age -> time_ms}
    slot_ages: dict = {}
    for a in hdr.get("age_ups", []):
        s = a.get("slot")
        if s: slot_ages.setdefault(s, {})[a["age"]] = a["time_ms"]

    AGE_KEYS = [
        ("封建升代", "Feudal Age"),
        ("城堡升代", "Castle Age"),
        ("帝王升代", "Imperial Age"),
    ]

    teams = hdr.get("teams", {})
    for tid, slots in sorted(teams.items()):
        win_tag = "★" if str(tid) == str(hdr.get("winner_team")) else " "
        print(f"\n  ══ Team {tid} {win_tag} ══")

        for slot in sorted(slots):
            p = pidx.get(slot, {})
            ages = slot_ages.get(slot, {})
            print(f"\n  P{slot} {p.get('name','?')} ({p.get('civilization_tw','?')})")

            if not ages:
                print("    (無升代紀錄 — 斷線)")
                continue

            for label, age_key in AGE_KEYS:
                t = ages.get(age_key)
                if t is None:
                    print(f"    {label}: 未升代")
                    continue

                snap = _nearest_sample(samples, t)
                psnap = snap.get("players", {}).get(str(slot), {})
                tr  = psnap.get("total_res", "—")
                obj = psnap.get("obj_count", "—")

                # Military units trained up to this moment (exclude villagers)
                utotals = _units_before(tevents, slot, t)
                mil_units = {uid: cnt for uid, cnt in utotals.items()
                             if unit_map.get(uid, {}).get("class") != "econ"}
                mil_total = sum(mil_units.values())
                mil_top = sorted(mil_units.items(), key=lambda x: -x[1])[:3]
                mil_str = ", ".join(
                    f"{unit_map.get(uid,{}).get('tw') or f'ID:{uid}'}×{cnt}"
                    for uid, cnt in mil_top
                ) if mil_top else "無"

                print(f"    [{ms_to_str(t)}] {label:5}  "
                      f"資源={str(tr):>6}  物件={str(obj):>4}  "
                      f"軍事累計={mil_total:>4} ({mil_str})")
    print()


# ── 8. Win/Loss Deep Analysis ─────────────────────────────────────────────────

def section_deep_verdict(hdr: dict, deep: dict):
    section("⑧ 勝負深度分析 (時段優勢 & 轉折點)")

    pidx     = build_player_index(hdr)
    samples  = deep.get("samples", [])
    tevents  = deep.get("training_events", [])
    unit_map = _load_unit_map()
    winner   = str(hdr.get("winner_team", ""))
    teams    = hdr.get("teams", {})

    # slot -> {age -> time_ms}
    slot_ages: dict = {}
    for a in hdr.get("age_ups", []):
        s = a.get("slot")
        if s: slot_ages.setdefault(s, {})[a["age"]] = a["time_ms"]

    # ── 1. 時段優勢對比 ─────────────────────────────────────
    print("\n  【各時段 經濟優勢對比】")
    checkpoints = [
        ("封建前 (10min)", 10*60*1000),
        ("城堡期 (20min)", 20*60*1000),
        ("城堡/帝王 (30min)", 30*60*1000),
        ("帝王期 (40min)", 40*60*1000),
        ("終局",           hdr.get("duration_ms", 99*60*1000)),
    ]

    col = 9
    print(f"\n  {'時段':<18}", end="")
    for tid in sorted(teams):
        tag = "★" if str(tid) == winner else " "
        print(f"  {'T'+str(tid)+tag+' total_res':>{col+4}}", end="")
        print(f"  {'obj_count':>{col}}", end="")
    print(f"  {'優勢方'}")
    print(f"  {'─'*18}", end="")
    for _ in teams: print(f"  {'─'*(col+4)}  {'─'*col}", end="")
    print()

    for label, cp_ms in checkpoints:
        snap = _nearest_sample(samples, cp_ms)
        pdata = snap.get("players", {})

        team_res  = {}
        team_obj  = {}
        for tid, slots in teams.items():
            alive = [s for s in slots if pidx.get(s, {}).get("name") and
                     not any(e["slot"] == s for e in hdr.get("early_leaves", []))]
            tr_sum  = sum(pdata.get(str(s), {}).get("total_res", 0) for s in alive)
            obj_sum = sum(pdata.get(str(s), {}).get("obj_count", 0)  for s in alive)
            team_res[tid]  = tr_sum
            team_obj[tid]  = obj_sum

        lead = max(team_res, key=lambda t: team_res[t]) if team_res else "?"
        lead_tag = f"T{lead}" if team_res.get(lead, 0) > 0 else "平"

        print(f"  {label:<18}", end="")
        for tid in sorted(teams):
            print(f"  {team_res.get(tid,0):>{col+4},}", end="")
            print(f"  {team_obj.get(tid,0):>{col}}", end="")
        print(f"  {lead_tag}")

    # ── 2. 升代速度對比 ─────────────────────────────────────
    print(f"\n  【升代速度對比 (隊伍平均)】")
    for age_key, age_tw in [("Feudal Age","封建"),("Castle Age","城堡"),("Imperial Age","帝王")]:
        print(f"\n  {age_tw}升代:")
        for tid, slots in sorted(teams.items()):
            tag = "★" if str(tid) == winner else " "
            times = [slot_ages[s][age_key] for s in slots
                     if s in slot_ages and age_key in slot_ages[s]]
            if times:
                avg = int(mean(times))
                fastest = min(times)
                slowest = max(times)
                print(f"    Team {tid}{tag}  平均={ms_to_str(avg)}  "
                      f"最快={ms_to_str(fastest)}  最慢={ms_to_str(slowest)}")

    # ── 3. 軍事投資對比 ─────────────────────────────────────
    print(f"\n  【軍事投資對比 (非經濟單位總數)】")
    for tid, slots in sorted(teams.items()):
        tag = "★" if str(tid) == winner else " "
        mil_by_age: dict = defaultdict(int)
        for slot in slots:
            sages = slot_ages.get(slot, {})
            for ev in tevents:
                if ev.get("slot") != slot: continue
                if unit_map.get(ev["unit_id"], {}).get("class") == "econ": continue
                age = _classify_age(ev["time_ms"], sages)
                mil_by_age[age] += ev.get("amount", 1)
        total = sum(mil_by_age.values())
        breakdown = "  ".join(f"{a}:{mil_by_age.get(a,0)}" for a in AGE_ORDER)
        print(f"    Team {tid}{tag}  軍事總={total:>5}  [{breakdown}]")

    # ── 4. 勝負關鍵判斷 ─────────────────────────────────────
    print(f"\n  【勝負關鍵推論】")

    # Check early DC
    el = hdr.get("early_leaves", [])
    if el:
        for e in el:
            p = pidx.get(e["slot"], {})
            print(f"  ❗ P{e['slot']} {p.get('name','?')} 於 {e['time_str']} 斷線"
                  f"，其隊以人數劣勢完賽")

    # Age-up advantage
    for age_key, age_tw in [("Feudal Age","封建"),("Castle Age","城堡"),("Imperial Age","帝王")]:
        team_avgs = {}
        for tid, slots in teams.items():
            times = [slot_ages[s][age_key] for s in slots
                     if s in slot_ages and age_key in slot_ages[s]]
            if times: team_avgs[tid] = int(mean(times))
        if len(team_avgs) == 2:
            tids = list(team_avgs.keys())
            diff = abs(team_avgs[tids[0]] - team_avgs[tids[1]])
            faster = min(team_avgs, key=lambda t: team_avgs[t])
            if diff > 60_000:
                tag = "★" if str(faster) == winner else "↯"
                print(f"  {tag} {age_tw}升代: Team {faster} 平均快 {ms_to_str(diff)}，"
                      + ("與勝利一致" if str(faster) == winner else "但最終敗北"))

    # Military volume vs outcome
    mil_totals = {}
    for tid, slots in teams.items():
        total = sum(
            ev.get("amount", 1) for ev in tevents
            if ev.get("slot") in slots and
               unit_map.get(ev["unit_id"], {}).get("class") != "econ"
        )
        mil_totals[tid] = total
    if len(mil_totals) == 2:
        tids = list(mil_totals.keys())
        higher_mil = max(mil_totals, key=lambda t: mil_totals[t])
        if str(higher_mil) != winner:
            print(f"  ↯ Team {higher_mil} 軍事總量更多({mil_totals[higher_mil]})但敗北"
                  f" → 純兵量非決定因素")
        else:
            print(f"  ★ Team {higher_mil} 軍事總量更多({mil_totals[higher_mil]}) 且勝利")

    # Resource hoarding
    last_snap = samples[-1].get("players", {}) if samples else {}
    for tid, slots in teams.items():
        tag = "★" if str(tid) == winner else " "
        hoard = [(s, last_snap.get(str(s), {}).get("total_res", 0))
                 for s in slots if last_snap.get(str(s), {}).get("total_res", 0) > 8000]
        for s, tr in hoard:
            p = pidx.get(s, {})
            print(f"  ⚠ P{s} {p.get('name','?')} 終局殘餘資源 {tr:,}"
                  f" → 資源未充分轉化為軍事優勢")

    print()


# ── Strategy detection ───────────────────────────────────────────────────────

def _detect_strategy(civ, by_class, by_age, top_units, total_mil):
    """Returns (strategy_name, description) from unit/age composition."""
    if total_mil == 0:
        return "未出兵", "全場無軍事單位訓練"

    cav = by_class.get("cavalry", 0) / total_mil
    inf = by_class.get("infantry", 0) / total_mil
    arc = by_class.get("archer",   0) / total_mil
    unq = by_class.get("unique",   0) / total_mil
    imp_r = by_age.get("帝王", 0) / total_mil
    cas_r = by_age.get("城堡", 0) / total_mil

    if imp_r > 0.85:  pace = "全帝王爆兵"
    elif imp_r > 0.6: pace = "帝王期主力"
    elif cas_r > 0.5: pace = "城堡期發展"
    else:              pace = "混合推進"

    # Civ-specific
    if civ == "高棉人":
        be = top_units.get("弩弓象 [高]", 0)
        sc = top_units.get("斥候騎兵",   0)
        if be > 20:
            return "弩弓象+斥候暴兵", f"高棉特色：{pace}，弩弓象({be})核心輸出，斥候({sc})機動輔助"
    if civ == "哥德人":
        if by_class.get("infantry", 0) > 200:
            return "哥德步兵人海", "帝王廉價步兵戰術：民兵/長矛/家衛大量爆發，以數量壓制"
    if civ == "法蘭克人":
        kn = top_units.get("騎士", 0)
        if kn > 50:
            return "法蘭克騎士流", f"法蘭克騎士天賦加成，{pace}，{kn} 騎士為主力衝擊"
    if civ == "孟加拉人":
        ratha = top_units.get("戰車 [孟]", 0)
        if ratha > 30:
            return "孟加拉戰車流", f"孟加拉特色戰車({ratha})，城堡期生產，機動高傷"
    if civ == "波斯人":
        arc_t = top_units.get("弓箭手", 0)
        if arc_t > 100:
            return "波斯帝王弓箭海", f"帝王期 {arc_t} 弓箭手傾倒，前期騎士騷擾鋪路"
    if civ == "波希米亞人":
        sp = top_units.get("長矛兵", 0)
        hw = top_units.get("胡斯車 [波]", 0)
        if sp > 100:
            return "波希米亞長矛+砲車", f"長矛兵({sp})為主體，胡斯車({hw})特色輸出，臼炮收尾"
    if civ == "拜占庭人" and total_mil < 5:
        return "斷線無策略", "遊戲早期斷線"

    # Generic
    if imp_r > 0.85:
        known_bc = {k: v for k, v in by_class.items() if k in CLASS_TW}
        dom = max(known_bc.items(), key=lambda x: x[1])[0] if known_bc else (
              max(by_class.items(), key=lambda x: x[1])[0] if by_class else "cavalry")
        dom_tw = CLASS_TW.get(dom, "特殊")
        return f"全帝王{dom_tw}暴兵", f"軍事投資全集中帝王，{dom_tw}為主"
    if cav > 0.6:  return "騎兵流",   f"騎兵佔 {cav:.0%}，{pace}"
    if inf > 0.6:  return "步兵流",   f"步兵佔 {inf:.0%}，{pace}"
    if arc > 0.6:  return "弓箭流",   f"弓箭佔 {arc:.0%}，{pace}"
    if unq > 0.35: return "特殊兵流", f"特殊兵佔 {unq:.0%}，{pace}"
    return "混合策略", f"多兵種混合，{pace}"


# ── 9. Strategy & MVP ─────────────────────────────────────────────────────────

def section_strategy_mvp(hdr: dict, deep: dict):
    section("⑨ 策略分析 & MVP 評選")

    unit_map     = _load_unit_map()
    pidx         = build_player_index(hdr)
    teams        = hdr.get("teams", {})
    winner_team  = str(hdr.get("winner_team", ""))
    el_slots     = {e["slot"] for e in hdr.get("early_leaves", [])}
    tevents      = deep.get("training_events", [])
    apc          = deep.get("actions_per_player", {})
    samples      = deep.get("samples", [])
    duration_ms  = hdr.get("duration_ms", 1)
    duration_min = duration_ms / 60000

    slot_ages: dict = {}
    for a in hdr.get("age_ups", []):
        s = a.get("slot")
        if s: slot_ages.setdefault(s, {})[a["age"]] = a["time_ms"]

    # ── Per-player strategy ───────────────────────────────────────────────
    print("\n  【玩家策略剖析】")
    player_data: dict = {}

    for tid, slots in sorted(teams.items()):
        win_tag = "★" if str(tid) == winner_team else " "
        print(f"\n  Team {tid} {win_tag}")
        for slot in sorted(slots):
            p = pidx.get(slot, {})
            civ  = p.get("civilization_tw", "?")
            name = p.get("name", "?")

            if slot in el_slots:
                print(f"  ⊘ P{slot} {name[:16]} ({civ}) — 斷線")
                player_data[slot] = {"strategy": "斷線", "desc": "", "total_mil": 0}
                continue

            sages = slot_ages.get(slot, {})
            by_class: dict = defaultdict(int)
            by_age_l: dict = defaultdict(int)
            top_units: dict = defaultdict(int)
            for ev in tevents:
                if ev.get("slot") != slot: continue
                uid = ev["unit_id"]; amt = ev.get("amount", 1)
                u   = unit_map.get(uid, {}); cls = u.get("class", "unknown")
                age = _classify_age(ev["time_ms"], sages)
                if cls != "econ":
                    by_class[cls] += amt
                    by_age_l[age] += amt
                    top_units[u.get("tw") or u.get("en") or f"ID:{uid}"] += amt

            total_mil = sum(by_class.values())
            strategy, desc = _detect_strategy(civ, dict(by_class), dict(by_age_l),
                                               dict(top_units), total_mil)
            top3 = sorted(top_units.items(), key=lambda x: -x[1])[:3]
            top3_str = "、".join(f"{n}×{c}" for n, c in top3)
            imp_pct = by_age_l.get("帝王", 0) / total_mil if total_mil else 0

            player_data[slot] = {"strategy": strategy, "desc": desc,
                                  "total_mil": total_mil, "by_class": dict(by_class),
                                  "by_age": dict(by_age_l), "top_units": dict(top_units)}

            print(f"  P{slot} {name[:16]} ({civ})")
            print(f"    ► 策略: {strategy}")
            print(f"    ► {desc}")
            print(f"    ► 核心: {top3_str or '無'}  | 軍事={total_mil}  帝王比={imp_pct:.0%}")

    # ── Key insights ──────────────────────────────────────────────────────
    print(f"\n  【關鍵戰略要點】")

    el = hdr.get("early_leaves", [])
    if el:
        e  = el[0]; pp = pidx.get(e["slot"], {})
        print(f"  ❗ 斷線事件: P{e['slot']} {pp.get('name','')} @ {e['time_str']}"
              f" → Team {pp.get('team_id','?')} 以 3v4 完賽")

    # Eco advantage at 20min
    snap20 = min(samples, key=lambda s: abs(s["time_ms"] - 20*60000)) if samples else {}
    if snap20:
        pdata = snap20.get("players", {})
        team_res20 = {
            str(tid): sum(pdata.get(str(s), {}).get("total_res", 0)
                          for s in slots if s not in el_slots)
            for tid, slots in teams.items()
        }
        leader = max(team_res20, key=lambda t: team_res20[t])
        loser  = min(team_res20, key=lambda t: team_res20[t])
        print(f"  📊 20min 經濟領先: Team {leader} ({team_res20[leader]:,}"
              f" vs {team_res20[loser]:,})")

    # When did winning team first overtake obj_count?
    w_slots = [s for tid, slots in teams.items()
               if str(tid) == winner_team for s in slots if s not in el_slots]
    l_slots  = [s for tid, slots in teams.items()
               if str(tid) != winner_team for s in slots]
    first_lead = next(
        (s for s in samples
         if sum(s.get("players",{}).get(str(sl),{}).get("obj_count",0) for sl in w_slots) >
            sum(s.get("players",{}).get(str(sl),{}).get("obj_count",0) for sl in l_slots)),
        None
    )
    if first_lead:
        print(f"  🔄 轉折點 {first_lead['time_str']}: Team {winner_team} obj_count"
              f" 首次超越 → 規模優勢確立")

    # Main contributor per team
    for tid, slots in teams.items():
        alive = [s for s in slots if s not in el_slots]
        if not alive: continue
        mil_ct = {s: sum(ev.get("amount",1) for ev in tevents
                         if ev.get("slot")==s
                         and unit_map.get(ev["unit_id"],{}).get("class")!="econ")
                  for s in alive}
        top_s = max(mil_ct, key=lambda s: mil_ct[s])
        pp    = pidx.get(top_s, {}); st = player_data.get(top_s, {})
        pct   = mil_ct[top_s] / max(sum(mil_ct.values()), 1)
        print(f"  ⚔️  Team {tid} 軍事主力: P{top_s} {pp.get('name','?')}"
              f" [{st.get('strategy','?')}] 貢獻 {pct:.0%} ({mil_ct[top_s]} 單位)")

    # ── MVP selection ─────────────────────────────────────────────────────
    print(f"\n  【MVP 評選】")

    for tid, slots in sorted(teams.items()):
        win_tag = "★" if str(tid) == winner_team else " "
        title   = "勝利隊 MVP" if str(tid) == winner_team else "最佳表現 (敗隊)"

        raw: dict = {}
        for slot in slots:
            if slot in el_slots:
                raw[slot] = 0.0; continue
            mil_t = sum(ev.get("amount",1) for ev in tevents
                        if ev.get("slot")==slot
                        and unit_map.get(ev["unit_id"],{}).get("class")!="econ")
            acts  = sum(apc.get(str(slot), {}).values())
            f_res = (samples[-1].get("players",{}).get(str(slot),{}).get("total_res",0)
                     if samples else 0)
            f_obj = (samples[-1].get("players",{}).get(str(slot),{}).get("obj_count",0)
                     if samples else 0)
            raw[slot] = (mil_t/duration_min*0.40 + acts/duration_min*0.30 +
                         max(0,1-f_res/20000)*10*0.20 + f_obj/500*10*0.10)

        max_r  = max(raw.values(), default=1) or 1
        normed = {s: round(raw[s]/max_r*100) for s in raw}
        mvp    = max(raw, key=lambda s: raw[s])
        pp     = pidx.get(mvp, {})
        st     = player_data.get(mvp, {})
        ms     = normed[mvp]

        mil_t = sum(ev.get("amount",1) for ev in tevents
                    if ev.get("slot")==mvp
                    and unit_map.get(ev["unit_id"],{}).get("class")!="econ")
        apm_v = sum(apc.get(str(mvp),{}).values()) / duration_min
        f_res = (samples[-1].get("players",{}).get(str(mvp),{}).get("total_res",0)
                 if samples else 0)

        reasons = []
        alive   = [s for s in slots if s not in el_slots]
        if mil_t == max(sum(ev.get("amount",1) for ev in tevents
                            if ev.get("slot")==s and
                            unit_map.get(ev["unit_id"],{}).get("class")!="econ")
                        for s in alive if alive):
            reasons.append(f"全隊最高軍事輸出 ({mil_t} 單位)")
        if apm_v == max(sum(apc.get(str(s),{}).values())/duration_min
                        for s in alive if alive):
            reasons.append(f"全隊操作最積極 (APM {apm_v:.0f})")
        if f_res < 3000:
            reasons.append(f"資源利用高效 (終局僅餘 {f_res:,})")
        elif mil_t > 200:
            reasons.append(f"軍事輸出足以彌補資源殘留 ({mil_t} 單位)")
        if not reasons:
            reasons.append("全隊綜合表現最佳")

        print(f"\n  🏆 Team {tid} {win_tag} — {title}")
        print(f"     🥇 P{mvp} {pp.get('name','?')} ({pp.get('civilization_tw','?')})")
        print(f"     策略: {st.get('strategy','?')}")
        print(f"     原因: {' | '.join(reasons)}")
        print(f"     隊伍評分:")
        for s in sorted(slots, key=lambda x: -normed.get(x, 0)):
            pp2 = pidx.get(s, {})
            pct = normed.get(s, 0)
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            dc  = " [DC]" if s in el_slots else ""
            crown = " 🥇" if s == mvp else ""
            print(f"       P{s} {pp2.get('name','?')[:12]:<13} {bar} {pct:>3}/100{dc}{crown}")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        candidates = sorted(Path(".").glob("*_parsed.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            print("ERROR: no _parsed.json found", file=sys.stderr); sys.exit(1)
        base = Path(str(candidates[0]).replace("_parsed.json", ""))
        print(f"Found: {candidates[0].name}")
    else:
        base = Path(sys.argv[1]).with_suffix("")
        if str(base).endswith("_parsed"):
            base = Path(str(base)[:-7])

    hdr = load(base, "_parsed.json")
    deep = load(base, "_deep.json")

    if not hdr:
        print(f"ERROR: {base}_parsed.json not found — run parse_replay.py + parse_body.py first", file=sys.stderr)
        sys.exit(1)
    if not deep:
        print(f"ERROR: {base}_deep.json not found — run parse_body_deep.py first", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'═'*65}")
    print(f"  AOE2 DE 分析報告")
    print(f"{'═'*65}")

    section_overview(hdr)
    section_ageup(hdr)
    section_econ(hdr, deep)
    section_apm(hdr, deep, hdr.get("duration_ms", 0))
    section_verdict(hdr, deep)
    section_units(hdr, deep)
    section_timeline(hdr, deep)
    section_deep_verdict(hdr, deep)
    section_strategy_mvp(hdr, deep)

    # Save report
    report_path = Path(str(base) + "_report.txt")
    import io as _io
    buf = _io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf

    print(f"\n{'═'*65}")
    print(f"  AOE2 DE 分析報告")
    print(f"{'═'*65}")
    section_overview(hdr)
    section_ageup(hdr)
    section_econ(hdr, deep)
    section_apm(hdr, deep, hdr.get("duration_ms", 0))
    section_verdict(hdr, deep)
    section_units(hdr, deep)
    section_timeline(hdr, deep)
    section_deep_verdict(hdr, deep)
    section_strategy_mvp(hdr, deep)

    sys.stdout = old_stdout
    report_path.write_text(buf.getvalue(), encoding="utf-8")
    print(f"\n{'═'*65}")
    print(f"  報告已存: {report_path.name}")
    print(f"{'═'*65}")


if __name__ == "__main__":
    main()
