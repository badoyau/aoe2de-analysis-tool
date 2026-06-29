"""
Generate a self-contained HTML visual report.
Reads: <replay>_parsed.json + <replay>_deep.json
Outputs: <replay>_report.html
"""

import json, sys
from pathlib import Path
from collections import defaultdict

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

PLAYER_COLORS = {
    1: '#4488ff', 2: '#ff4444', 3: '#44cc44', 4: '#ffcc00',
    5: '#00cccc', 6: '#cc44cc', 7: '#aaaaaa', 8: '#ff8800',
}
AGE_COLORS  = {'黑暗': '#8B6914', '封建': '#5C8A3C', '城堡': '#3C5C8A', '帝王': '#8A3C3C'}
AGE_ORDER   = ['黑暗', '封建', '城堡', '帝王']
CLASS_ORDER = ['cavalry', 'infantry', 'archer', 'unique', 'siege', 'support']
CLASS_TW    = {'cavalry':'騎兵','infantry':'步兵','archer':'弓箭',
               'unique':'特殊','siege':'攻城','support':'輔助','econ':'經濟'}
CLASS_COLORS= {'cavalry':'#e8a838','infantry':'#e85838','archer':'#38a8e8',
               'unique':'#c838e8','siege':'#888888','support':'#38e888'}
AGE_KEYS    = [('Feudal Age','封建'),('Castle Age','城堡'),('Imperial Age','帝王')]


def ms_to_str(ms):
    if not ms: return 'N/A'
    s = ms // 1000; m, s = divmod(s, 60); h, m = divmod(m, 60)
    return f'{h}h{m:02d}m{s:02d}s' if h else f'{m}m{s:02d}s'

def ms_to_min(ms): return round(ms / 60000, 2) if ms else 0

def nearest_sample(samples, t):
    if not samples: return {}
    return min(samples, key=lambda s: abs(s['time_ms'] - t))

def load_unit_map(base_path):
    for p in [base_path.parent / 'data' / 'units.json', Path('data/units.json')]:
        if p.exists():
            raw = json.loads(p.read_text(encoding='utf-8'))
            return {u['id']: u for u in raw.get('units', [])}
    return {}

def classify_age(time_ms, slot_age_times):
    imp = slot_age_times.get('Imperial Age')
    cas = slot_age_times.get('Castle Age')
    feu = slot_age_times.get('Feudal Age')
    if imp and time_ms >= imp: return '帝王'
    if cas and time_ms >= cas: return '城堡'
    if feu and time_ms >= feu: return '封建'
    return '黑暗'


def _detect_strategy(civ, by_class, by_age, top_units, total_mil):
    if total_mil == 0:
        return "未出兵", "全場無軍事單位"
    cav = by_class.get('cavalry',  0) / total_mil
    inf = by_class.get('infantry', 0) / total_mil
    arc = by_class.get('archer',   0) / total_mil
    unq = by_class.get('unique',   0) / total_mil
    imp_r = by_age.get('帝王', 0) / total_mil
    cas_r = by_age.get('城堡', 0) / total_mil
    if imp_r > 0.85:  pace = '全帝王爆兵'
    elif imp_r > 0.6: pace = '帝王期主力'
    elif cas_r > 0.5: pace = '城堡期發展'
    else:              pace = '混合推進'

    if civ == '高棉人':
        be = top_units.get('弩弓象 [高]', 0); sc = top_units.get('斥候騎兵', 0)
        if be > 20:
            return '弩弓象+斥候暴兵', f'{pace}，弩弓象({be})核心輸出，斥候({sc})機動輔助'
    if civ == '哥德人' and by_class.get('infantry', 0) > 200:
        return '哥德步兵人海', '帝王廉價步兵大海，民兵/長矛/家衛以數量壓制'
    if civ == '法蘭克人':
        kn = top_units.get('騎士', 0)
        if kn > 50: return '法蘭克騎士流', f'{pace}，{kn} 騎士為主力衝擊'
    if civ == '孟加拉人':
        ratha = top_units.get('戰車 [孟]', 0)
        if ratha > 30: return '孟加拉戰車流', f'戰車({ratha})城堡期機動高傷'
    if civ == '波斯人':
        arc_t = top_units.get('弓箭手', 0)
        if arc_t > 100: return '波斯帝王弓箭海', f'帝王 {arc_t} 弓箭手傾倒，騎士鋪路'
    if civ == '波希米亞人':
        sp = top_units.get('長矛兵', 0); hw = top_units.get('胡斯車 [波]', 0)
        if sp > 100: return '波希米亞長矛+砲車', f'長矛({sp})主體，胡斯車({hw})特色，臼炮收尾'
    if civ == '拜占庭人' and total_mil < 5:
        return '斷線無策略', '遊戲早期斷線'

    known = {k: v for k, v in by_class.items() if k in CLASS_TW}
    dom = max(known.items(), key=lambda x: x[1])[0] if known else (
          max(by_class.items(), key=lambda x: x[1])[0] if by_class else 'cavalry')
    dom_tw = CLASS_TW.get(dom, '特殊')
    if imp_r > 0.85: return f'全帝王{dom_tw}暴兵', f'軍事全投帝王，{dom_tw}為主'
    if cav > 0.6: return '騎兵流', f'騎兵佔 {cav:.0%}，{pace}'
    if inf > 0.6: return '步兵流', f'步兵佔 {inf:.0%}，{pace}'
    if arc > 0.6: return '弓箭流', f'弓箭佔 {arc:.0%}，{pace}'
    if unq > 0.35: return '特殊兵流', f'特殊兵佔 {unq:.0%}，{pace}'
    return '混合策略', f'多兵種混合，{pace}'


