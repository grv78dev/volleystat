#!/usr/bin/env python3
"""
VolleyStat — Gestione Statistiche Pallavolo (Multi-Categoria)
Avvia con: python3 app.py
"""

import csv
import io
import json
import math
import re
import shutil
import threading
import time
import webbrowser
import zipfile
from datetime import datetime
from pathlib import Path

from flask import (Flask, abort, jsonify, make_response, redirect,
                   render_template, request, send_file, url_for)

from parser import parse_command, compute_state
from stats import (
    compute_player_stats, enrich_stats, pct,
    compute_game_continuity,
    compute_setter_stats, compute_attack_zone_stats, compute_rotation_stats,
    compute_minutes_played, compute_score_timeline,
    zone_distance, displacement_label, displacement_class, setter_slot_in_lineup,
    ZONE_LAYOUT, ZONE_NAMES, ZONE_COORDS, SLOT_TO_ZONE, ROLE_FRONT_ZONE,
    ROT_LABELS, ROT_SHORT, ROT_ORDER,
)

app = Flask(__name__)
ROOT = Path('data')

# Serializza i read-modify-write sui file dei set (più dispositivi in LAN)
_events_lock = threading.Lock()

# ─────────────────────────────────────────────────────────────
# STRUTTURA DATI
#  data/
#    club.json
#    categorie/
#      <cat_id>/
#        info.json   {name, short, color, season, order}
#        players.json
#        matches.json
#        sets/<match_id>_<n>.json
# ─────────────────────────────────────────────────────────────

PALETTE = ['#4a9eff','#3fb950','#ff6b35','#e3b341',
           '#a78bfa','#f778ba','#39d0c8','#ff5370']

def ensure_root():
    ROOT.mkdir(exist_ok=True)
    (ROOT / 'categorie').mkdir(exist_ok=True)

ensure_root()

# ── club ──────────────────────────────────────────────────────
def get_club():
    p = ROOT / 'club.json'
    if p.exists():
        return json.loads(p.read_text(encoding='utf-8'))
    return {'name': '', 'season': ''}

def save_club(data):
    (ROOT / 'club.json').write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')

# ── categorie ─────────────────────────────────────────────────
def get_categories():
    cats, base = [], ROOT / 'categorie'
    if not base.exists():
        return cats
    for d in sorted(base.iterdir()):
        if d.is_dir() and (d / 'info.json').exists():
            info = json.loads((d / 'info.json').read_text(encoding='utf-8'))
            info['id'] = d.name
            cats.append(info)
    return sorted(cats, key=lambda c: c.get('order', 99))

def get_category(cat_id):
    p = ROOT / 'categorie' / cat_id / 'info.json'
    if not p.exists():
        return None
    info = json.loads(p.read_text(encoding='utf-8'))
    info['id'] = cat_id
    return info

def save_category_info(cat_id, info):
    d = ROOT / 'categorie' / cat_id
    d.mkdir(parents=True, exist_ok=True)
    (d / 'sets').mkdir(exist_ok=True)
    (d / 'info.json').write_text(
        json.dumps(info, indent=2, ensure_ascii=False), encoding='utf-8')

def slugify(s):
    s = re.sub(r'[^a-z0-9]+', '_', s.lower().strip())
    return s.strip('_') or 'cat'

# ── dati categoria ─────────────────────────────────────────────
def _jload(path, default=None):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            pass
    return default