def _compute_strategy_mvp(hdr, deep, unit_map, sorted_slots):
    """Compute per-player strategy and MVP scores. Returns dict added to DATA."""
    duration_ms  = hdr.get('duration_ms', 1)
    duration_min = duration_ms / 60000
    players      = {p['slot']: p for p in hdr.get('players', [])}
    teams        = hdr.get('teams', {})
    winner_team  = str(hdr.get('winner_team', ''))
    el_slots     = {e['slot'] for e in hdr.get('early_leaves', [])}
    tevents      = deep.get('training_events', [])
    apc          = deep.get('actions_per_player', {})
    samples      = deep.get('samples', [])

    slot_ages = {}
    for a in hdr.get('age_ups', []):
        s = a.get('slot')
        if s: slot_ages.setdefault(s, {})[a['age']] = a['time_ms']

    # ── Per-player strategy ───────────────────────────────────────────────
    strategies = {}
    for slot in sorted_slots:
        p   = players.get(slot, {})
        civ = p.get('civilization_tw', '')
        if slot in el_slots:
            strategies[str(slot)] = {'name': '斷線', 'desc': '遊戲早期斷線',
                                      'pace': '—', 'total_mil': 0,
                                      'top3': [], 'class_pct': {}, 'imp_pct': 0}
            continue

        sages     = slot_ages.get(slot, {})
        by_class  = defaultdict(int)
        by_age_l  = defaultdict(int)
        top_units = defaultdict(int)
        for ev in tevents:
            if ev.get('slot') != slot: continue
            uid = ev['unit_id']; amt = ev.get('amount', 1)
            u   = unit_map.get(uid, {}); cls = u.get('class', 'unknown')
            age = classify_age(ev['time_ms'], sages)
            if cls != 'econ':
                by_class[cls] += amt
                by_age_l[age] += amt
                top_units[u.get('tw') or u.get('en') or f'ID:{uid}'] += amt

        total_mil    = sum(by_class.values())
        name, desc   = _detect_strategy(civ, dict(by_class), dict(by_age_l),
                                         dict(top_units), total_mil)
        top3         = sorted(top_units.items(), key=lambda x: -x[1])[:3]
        class_pct    = {CLASS_TW.get(k, k): round(v/total_mil*100) if total_mil else 0
                        for k, v in by_class.items()}
        imp_pct      = round(by_age_l.get('帝王', 0) / total_mil * 100) if total_mil else 0

        # Determine pace string
        imp_r = by_age_l.get('帝王', 0) / total_mil if total_mil else 0
        cas_r = by_age_l.get('城堡', 0) / total_mil if total_mil else 0
        if imp_r > 0.85:  pace = '全帝王爆兵'
        elif imp_r > 0.6: pace = '帝王期主力'
        elif cas_r > 0.5: pace = '城堡期發展'
        else:              pace = '混合推進'

        strategies[str(slot)] = {
            'name': name, 'desc': desc, 'pace': pace,
            'top3': [[n, c] for n, c in top3],
            'total_mil': total_mil, 'class_pct': class_pct, 'imp_pct': imp_pct,
        }

    # ── MVP scoring ───────────────────────────────────────────────────────
    def raw_score(slot):
        if slot in el_slots: return 0.0
        mil_t = sum(ev.get('amount',1) for ev in tevents
                    if ev.get('slot')==slot and
                       unit_map.get(ev['unit_id'],{}).get('class')!='econ')
        acts  = sum(apc.get(str(slot), {}).values())
        f_res = samples[-1].get('players',{}).get(str(slot),{}).get('total_res',0) if samples else 0
        f_obj = samples[-1].get('players',{}).get(str(slot),{}).get('obj_count',0)  if samples else 0
        return (mil_t/duration_min*0.40 + acts/duration_min*0.30 +
                max(0,1-f_res/20000)*10*0.20 + f_obj/500*10*0.10)

    mvp = {}
    for tid, slots in teams.items():
        scores = {s: raw_score(s) for s in slots}
        max_s  = max(scores.values(), default=1) or 1
        normed = {s: round(scores[s]/max_s*100) for s in scores}
        best   = max(scores, key=lambda s: scores[s])
        p_best = players.get(best, {})

        # breakdown for MVP (normalized within team)
        def breakdown(slot):
            if slot in el_slots: return {'mil':0,'apm':0,'res':0,'obj':0}
            mil_t = sum(ev.get('amount',1) for ev in tevents if ev.get('slot')==slot
                        and unit_map.get(ev['unit_id'],{}).get('class')!='econ')
            acts  = sum(apc.get(str(slot),{}).values())
            f_res = samples[-1].get('players',{}).get(str(slot),{}).get('total_res',0) if samples else 0
            f_obj = samples[-1].get('players',{}).get(str(slot),{}).get('obj_count',0)  if samples else 0
            alive = [s for s in slots if s not in el_slots]
            def norm(v, vals): return round(v/max(max(vals),1)*100)
            return {
                'mil': norm(mil_t, [sum(ev.get('amount',1) for ev in tevents if ev.get('slot')==s
                                        and unit_map.get(ev['unit_id'],{}).get('class')!='econ')
                                     for s in alive]),
                'apm': norm(acts,  [sum(apc.get(str(s),{}).values()) for s in alive]),
                'res': norm(max(0,20000-f_res), [max(0,20000-
                            (samples[-1].get('players',{}).get(str(s),{}).get('total_res',0) if samples else 0))
                            for s in alive]),
                'obj': norm(f_obj, [samples[-1].get('players',{}).get(str(s),{}).get('obj_count',0)
                                    if samples else 0 for s in alive]),
            }

        # reasons
        mil_vals = {s: sum(ev.get('amount',1) for ev in tevents if ev.get('slot')==s
                           and unit_map.get(ev['unit_id'],{}).get('class')!='econ')
                    for s in slots if s not in el_slots}
        apm_vals = {s: sum(apc.get(str(s),{}).values())/duration_min for s in slots if s not in el_slots}
        f_res_best = samples[-1].get('players',{}).get(str(best),{}).get('total_res',0) if samples else 0

        reasons = []
        if mil_vals and mil_vals.get(best,0) == max(mil_vals.values()):
            reasons.append(f"全隊最高軍事輸出 ({mil_vals.get(best,0)} 單位)")
        if apm_vals and apm_vals.get(best,0) == max(apm_vals.values()):
            reasons.append(f"全隊操作最積極 (APM {apm_vals.get(best,0):.0f})")
        if f_res_best < 3000:
            reasons.append(f"資源利用高效（終局僅餘 {f_res_best:,}）")
        elif mil_vals.get(best,0) > 200:
            reasons.append(f"軍事輸出彌補資源殘留（{mil_vals.get(best,0)} 單位）")
        if not reasons:
            reasons.append("全隊綜合表現最佳")

        mvp[str(tid)] = {
            'slot':      best,
            'name':      p_best.get('name', '?'),
            'civ':       p_best.get('civilization_tw', '?'),
            'color':     PLAYER_COLORS.get(best, '#888'),
            'strategy':  strategies.get(str(best), {}).get('name', '?'),
            'score':     normed[best],
            'reasons':   reasons,
            'breakdown': breakdown(best),
            'ranking':   sorted([[s, normed[s]] for s in slots], key=lambda x: -x[1]),
        }

    # ── Key moments ───────────────────────────────────────────────────────
    key_moments = []
    for e in hdr.get('early_leaves', []):
        pp = players.get(e['slot'], {})
        key_moments.append({'time_str': e['time_str'], 'type': 'danger',
            'text': f"P{e['slot']} {pp.get('name','?')} 斷線 → 以 3v4 完賽"})

    # First to each age
    age_firsts = {}
    for a in hdr.get('age_ups', []):
        k = a['age']
        if k not in age_firsts or a['time_ms'] < age_firsts[k]['time_ms']:
            age_firsts[k] = a
    age_icons  = {'Feudal Age': '⚡', 'Castle Age': '🏰', 'Imperial Age': '👑'}
    age_tw_map = {'Feudal Age': '封建', 'Castle Age': '城堡', 'Imperial Age': '帝王'}
    for age_key, a in sorted(age_firsts.items(), key=lambda x: x[1]['time_ms']):
        pp = players.get(a['slot'], {})
        key_moments.append({'time_str': ms_to_str(a['time_ms']), 'type': 'info',
            'text': f"{age_icons.get(age_key,'⚡')} 全場首個{age_tw_map.get(age_key,'')}:"
                    f" P{a['slot']} {pp.get('name','?')} ({pp.get('civilization_tw','?')})"})

    # When did winning team first overtake obj_count?
    w_slots = [s for tid, slots in teams.items()
               if str(tid) == winner_team for s in slots if s not in el_slots]
    l_slots  = [s for tid, slots in teams.items()
               if str(tid) != winner_team for s in slots]
    for s in samples:
        pdata = s.get('players', {})
        w_obj = sum(pdata.get(str(sl), {}).get('obj_count', 0) for sl in w_slots)
        l_obj = sum(pdata.get(str(sl), {}).get('obj_count', 0) for sl in l_slots)
        if w_obj > l_obj and s.get('time_ms', 0) >= 300_000:
            key_moments.append({'time_str': s['time_str'], 'type': 'win',
                'text': f"🔄 Team {winner_team} obj_count 首次超越 → 軍事規模轉折點"})
            break

    # Sort by time
    def time_order(km):
        t = km['time_str']
        if t in ('—', 'N/A'): return 9999
        try:
            parts = t.replace('h','m').replace('s','').split('m')
            if len(parts) == 3: return int(parts[0])*60 + int(parts[1])
            return int(parts[0])
        except Exception: return 9999
    key_moments.sort(key=time_order)

    # ── Strategic insights (text bullets) ────────────────────────────────
    insights = []
    for tid, slots in teams.items():
        alive = [s for s in slots if s not in el_slots]
        if not alive: continue
        mil_ct = {s: sum(ev.get('amount',1) for ev in tevents if ev.get('slot')==s
                         and unit_map.get(ev['unit_id'],{}).get('class')!='econ')
                  for s in alive}
        top_s = max(mil_ct, key=lambda s: mil_ct[s]) if mil_ct else None
        if top_s:
            pp  = players.get(top_s, {})
            st  = strategies.get(str(top_s), {})
            pct = round(mil_ct[top_s] / max(sum(mil_ct.values()), 1) * 100)
            insights.append(
                f"Team {tid} 軍事主力：P{top_s} {pp.get('name','?')} 採用「{st.get('name','?')}」，"
                f"貢獻 {pct}% 軍事輸出（{mil_ct[top_s]} 單位）"
            )

    # DC impact insight
    if hdr.get('early_leaves'):
        e   = hdr['early_leaves'][0]
        pp  = players.get(e['slot'], {})
        dc_team = pp.get('team_id', '?')
        # Who compensated?
        dc_teammates = [s for s in teams.get(str(dc_team), []) if s not in el_slots]
        if dc_teammates:
            top_comp = max(dc_teammates,
                           key=lambda s: sum(ev.get('amount',1) for ev in tevents
                                             if ev.get('slot')==s and
                                             unit_map.get(ev['unit_id'],{}).get('class')!='econ'))
            pp_comp = players.get(top_comp, {})
            st_comp = strategies.get(str(top_comp), {})
            mil_comp = sum(ev.get('amount',1) for ev in tevents if ev.get('slot')==top_comp
                           and unit_map.get(ev['unit_id'],{}).get('class')!='econ')
            insights.append(
                f"P{e['slot']} 斷線後，P{top_comp} {pp_comp.get('name','?')} 的"
                f"「{st_comp.get('name','?')}」（{mil_comp} 單位）有效填補兵力缺口"
            )

    # Military volume vs outcome
    team_mil = {str(tid): sum(ev.get('amount',1) for ev in tevents if ev.get('slot') in slots
                               and unit_map.get(ev['unit_id'],{}).get('class')!='econ')
                for tid, slots in teams.items()}
    if len(team_mil) == 2:
        higher = max(team_mil, key=lambda t: team_mil[t])
        if higher != winner_team:
            insights.append(
                f"Team {higher} 軍事總量({team_mil[higher]}) > Team {winner_team}({team_mil[winner_team]})，"
                f"但最終敗北 → 兵種組成與時機比純數量更關鍵"
            )

    return {
        'strategies':   strategies,
        'mvp':          mvp,
        'key_moments':  key_moments,
        'insights':     insights,
    }