def _jsave(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')

def get_players(cat_id):
    return _jload(ROOT/'categorie'/cat_id/'players.json',
                  {'players':[]})['players']

def save_players(cat_id, players):
    _jsave(ROOT/'categorie'/cat_id/'players.json', {'players': players})

def get_matches(cat_id):
    return _jload(ROOT/'categorie'/cat_id/'matches.json',
                  {'matches':[]})['matches']

def save_matches(cat_id, matches):
    _jsave(ROOT/'categorie'/cat_id/'matches.json', {'matches': matches})

def get_set(cat_id, match_id, set_n):
    return _jload(ROOT/'categorie'/cat_id/'sets'/f'{match_id}_{set_n}.json')

def save_set(cat_id, match_id, set_n, data):
    _jsave(ROOT/'categorie'/cat_id/'sets'/f'{match_id}_{set_n}.json', data)

def compute_match_continuity(cat_id, match_id, sets=None):
    """Aggrega la continuità su tutti i set della partita."""
    agg_t = {'rpos':0,'kills':0,'cont':0,'err':0,'no_attack':0}
    agg_r = {}
    agg_a = {}

    if sets is None:
        sets = get_match_sets(cat_id, match_id)
    for sn, sd, state in sets:
        gc = compute_game_continuity(sd)
        for k in ('rpos','kills','cont','err','no_attack'):
            agg_t[k] += gc['team'].get(k, 0)
        for n, d in gc['by_receiver'].items():
            if n not in agg_r:
                agg_r[n] = {'rpos':0,'kills':0,'cont':0,'err':0}
            for k in ('rpos','kills','cont','err'):
                agg_r[n][k] += d.get(k, 0)
        for n, d in gc['by_attacker'].items():
            if n not in agg_a:
                agg_a[n] = {'rpos_received':0,'kills':0,'cont':0,'err':0}
            for k in ('rpos_received','kills','cont','err'):
                agg_a[n][k] += d.get(k, 0)

    rp = agg_t['rpos']
    agg_t['conv_pct'] = pct(agg_t['kills'],                    rp)
    agg_t['cont_pct'] = pct(agg_t['kills'] + agg_t['cont'],    rp)
    agg_t['disp_pct'] = pct(agg_t['err'],                      rp)
    for n, d in agg_r.items():
        r = d['rpos']
        d['conv_pct'] = pct(d['kills'],           r)
        d['cont_pct'] = pct(d['kills']+d['cont'], r)
        d['disp_pct'] = pct(d['err'],             r)
    for n, d in agg_a.items():
        r = d['rpos_received']
        d['conv_pct'] = pct(d['kills'],           r)
        d['cont_pct'] = pct(d['kills']+d['cont'], r)
        d['disp_pct'] = pct(d['err'],             r)

    return {'team':agg_t,'by_receiver':agg_r,'by_attacker':agg_a}


def compute_match_setter_stats(cat_id, match_id, sets=None):
    """Aggrega le setter stats su tutti i set della partita."""
    heatmap_tot   = {z: 0 for z in range(1, 7)}
    dist_tot      = {z: {} for z in range(1, 7)}
    totals_tot    = {}
    displacement_tot = []
    disp_sum_tot  = {'In zona':0, 'Corto':0, 'Lungo':0, 'Fuori zona':0}
    setter_num    = None

    if sets is None:
        sets = get_match_sets(cat_id, match_id)
    for sn, sd, state in sets:
        ss = compute_setter_stats(sd)
        if ss.get('setter_num'):
            setter_num = ss['setter_num']
        for z in range(1, 7):
            heatmap_tot[z] += ss['heatmap'][z]
        for z, players in ss['distribution'].items():
            for p, d in players.items():
                if p not in dist_tot[z]:
                    dist_tot[z][p] = {'kill':0,'cont':0,'err':0,'total':0}
                for k in ('kill','cont','err','total'):
                    dist_tot[z][p][k] += d.get(k, 0)
        for p, d in ss['totals'].items():
            if p not in totals_tot:
                totals_tot[p] = {'kill':0,'cont':0,'err':0,'total':0}
            for k in ('kill','cont','err','total'):
                totals_tot[p][k] += d.get(k, 0)
        displacement_tot.extend(ss.get('displacement', []))
        for label, cnt in ss.get('disp_summary', {}).items():
            disp_sum_tot[label] = disp_sum_tot.get(label, 0) + cnt

    def add_eff(d):
        t = d.get('total', 0)
        d['eff'] = round((d.get('kill',0)+d.get('cont',0)-d.get('err',0))/t*100,1) if t>0 else None
        return d
    for z in dist_tot:
        for p in dist_tot[z]: add_eff(dist_tot[z][p])
    for p in totals_tot:      add_eff(totals_tot[p])

    # Efficienza aggregata per categoria spostamento
    disp_eff_tot = {}
    for label in ('In zona','Corto','Lungo','Fuori zona'):
        entries = [e for e in displacement_tot if e['label']==label]
        if entries:
            k   = sum(1 for e in entries if e['outcome']=='kill')
            c   = sum(1 for e in entries if e['outcome']=='cont')
            r   = sum(1 for e in entries if e['outcome']=='err')
            tot = len(entries)
            disp_eff_tot[label] = {
                'total':tot,'kill':k,'cont':c,'err':r,
                'eff': round((k+c-r)/tot*100,1) if tot>0 else None,
            }

    return {
        'heatmap':      heatmap_tot,
        'distribution': dist_tot,
        'totals':       totals_tot,
        'total_sets':   sum(heatmap_tot.values()),
        'zone_layout':  ZONE_LAYOUT,
        'zone_names':   ZONE_NAMES,
        'displacement': displacement_tot,
        'disp_summary': disp_sum_tot,
        'disp_eff':     disp_eff_tot,
        'setter_num':   setter_num,
    }


def compute_match_attack_zone_stats(cat_id, match_id, sets=None):
    """Aggrega le attack zone stats su tutti i set della partita."""
    heatmap_tot = {z: 0 for z in range(1, 7)}
    dist_tot    = {z: {} for z in range(1, 7)}
    totals_tot  = {}

    players_by_num = {p['number']: p for p in get_players(cat_id)}

    if sets is None:
        sets = get_match_sets(cat_id, match_id)
    for sn, sd, state in sets:
        az = compute_attack_zone_stats(sd, players_by_num)
        for z in range(1, 7):
            heatmap_tot[z] += az['heatmap'][z]
        for z, players in az['distribution'].items():
            for p, d in players.items():
                if p not in dist_tot[z]:
                    dist_tot[z][p] = {'kill':0,'cont':0,'err':0,'total':0}
                for k in ('kill','cont','err','total'):
                    dist_tot[z][p][k] += d.get(k, 0)
        for p, d in az['totals'].items():
            if p not in totals_tot:
                totals_tot[p] = {'kill':0,'cont':0,'err':0,'total':0}
            for k in ('kill','cont','err','total'):
                totals_tot[p][k] += d.get(k, 0)

    def add_eff(d):
        t = d.get('total', 0)
        d['eff']      = round((d.get('kill',0)+d.get('cont',0)-d.get('err',0))/t*100,1) if t>0 else None
        d['kill_pct'] = round(d.get('kill',0)/t*100,1) if t>0 else None
        return d
    for z in dist_tot:
        for p in dist_tot[z]: add_eff(dist_tot[z][p])
    for p in totals_tot: add_eff(totals_tot[p])

    zone_eff_tot = {}
    for z in range(1, 7):
        k   = sum(d.get('kill',0) for d in dist_tot[z].values())
        c   = sum(d.get('cont',0) for d in dist_tot[z].values())
        r   = sum(d.get('err',0)  for d in dist_tot[z].values())
        tot = heatmap_tot[z]
        zone_eff_tot[z] = {
            'kill':k, 'cont':c, 'err':r, 'total':tot,
            'eff':      round((k+c-r)/tot*100,1) if tot>0 else None,
            'kill_pct': round(k/tot*100,1)        if tot>0 else None,
        }

    return {
        'heatmap':       heatmap_tot,
        'distribution':  dist_tot,
        'totals':        totals_tot,
        'total_attacks': sum(heatmap_tot.values()),
        'zone_eff':      zone_eff_tot,
        'zone_layout':   ZONE_LAYOUT,
        'zone_names':    ZONE_NAMES,
    }


# ─────────────────────────────────────────────────────────────
# ANALISI PER ROTAZIONE
# ─────────────────────────────────────────────────────────────
# La rotazione è identificata dalla zona del palleggiatore (1-6):
# P1 = palleggiatore in zona 1 (batte), P6 = zona 6, ecc.
# Ordine temporale nel set: P1 → P6 → P5 → P4 → P3 → P2.
# Senza palleggiatore registrato, usiamo lo slot 1 della formazione
# come riferimento (il giocatore in P1 che serve per primo).

def compute_match_rotation_stats(cat_id, match_id, sets=None):
    """Aggrega le rotation stats su tutti i set della partita."""
    rots_tot = {i: {'pts_scored':0,'pts_lost':0,'saldo':0,
                    'side_out_won':0,'side_out_tot':0,
                    'break_won':0,'break_tot':0}
                for i in range(1,7)}

    if sets is None:
        sets = get_match_sets(cat_id, match_id)
    for sn, sd, state in sets:
        rs = compute_rotation_stats(sd)
        for slot, r in rs['rotations'].items():
            for k in ('pts_scored','pts_lost','side_out_won','side_out_tot',
                      'break_won','break_tot'):
                rots_tot[slot][k] += r.get(k, 0)

    # Ricalcola saldo e percentuali sui totali
    for slot, r in rots_tot.items():
        r['saldo']   = r['pts_scored'] - r['pts_lost']
        r['so_pct']  = round(r['side_out_won']/r['side_out_tot']*100,1) \
                       if r['side_out_tot'] > 0 else None
        r['brk_pct'] = round(r['break_won']  /r['break_tot']  *100,1) \
                       if r['break_tot']   > 0 else None

    active = {s:r for s,r in rots_tot.items()
              if r['pts_scored']+r['pts_lost'] >= 2}
    best  = max(active, key=lambda s: active[s]['saldo']) if active else None
    worst = min(active, key=lambda s: active[s]['saldo']) if active else None
    if best == worst:
        worst = None   # una sola rotazione attiva: nessuna "critica"

    so_won  = sum(r['side_out_won'] for r in rots_tot.values())
    so_tot  = sum(r['side_out_tot'] for r in rots_tot.values())
    brk_won = sum(r['break_won']    for r in rots_tot.values())
    brk_tot = sum(r['break_tot']    for r in rots_tot.values())

    return {
        'rotations': rots_tot,
        'summary': {
            'best_rot':  best,
            'worst_rot': worst,
            'so_pct':    round(so_won /so_tot *100,1) if so_tot  > 0 else None,
            'brk_pct':   round(brk_won/brk_tot*100,1) if brk_tot > 0 else None,
            'so_won':    so_won,  'so_tot':  so_tot,
            'brk_won':   brk_won, 'brk_tot': brk_tot,
        },
        'rot_labels': ROT_LABELS,
        'rot_short':  ROT_SHORT,
        'rot_order':  ROT_ORDER,
    }


def compute_match_minutes(cat_id, match_id, sets=None):
    """
    Aggrega i minuti giocati in tutta la partita.
    Ritorna dict {player_num: minuti_totali}.
    """
    totals = {}
    if sets is None:
        sets = get_match_sets(cat_id, match_id)
    for sn, sd, state in sets:
        for player, mins in compute_minutes_played(sd).items():
            totals[player] = totals.get(player, 0) + mins
    return totals

def get_match_sets(cat_id, match_id):
    sets = []
    for sn in range(1,6):
        sd = get_set(cat_id, match_id, sn)
        if sd:
            sets.append((sn, sd, compute_state(sd)))
    return sets

def _update_match_result(cat_id, match_id):
    """Ricalcola sets_us/sets_them e lo status della partita dai set su disco."""
    matches = get_matches(cat_id)
    m = next((x for x in matches if x['id']==match_id), None)
    if not m:
        return
    su = st = 0
    for sn, sd, s in get_match_sets(cat_id, match_id):
        if s and s['set_over']:
            if s['winner']=='us': su+=1
            else: st+=1
    m['sets_us']   = su
    m['sets_them'] = st
    sets_to_win = 3  # best of 5 sia standard che pgs
    if su >= sets_to_win or st >= sets_to_win:
        m['status'] = 'completed'
    elif m.get('status') == 'completed':
        # un UNDO ha riaperto la partita
        m['status'] = 'ongoing'
    save_matches(cat_id, matches)

def compute_match_score_timeline(cat_id, match_id, sets=None):
    result = []
    if sets is None:
        sets = get_match_sets(cat_id, match_id)
    for sn, sd, state in sets:
        tl = compute_score_timeline(sd)
        tl['set_number'] = sn
        tl['winner']     = state.get('winner') if state else None
        result.append(tl)
    return result


def category_season_stats(cat_id):
    """Stats di stagione aggregate per la pagina confronto."""
    matches   = get_matches(cat_id)
    players   = get_players(cat_id)
    p_by_num  = {p['number']: p for p in players}
    completed = [m for m in matches if m.get('status') == 'completed']

    wins   = sum(1 for m in completed if m.get('sets_us',0) > m.get('sets_them',0))
    losses = len(completed) - wins

    total_pts_us = total_pts_them = total_sets = 0
    player_season = {}

    for m in completed:
        for sn, sd, state in get_match_sets(cat_id, m['id']):
            if state:
                total_pts_us   += state['score_us']
                total_pts_them += state['score_them']
                total_sets     += 1
            for pnum, ps in compute_player_stats(sd).items():
                if pnum not in player_season:
                    player_season[pnum] = dict(ps)
                else:
                    for k,v in ps.items():
                        player_season[pnum][k] = player_season[pnum].get(k,0)+v

    avg_pts = round(total_pts_us / total_sets, 1) if total_sets else 0

    top_scorer = None
    top_pts    = 0
    for pnum, ps in player_season.items():
        if ps.get('pts_scored',0) > top_pts:
            top_pts    = ps['pts_scored']
            top_scorer = pnum

    return {
        'matches_played': len(completed),
        'wins':           wins,
        'losses':         losses,
        'avg_pts':        avg_pts,
        'total_sets':     total_sets,
        'total_pts_us':   total_pts_us,
        'total_pts_them': total_pts_them,
        'player_season':  player_season,
        'top_scorer':     top_scorer,
        'top_pts':        top_pts,
        'p_by_num':       p_by_num,
    }


def compute_player_trends(cat_id):
    """
    Calcola 4 metriche di trend multi-partita per ogni giocatore della categoria.

    Indice base: (pts_scored − pts_lost) / n_set_giocati  →  "rendimento netto per set"

    Ritorna {player_num: {
        trend_values:       lista float delle ultime 3 partite (oldest→newest)
        trend_direction:    'up' | 'down' | 'stable' | None
        consistency:        deviazione standard sulle ultime 5 partite (None se <2)
        close_avg:          media indice in partite ravvicinate (≤7gg), None se <2
        close_n:            numero partite ravvicinate
        normal_avg:         media indice in partite non ravvicinate
        pts_per_set:        punti segnati / set giocati (stagione intera)
        matches_played:     partite completate con almeno 1 azione
        total_sets:         set totali giocati
    } | None}
    """
    matches = get_matches(cat_id)
    completed = sorted(
        [m for m in matches if m.get('status') == 'completed' and m.get('date')],
        key=lambda m: m['date']
    )

    # ── Per ogni match: stats aggregate e set giocati per ciascun giocatore
    match_data = []
    for m in completed:
        m_stats = {}
        sets_played = {}
        for _sn, sd, _state in get_match_sets(cat_id, m['id']):
            for pnum, ps in compute_player_stats(sd).items():
                if pnum not in m_stats:
                    m_stats[pnum] = dict(ps)
                    sets_played[pnum] = 0
                else:
                    for k, v in ps.items():
                        m_stats[pnum][k] = m_stats[pnum].get(k, 0) + v
                if sum(ps.values()) > 0:
                    sets_played[pnum] = sets_played.get(pnum, 0) + 1
        enriched = enrich_stats(m_stats)
        match_data.append({'date': m['date'], 'stats': enriched, 'sets': sets_played})

    players = get_players(cat_id)
    result = {}

    for p in players:
        pnum = p['number']
        pm = [md for md in match_data if pnum in md['stats']]
        if not pm:
            result[pnum] = None
            continue

        def net_index(md):
            s = md['stats'][pnum]
            net = s.get('pts_scored', 0) - s.get('pts_lost', 0)
            n_sets = md['sets'].get(pnum, 1) or 1
            return round(net / n_sets, 2)

        effs = [net_index(md) for md in pm]

        # ── 1. Trend ultime 3 partite
        last3 = effs[-3:]
        direction = None
        if len(last3) >= 2:
            delta = last3[-1] - last3[-2]
            direction = 'up' if delta > 0.3 else ('down' if delta < -0.3 else 'stable')

        # ── 2. Consistenza: std dev ultime 5
        last5 = effs[-5:]
        consistency = None
        if len(last5) >= 2:
            mean5 = sum(last5) / len(last5)
            consistency = round(math.sqrt(sum((x - mean5) ** 2 for x in last5) / len(last5)), 2)

        # ── 3. Partite ravvicinate (≤7 giorni dalla precedente o dalla successiva)
        close_effs, normal_effs = [], []
        for i, md in enumerate(pm):
            try:
                d = datetime.strptime(md['date'], '%Y-%m-%d')
                ravvic = False
                if i > 0:
                    d_prev = datetime.strptime(pm[i - 1]['date'], '%Y-%m-%d')
                    if (d - d_prev).days <= 7:
                        ravvic = True
                if i < len(pm) - 1:
                    d_next = datetime.strptime(pm[i + 1]['date'], '%Y-%m-%d')
                    if (d_next - d).days <= 7:
                        ravvic = True
                (close_effs if ravvic else normal_effs).append(effs[i])
            except ValueError:
                normal_effs.append(effs[i])

        close_avg  = round(sum(close_effs) / len(close_effs), 2) if len(close_effs) >= 2 else None
        normal_avg = round(sum(normal_effs) / len(normal_effs), 2) if normal_effs else None

        # ── 4. Punti per set (stagione intera)
        total_pts  = sum(md['stats'][pnum].get('pts_scored', 0) for md in pm)
        total_sets = sum(md['sets'].get(pnum, 0) for md in pm)
        pts_per_set = round(total_pts / total_sets, 2) if total_sets > 0 else None

        result[pnum] = {
            'trend_values':    last3,
            'trend_direction': direction,
            'consistency':     consistency,
            'close_avg':       close_avg,
            'close_n':         len(close_effs),
            'normal_avg':      normal_avg,
            'pts_per_set':     pts_per_set,
            'matches_played':  len(pm),
            'total_sets':      total_sets,
        }

    return result


# ─────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────
# PWA — manifest e service worker
# ─────────────────────────────────────────────────────────────
@app.route('/manifest.json')
def pwa_manifest():
    return jsonify({
        "name": "VolleyStat",
        "short_name": "VolleyStat",
        "description": "Statistiche pallavolo in tempo reale",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0d1117",
        "theme_color": "#0d1117",
        "orientation": "any",
        "lang": "it",
        "icons": [
            {"src": "/static/icons/icon.svg", "sizes": "512x512",
             "type": "image/svg+xml", "purpose": "any maskable"},
        ]
    })

@app.route('/sw.js')
def service_worker():
    r = make_response(Path('static/sw.js').read_text(encoding='utf-8'))
    r.headers['Content-Type'] = 'application/javascript'
    r.headers['Service-Worker-Allowed'] = '/'
    return r

# ─────────────────────────────────────────────────────────────
# ROUTES — HOME (hub sodalizio)
# ─────────────────────────────────────────────────────────────
@app.route('/', methods=['GET','POST'])
def home():
    club = get_club()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'save_club':
            club['name']   = request.form.get('name','').strip()
            club['season'] = request.form.get('season','').strip()
            save_club(club)
        elif action == 'add_cat':
            cats  = get_categories()
            name  = request.form.get('cat_name','').strip()
            if not name:
                return redirect(url_for('home'))
            short = (request.form.get('cat_short') or name[:5]).strip().upper()
            cat_id = slugify(name)
            existing = [c['id'] for c in cats]
            base_id, n = cat_id, 2
            while cat_id in existing:
                cat_id = f'{base_id}_{n}'; n += 1
            color = PALETTE[len(cats) % len(PALETTE)]
            save_category_info(cat_id, {
                'name':   name,
                'short':  short,
                'color':  request.form.get('cat_color', color),
                'season': request.form.get('cat_season', club.get('season','')),
                'order':  len(cats),
            })
        elif action == 'delete_cat':
            cat_id = request.form['cat_id']
            # Solo id generati da slugify: blocca path traversal (es. "../..")
            if not re.fullmatch(r'[a-z0-9_]+', cat_id):
                abort(400, 'Identificativo categoria non valido')
            d = ROOT / 'categorie' / cat_id
            if d.is_dir():
                shutil.rmtree(d)
        return redirect(url_for('home'))

    cats = get_categories()
    for c in cats:
        ms = get_matches(c['id'])
        c['n_players']   = len(get_players(c['id']))
        c['n_completed'] = sum(1 for m in ms if m.get('status')=='completed')
        c['n_ongoing']   = sum(1 for m in ms if m.get('status')=='ongoing')
        c['n_scheduled'] = sum(1 for m in ms if m.get('status')=='scheduled')
    return render_template('home.html', club=club, cats=cats)

# ─────────────────────────────────────────────────────────────
# ROUTES — DASHBOARD CATEGORIA
# ─────────────────────────────────────────────────────────────
@app.route('/c/<cat_id>/')
def index(cat_id):
    cat = get_category(cat_id)
    if not cat: abort(404)
    matches = get_matches(cat_id)
    matches.sort(key=lambda m: m.get('date',''))
    today    = datetime.now().strftime('%Y-%m-%d')
    upcoming = [m for m in matches
                if m.get('status') == 'ongoing'
                or (m.get('date','')>=today and m.get('status')!='completed')][:5]
    recent   = [m for m in reversed(matches)
                if m.get('status')=='completed'][:5]
    return render_template('index.html', cat=cat,
                           upcoming=upcoming, recent=recent, today=today)

# ─────────────────────────────────────────────────────────────
# ROUTES — ROSA
# ─────────────────────────────────────────────────────────────
@app.route('/c/<cat_id>/rosa', methods=['GET','POST'])
def roster(cat_id):
    cat = get_category(cat_id)
    if not cat: abort(404)
    players = get_players(cat_id)
    if request.method == 'POST':
        action = request.form.get('action')

        # Validazione comune a add/edit: numero valido, range 1-99, no duplicati
        if action in ('add', 'edit'):
            try:
                numero = int(request.form['number'])
                pid    = int(request.form['id']) if action == 'edit' else None
            except (ValueError, KeyError):
                return redirect(url_for('roster', cat_id=cat_id,
                                        msg='Numero di maglia non valido.', msg_type='error'))
            if not (1 <= numero <= 99):
                return redirect(url_for('roster', cat_id=cat_id,
                                        msg=f'Numero {numero} fuori range (1–99).', msg_type='error'))
            if any(p['number'] == numero and p['id'] != pid for p in players):
                return redirect(url_for('roster', cat_id=cat_id,
                                        msg=f'Maglia #{numero} già assegnata a un altro atleta.',
                                        msg_type='error'))

        if action == 'add':
            new_id = max((p['id'] for p in players), default=0)+1
            players.append({'id':new_id,
                            'number':numero,
                            'name':request.form['name'].strip(),
                            'role':request.form.get('role','U'),
                            'active':True})
            save_players(cat_id, players)
        elif action == 'delete':
            try:
                pid = int(request.form['id'])
            except (ValueError, KeyError):
                return redirect(url_for('roster', cat_id=cat_id))
            players = [p for p in players if p['id']!=pid]
            save_players(cat_id, players)
        elif action == 'edit':
            for p in players:
                if p['id']==pid:
                    p['number'] = numero
                    p['name']   = request.form['name'].strip()
                    p['role']   = request.form.get('role','U')
                    break
            save_players(cat_id, players)
        return redirect(url_for('roster', cat_id=cat_id))
    players.sort(key=lambda p: p['number'])
    trends = compute_player_trends(cat_id)
    return render_template('roster.html', cat=cat, players=players, trends=trends)

@app.route('/c/<cat_id>/rosa/import-csv', methods=['POST'])
def roster_import_csv(cat_id):
    cat = get_category(cat_id)
    if not cat: abort(404)

    f = request.files.get('csvfile')
    if not f or not f.filename:
        return redirect(url_for('roster', cat_id=cat_id,
                                msg='Nessun file selezionato.', msg_type='error'))

    players = get_players(cat_id)
    existing_numbers = {p['number'] for p in players}
    next_id = max((p['id'] for p in players), default=0) + 1
    VALID_ROLES = {'S', 'O', 'P', 'C', 'L', 'U'}

    imported = 0
    skipped_msgs = []

    try:
        raw = f.stream.read()
        # supporta UTF-8, UTF-8 con BOM (Excel) e latin-1
        for enc in ('utf-8-sig', 'utf-8', 'latin-1'):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            return redirect(url_for('roster', cat_id=cat_id,
                                    msg='Impossibile leggere il file: encoding non supportato.',
                                    msg_type='error'))

        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            return redirect(url_for('roster', cat_id=cat_id,
                                    msg='File CSV vuoto o senza intestazione.', msg_type='error'))

        # normalizza nomi colonne
        fieldnames_norm = [k.strip().lower() for k in reader.fieldnames]
        if 'numero' not in fieldnames_norm or 'nome' not in fieldnames_norm:
            return redirect(url_for('roster', cat_id=cat_id,
                                    msg='Colonne obbligatorie mancanti: "numero" e "nome".',
                                    msg_type='error'))

        for row_i, raw_row in enumerate(reader, start=2):
            row = {k.strip().lower(): (v or '').strip() for k, v in raw_row.items() if k}

            numero_str = row.get('numero', '')
            nome       = row.get('nome', '')
            ruolo      = row.get('ruolo', 'U').upper()

            if not numero_str or not nome:
                skipped_msgs.append(f'Riga {row_i}: numero o nome mancante')
                continue

            try:
                numero = int(numero_str)
            except ValueError:
                skipped_msgs.append(f'Riga {row_i}: numero non valido "{numero_str}"')
                continue

            if not (1 <= numero <= 99):
                skipped_msgs.append(f'Riga {row_i}: numero {numero} fuori range (1–99)')
                continue

            if ruolo not in VALID_ROLES:
                ruolo = 'U'

            if numero in existing_numbers:
                skipped_msgs.append(f'Riga {row_i}: maglia #{numero} ({nome}) già presente')
                continue

            players.append({'id': next_id, 'number': numero,
                            'name': nome, 'role': ruolo, 'active': True})
            existing_numbers.add(numero)
            next_id += 1
            imported += 1

        save_players(cat_id, players)

    except Exception as e:
        return redirect(url_for('roster', cat_id=cat_id,
                                msg=f'Errore nel file CSV: {e}', msg_type='error'))

    if imported == 0 and skipped_msgs:
        msg = 'Nessun atleta importato. ' + ' | '.join(skipped_msgs[:3])
        msg_type = 'error'
    else:
        msg = f'Importati {imported} atleti'
        if skipped_msgs:
            msg += f' ({len(skipped_msgs)} righe saltate)'
        msg_type = 'ok'

    return redirect(url_for('roster', cat_id=cat_id, msg=msg, msg_type=msg_type))


# ─────────────────────────────────────────────────────────────
# ROUTES — CALENDARIO
# ─────────────────────────────────────────────────────────────
@app.route('/c/<cat_id>/calendario', methods=['GET','POST'])
def calendar(cat_id):
    cat = get_category(cat_id)
    if not cat: abort(404)
    matches = get_matches(cat_id)
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            date     = request.form.get('date','').strip()
            opponent = request.form.get('opponent','').strip()
            if not date or not opponent:
                return redirect(url_for('calendar', cat_id=cat_id))
            mid = datetime.now().strftime('%Y%m%d%H%M%S')
            matches.append({'id':mid,
                            'date':date,
                            'time':request.form.get('time',''),
                            'opponent':opponent,
                            'home':request.form.get('home')=='on',
                            'location':request.form.get('location','').strip(),
                            'competition':request.form.get('competition','').strip(),
                            'ruleset':request.form.get('ruleset','standard'),
                            'status':'scheduled','sets_us':0,'sets_them':0})
            save_matches(cat_id, matches)
        elif action == 'delete':
            mid = request.form['id']
            matches = [m for m in matches if m['id']!=mid]
            save_matches(cat_id, matches)
        return redirect(url_for('calendar', cat_id=cat_id))
    matches.sort(key=lambda m: m.get('date',''))
    return render_template('calendar.html', cat=cat, matches=matches)

# ─────────────────────────────────────────────────────────────
# ROUTES — PARTITA
# ─────────────────────────────────────────────────────────────
@app.route('/c/<cat_id>/partita/<match_id>')
def match_view(cat_id, match_id):
    cat = get_category(cat_id)
    matches = get_matches(cat_id)
    m = next((x for x in matches if x['id']==match_id), None)
    if not cat or not m: abort(404)
    players  = sorted(get_players(cat_id), key=lambda p: p['number'])
    p_by_num = {p['number']: p for p in players}
    sets     = get_match_sets(cat_id, match_id)
    return render_template('match.html', cat=cat, match=m,
                           sets=sets, players=players, p_by_num=p_by_num)

@app.route('/c/<cat_id>/partita/<match_id>/nuovo-set', methods=['POST'])
def new_set(cat_id, match_id):
    cat = get_category(cat_id)
    matches = get_matches(cat_id)
    m = next((x for x in matches if x['id']==match_id), None)
    if not cat or not m: abort(404)

    set_num = 1
    for sn in range(1,6):
        if get_set(cat_id, match_id, sn):
            set_num = sn+1
    if set_num > 5:
        return 'Partita già completa: massimo 5 set', 400

    lineup_raw = request.form.get('lineup','')
    try:
        lineup = [int(x.strip()) for x in lineup_raw.split(',') if x.strip()]
        if len(lineup)!=6:
            return 'Servono esattamente 6 giocatori nella formazione', 400
    except Exception:
        return 'Formato formazione non valido', 400
    if len(set(lineup)) != 6:
        return 'Formazione non valida: numeri di maglia duplicati', 400

    libero_raw      = request.form.get('libero','').strip()
    palleggiatore_raw = request.form.get('palleggiatore','').strip()
    partner_raw     = request.form.get('libero_partner','').strip()
    libero          = int(libero_raw)        if libero_raw.isdigit()        else None
    palleggiatore   = int(palleggiatore_raw) if palleggiatore_raw.isdigit() else None
    libero_partner  = int(partner_raw)       if partner_raw.isdigit()       else None

    if palleggiatore is not None and palleggiatore not in lineup:
        return 'Il palleggiatore deve essere nella formazione iniziale', 400

    if libero_partner is not None:
        if libero is None:
            return 'Il 7° titolare (centrale abbinato) richiede di selezionare anche il libero', 400
        if libero_partner == libero:
            return 'Il centrale abbinato al libero deve essere un giocatore diverso dal libero', 400
        if (libero in lineup) == (libero_partner in lineup):
            return ('Libero e centrale abbinato: uno dei due deve partire in campo, '
                    'l\'altro in panchina'), 400

    roster_nums = {p['number'] for p in get_players(cat_id)}
    if roster_nums:
        unknown = [n for n in lineup if n not in roster_nums]
        if libero is not None and libero not in roster_nums:
            unknown.append(libero)
        if libero_partner is not None and libero_partner not in roster_nums:
            unknown.append(libero_partner)
        if unknown:
            return ('Numeri non presenti in rosa: '
                    + ', '.join(f'#{n}' for n in unknown)), 400

    auto_libero = request.form.get('auto_libero') == 'on' and libero is not None

    sd = {
        'match_id':match_id, 'set_number':set_num,
        'lineup':lineup,
        'libero':         libero,
        'libero_partner': libero_partner,
        'palleggiatore':  palleggiatore,
        'auto_libero':    auto_libero,
        'first_serve':request.form.get('first_serve','us'),
        'ruleset':m.get('ruleset','standard'),
        'events':[], 'created_at':datetime.now().isoformat(),
    }
    if auto_libero:
        # Centrale già in seconda linea a inizio set → libero entra subito
        _append_auto_libero(cat_id, sd)
    save_set(cat_id, match_id, set_num, sd)
    m['status'] = 'ongoing'
    save_matches(cat_id, matches)
    return redirect(url_for('set_view', cat_id=cat_id,
                            match_id=match_id, set_num=set_num))

# ─────────────────────────────────────────────────────────────
# ROUTES — SET (rilevamento live)
# ─────────────────────────────────────────────────────────────
@app.route('/c/<cat_id>/partita/<match_id>/set/<int:set_num>')
def set_view(cat_id, match_id, set_num):
    cat = get_category(cat_id)
    matches = get_matches(cat_id)
    m  = next((x for x in matches if x['id']==match_id), None)
    sd = get_set(cat_id, match_id, set_num)
    if not cat or not m or not sd: abort(404)
    players  = get_players(cat_id)
    p_by_num = {p['number']: p for p in players}
    return render_template('set.html', cat=cat, match=m, sd=sd,
                           state=compute_state(sd), p_by_num=p_by_num,
                           set_num=set_num)

def _libero_partner(sd, lib):
    """Numero del giocatore che il libero ha rimpiazzato (ultimo cambio libero).

    Se non c'è ancora nessuno cambio libero in storico (es. il libero è
    partito titolare in campo), usa il 7° titolare dichiarato a inizio set
    (`libero_partner`) come compagno di riferimento.
    """
    for ev in reversed(sd.get('events', [])):
        if ev.get('type') == 'libero_exchange':
            n1, n2 = ev.get('n1'), ev.get('n2')
            if n1 == lib: return n2
            if n2 == lib: return n1
    partner = sd.get('libero_partner')
    return partner if partner is not None and partner != lib else None

def _find_auto_libero_event(cat_id, sd):
    """Giro automatico centrale-libero: calcola l'eventuale cambio libero
    da registrare dopo l'ultimo evento. Ritorna un evento libero_exchange
    con auto=True, oppure None se non serve alcun cambio.

    Regole (FIPAV/FIVB):
    - il libero entra per un centrale (ruolo C) in seconda linea
      (zona 5, 6, o 1 solo in ricezione: il libero non può servire);
    - il libero esce — rientra il centrale rimpiazzato — quando la
      rotazione lo porterebbe in prima linea (zone 2/3/4) o al servizio.
    """
    if not sd.get('auto_libero') or not sd.get('libero'):
        return None
    st = compute_state(sd)
    if not st or st['set_over'] or len(st['lineup']) != 6:
        return None
    lineup = st['lineup']
    lib = sd['libero']

    if lib in lineup:
        zone = lineup.index(lib) + 1
        if zone in (2, 3, 4) or (zone == 1 and st['our_serve']):
            partner = _libero_partner(sd, lib)
            if partner is not None and partner not in lineup:
                return {'type':'libero_exchange','n1':lib,'n2':partner,'auto':True,
                        'desc':f'Cambio libero automatico: #{lib} esce, #{partner} entra'}
        return None

    # Libero in panchina: entra per un centrale in seconda linea.
    # Zona 5 per prima (è la prossima a ruotare in prima linea), poi 6 e 1.
    roles = {p['number']: p.get('role', 'U') for p in get_players(cat_id)}
    for zone in (5, 6, 1):
        if zone == 1 and st['our_serve']:
            continue
        num = lineup[zone - 1]
        if roles.get(num) == 'C':
            return {'type':'libero_exchange','n1':num,'n2':lib,'auto':True,
                    'desc':f'Cambio libero automatico: #{num} esce, #{lib} entra'}
    return None

def _append_auto_libero(cat_id, sd):
    """Se necessario, accoda il cambio libero automatico. Ritorna l'evento o None."""
    auto_ev = _find_auto_libero_event(cat_id, sd)
    if auto_ev:
        auto_ev['id'] = max((e.get('id', 0) for e in sd['events']), default=0) + 1
        auto_ev['timestamp'] = datetime.now().strftime('%H:%M:%S')
        sd['events'].append(auto_ev)
    return auto_ev

@app.route('/c/<cat_id>/partita/<match_id>/set/<int:set_num>/comando', methods=['POST'])
def add_command(cat_id, match_id, set_num):
    with _events_lock:
        return _add_command(cat_id, match_id, set_num)

def _add_command(cat_id, match_id, set_num):
    sd = get_set(cat_id, match_id, set_num)
    if not sd:
        return jsonify(error='Set non trovato'), 404

    ev = parse_command(request.json.get('command','').strip())
    if ev['type'] == 'error':
        return jsonify(error=ev['message']), 400

    if ev['type'] == 'undo':
        if sd['events']:
            # I cambi libero automatici vengono annullati insieme
            # all'evento che li ha generati
            removed = [sd['events'].pop()]
            while removed[-1].get('auto') and sd['events']:
                removed.append(sd['events'].pop())
            save_set(cat_id, match_id, set_num, sd)
            # L'evento annullato può aver chiuso il set: riallinea la partita
            if any(r.get('type') == 'point' for r in removed):
                _update_match_result(cat_id, match_id)
            return jsonify(success=True, state=compute_state(sd),
                           undone=' · '.join(r.get('desc','') for r in reversed(removed)))
        return jsonify(error='Nessun evento da annullare'), 400

    if ev['type'] == 'toggle_auto_libero':
        if not sd.get('libero'):
            return jsonify(error='Nessun libero impostato per questo set'), 400
        sd['auto_libero'] = not sd.get('auto_libero', False)
        auto_ev = _append_auto_libero(cat_id, sd) if sd['auto_libero'] else None
        save_set(cat_id, match_id, set_num, sd)
        stato = 'attivato' if sd['auto_libero'] else 'disattivato'
        return jsonify(success=True, state=compute_state(sd),
                       event={'desc': f'Giro automatico centrale-libero {stato}'},
                       auto_event=auto_ev)

    # Validazione duplicati in campo
    if ev['type'] == 'substitution':
        cur = compute_state(sd)
        lineup = cur['lineup'] if cur else []
        pin, pout = ev['player_in'], ev['player_out']
        if pin in lineup:
            return jsonify(error=f'#{pin} è già in campo — sostituzione non valida'), 400
        if pout not in lineup:
            return jsonify(error=f'#{pout} non è in campo — sostituzione non valida'), 400

    if ev['type'] == 'libero_exchange':
        cur = compute_state(sd)
        lineup = cur['lineup'] if cur else []
        n1, n2 = ev.get('n1'), ev.get('n2')
        if n1 in lineup and n2 in lineup:
            return jsonify(error=f'#{n1} e #{n2} sono entrambi in campo — cambio libero non valido'), 400
        if n1 not in lineup and n2 not in lineup:
            return jsonify(error=f'Né #{n1} né #{n2} sono in campo — cambio libero non valido'), 400

    # Massimo 2 timeout per squadra per set
    if ev['type'] == 'timeout':
        cur = compute_state(sd)
        if cur:
            side = ev.get('side', 'us')
            used = cur['timeouts_us'] if side == 'us' else cur['timeouts_them']
            if used >= 2:
                chi = 'Noi' if side == 'us' else 'Avversario'
                return jsonify(error=f'Timeout esauriti ({chi}: già 2 in questo set)'), 400

    # Validazione: azioni legate a un giocatore (S, A, B, R+, D, ...)
    # devono riferirsi a un numero realmente in campo in questo momento
    if ev['type'] in ('point', 'stat') and ev.get('player') is not None:
        cur = compute_state(sd)
        lineup = cur['lineup'] if cur else []
        if ev['player'] not in lineup:
            return jsonify(error=f"#{ev['player']} non è in campo — azione non valida"), 400

    # max+1 e non len+1: dopo un UNDO len+1 produrrebbe id duplicati
    ev['id']        = max((e.get('id', 0) for e in sd['events']), default=0) + 1
    ev['timestamp'] = datetime.now().strftime('%H:%M:%S')
    sd['events'].append(ev)

    # Giro automatico centrale-libero: solo dopo eventi che possono
    # cambiare rotazione o formazione
    auto_ev = None
    if ev['type'] in ('point', 'substitution'):
        auto_ev = _append_auto_libero(cat_id, sd)

    save_set(cat_id, match_id, set_num, sd)
    state = compute_state(sd)

    if state['set_over']:
        _update_match_result(cat_id, match_id)

    return jsonify(success=True, state=state, event=ev, auto_event=auto_ev)

@app.route('/c/<cat_id>/partita/<match_id>/set/<int:set_num>/stato')
def set_state_api(cat_id, match_id, set_num):
    sd = get_set(cat_id, match_id, set_num)
    if not sd:
        return jsonify(error='Set non trovato'), 404
    return jsonify(state=compute_state(sd),
                   player_stats=enrich_stats(compute_player_stats(sd)),
                   recent_events=sd.get('events',[])[-15:])

# ─────────────────────────────────────────────────────────────
# ROUTES — STATISTICHE & REPORT
# ─────────────────────────────────────────────────────────────
def _build_stats(cat_id, match_id, sets=None):
    players  = get_players(cat_id)
    p_by_num = {p['number']: p for p in players}
    all_sets, total_raw = [], {}
    if sets is None:
        sets = get_match_sets(cat_id, match_id)
    for sn, sd, state in sets:
        pstats   = compute_player_stats(sd)
        set_mins = compute_minutes_played(sd)
        all_sets.append({
            'number':      sn,
            'state':       state,
            'player_stats':enrich_stats(pstats),
            'minutes':     set_mins,
        })
        for pnum, pdata in pstats.items():
            if pnum not in total_raw:
                total_raw[pnum] = dict(pdata)
            else:
                for k,v in pdata.items():
                    total_raw[pnum][k] = total_raw[pnum].get(k,0)+v
    return p_by_num, all_sets, enrich_stats(total_raw)

@app.route('/c/<cat_id>/partita/<match_id>/statistiche')
def stats_view(cat_id, match_id):
    cat = get_category(cat_id)
    matches = get_matches(cat_id)
    m = next((x for x in matches if x['id']==match_id), None)
    if not cat or not m: abort(404)
    sets_data = get_match_sets(cat_id, match_id)
    p_by_num, all_sets, total_stats = _build_stats(cat_id, match_id, sets_data)
    match_minutes       = compute_match_minutes(cat_id, match_id, sets_data)
    setter_stats        = compute_match_setter_stats(cat_id, match_id, sets_data)
    attack_zone_stats   = compute_match_attack_zone_stats(cat_id, match_id, sets_data)
    rotation_stats      = compute_match_rotation_stats(cat_id, match_id, sets_data)
    continuity_stats    = compute_match_continuity(cat_id, match_id, sets_data)
    return render_template('stats.html', cat=cat, match=m,
                           sets=all_sets, total_stats=total_stats, p_by_num=p_by_num,
                           match_minutes=match_minutes, setter_stats=setter_stats,
                           attack_zone_stats=attack_zone_stats,
                           rotation_stats=rotation_stats,
                           continuity_stats=continuity_stats,
                           zone_layout=ZONE_LAYOUT, zone_names=ZONE_NAMES)

# ─────────────────────────────────────────────────────────────
# EXPORT AI ANALYSIS
# ─────────────────────────────────────────────────────────────
def build_ai_export(cat_id, match_id):
    """
    Costruisce il testo strutturato da incollare in Claude per l'analisi.
    I giocatori sono identificati SOLO dal numero di maglia (nessun nome).
    """
    cat     = get_category(cat_id)
    matches = get_matches(cat_id)
    m       = next((x for x in matches if x['id']==match_id), None)
    if not cat or not m:
        return None

    ruleset = m.get('ruleset','standard')
    rule_desc = "PGS (set a 17 pt, 5 set, nessun tie-break)" if ruleset=='pgs' \
                else "Standard FIPAV (set 1-4 a 25 pt, 5° set tie-break a 15 pt)"

    sets_data = get_match_sets(cat_id, match_id)
    sd_by_num = {sn: sd for sn, sd, _state in sets_data}
    p_by_num, all_sets, total_stats = _build_stats(cat_id, match_id, sets_data)
    match_minutes = compute_match_minutes(cat_id, match_id, sets_data)

    lines = []
    lines.append("=== ANALISI PARTITA PALLAVOLO — DATI ANONIMI ===")
    lines.append("")
    lines.append(f"Categoria:   {cat.get('name','')} — Stagione {cat.get('season','')}")
    lines.append(f"Avversario:  {m['opponent']}")
    lines.append(f"Data:        {m.get('date','')}" + (f" ore {m['time']}" if m.get('time') else ""))
    lines.append(f"Campo:       {'Casa' if m.get('home') else 'Trasferta'}")
    lines.append(f"Competizione:{m.get('competition','—')}")
    lines.append(f"Regolamento: {rule_desc}")
    if m.get('status') == 'completed':
        esito_match = " (VITTORIA)" if m['sets_us'] > m['sets_them'] else " (SCONFITTA)"
    else:
        esito_match = " (IN CORSO)"
    lines.append(f"Risultato:   {m['sets_us']} — {m['sets_them']} set" + esito_match)
    lines.append("")

    # ── Dettaglio per set ──────────────────────────────────────
    lines.append("─── DETTAGLIO SET ───────────────────────────────────────")
    for s in all_sets:
        st    = s['state']
        snum  = s['number']
        mins  = s.get('minutes', {})
        esito = "VINTO" if st['winner']=='us' else ("PERSO" if st['winner'] else "IN CORSO")

        lines.append(f"\nSET {snum}: {st['score_us']}-{st['score_them']} [{esito}]")

        # Chi era in campo (formazione iniziale del set)
        sd_raw = sd_by_num.get(snum)
        if sd_raw:
            lineup = sd_raw.get('lineup', [])
            lines.append(f"  Formazione iniziale (P1→P6): {' '.join(f'#{n}' for n in lineup)}")
            lines.append(f"  Servizio iniziale: {'Noi' if sd_raw.get('first_serve')=='us' else 'Avversario'}")

            # Sostituzioni ufficiali (esclusi cambi libero)
            subs = [e for e in sd_raw.get('events',[]) if e.get('type')=='substitution']
            if subs:
                sub_txt = ', '.join(f"#{e['player_out']}→#{e['player_in']} ({e.get('timestamp','')})"
                                    for e in subs)
                lines.append(f"  Sostituzioni ({len(subs)}): {sub_txt}")
            else:
                lines.append(f"  Sostituzioni: nessuna")

            # Cambi palleggiatore in corsa
            setter_changes = [e for e in sd_raw.get('events',[]) if e.get('type')=='setter_change']
            if setter_changes:
                sc_txt = ', '.join(f"#{e['setter_num']} ({e.get('timestamp','')})"
                                   for e in setter_changes)
                lines.append(f"  Cambio palleggiatore: {sc_txt}")
            lib_changes = [e for e in sd_raw.get('events',[]) if e.get('type')=='libero_exchange']
            if lib_changes:
                lib_txt = ', '.join(
                    f"#{e.get('n1',e.get('libero_num','?'))}↔#{e.get('n2',e.get('centrale_num','?'))} ({e.get('timestamp','')})"
                    for e in lib_changes
                )
                lines.append(f"  Cambi libero ({len(lib_changes)}, non contano come sost.): {lib_txt}")

            # Timeout
            to_us   = sum(1 for e in sd_raw.get('events',[]) if e.get('type')=='timeout' and e.get('side')=='us')
            to_them = sum(1 for e in sd_raw.get('events',[]) if e.get('type')=='timeout' and e.get('side')=='them')
            lines.append(f"  Timeout: noi={to_us}, avversario={to_them}")

            # Statistiche giocatori per questo set
            ps = s['player_stats']
            if ps:
                lines.append(f"  Statistiche giocatori:")
                for pnum in sorted(ps.keys()):
                    p  = ps[pnum]
                    mn = mins.get(pnum, 0)
                    parts = [f"#{pnum} ({mn}')"]

                    if p.get('rec_total',0) > 0:
                        parts.append(
                            f"Ric: R+={p['rec_pos']} R-={p['rec_neg']} RE={p['rec_err']}"
                            f" Pos={p['rec_positivity']}% Eff={p['rec_efficiency']}%"
                        )
                    if p.get('att_total',0) > 0:
                        parts.append(
                            f"Att: Kill={p['attack_kill']} Cont={p['attack_cont']}"
                            f" Err={p['attack_err']} Mur={p['attack_blk']}"
                            f" Pos={p['att_positivity']}% Eff={p['att_efficiency']}%"
                        )
                    sv = p.get('serve_ace',0) + p.get('serve_err',0)
                    if sv > 0:
                        parts.append(f"Serv: Ace={p['serve_ace']} Err={p['serve_err']}")
                    if p.get('block_pt',0) + p.get('block_err',0) + p.get('block_touch',0) > 0:
                        parts.append(f"Muro: Pt={p['block_pt']} Err={p['block_err']} Camp={p.get('block_touch',0)}")
                    if p.get('def_pos',0) + p.get('def_err',0) > 0:
                        parts.append(f"Dif: Pos={p['def_pos']} Err={p['def_err']}")
                    parts.append(f"+Pt={p['pts_scored']} -Pt={p['pts_lost']}")
                    lines.append("    " + " | ".join(parts))

    # ── Totali partita ────────────────────────────────────────
    lines.append("")
    lines.append("─── TOTALI PARTITA ──────────────────────────────────────")

    all_players = sorted(total_stats.keys())
    for pnum in all_players:
        p   = total_stats[pnum]
        mn  = match_minutes.get(pnum, 0)
        row = [f"#{pnum} — {mn}' totali"]

        if p.get('rec_total',0) > 0:
            row.append(
                f"RICEZIONE: R+={p['rec_pos']} R-={p['rec_neg']} RE={p['rec_err']}"
                f" | Positività={p['rec_positivity']}% Efficienza={p['rec_efficiency']}%"
                f" (su {p['rec_total']} ric.)"
            )
        if p.get('att_total',0) > 0:
            row.append(
                f"ATTACCO: Kill={p['attack_kill']} Cont={p['attack_cont']}"
                f" Err={p['attack_err']} Mur={p['attack_blk']}"
                f" | Positività={p['att_positivity']}% Efficienza={p['att_efficiency']}%"
                f" (su {p['att_total']} att.)"
            )
        sv = p.get('serve_ace',0) + p.get('serve_err',0)
        if sv > 0:
            row.append(f"SERVIZIO: Ace={p['serve_ace']} Err={p['serve_err']}")
        if p.get('block_pt',0)+p.get('block_err',0)+p.get('block_touch',0) > 0:
            row.append(f"MURO: Pt={p['block_pt']} Err={p['block_err']} Camp={p.get('block_touch',0)}")
        if p.get('def_pos',0)+p.get('def_err',0) > 0:
            row.append(f"DIFESA: Pos={p['def_pos']} Err={p['def_err']}")
        row.append(f"PUNTI: +{p['pts_scored']} / -{p['pts_lost']}")
        lines.append("\n  ".join(row))
        lines.append("")

    # ── Continuità del gioco ──────────────────────────────────
    cont = compute_match_continuity(cat_id, match_id, sets_data)
    ct   = cont['team']
    if ct.get('rpos', 0) > 0:
        lines.append("─── CONTINUITÀ DEL GIOCO (CAMBIO PALLA) ─────────────────")
        lines.append(f"  Ricezioni positive (R+) totali: {ct['rpos']}")
        lines.append(f"  → Conversione (Kill dopo R+): "
                     f"{ct['kills']}/{ct['rpos']} = {ct['conv_pct']}%"
                     f"  (riferimento buono ≥30%)")
        lines.append(f"  → Continuità (Kill+Cont dopo R+): "
                     f"{ct['kills']+ct['cont']}/{ct['rpos']} = {ct['cont_pct']}%"
                     f"  (riferimento buono ≥70%)")
        lines.append(f"  → Dispersione (Errore dopo R+): "
                     f"{ct['err']}/{ct['rpos']} = {ct['disp_pct']}%"
                     f"  (riferimento: preoccupante >20%)")
        lines.append(f"  → R+ senza attacco registrato: {ct['no_attack']}")
        lines.append("")
        if cont['by_receiver']:
            lines.append("  Per ricettore (min 3 R+):")
            for n, d in sorted(cont['by_receiver'].items(),
                               key=lambda x: x[1]['rpos'], reverse=True):
                if d['rpos'] >= 3:
                    lines.append(
                        f"    #{n}: {d['rpos']} R+ → "
                        f"Conv={d['conv_pct']}% "
                        f"Cont={d['cont_pct']}% "
                        f"Disp={d['disp_pct']}%"
                    )
        if cont['by_attacker']:
            lines.append("  Per attaccante (min 3 alzate ricevute):")
            for n, d in sorted(cont['by_attacker'].items(),
                               key=lambda x: x[1]['rpos_received'], reverse=True):
                if d['rpos_received'] >= 3:
                    lines.append(
                        f"    #{n}: {d['rpos_received']} att. da R+ → "
                        f"Conv={d['conv_pct']}% "
                        f"Disp={d['disp_pct']}%"
                    )
        lines.append("")

    # ── Analisi per rotazione ──────────────────────────────────
    rot_stats = compute_match_rotation_stats(cat_id, match_id, sets_data)
    if rot_stats and any(r['pts_scored']+r['pts_lost'] > 0
                         for r in rot_stats['rotations'].values()):
        lines.append("─── ANALISI PER ROTAZIONE ───────────────────────────────")
        sm = rot_stats['summary']
        if sm.get('so_pct') is not None:
            lines.append(f"  Side-out (punto in ricezione): "
                         f"{sm['so_won']}/{sm['so_tot']} = {sm['so_pct']}%"
                         f"  (riferimento: buono ≥55%)")
        if sm.get('brk_pct') is not None:
            lines.append(f"  Break point (punto al servizio): "
                         f"{sm['brk_won']}/{sm['brk_tot']} = {sm['brk_pct']}%"
                         f"  (riferimento: buono ≥35%)")
        lines.append("")
        lines.append("  Rotazione | +Pt | -Pt | Saldo | SO% | Break%")
        lines.append("  " + "-"*55)
        for slot in ROT_ORDER:
            r = rot_stats['rotations'][slot]
            tot = r['pts_scored'] + r['pts_lost']
            if tot == 0:
                continue
            flag = ""
            if slot == sm.get('best_rot'):  flag = " ← MIGLIORE"
            if slot == sm.get('worst_rot'): flag = " ← CRITICA"
            so_s  = f"{r['so_pct']}%"  if r['so_pct']  is not None else "—"
            brk_s = f"{r['brk_pct']}%" if r['brk_pct'] is not None else "—"
            lines.append(
                f"  {ROT_LABELS[slot]:<38} "
                f"+{r['pts_scored']:2} -{r['pts_lost']:2} "
                f"[{'+' if r['saldo']>=0 else ''}{r['saldo']:3}] "
                f"SO={so_s:6} Brk={brk_s}{flag}"
            )
        lines.append("")

    # ── Prompt di analisi ─────────────────────────────────────
    lines.append("─── RICHIESTA DI ANALISI ────────────────────────────────")
    lines.append("""
Sei un assistente tecnico di pallavolo. Analizza in modo dettagliato \
questa partita seguendo esattamente la struttura indicata.
I giocatori sono identificati SOLO dal numero di maglia.

Legenda dati:
  Ricezione — R+: permette attacco | R-: non permette attacco | RE: ace subito
  Ricezione — Pos%=(R++R-)/Tot×100 | Eff%=(R++R--RE)/Tot×100
  Attacco   — Kill: punto diretto | Cont: in campo senza punto | AE: errore | AB: murato
  Attacco   — Pos%=(Kill+Cont)/Tot×100 | Eff%=(Kill+Cont-AE-AB)/Tot×100

════════════════════════════════════════════════════════════
SEZIONE 1 — ANALISI SET PER SET
════════════════════════════════════════════════════════════
Per OGNI set disputato scrivi un paragrafo con:

a) PUNTEGGIO E ESITO — chi ha vinto il set e con che divario.

b) PUNTO CRITICO — identifica il momento decisivo del set.
   Guarda i dati: in quale rotazione/momento i punti si sono
   accumulati o dispersi? Se ci sono stati timeout, erano necessari?
   Se c'è stato un cambio di servizio critico, evidenzialo.

c) RICEZIONE IN QUESTO SET — chi ha ricevuto? Con quale Pos% ed Eff%?
   Il livello è sufficiente per costruire il gioco?
   (Riferimento: Pos% buona ≥60%, Eff% buona ≥30%)

d) ATTACCO IN QUESTO SET — chi ha attaccato? Con quale Eff%?
   C'è stato un terminale dominante o il carico era distribuito?
   (Riferimento: Pos% buona ≥50%, Eff% buona ≥25%)

e) SERVIZIO — ace e errori in questo set. Il servizio ha creato
   rotture di ritmo o ha regalato punti agli avversari?

════════════════════════════════════════════════════════════
SEZIONE 2 — CONFRONTO TRA SET (cosa è cambiato)
════════════════════════════════════════════════════════════
Confronta i set tra loro e rispondi a:

- La ricezione è migliorata o peggiorata nel corso della partita?
  Chi ha mantenuto la costanza e chi ha avuto cali?

- L'efficienza in attacco è cambiata? Ci sono stati set in cui
  la squadra ha attaccato peggio? A cosa è imputabile (ricezione
  bassa che non permetteva costruzione, errori individuali, stanchezza)?

- Il servizio: la tendenza è stata aggressiva-con-rischio o
  sicura-senza-pressione? È cambiata tra i set?

- Le sostituzioni hanno avuto effetto positivo, negativo o neutro?
  Confronta i dati del titolare con quelli del subentrato se disponibili.

- Qual è stato il set migliore della squadra? E il peggiore?
  Cosa ha fatto la differenza concretamente?

════════════════════════════════════════════════════════════
SEZIONE 3 — GIOCATORI MIGLIORI E PEGGIORI PER REPARTO
════════════════════════════════════════════════════════════
Valuta ogni reparto e indica il migliore e il peggiore in base ai dati.
Usa i numeri di maglia. Sii specifico e cita sempre i valori.

RICEZIONE
  → Migliore ricettore: numero e motivazione (Pos%, Eff%, volume)
  → Peggiore ricettore: numero e motivazione
  → Considerazione generale sul reparto ricezione

ATTACCO
  → Terminale più efficace: numero, Kill totali, Eff%
  → Terminale meno efficace (se ha avuto volume sufficiente)
  → Distribuzione del carico: era equilibrata o squilibrata?

SERVIZIO
  → Miglior battitore: numero, rapporto ace/errori
  → Chi ha pesato di più sugli errori?

MURO E DIFESA
  → Chi ha contribuito di più a muro?
  → Considerazioni sulla fase difensiva

════════════════════════════════════════════════════════════
SEZIONE 4 — CONTINUITÀ DEL GIOCO (CAMBIO PALLA)
════════════════════════════════════════════════════════════
I dati CONTINUITÀ DEL GIOCO mostrano cosa succede dopo ogni ricezione
positiva (R+): la squadra finalizza, mantiene il pallone o spreca?

Legenda:
  Conversione% = Kill dopo R+ / R+ totali × 100   (si chiude il punto)
  Continuità%  = (Kill+Cont) dopo R+ / R+ totali  (si mantiene il gioco)
  Dispersione% = Errori dopo R+ / R+ totali        (si spreca la R+)

Analizza e rispondi a:

a) TASSO DI CONVERSIONE — la squadra finalizza quando riceve bene?
   (Riferimento: buono ≥30%. Sotto il 20% c'è un problema di finalizzazione.)
   Chi tra i ricettori genera più conversioni? Chi le disperde?

b) TASSO DI CONTINUITÀ — la squadra mantiene il pallone in gioco?
   (Riferimento: buono ≥70%. Sotto il 50% indica attacchi precipitosi o fuori controllo.)

c) TASSO DI DISPERSIONE — quante R+ si trasformano in errori?
   (Riferimento: preoccupante >20%. Significa che una buona ricezione
   viene sprecata da una scelta d'attacco sbagliata o da un errore tecnico.)

d) ANALISI PER ATTACCANTE — quale attaccante converte meglio le alzate
   ricevute dopo R+? Chi spreca di più? Questo dato separa chi è efficace
   dalla ricezione da chi lo è solo in condizioni ideali.

e) IMPLICAZIONE — se Conversione% è bassa ma Continuità% è alta,
   la squadra palleggia ma non finalizza (problema di potenza/tecnica
   d'attacco). Se entrambe sono basse, c'è un problema strutturale
   nel sistema di cambio palla.

════════════════════════════════════════════════════════════
SEZIONE 5 — ANALISI PER ROTAZIONE
════════════════════════════════════════════════════════════
I dati ANALISI PER ROTAZIONE contengono i punti fatti/persi per ciascuna
delle 6 rotazioni (identificate dallo slot del palleggiatore).

Analizza e rispondi a:

a) ROTAZIONE MIGLIORE — quale rotazione ha prodotto il saldo positivo più alto?
   Cosa caratterizza quella rotazione (chi attacca, chi riceve, chi serve)?

b) ROTAZIONE CRITICA — quale rotazione ha il saldo più negativo?
   È un problema di ricezione in quella posizione, di attacco, o di servizio?
   Questa rotazione va affrontata in allenamento con priorità.

c) SIDE-OUT % — la squadra riesce a togliere il servizio all'avversario?
   (Riferimento: buono ≥55%. Sotto il 45% è un problema grave di ricezione/attacco.)

d) BREAK POINT % — la squadra segna punti al proprio servizio?
   (Riferimento: buono ≥35%. Sotto il 25% significa che il servizio non crea pressione.)

e) IMPLICAZIONE TATTICA — suggerisci 1-2 aggiustamenti concreti basati
   sulla rotazione critica identificata.

════════════════════════════════════════════════════════════
SEZIONE 6 — SUGGERIMENTI TATTICI PER LA PROSSIMA PARTITA
════════════════════════════════════════════════════════════
Fornisci esattamente 5 suggerimenti concreti basati sui dati osservati
(inclusi i dati di rotazione).
Ogni suggerimento deve:
  - Indicare il PROBLEMA specifico emerso dai dati (con numeri)
  - Indicare la SOLUZIONE pratica (cosa fare in allenamento o in partita)
  - Essere realizzabile con una squadra della categoria indicata

Formato per ogni suggerimento:
  [AREA] Problema: ... → Soluzione: ...

Chiudi con un giudizio sintetico in 2-3 righe:
"GIUDIZIO COMPLESSIVO — ..."

Nota: se i dati di un reparto sono scarsi (pochi eventi registrati),
segnalalo e concentrati su quelli con volume sufficiente.
""")
    return "\n".join(lines)

@app.route('/c/<cat_id>/partita/<match_id>/esporta-ai')
def esporta_ai(cat_id, match_id):
    """Pagina con il testo da copiare in Claude per l'analisi."""
    cat = get_category(cat_id)
    matches = get_matches(cat_id)
    m = next((x for x in matches if x['id']==match_id), None)
    if not cat or not m: abort(404)
    export_text = build_ai_export(cat_id, match_id)
    return render_template('esporta_ai.html', cat=cat, match=m,
                           export_text=export_text)

@app.route('/c/<cat_id>/partita/<match_id>/report')
def report_view(cat_id, match_id):
    cat = get_category(cat_id)
    matches = get_matches(cat_id)
    m = next((x for x in matches if x['id']==match_id), None)
    if not cat or not m: abort(404)
    sets_data = get_match_sets(cat_id, match_id)
    p_by_num, all_sets, total_stats = _build_stats(cat_id, match_id, sets_data)
    match_minutes       = compute_match_minutes(cat_id, match_id, sets_data)
    setter_stats        = compute_match_setter_stats(cat_id, match_id, sets_data)
    attack_zone_stats   = compute_match_attack_zone_stats(cat_id, match_id, sets_data)
    rotation_stats      = compute_match_rotation_stats(cat_id, match_id, sets_data)
    continuity_stats    = compute_match_continuity(cat_id, match_id, sets_data)
    score_timeline      = compute_match_score_timeline(cat_id, match_id, sets_data)
    return render_template('report.html', cat=cat, match=m, club=get_club(),
                           sets=all_sets, total_stats=total_stats, p_by_num=p_by_num,
                           match_minutes=match_minutes, setter_stats=setter_stats,
                           attack_zone_stats=attack_zone_stats,
                           rotation_stats=rotation_stats,
                           continuity_stats=continuity_stats,
                           score_timeline=score_timeline,
                           zone_names=ZONE_NAMES,
                           generated=datetime.now().strftime('%d/%m/%Y %H:%M'))

# ─────────────────────────────────────────────────────────────
# ROUTES — CONFRONTO CATEGORIE
# ─────────────────────────────────────────────────────────────
@app.route('/confronto')
def confronto():
    club = get_club()
    cats = get_categories()
    data = []
    for c in cats:
        ss = category_season_stats(c['id'])
        ts_info = ss['p_by_num'].get(ss['top_scorer']) if ss['top_scorer'] else None
        data.append({'cat':c, 'stats':ss, 'top_scorer_info':ts_info})
    return render_template('confronto.html', club=club, data=data)

@app.route('/c/<cat_id>/partita/<match_id>/report-sintetico')
def report_sintetico(cat_id, match_id):
    """Scheda statistica sintetica stile Lega Volley — una pagina A4 orizzontale."""
    cat = get_category(cat_id)
    matches = get_matches(cat_id)
    m = next((x for x in matches if x['id']==match_id), None)
    if not cat or not m: abort(404)

    p_by_num, all_sets, total_stats = _build_stats(cat_id, match_id)

    RAW_KEYS = ('serve_ace','serve_err','attack_kill','attack_cont','attack_err',
                'attack_blk','block_pt','block_err','block_touch','rec_pos','rec_neg','rec_err',
                'def_pos','def_err','pts_scored','pts_lost')

    # Set in cui ogni giocatore ha partecipato (dict pnum → list di numeri set)
    _psets_tmp = {}
    for s in all_sets:
        for pnum in s['player_stats']:
            _psets_tmp.setdefault(pnum, set()).add(s['number'])
    player_sets = {pnum: sorted(sn) for pnum, sn in _psets_tmp.items()}

    # Aggiunge rec_prf (perfezione: R+ / tot) a tutti i player stats
    for pdata in total_stats.values():
        rt = pdata.get('rec_total', 0)
        pdata['rec_prf'] = round(pdata['rec_pos'] / rt * 100, 1) if rt > 0 else None

    # Totali per set (aggregati su tutta la squadra)
    set_totals = []
    for s in all_sets:
        team_raw = {k: 0 for k in RAW_KEYS}
        for pdata in s['player_stats'].values():
            for k in RAW_KEYS:
                team_raw[k] += pdata.get(k, 0)
        enriched = enrich_stats({'t': team_raw})['t']
        rt = enriched.get('rec_total', 0)
        enriched['rec_prf'] = round(enriched['rec_pos'] / rt * 100, 1) if rt > 0 else None
        set_totals.append({'number': s['number'], 'state': s['state'], 'stats': enriched})

    # Totali globali squadra
    team_raw = {k: 0 for k in RAW_KEYS}
    for pdata in total_stats.values():
        for k in RAW_KEYS:
            team_raw[k] += pdata.get(k, 0)
    team_totals = enrich_stats({'t': team_raw})['t']
    rt = team_totals.get('rec_total', 0)
    team_totals['rec_prf'] = round(team_totals['rec_pos'] / rt * 100, 1) if rt > 0 else None

    sorted_players = sorted(total_stats.keys())

    return render_template('report_sintetico.html',
                           cat=cat, match=m, club=get_club(),
                           p_by_num=p_by_num,
                           total_stats=total_stats,
                           player_sets=player_sets,
                           set_totals=set_totals,
                           team_totals=team_totals,
                           all_sets=all_sets,
                           sorted_players=sorted_players,
                           generated=datetime.now().strftime('%d/%m/%Y %H:%M'))


@app.route('/confronto/report')
def confronto_report():
    """PDF confronto tutte le categorie."""
    club = get_club()
    cats = get_categories()
    data = []
    for c in cats:
        ss  = category_season_stats(c['id'])
        ts  = ss['p_by_num'].get(ss['top_scorer']) if ss['top_scorer'] else None
        # top 5 marcatori per categoria
        top5 = sorted(ss['player_season'].items(),
                      key=lambda x: x[1].get('pts_scored',0), reverse=True)[:5]
        data.append({'cat':c, 'stats':ss, 'top_scorer_info':ts, 'top5':top5})
    return render_template('report_confronto.html', club=club, data=data,
                           generated=datetime.now().strftime('%d/%m/%Y %H:%M'))

# ─────────────────────────────────────────────────────────────
# ROUTES — REPORT STAGIONE CATEGORIA
# ─────────────────────────────────────────────────────────────
@app.route('/c/<cat_id>/report-stagione')
def report_stagione(cat_id):
    """PDF stagione completa: tutte le partite + totali per giocatore."""
    cat = get_category(cat_id)
    if not cat: abort(404)
    club     = get_club()
    matches  = get_matches(cat_id)
    players  = get_players(cat_id)
    p_by_num = {p['number']: p for p in players}
    matches_sorted = sorted(matches, key=lambda m: m.get('date',''))

    # Per ogni partita completata o in corso, aggrega stats
    match_reports = []
    season_raw = {}
    for m in matches_sorted:
        if m.get('status') not in ('completed','ongoing'):
            continue
        m_sets = get_match_sets(cat_id, m['id'])
        p_by_num_m, all_sets, total_stats = _build_stats(cat_id, m['id'], m_sets)
        # ri-accumula raw per stagione (senza enrich per sommare correttamente)
        for sn, sd, state in m_sets:
            for pnum, pdata in compute_player_stats(sd).items():
                if pnum not in season_raw:
                    season_raw[pnum] = dict(pdata)
                else:
                    for k,v in pdata.items():
                        season_raw[pnum][k] = season_raw[pnum].get(k,0)+v
        match_reports.append({
            'match':       m,
            'total_stats': total_stats,
            'all_sets':    all_sets,
        })

    season_stats = enrich_stats(season_raw)
    return render_template('report_stagione.html',
                           cat=cat, club=club, p_by_num=p_by_num,
                           match_reports=match_reports,
                           season_stats=season_stats,
                           generated=datetime.now().strftime('%d/%m/%Y %H:%M'))

# ─────────────────────────────────────────────────────────────
# ROUTES — SCHEDA GIOCATORE
# ─────────────────────────────────────────────────────────────
@app.route('/c/<cat_id>/giocatore/<int:player_num>/report')
def report_giocatore(cat_id, player_num):
    """PDF scheda individuale di un giocatore su tutta la stagione."""
    cat = get_category(cat_id)
    if not cat: abort(404)
    club    = get_club()
    players = get_players(cat_id)
    player  = next((p for p in players if p['number'] == player_num), None)
    if not player: abort(404)

    matches = sorted(get_matches(cat_id), key=lambda m: m.get('date',''))
    match_data = []
    season_raw = {}

    for m in matches:
        if m.get('status') not in ('completed','ongoing'):
            continue
        match_raw = {}
        sets_detail = []
        for sn, sd, state in get_match_sets(cat_id, m['id']):
            ps = compute_player_stats(sd)
            if player_num in ps:
                pdata = ps[player_num]
                sets_detail.append({
                    'number':    sn,
                    'score_us':  state['score_us'] if state else 0,
                    'score_them':state['score_them'] if state else 0,
                    'stats':     enrich_stats({player_num: pdata})[player_num],
                })
                for k,v in pdata.items():
                    match_raw[k] = match_raw.get(k,0)+v
                    season_raw[k] = season_raw.get(k,0)+v

        if match_raw:
            match_data.append({
                'match':       m,
                'stats':       enrich_stats({player_num: match_raw})[player_num],
                'sets_detail': sets_detail,
            })

    season_stats = enrich_stats({player_num: season_raw})[player_num] if season_raw else None
    return render_template('report_giocatore.html',
                           cat=cat, club=club, player=player,
                           match_data=match_data,
                           season_stats=season_stats,
                           generated=datetime.now().strftime('%d/%m/%Y %H:%M'))

# ─────────────────────────────────────────────────────────────
# ROUTES — BACKUP / RIPRISTINO
# ─────────────────────────────────────────────────────────────
@app.route('/esporta-backup')
def esporta_backup():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in ROOT.rglob('*'):
            if f.is_file():
                zf.write(f, f.relative_to(ROOT.parent))
    buf.seek(0)
    filename = f"volleystat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    return send_file(buf, mimetype='application/zip',
                     as_attachment=True, download_name=filename)