def prepare_data(hdr, deep, unit_map):
    duration_ms = hdr.get('duration_ms', 0)
    players     = {p['slot']: p for p in hdr.get('players', [])}
    teams       = hdr.get('teams', {})
    winner_team = str(hdr.get('winner_team', ''))
    samples     = deep.get('samples', [])
    tevents     = deep.get('training_events', [])
    el          = hdr.get('early_leaves', [])
    el_slots    = {e['slot'] for e in el}

    slot_ages = {}
    for a in hdr.get('age_ups', []):
        s = a.get('slot')
        if s: slot_ages.setdefault(s, {})[a['age']] = a['time_ms']

    sorted_slots = []
    for tid in sorted(teams.keys()):
        for s in sorted(teams[tid]):
            sorted_slots.append(s)

    # ── Gantt ──────────────────────────────────────────────────────────────
    gantt = {'labels': [], 'datasets': {a: [] for a in AGE_ORDER},
             'duration_min': ms_to_min(duration_ms)}
    for slot in sorted_slots:
        p    = players.get(slot, {})
        ages = slot_ages.get(slot, {})
        gantt['labels'].append(f"P{slot} {p.get('name','?')[:10]}")
        feu = ages.get('Feudal Age',  duration_ms)
        cas = ages.get('Castle Age',  duration_ms)
        imp = ages.get('Imperial Age',duration_ms)
        gantt['datasets']['黑暗'].append(ms_to_min(feu))
        gantt['datasets']['封建'].append(ms_to_min(cas - feu) if 'Feudal Age'   in ages else 0)
        gantt['datasets']['城堡'].append(ms_to_min(imp - cas) if 'Castle Age'   in ages else 0)
        gantt['datasets']['帝王'].append(ms_to_min(duration_ms - imp) if 'Imperial Age' in ages else 0)

    # ── Economy ────────────────────────────────────────────────────────────
    econ_s = samples[::2]
    econ = {
        'times': [ms_to_min(s['time_ms']) for s in econ_s],
        'per_player': {},
        'per_team_res': {},
        'per_team_obj': {},
    }
    for slot in sorted_slots:
        econ['per_player'][str(slot)] = {
            'res': [s.get('players',{}).get(str(slot),{}).get('total_res',0) for s in econ_s],
            'obj': [s.get('players',{}).get(str(slot),{}).get('obj_count',0) for s in econ_s],
        }
    for tid, slots in teams.items():
        alive = [s for s in slots if s not in el_slots]
        econ['per_team_res'][str(tid)] = [
            sum(s.get('players',{}).get(str(sl),{}).get('total_res',0) for sl in alive)
            for s in econ_s]
        econ['per_team_obj'][str(tid)] = [
            sum(s.get('players',{}).get(str(sl),{}).get('obj_count',0) for sl in alive)
            for s in econ_s]

    # ── Units ──────────────────────────────────────────────────────────────
    unit_by_class = {}
    unit_detail   = {}
    for slot in sorted_slots:
        sages       = slot_ages.get(slot, {})
        by_class    = defaultdict(int)
        by_uid_age  = defaultdict(lambda: defaultdict(int))
        for ev in tevents:
            if ev.get('slot') != slot: continue
            uid = ev['unit_id']; amt = ev.get('amount', 1)
            u   = unit_map.get(uid, {}); cls = u.get('class', 'unknown')
            age = classify_age(ev['time_ms'], sages)
            if cls != 'econ': by_class[cls] += amt
            by_uid_age[uid][age] += amt

        unit_by_class[str(slot)] = {CLASS_TW.get(k, k): v for k, v in by_class.items()}
        detail = []
        for uid, age_data in sorted(by_uid_age.items(), key=lambda x: -sum(x[1].values())):
            u = unit_map.get(uid, {})
            if u.get('class') == 'econ': continue
            detail.append({
                'name':   u.get('tw') or u.get('en') or f'ID:{uid}',
                'total':  sum(age_data.values()),
                'by_age': {age: age_data.get(age, 0) for age in AGE_ORDER},
            })
        unit_detail[str(slot)] = detail

    # ── Checkpoints ────────────────────────────────────────────────────────
    cps = [('10min',10*60000),('20min',20*60000),('30min',30*60000),('40min',40*60000)]
    cp_data = []
    for label, cp_ms in cps:
        snap = nearest_sample(samples, cp_ms); pdata = snap.get('players', {})
        entry = {'label': label}
        for tid, slots in teams.items():
            alive = [s for s in slots if s not in el_slots]
            entry[str(tid)] = {
                'res': sum(pdata.get(str(s),{}).get('total_res',0) for s in alive),
                'obj': sum(pdata.get(str(s),{}).get('obj_count',0) for s in alive),
            }
        cp_data.append(entry)

    # ── Snapshots ──────────────────────────────────────────────────────────
    snapshots = []
    for slot in sorted_slots:
        p = players.get(slot, {}); ages = slot_ages.get(slot, {})
        ages_list = []
        for age_key, age_tw in AGE_KEYS:
            t = ages.get(age_key)
            if t:
                s = nearest_sample(samples, t)
                ps = s.get('players',{}).get(str(slot),{})
                mil = sum(ev.get('amount',1) for ev in tevents
                          if ev.get('slot')==slot and ev['time_ms']<=t
                          and unit_map.get(ev['unit_id'],{}).get('class')!='econ')
                ages_list.append({'age':age_tw,'time_str':ms_to_str(t),
                                  'time_min':ms_to_min(t),
                                  'res':ps.get('total_res',0),
                                  'obj':ps.get('obj_count',0),'mil':mil})
            else:
                ages_list.append({'age':age_tw,'time_str':'—','res':0,'obj':0,'mil':0})
        snapshots.append({'slot':slot,'name':p.get('name','?'),
                          'civ':p.get('civilization_tw','?'),
                          'team':p.get('team_id',0),'ages':ages_list})

    # ── Key factors ────────────────────────────────────────────────────────
    key_factors = []
    for e in el:
        p = players.get(e['slot'], {})
        key_factors.append({'icon':'❗','type':'danger',
            'text':f"P{e['slot']} {p.get('name','?')} 於 {e['time_str']} 斷線，其隊以 3v4 完賽"})

    for age_key, age_tw in AGE_KEYS:
        avgs = {}
        for tid, slots in teams.items():
            ts = [slot_ages[s][age_key] for s in slots if s in slot_ages and age_key in slot_ages[s]]
            if ts: avgs[str(tid)] = int(sum(ts)/len(ts))
        if len(avgs) == 2:
            diff = abs(list(avgs.values())[0] - list(avgs.values())[1])
            faster = min(avgs, key=lambda t: avgs[t])
            if diff > 60_000:
                is_w = faster == winner_team
                key_factors.append({'icon':'🏆' if is_w else '↯','type':'win' if is_w else 'neutral',
                    'text':f"{age_tw}升代: Team {faster} 平均快 {ms_to_str(diff)}" +
                           ('（與勝利一致）' if is_w else '（但最終敗北）')})

    mil_totals = {str(tid): sum(ev.get('amount',1) for ev in tevents
                                if ev.get('slot') in slots
                                and unit_map.get(ev['unit_id'],{}).get('class')!='econ')
                  for tid, slots in teams.items()}
    if len(mil_totals) == 2:
        higher = max(mil_totals, key=lambda t: mil_totals[t])
        is_w   = higher == winner_team
        key_factors.append({'icon':'⚔️','type':'win' if is_w else 'neutral',
            'text':f"軍事總量: Team {higher} 更多 ({mil_totals[higher]}) " +
                   ('且勝利' if is_w else '但敗北 → 純兵量非決定因素')})

    last_snap = samples[-1].get('players',{}) if samples else {}
    for slot in sorted_slots:
        tr = last_snap.get(str(slot),{}).get('total_res',0)
        if tr > 8000:
            p = players.get(slot,{})
            key_factors.append({'icon':'⚠️','type':'warning',
                'text':f"P{slot} {p.get('name','?')} 終局殘餘資源 {tr:,} → 資源轉化效率待提升"})

    # ── APM ────────────────────────────────────────────────────────────────
    apc = deep.get('actions_per_player', {})
    dur_min = duration_ms / 60000 if duration_ms else 1
    apm_data = {str(slot): {
        'total': sum(apc.get(str(slot),{}).values()),
        'apm':   round(sum(apc.get(str(slot),{}).values()) / dur_min, 1)
    } for slot in sorted_slots}

    strat_mvp = _compute_strategy_mvp(hdr, deep, unit_map, sorted_slots)

    return {
        'game': {'map': hdr.get('map_name','?'), 'duration_str': hdr.get('duration_str','?'),
                 'duration_min': ms_to_min(duration_ms), 'version': hdr.get('game_version','?'),
                 'winner_team': winner_team},
        'players': {str(p['slot']): {
            'slot': p['slot'], 'name': p['name'],
            'civ':  p.get('civilization_tw','?'), 'team': p.get('team_id',0),
            'color': PLAYER_COLORS.get(p['slot'],'#888'),
        } for p in hdr.get('players', [])},
        'teams':        {str(k): v for k, v in teams.items()},
        'sorted_slots': sorted_slots,
        'winner_team':  winner_team,
        'early_leaves': [{'slot': e['slot'], 'time_str': e['time_str']} for e in el],
        'gantt':         gantt,
        'econ':          econ,
        'unit_by_class': unit_by_class,
        'unit_detail':   unit_detail,
        'cp_data':       cp_data,
        'snapshots':     snapshots,
        'key_factors':   key_factors,
        'apm':           apm_data,
        **strat_mvp,
    }