@app.route('/importa-backup', methods=['POST'])
def importa_backup():
    uploaded = request.files.get('backup')
    if not uploaded or not uploaded.filename.lower().endswith('.zip'):
        abort(400, 'È richiesto un file .zip')

    buf = io.BytesIO(uploaded.read())
    try:
        zf = zipfile.ZipFile(buf, 'r')
    except zipfile.BadZipFile:
        abort(400, 'File ZIP non valido')

    with zf:
        for member in zf.namelist():
            parts = Path(member).parts
            if not parts or parts[0] != 'data' or '..' in parts:
                abort(400, 'Archivio non compatibile: struttura directory non riconosciuta')

        if ROOT.exists():
            backup_path = Path(f"data_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            shutil.copytree(ROOT, backup_path)
            shutil.rmtree(ROOT)

        zf.extractall(ROOT.parent)

    ensure_root()
    return redirect(url_for('home'))


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import socket
    port = 8000
    def get_local_ip():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return '—'
    local_ip = get_local_ip()
    def open_browser():
        time.sleep(1.2)
        webbrowser.open(f'http://127.0.0.1:{port}')
    print(f"""
╔══════════════════════════════════════════════╗
║   VolleyStat  —  Statistiche VB              ║
║   Locale:  http://127.0.0.1:{port}              ║
║   Tablet:  http://{local_ip}:{port}
║   Ctrl+C per uscire                          ║
╚══════════════════════════════════════════════╝
""")
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(host='0.0.0.0', port=port, debug=False)