# ── HTML template (no f-string — use .replace() for placeholders) ──────────
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AOE2 DE 分析報告</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{--bg:#1a1a2e;--card:#16213e;--border:#0f3460;--gold:#c8a45e;--text:#e8e8e8;--muted:#888;--win:#4caf50;--lose:#ef5350;--warn:#ff9800;--info:#42a5f5;}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',Arial,sans-serif;font-size:14px;}
.header{background:linear-gradient(135deg,#0f3460,#1a1a2e);padding:18px 24px;border-bottom:2px solid var(--gold);}
.header h1{font-size:20px;color:var(--gold);margin-bottom:5px;}
.header .meta{color:var(--muted);font-size:13px;}
.winner-badge{display:inline-block;background:var(--win);color:#fff;padding:1px 10px;border-radius:12px;font-size:12px;margin-left:8px;}
.tabs{display:flex;background:var(--card);border-bottom:1px solid var(--border);padding:0 16px;overflow-x:auto;}
.tab{padding:11px 16px;cursor:pointer;color:var(--muted);font-size:13px;border-bottom:3px solid transparent;transition:all .2s;white-space:nowrap;user-select:none;}
.tab:hover{color:var(--text);}
.tab.active{color:var(--gold);border-bottom-color:var(--gold);}
.content{padding:18px;max-width:1200px;margin:0 auto;}
.section{display:none;}.section.active{display:block;}
.card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:16px;}
.card h3{color:var(--gold);font-size:13px;margin-bottom:12px;padding-bottom:6px;border-bottom:1px solid var(--border);}
.teams-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;}
.team-card{background:var(--card);border-radius:8px;padding:16px;}
.team-card.winner{border-left:4px solid var(--win);}
.team-card.loser{border-left:4px solid var(--lose);}
.team-title{font-size:15px;font-weight:bold;margin-bottom:12px;}
.badge{font-size:11px;padding:1px 8px;border-radius:10px;margin-left:6px;}
.win-badge{background:var(--win);color:#fff;}
.lose-badge{background:var(--lose);color:#fff;}
.player-row{display:flex;align-items:center;gap:8px;padding:7px 0;border-bottom:1px solid rgba(255,255,255,.05);}
.player-row:last-child{border-bottom:none;}
.player-dot{width:12px;height:12px;border-radius:50%;flex-shrink:0;}
.player-name{font-weight:500;flex:1;}
.player-civ{color:var(--muted);font-size:12px;}
.player-slot{color:var(--muted);font-size:11px;width:22px;}
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:16px;}
.stat-box{background:var(--card);border:1px solid var(--border);border-radius:6px;padding:12px;text-align:center;}
.stat-box .val{font-size:20px;font-weight:bold;color:var(--gold);}
.stat-box .lbl{font-size:11px;color:var(--muted);margin-top:3px;}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:16px;}
.chart-wrap canvas{max-height:340px;}
.chart-tall canvas{max-height:440px;}
.player-btns{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px;}
.player-btn{padding:3px 11px;border:2px solid;border-radius:12px;cursor:pointer;font-size:12px;background:transparent;color:var(--text);transition:all .2s;}
.player-btn:hover{opacity:.8;}
.snap-table{width:100%;border-collapse:collapse;font-size:12px;}
.snap-table th{background:rgba(200,164,94,.15);color:var(--gold);padding:7px 8px;text-align:center;border-bottom:1px solid var(--border);white-space:nowrap;}
.snap-table td{padding:6px 8px;border-bottom:1px solid rgba(255,255,255,.04);text-align:center;}
.snap-table td.left{text-align:left;}
.snap-table tr:hover td{background:rgba(255,255,255,.03);}
.factor-list{display:flex;flex-direction:column;gap:8px;}
.factor-item{display:flex;gap:10px;align-items:flex-start;padding:10px 14px;border-radius:6px;}
.factor-item.win{background:rgba(76,175,80,.12);border-left:3px solid var(--win);}
.factor-item.lose{background:rgba(239,83,80,.12);border-left:3px solid var(--lose);}
.factor-item.danger{background:rgba(239,83,80,.15);border-left:3px solid #f44336;}
.factor-item.warning{background:rgba(255,152,0,.12);border-left:3px solid var(--warn);}
.factor-item.neutral{background:rgba(66,165,245,.1);border-left:3px solid var(--info);}
.factor-icon{font-size:17px;flex-shrink:0;}
.factor-text{line-height:1.6;}
@media(max-width:700px){.teams-grid,.two-col{grid-template-columns:1fr;}}

/* MVP cards */
.mvp-card{background:var(--card);border-radius:10px;padding:18px;position:relative;overflow:hidden;}
.mvp-card.winner-mvp{border:2px solid var(--win);}
.mvp-card.loser-mvp{border:2px solid #5a7ab8;}
.mvp-crown{font-size:28px;margin-bottom:4px;}
.mvp-title{font-size:11px;color:var(--muted);letter-spacing:.08em;text-transform:uppercase;margin-bottom:8px;}
.mvp-name{font-size:18px;font-weight:bold;margin-bottom:2px;}
.mvp-sub{font-size:12px;color:var(--muted);margin-bottom:10px;}
.mvp-strategy{display:inline-block;background:rgba(200,164,94,.18);color:var(--gold);
  font-size:11px;padding:2px 10px;border-radius:10px;margin-bottom:10px;}
.mvp-score-bar{margin:4px 0;}
.mvp-score-bar .lbl{font-size:11px;color:var(--muted);width:60px;display:inline-block;}
.mvp-score-bar .bar-outer{display:inline-block;width:120px;height:7px;
  background:rgba(255,255,255,.08);border-radius:4px;vertical-align:middle;margin:0 6px;}
.mvp-score-bar .bar-inner{height:100%;border-radius:4px;transition:width .6s;}
.mvp-score-bar .val{font-size:11px;color:var(--text);}
.mvp-reasons{margin-top:10px;font-size:12px;color:#bbb;line-height:1.7;}
.mvp-reasons span{display:block;}
.mvp-ranking{margin-top:10px;}
.mvp-rank-row{display:flex;align-items:center;gap:6px;padding:3px 0;font-size:12px;}
.mvp-rank-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0;}
.mvp-rank-bar{flex:1;height:5px;background:rgba(255,255,255,.06);border-radius:3px;overflow:hidden;}
.mvp-rank-fill{height:100%;border-radius:3px;}
.mvp-rank-val{width:36px;text-align:right;color:var(--muted);font-size:11px;}
.mvp-rank-name{width:80px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;}

/* Strategy cards */
.strat-card{background:#0f2040;border:1px solid var(--border);border-radius:8px;padding:14px;}
.strat-card .s-header{display:flex;align-items:center;gap:8px;margin-bottom:8px;}
.strat-card .s-dot{width:12px;height:12px;border-radius:50%;flex-shrink:0;}
.strat-card .s-name-line{font-size:13px;font-weight:600;}
.strat-card .s-civ{font-size:11px;color:var(--muted);}
.strat-badge{display:inline-block;background:rgba(200,164,94,.15);color:var(--gold);
  font-size:11px;padding:2px 9px;border-radius:8px;margin:4px 0 6px;}
.strat-desc{font-size:12px;color:#aaa;line-height:1.5;margin-bottom:8px;}
.strat-units{font-size:11px;color:#888;}
.strat-units span{color:#bbb;}
.strat-mil{font-size:11px;color:var(--muted);margin-top:4px;}
.strat-imp-bar{margin-top:6px;}
.strat-imp-bar .age-seg{display:inline-block;height:6px;border-radius:2px;}

/* Key moments */
.moment-item{display:flex;gap:10px;align-items:flex-start;padding:8px 10px;
  border-radius:6px;margin-bottom:6px;font-size:13px;}
.moment-item.win{background:rgba(76,175,80,.1);border-left:3px solid var(--win);}
.moment-item.danger{background:rgba(239,83,80,.1);border-left:3px solid var(--lose);}
.moment-item.info{background:rgba(66,165,245,.08);border-left:3px solid var(--info);}
.moment-time{color:var(--gold);font-weight:bold;white-space:nowrap;min-width:58px;}

/* Insight bullets */
.insight-item{padding:8px 12px;border-left:3px solid var(--gold);
  margin-bottom:8px;background:rgba(200,164,94,.06);border-radius:0 6px 6px 0;
  font-size:13px;line-height:1.6;color:#ccc;}
</style>
</head>
<body>
<div class="header">
  <h1>⚔️ AOE2 DE 分析報告 — <span id="map-title"></span></h1>
  <div class="meta" id="game-meta"></div>
</div>
<div class="tabs">
  <div class="tab active" data-tab="overview">📊 概覽</div>
  <div class="tab" data-tab="ageup">⏱ 升代時序</div>
  <div class="tab" data-tab="economy">📈 經濟走勢</div>
  <div class="tab" data-tab="units">⚔️ 兵種組成</div>
  <div class="tab" data-tab="snapshot">📸 時序快照</div>
  <div class="tab" data-tab="verdict">🏆 勝負分析</div>
  <div class="tab" data-tab="strategy">🎯 策略&MVP</div>
</div>
<div class="content">
  <div id="tab-overview" class="section active">
    <div class="stats-grid" id="overview-stats"></div>
    <div class="teams-grid" id="teams-grid"></div>
  </div>
  <div id="tab-ageup" class="section">
    <div class="card chart-tall">
      <h3>升代時序甘特圖 — 各時代持續時間（分鐘）</h3>
      <div class="chart-wrap"><canvas id="chart-gantt"></canvas></div>
    </div>
  </div>
  <div id="tab-economy" class="section">
    <div class="card">
      <h3>隊伍累積資源對比 (total_res 合計)</h3>
      <div class="chart-wrap"><canvas id="chart-team-res"></canvas></div>
    </div>
    <div class="two-col">
      <div class="card">
        <h3>個人資源走勢 (total_res)</h3>
        <div class="chart-wrap"><canvas id="chart-player-res"></canvas></div>
      </div>
      <div class="card">
        <h3>個人物件數走勢 (obj_count)</h3>
        <div class="chart-wrap"><canvas id="chart-player-obj"></canvas></div>
      </div>
    </div>
  </div>
  <div id="tab-units" class="section">
    <div class="card">
      <h3>各玩家兵種類型分布（全場，不含村民）</h3>
      <div class="chart-wrap"><canvas id="chart-unit-class"></canvas></div>
    </div>
    <div class="card">
      <h3>個人兵種 × 時代詳情</h3>
      <div class="player-btns" id="unit-player-btns"></div>
      <div class="chart-wrap"><canvas id="chart-unit-detail"></canvas></div>
    </div>
  </div>
  <div id="tab-snapshot" class="section">
    <div class="card">
      <h3>升代瞬間狀態快照</h3>
      <div style="overflow-x:auto"><table class="snap-table" id="snap-table"></table></div>
    </div>
    <div class="card">
      <h3>升代時刻 obj_count 對比</h3>
      <div class="chart-wrap"><canvas id="chart-snap-obj"></canvas></div>
    </div>
  </div>
  <div id="tab-strategy" class="section">
    <div id="mvp-cards" class="two-col"></div>
    <div class="card" id="insights-card">
      <h3>💡 關鍵戰略要點</h3>
      <div id="insights-list"></div>
    </div>
    <div class="card">
      <h3>⏰ 關鍵時刻軸</h3>
      <div id="moments-list"></div>
    </div>
    <div class="card">
      <h3>📋 玩家策略卡</h3>
      <div id="strategy-grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;margin-top:4px"></div>
    </div>
  </div>
  <div id="tab-verdict" class="section">
    <div class="two-col">
      <div class="card">
        <h3>各時段隊伍資源對比</h3>
        <div class="chart-wrap"><canvas id="chart-cp-res"></canvas></div>
      </div>
      <div class="card">
        <h3>各時段隊伍物件數對比</h3>
        <div class="chart-wrap"><canvas id="chart-cp-obj"></canvas></div>
      </div>
    </div>
    <div class="card">
      <h3>APM 操作強度對比</h3>
      <div class="chart-wrap"><canvas id="chart-apm"></canvas></div>
    </div>
    <div class="card">
      <h3>勝負關鍵推論</h3>
      <div class="factor-list" id="factor-list"></div>
    </div>
  </div>
</div>
<script>
const DATA = __DATA_JSON__;
const PC   = __PC_JSON__;
const AGE_ORDER  = ["黑暗","封建","城堡","帝王"];
const AGE_COLORS = {"黑暗":"#8B6914","封建":"#5C8A3C","城堡":"#3C5C8A","帝王":"#8A3C3C"};
const CLS_COLORS = {"騎兵":"#e8a838","步兵":"#e85838","弓箭":"#38a8e8","特殊":"#c838e8","攻城":"#888","輔助":"#38e888"};
const BUILT = {};

function pColor(s){ return PC[s]||"#888"; }
function hexRgba(hex,a){
  const r=parseInt(hex.slice(1,3),16),g=parseInt(hex.slice(3,5),16),b=parseInt(hex.slice(5,7),16);
  return `rgba(${r},${g},${b},${a})`;
}
function mkChart(id,type,data,extra){
  const el=document.getElementById(id); if(!el)return;
  if(el._ch)el._ch.destroy();
  const base={
    responsive:true,maintainAspectRatio:true,
    plugins:{
      legend:{labels:{color:"#ccc",font:{size:12}}},
      tooltip:{backgroundColor:"rgba(15,25,55,.95)",titleColor:"#c8a45e",bodyColor:"#ddd"}
    },
    scales:{
      x:{ticks:{color:"#999"},grid:{color:"rgba(255,255,255,.05)"}},
      y:{ticks:{color:"#999"},grid:{color:"rgba(255,255,255,.08)"}}
    }
  };
  function merge(t,s){for(const k in s){if(s[k]&&typeof s[k]==="object"&&!Array.isArray(s[k])){t[k]=t[k]||{};merge(t[k],s[k]);}else t[k]=s[k];}return t;}
  el._ch=new Chart(el,{type,data,options:merge(base,extra||{})});
  return el._ch;
}

// tabs
document.querySelectorAll(".tab").forEach(t=>{
  t.addEventListener("click",()=>{
    document.querySelectorAll(".tab").forEach(x=>x.classList.remove("active"));
    document.querySelectorAll(".section").forEach(x=>x.classList.remove("active"));
    t.classList.add("active");
    const id=t.dataset.tab;
    document.getElementById("tab-"+id).classList.add("active");
    if(!BUILT[id]){BUILT[id]=true;buildTab(id);}
  });
});

// Overview (built immediately)
(function(){
  const g=DATA.game;
  document.getElementById("map-title").textContent=g.map;
  document.getElementById("game-meta").innerHTML=
    `版本: ${g.version} &nbsp;|&nbsp; 時長: <strong>${g.duration_str}</strong> &nbsp;|&nbsp; 勝隊: <span class="winner-badge">Team ${g.winner_team}</span>`;
  document.getElementById("overview-stats").innerHTML=
    [{val:g.map,lbl:"地圖"},{val:g.duration_str,lbl:"時長"},
     {val:"Team "+g.winner_team+" ★",lbl:"勝利隊伍"},
     {val:Object.keys(DATA.players).length+"人",lbl:"玩家數"}]
    .map(s=>`<div class="stat-box"><div class="val">${s.val}</div><div class="lbl">${s.lbl}</div></div>`).join("");
  const grid=document.getElementById("teams-grid");
  Object.entries(DATA.teams).sort().forEach(([tid,slots])=>{
    const isW=tid===DATA.winner_team;
    const el=document.createElement("div");
    el.className="team-card "+(isW?"winner":"loser");
    el.innerHTML=`<div class="team-title">Team ${tid}<span class="badge ${isW?"win-badge":"lose-badge"}">${isW?"★ 勝利":"✗ 敗北"}</span></div>`+
      [...slots].sort((a,b)=>a-b).map(s=>{
        const p=DATA.players[s]||{};
        const dc=DATA.early_leaves.some(e=>e.slot===s);
        return `<div class="player-row">
          <div class="player-dot" style="background:${pColor(s)}"></div>
          <div class="player-slot">P${s}</div>
          <div class="player-name">${p.name||"?"}${dc?' <span style="color:#f44;font-size:11px">[DC]</span>':""}</div>
          <div class="player-civ">${p.civ||""}</div>
        </div>`;
      }).join("");
    grid.appendChild(el);
  });
})();

function buildTab(id){
  if(id==="ageup")     buildGantt();
  else if(id==="economy")   buildEconomy();
  else if(id==="units")     buildUnits();
  else if(id==="snapshot")  buildSnapshot();
  else if(id==="verdict")   buildVerdict();
  else if(id==="strategy")  buildStrategy();
}

// Gantt
function buildGantt(){
  const g=DATA.gantt;
  mkChart("chart-gantt","bar",{
    labels:g.labels,
    datasets:AGE_ORDER.map(age=>({
      label:age+"時代",data:g.datasets[age],
      backgroundColor:AGE_COLORS[age],borderWidth:1,borderColor:"rgba(0,0,0,.3)"
    }))
  },{
    indexAxis:"y",
    plugins:{tooltip:{callbacks:{label:c=>` ${c.dataset.label}: ${c.raw.toFixed(1)} min`}}},
    scales:{
      x:{stacked:true,title:{display:true,text:"分鐘",color:"#999"},ticks:{color:"#999"}},
      y:{stacked:true,ticks:{color:"#ddd",font:{size:12}}}
    }
  });
}

// Economy
function buildEconomy(){
  const e=DATA.econ;
  const tColors={};
  Object.keys(DATA.teams).forEach(tid=>{tColors[tid]=tid===DATA.winner_team?"#4caf50":"#ef5350";});
  mkChart("chart-team-res","line",{
    labels:e.times,
    datasets:Object.entries(e.per_team_res).map(([tid,vals])=>({
      label:"Team "+tid+(tid===DATA.winner_team?" ★":""),data:vals,
      borderColor:tColors[tid],backgroundColor:hexRgba(tColors[tid],.1),
      borderWidth:2.5,pointRadius:0,fill:true,tension:.3
    }))
  },{scales:{x:{title:{display:true,text:"分鐘",color:"#999"}}}});

  const mkLine=(canvasId,key)=>mkChart(canvasId,"line",{
    labels:e.times,
    datasets:DATA.sorted_slots.map(s=>({
      label:"P"+s+" "+(DATA.players[s]?.name||"").slice(0,15),
      data:e.per_player[s]?.[key]||[],
      borderColor:pColor(s),borderWidth:1.5,pointRadius:0,tension:.3,backgroundColor:"transparent"
    }))
  },{scales:{x:{title:{display:true,text:"分鐘",color:"#999"}}}});
  mkLine("chart-player-res","res");
  mkLine("chart-player-obj","obj");
}

// Units
function buildUnits(){
  const uc=DATA.unit_by_class;
  const allCls=["騎兵","步兵","弓箭","特殊","攻城","輔助"];
  const labels=DATA.sorted_slots.map(s=>"P"+s+" "+(DATA.players[s]?.name||"").slice(0,15));
  mkChart("chart-unit-class","bar",{
    labels,
    datasets:allCls.map(cls=>({
      label:cls,data:DATA.sorted_slots.map(s=>uc[s]?.[cls]||0),
      backgroundColor:CLS_COLORS[cls]||"#666"
    }))
  },{plugins:{tooltip:{mode:"index"}},scales:{x:{stacked:true},y:{stacked:true}}});

  const btns=document.getElementById("unit-player-btns");
  DATA.sorted_slots.forEach((s,i)=>{
    const p=DATA.players[s]||{};
    const btn=document.createElement("button");
    btn.className="player-btn"; btn.dataset.slot=s;
    btn.textContent="P"+s+" "+(p.name||"");
    btn.style.borderColor=pColor(s);
    btn.onclick=()=>showUnitDetail(s);
    btns.appendChild(btn);
  });
  showUnitDetail(DATA.sorted_slots[0]);
}
function showUnitDetail(slot){
  document.querySelectorAll(".player-btn").forEach(b=>{
    const s=parseInt(b.dataset.slot);
    b.classList.toggle("active",s===slot);
    b.style.background=s===slot?pColor(slot):"transparent";
    b.style.color=s===slot?"#fff":"var(--text)";
  });
  const detail=DATA.unit_detail[slot]||[];
  mkChart("chart-unit-detail","bar",{
    labels:detail.map(d=>d.name),
    datasets:AGE_ORDER.map(age=>({
      label:age+"時代",data:detail.map(d=>d.by_age[age]||0),
      backgroundColor:AGE_COLORS[age]
    }))
  },{
    plugins:{tooltip:{mode:"index",callbacks:{
      afterBody:items=>{const t=items.reduce((s,i)=>s+i.raw,0);return t?["合計: "+t]:[];}
    }}},
    scales:{x:{stacked:true},y:{stacked:true,title:{display:true,text:"訓練數量",color:"#999"}}}
  });
}

// Snapshot
function buildSnapshot(){
  const snaps=DATA.snapshots;
  const tbl=document.getElementById("snap-table");
  tbl.innerHTML=`<thead><tr>
    <th>玩家</th><th>文明</th>
    <th>封建時刻</th><th>資源</th><th>物件</th><th>軍事累計</th>
    <th>城堡時刻</th><th>資源</th><th>物件</th><th>軍事累計</th>
    <th>帝王時刻</th><th>資源</th><th>物件</th><th>軍事累計</th>
  </tr></thead>`;
  const tbody=document.createElement("tbody");
  snaps.forEach(snap=>{
    const p=DATA.players[snap.slot]||{};
    const isW=String(p.team)===DATA.winner_team;
    const row=document.createElement("tr");
    let cells=`<td class="left"><span style="color:${pColor(snap.slot)}">P${snap.slot}</span> ${snap.name}</td>
               <td style="color:#888">${snap.civ}</td>`;
    snap.ages.forEach(a=>{
      const c=a.time_str==="—"?"#555":(isW?"#5db85d":"#e57373");
      cells+=`<td style="color:${c};font-weight:bold">${a.time_str}</td>
              <td>${a.res?a.res.toLocaleString():"—"}</td>
              <td>${a.obj||"—"}</td><td>${a.mil||"—"}</td>`;
    });
    row.innerHTML=cells; tbody.appendChild(row);
  });
  tbl.appendChild(tbody);

  mkChart("chart-snap-obj","bar",{
    labels:snaps.map(s=>"P"+s.slot+" "+s.name.slice(0,15)),
    datasets:["封建","城堡","帝王"].map((age,i)=>({
      label:age+"升代時 obj_count",
      data:snaps.map(s=>s.ages[i]?.obj||0),
      backgroundColor:["#5C8A3C","#3C5C8A","#8A3C3C"][i]
    }))
  },{plugins:{tooltip:{mode:"index"}}});
}

// Verdict
function buildVerdict(){
  const cp=DATA.cp_data;
  const labels=cp.map(c=>c.label);
  const tkeys=Object.keys(DATA.teams).sort();
  const tColors={};
  tkeys.forEach(tid=>{tColors[tid]=tid===DATA.winner_team?"#4caf50":"#ef5350";});

  const mkCpChart=(id,key)=>mkChart(id,"bar",{
    labels,
    datasets:tkeys.map(tid=>({
      label:"Team "+tid+(tid===DATA.winner_team?" ★":""),
      data:cp.map(c=>c[tid]?.[key]||0),
      backgroundColor:hexRgba(tColors[tid],.7),
      borderColor:tColors[tid],borderWidth:1
    }))
  },{plugins:{tooltip:{mode:"index"}}});
  mkCpChart("chart-cp-res","res");
  mkCpChart("chart-cp-obj","obj");

  mkChart("chart-apm","bar",{
    labels:DATA.sorted_slots.map(s=>"P"+s+" "+(DATA.players[s]?.name||"").slice(0,15)),
    datasets:[{
      label:"APM",
      data:DATA.sorted_slots.map(s=>DATA.apm[s]?.apm||0),
      backgroundColor:DATA.sorted_slots.map(s=>pColor(s))
    }]
  },{plugins:{legend:{display:false}}});

  const fl=document.getElementById("factor-list");
  DATA.key_factors.forEach(f=>{
    const el=document.createElement("div");
    el.className="factor-item "+f.type;
    el.innerHTML=`<span class="factor-icon">${f.icon}</span><span class="factor-text">${f.text}</span>`;
    fl.appendChild(el);
  });
}
// Strategy & MVP
function buildStrategy(){
  // MVP cards
  const mc = document.getElementById("mvp-cards");
  const barColor = (pct) => pct>=70?"#4caf50":pct>=40?"#c8a45e":"#ef5350";
  Object.entries(DATA.mvp).sort().forEach(([tid, m])=>{
    const isW = tid===DATA.winner_team;
    const div = document.createElement("div");
    div.className="mvp-card "+(isW?"winner-mvp":"loser-mvp");
    const bd = m.breakdown||{};
    const scoreRows = [
      ["軍事輸出", bd.mil||0, "#e8a838"],
      ["APM",      bd.apm||0, "#38a8e8"],
      ["資源效率",  bd.res||0, "#38e888"],
      ["規模成長",  bd.obj||0, "#c838e8"],
    ].map(([lbl,pct,col])=>`
      <div class="mvp-score-bar">
        <span class="lbl">${lbl}</span>
        <span class="bar-outer"><span class="bar-inner" style="width:${pct}%;background:${col}"></span></span>
        <span class="val">${pct}%</span>
      </div>`).join("");

    const rankRows = (m.ranking||[]).map(([s,pct])=>{
      const p=DATA.players[s]||{};
      const dc=DATA.early_leaves.some(e=>e.slot===s);
      const crown=s===m.slot?"🥇 ":"";
      return `<div class="mvp-rank-row">
        <div class="mvp-rank-dot" style="background:${pColor(s)}"></div>
        <div class="mvp-rank-name">${crown}P${s} ${(p.name||"")}${dc?" [DC]":""}</div>
        <div class="mvp-rank-bar"><div class="mvp-rank-fill" style="width:${pct}%;background:${pColor(s)}"></div></div>
        <div class="mvp-rank-val">${pct}</div>
      </div>`;
    }).join("");

    div.innerHTML=`
      <div class="mvp-crown">${isW?"🏆":"🎖️"}</div>
      <div class="mvp-title">${isW?"勝利隊 MVP":"最佳表現（敗）"} · Team ${tid}</div>
      <div class="mvp-name"><span style="color:${m.color}">P${m.slot}</span> ${m.name}</div>
      <div class="mvp-sub">${m.civ}</div>
      <div class="mvp-strategy">${m.strategy}</div>
      <div style="font-size:11px;color:var(--muted);margin-bottom:6px">綜合評分 <strong style="color:var(--gold);font-size:16px">${m.score}</strong>/100</div>
      ${scoreRows}
      <div class="mvp-reasons">${(m.reasons||[]).map(r=>`<span>• ${r}</span>`).join("")}</div>
      <div style="margin-top:12px;font-size:11px;color:var(--muted);margin-bottom:4px">隊伍評分</div>
      <div class="mvp-ranking">${rankRows}</div>`;
    mc.appendChild(div);
  });

  // Insights
  const il = document.getElementById("insights-list");
  (DATA.insights||[]).forEach(txt=>{
    const d=document.createElement("div");
    d.className="insight-item"; d.textContent=txt;
    il.appendChild(d);
  });

  // Key moments
  const ml = document.getElementById("moments-list");
  (DATA.key_moments||[]).forEach(m=>{
    const d=document.createElement("div");
    d.className="moment-item "+(m.type||"info");
    d.innerHTML=`<span class="moment-time">${m.time_str}</span><span>${m.text}</span>`;
    ml.appendChild(d);
  });

  // Strategy cards
  const sg = document.getElementById("strategy-grid");
  DATA.sorted_slots.forEach(s=>{
    const p  = DATA.players[s]||{};
    const st = DATA.strategies[s]||{};
    const top3 = (st.top3||[]).slice(0,3);
    const top3str = top3.map(([n,c])=>`${n}×${c}`).join("、")||"—";

    // Age bar segments
    const ageSegs = AGE_ORDER.map(age=>{
      const pct = st[`${age}_pct`]||0;
      return `<span class="age-seg" style="width:${pct}%;background:${AGE_COLORS[age]};opacity:.85" title="${age} ${pct}%"></span>`;
    }).join("");

    // Class pct chips
    const clsChips = Object.entries(st.class_pct||{}).sort((a,b)=>b[1]-a[1]).slice(0,3)
      .map(([cls,pct])=>`<span style="display:inline-block;background:rgba(255,255,255,.07);
        font-size:10px;padding:1px 6px;border-radius:6px;margin:2px">${cls} ${pct}%</span>`).join("");

    const dc = DATA.early_leaves.some(e=>e.slot===s);
    const card = document.createElement("div");
    card.className="strat-card";
    card.innerHTML=`
      <div class="s-header">
        <div class="s-dot" style="background:${pColor(s)}"></div>
        <div>
          <div class="s-name-line">P${s} ${(p.name||"")}${dc?' <span style="color:#f44;font-size:10px">[DC]</span>':""}</div>
          <div class="s-civ">${p.civ||""}</div>
        </div>
      </div>
      <div class="strat-badge">${st.name||"—"}</div>
      <div class="strat-desc">${st.desc||""}</div>
      <div class="strat-units">核心兵種: <span>${top3str}</span></div>
      <div class="strat-mil">軍事合計: ${st.total_mil||0}　帝王: ${st.imp_pct||0}%</div>
      <div class="strat-imp-bar" style="margin-top:6px" title="兵種類型分布">
        ${clsChips}
      </div>`;
    sg.appendChild(card);
  });
}
</script>
</body>
</html>"""


def generate_html(data: dict) -> str:
    return (HTML_TEMPLATE
            .replace('__DATA_JSON__', json.dumps(data, ensure_ascii=False))
            .replace('__PC_JSON__',   json.dumps(PLAYER_COLORS)))


def main():
    if len(sys.argv) < 2:
        candidates = sorted(Path('.').glob('*_parsed.json'),
                            key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            print('ERROR: no _parsed.json found', file=sys.stderr); sys.exit(1)
        base = Path(str(candidates[0]).replace('_parsed.json', ''))
        print(f'Found: {candidates[0].name}')
    else:
        base = Path(sys.argv[1]).with_suffix('')
        if str(base).endswith('_parsed'):
            base = Path(str(base)[:-7])

    hdr      = json.loads(Path(str(base) + '_parsed.json').read_text(encoding='utf-8'))
    deep     = json.loads(Path(str(base) + '_deep.json').read_text(encoding='utf-8'))
    unit_map = load_unit_map(base)

    data = prepare_data(hdr, deep, unit_map)
    html = generate_html(data)

    out = Path(str(base) + '_report.html')
    out.write_text(html, encoding='utf-8')
    print(f'HTML report : {out}')
    print(f'File size   : {out.stat().st_size // 1024} KB')


if __name__ == '__main__':
    main()
