"""
VolleyStat — Funzioni di calcolo statistico.
Tutte le funzioni prendono `sd` (set data dict) come input.
Nessuna dipendenza da Flask o dal layer di storage.
"""

# ─────────────────────────────────────────────────────────────
# COSTANTI DI DOMINIO
# ─────────────────────────────────────────────────────────────

# Layout zone FIPAV sul campo (per rendering SVG)
# Vista dalla nostra panchina: zona 1 = dx dietro, senso antiorario
#  ┌───────────────────┐  ← rete
#  │  4  │  3  │  2   │  ← prima linea
#  │  5  │  6  │  1   │  ← seconda linea
#  └───────────────────┘  ← fondo campo
ZONE_LAYOUT = {
    # zona: (col, row)  col=0..2 sinistra→destra, row=0..1 davanti→dietro
    4: (0, 0), 3: (1, 0), 2: (2, 0),
    5: (0, 1), 6: (1, 1), 1: (2, 1),
}
ZONE_NAMES = {
    1:'Destra Dietro', 2:'Destra Davanti', 3:'Centro Davanti',
    4:'Sinistra Davanti', 5:'Sinistra Dietro', 6:'Centro Dietro',
}

# Coordinate fisiche zona → (colonna, riga)  col 0=sx, riga 0=davanti
ZONE_COORDS = {
    4:(0,0), 3:(1,0), 2:(2,0),
    5:(0,1), 6:(1,1), 1:(2,1),
}

# Slot rotazione → zona FIPAV attesa.
# L'array lineup è mantenuto "per zona": lineup[i-1] è il giocatore in zona i
# (vedi set.html) e la rotazione cur[1:]+cur[:1] preserva l'invariante
# (chi è in zona 2 passa in zona 1 a battere). Quindi slot == zona.
SLOT_TO_ZONE = {1:1, 2:2, 3:3, 4:4, 5:5, 6:6}

# Zona funzionale per ruolo in prima linea (zone 2, 3, 4):
# indipendentemente dalla rotazione i giocatori si spostano nella propria
# posizione specializzata prima di attaccare.
ROLE_FRONT_ZONE = {'C': 3, 'B': 4, 'O': 2}

# Rotazioni identificate dalla zona del palleggiatore (convenzione P1..P6).
# Ordine temporale dopo ogni cambio palla: P1 → P6 → P5 → P4 → P3 → P2.
ROT_LABELS = {
    1: 'P1 — Pall. in Z1 (batte)',
    2: 'P2 — Pall. in Z2 (davanti dx)',
    3: 'P3 — Pall. in Z3 (centro rete)',
    4: 'P4 — Pall. in Z4 (davanti sx)',
    5: 'P5 — Pall. in Z5 (dietro sx)',
    6: 'P6 — Pall. in Z6 (centro dietro)',
}
ROT_SHORT = {1:'P1',2:'P2',3:'P3',4:'P4',5:'P5',6:'P6'}
ROT_ORDER = [1, 6, 5, 4, 3, 2]   # ordine temporale delle rotazioni nel set


# ─────────────────────────────────────────────────────────────
# STATISTICHE GIOCATORE
# ─────────────────────────────────────────────────────────────

def compute_player_stats(sd):
    stats = {}
    def g(n):
        if n not in stats:
            stats[n] = dict(
                # Servizio
                serve_ace=0, serve_err=0,
                # Attacco: kill, continua, errore, murato, a rete (nuovi codici)
                attack_kill=0, attack_cont=0, attack_err=0, attack_blk=0, attack_net=0,
                # Muro: punto, errore, tocco (palla resta in gioco)
                block_pt=0, block_err=0, block_touch=0,
                # Ricezione: positiva (permette att.), negativa, ace subito, in out (nuovi codici)
                rec_pos=0, rec_neg=0, rec_err=0, rec_out=0,
                # Difesa
                def_pos=0, def_err=0,
                # Falli (nuovi codici): trattenuta, doppia, salto 2ª→1ª linea
                fault_ft=0, fault_fd=0, fault_fs=0,
                # Alzate ricevute per tipo (nuovi codici, solo informativo qui —
                # vedi compute_setter_distribution_stats per le conversioni)
                set_p1=0, set_p2=0, set_pc=0,
                # Punti
                pts_scored=0, pts_lost=0,
            )
        return stats[n]

    AM = {
        'S':  lambda p: g(p).update(serve_ace=g(p)['serve_ace']+1,    pts_scored=g(p)['pts_scored']+1),
        'SE': lambda p: g(p).update(serve_err=g(p)['serve_err']+1,    pts_lost=g(p)['pts_lost']+1),
        'A':  lambda p: g(p).update(attack_kill=g(p)['attack_kill']+1, pts_scored=g(p)['pts_scored']+1),
        'AN': lambda p: g(p).update(attack_cont=g(p)['attack_cont']+1),
        'AE': lambda p: g(p).update(attack_err=g(p)['attack_err']+1,  pts_lost=g(p)['pts_lost']+1),
        'AR': lambda p: g(p).update(attack_net=g(p)['attack_net']+1,  pts_lost=g(p)['pts_lost']+1),
        'AB': lambda p: g(p).update(attack_blk=g(p)['attack_blk']+1,  pts_lost=g(p)['pts_lost']+1),
        'ABN':lambda p: g(p).update(attack_blk=g(p)['attack_blk']+1),   # murato, palla in gioco — no punto perso
        'B':  lambda p: g(p).update(block_pt=g(p)['block_pt']+1,      pts_scored=g(p)['pts_scored']+1),
        'BE': lambda p: g(p).update(block_err=g(p)['block_err']+1,    pts_lost=g(p)['pts_lost']+1),
        'BN': lambda p: g(p).update(block_touch=g(p)['block_touch']+1),  # muro, palla in gioco — no punto
        'R+': lambda p: g(p).update(rec_pos=g(p)['rec_pos']+1),
        'R-': lambda p: g(p).update(rec_neg=g(p)['rec_neg']+1),
        'RE': lambda p: g(p).update(rec_err=g(p)['rec_err']+1,        pts_lost=g(p)['pts_lost']+1),
        'RO': lambda p: g(p).update(rec_out=g(p)['rec_out']+1,        pts_lost=g(p)['pts_lost']+1),
        'D':  lambda p: g(p).update(def_pos=g(p)['def_pos']+1),
        'DE': lambda p: g(p).update(def_err=g(p)['def_err']+1,        pts_lost=g(p)['pts_lost']+1),
        'FT': lambda p: g(p).update(fault_ft=g(p)['fault_ft']+1,      pts_lost=g(p)['pts_lost']+1),
        'FD': lambda p: g(p).update(fault_fd=g(p)['fault_fd']+1,      pts_lost=g(p)['pts_lost']+1),
        'FS': lambda p: g(p).update(fault_fs=g(p)['fault_fs']+1,      pts_lost=g(p)['pts_lost']+1),
        'P1': lambda p: g(p).update(set_p1=g(p)['set_p1']+1),
        'P2': lambda p: g(p).update(set_p2=g(p)['set_p2']+1),
        'PC': lambda p: g(p).update(set_pc=g(p)['set_pc']+1),
    }
    for ev in sd.get('events',[]):
        if ev.get('type') not in ('point','stat'):
            continue
        player = ev.get('player')
        if player is None:
            continue
        action = ev.get('action','')
        if action in AM:
            AM[action](player)
    return stats


def pct(num, den):
    """Percentuale arrotondata a 1 decimale, None se nessun dato."""
    if den == 0:
        return None
    return round(num / den * 100, 1)


def enrich_stats(raw_stats):
    """Aggiunge campi derivati (positività/efficienza) ad ogni giocatore."""
    result = {}
    for pnum, s in raw_stats.items():
        e = dict(s)
        # ── Ricezione ──
        # Positività = (R+ + R−) / Tot   → R+ e R− sono entrambi valori positivi
        # Efficienza = (R+ + R− − RE − RO) / Tot → RE e RO (ric. in out, nuovi
        # codici) sono gli unici valori negativi
        rec_err_tot = s['rec_err'] + s.get('rec_out', 0)
        rec_tot = s['rec_pos'] + s['rec_neg'] + rec_err_tot
        e['rec_total']      = rec_tot
        e['rec_positivity'] = pct(s['rec_pos'] + s['rec_neg'], rec_tot)
        e['rec_efficiency'] = pct(s['rec_pos'] + s['rec_neg'] - rec_err_tot, rec_tot)
        # ── Attacco ──
        # Positività = (Kill + Cont) / Tot  → A e AN sono valori positivi
        # Efficienza = (Kill + Cont − Err − Mur − Rete) / Tot → AE, AB e AR
        # (attacco a rete, nuovi codici) sono negativi
        att_err_tot = s['attack_err'] + s['attack_blk'] + s.get('attack_net', 0)
        att_tot = s['attack_kill'] + s['attack_cont'] + att_err_tot
        e['att_total']      = att_tot
        e['att_positivity'] = pct(s['attack_kill'] + s['attack_cont'], att_tot)
        e['att_efficiency'] = pct(s['attack_kill'] + s['attack_cont'] - att_err_tot, att_tot)
        # ── Falli (nuovi codici) ──
        e['fault_total'] = s.get('fault_ft', 0) + s.get('fault_fd', 0) + s.get('fault_fs', 0)
        result[pnum] = e
    return result


# ─────────────────────────────────────────────────────────────
# CONTINUITÀ DI GIOCO
# ─────────────────────────────────────────────────────────────

def compute_game_continuity(sd):
    """
    Continuità del Gioco — Fase di Cambio Palla.
    Collega ogni R+ al successivo attacco:
      conv_pct = Kill / R+          (si finalizza)
      cont_pct = (Kill+Cont) / R+   (si mantiene il pallone)
      disp_pct = Err / R+           (si spreca la ricezione positiva)
    """
    events = sd.get('events', [])
    team   = {'rpos':0,'kills':0,'cont':0,'err':0,'no_attack':0}
    by_recv = {}
    by_att  = {}

    def gr(n):
        if n not in by_recv:
            by_recv[n] = {'rpos':0,'kills':0,'cont':0,'err':0}
        return by_recv[n]

    def ga(n):
        if n not in by_att:
            by_att[n] = {'rpos_received':0,'kills':0,'cont':0,'err':0}
        return by_att[n]

    pending = None   # numero di maglia del ricettore dell'ultimo R+

    for ev in events:
        t      = ev.get('type')
        action = ev.get('action','')
        player = ev.get('player')

        if t == 'stat' and action == 'R+':
            if pending is not None:
                team['no_attack'] += 1
            pending = player
            team['rpos'] += 1
            if player is not None:
                gr(player)['rpos'] += 1
            continue

        if t in ('point','stat') and action in ('A','AN','AE','AB','ABN','AR'):
            if pending is not None:
                outcome = ('kills' if action == 'A'
                           else 'cont' if action == 'AN'
                           else 'err')
                team[outcome] += 1
                gr(pending)[outcome] += 1
                if player is not None:
                    ga(player)['rpos_received'] += 1
                    ga(player)[outcome] += 1
                pending = None
            continue

        # Qualsiasi altro punto / timeout interrompe la catena
        if t in ('point','timeout','substitution','libero_exchange'):
            if pending is not None:
                team['no_attack'] += 1
                pending = None

    if pending is not None:
        team['no_attack'] += 1

    rp = team['rpos']
    team['conv_pct'] = pct(team['kills'],                   rp)
    team['cont_pct'] = pct(team['kills'] + team['cont'],    rp)
    team['disp_pct'] = pct(team['err'],                     rp)

    for n, d in by_recv.items():
        r = d['rpos']
        d['conv_pct'] = pct(d['kills'],           r)
        d['cont_pct'] = pct(d['kills']+d['cont'], r)
        d['disp_pct'] = pct(d['err'],             r)

    for n, d in by_att.items():
        r = d['rpos_received']
        d['conv_pct'] = pct(d['kills'],           r)
        d['cont_pct'] = pct(d['kills']+d['cont'], r)
        d['disp_pct'] = pct(d['err'],             r)

    return {'team':team,'by_receiver':by_recv,'by_attacker':by_att}


# ─────────────────────────────────────────────────────────────
# ZONA PALLEGGIATORE (SETTER STATS)
# ─────────────────────────────────────────────────────────────

def zone_distance(z1, z2):
    """Distanza Manhattan tra due zone FIPAV (0-3)."""
    if z1 is None or z2 is None:
        return None
    c1, r1 = ZONE_COORDS[z1]
    c2, r2 = ZONE_COORDS[z2]
    return abs(c1-c2) + abs(r1-r2)

def displacement_label(dist):
    """Etichetta testuale per lo spostamento del palleggiatore."""
    if dist is None:   return '—'
    if dist == 0:      return 'In zona'
    if dist == 1:      return 'Corto'
    if dist == 2:      return 'Lungo'
    return                    'Fuori zona'

def displacement_class(label):
    """Classe CSS per colorare l'etichetta."""
    return {
        'In zona':   'disp-inzona',
        'Corto':     'disp-corto',
        'Lungo':     'disp-lungo',
        'Fuori zona':'disp-fuori',
    }.get(label, '')

def setter_slot_in_lineup(lineup, setter_num):
    """Ritorna lo slot (1-6) del palleggiatore nella formazione attuale."""
    if setter_num is None: return None
    try:
        return lineup.index(setter_num) + 1   # 1-based
    except ValueError:
        return None

def compute_setter_stats(sd):
    """
    Analizza la distribuzione del palleggiatore dal set data.
    Aggiunge il calcolo dello spostamento rispetto alla posizione attesa
    dalla rotazione (senza considerare scambi di posizione).

    Ritorna:
      heatmap:        {zona: conteggio_alzate}
      distribution:   {zona: {player_num: {kill, cont, err, total}}}
      totals:         {player_num: {kill, cont, err, total}}
      displacement:   lista di {zona_attesa, zona_reale, dist, label, outcome, player}
      disp_summary:   {'In zona':n, 'Corto':n, 'Lungo':n, 'Fuori zona':n}
    """
    events          = sd.get('events', [])
    lineup_init     = list(sd.get('lineup', []))
    setter_num      = sd.get('palleggiatore')
    heatmap         = {z: 0 for z in range(1, 7)}
    distribution    = {z: {} for z in range(1, 7)}
    totals          = {}
    displacement    = []
    disp_summary    = {'In zona':0, 'Corto':0, 'Lungo':0, 'Fuori zona':0}

    # Ricostruisce la formazione in tempo reale (rotazioni + sostituzioni)
    cur_lineup = list(lineup_init)
    # Conta i punti per sapere quante rotazioni sono avvenute
    # (uguale logica di compute_state ma semplificata)
    score_us = 0
    our_serve = sd.get('first_serve','us') == 'us'

    def g_dist(zone, player):
        if player not in distribution[zone]:
            distribution[zone][player] = {'kill':0,'cont':0,'err':0,'total':0}
        return distribution[zone][player]

    def g_tot(player):
        if player not in totals:
            totals[player] = {'kill':0,'cont':0,'err':0,'total':0}
        return totals[player]

    last_zone      = None   # ultima zona W registrata
    last_lineup_at_w = None  # formazione al momento del W

    for ev in events:
        t = ev.get('type')

        # Cambio palleggiatore in corsa — aggiorna il riferimento
        if t == 'setter_change':
            setter_num = ev.get('setter_num')
            continue

        # Aggiorna la formazione in tempo reale
        if t == 'point':
            if ev.get('points_us', 0) > 0:
                if not our_serve:
                    cur_lineup = cur_lineup[1:] + cur_lineup[:1]
                    our_serve = True
            else:
                if our_serve:
                    our_serve = False
        if t in ('substitution', 'libero_exchange'):
            n1 = ev.get('n1')
            n2 = ev.get('n2')
            out = inp = None
            if n1 and n2:
                if n1 in cur_lineup:   out, inp = n1, n2
                elif n2 in cur_lineup: out, inp = n2, n1
            else:
                out = ev.get('player_out')
                inp = ev.get('player_in')
            if out and inp:
                cur_lineup = [inp if p==out else p for p in cur_lineup]
                # Se esce il palleggiatore senza PAL, segue il subentrato
                if out == setter_num:
                    setter_num = inp

        if t == 'setter_pos':
            last_zone = ev.get('zone')
            last_lineup_at_w = list(cur_lineup)
            continue

        # Solo attacchi con giocatore identificato
        if t not in ('point', 'stat'):
            continue
        action = ev.get('action', '')
        player = ev.get('player')
        if action not in ('A', 'AN', 'AE', 'AB', 'ABN', 'AR') or player is None:
            continue

        outcome = 'kill' if action == 'A' else ('cont' if action == 'AN' else 'err')

        # Totali (indipendenti dalla zona)
        gt = g_tot(player)
        gt[outcome] = gt.get(outcome, 0) + 1
        gt['total'] = gt.get('total', 0) + 1

        # Distribuzione per zona + spostamento
        if last_zone is not None:
            heatmap[last_zone] += 1
            gd = g_dist(last_zone, player)
            gd[outcome] = gd.get(outcome, 0) + 1
            gd['total'] = gd.get('total', 0) + 1

            # Calcola spostamento palleggiatore
            zona_attesa = None
            if setter_num and last_lineup_at_w:
                slot = setter_slot_in_lineup(last_lineup_at_w, setter_num)
                if slot:
                    zona_attesa = SLOT_TO_ZONE.get(slot)

            dist  = zone_distance(zona_attesa, last_zone)
            label = displacement_label(dist)

            disp_entry = {
                'zona_attesa': zona_attesa,
                'zona_reale':  last_zone,
                'dist':        dist,
                'label':       label,
                'outcome':     outcome,
                'player':      player,
            }
            displacement.append(disp_entry)
            if label in disp_summary:
                disp_summary[label] += 1

            last_zone         = None
            last_lineup_at_w  = None

    def add_eff(d):
        t = d.get('total', 0)
        d['eff'] = round((d.get('kill',0)+d.get('cont',0)-d.get('err',0))/t*100,1) if t>0 else None
        return d

    for z in distribution:
        for p in distribution[z]:
            add_eff(distribution[z][p])
    for p in totals:
        add_eff(totals[p])

    # Efficienza per categoria di spostamento
    disp_eff = {}
    for label in ('In zona','Corto','Lungo','Fuori zona'):
        entries = [e for e in displacement if e['label']==label]
        if entries:
            k = sum(1 for e in entries if e['outcome']=='kill')
            c = sum(1 for e in entries if e['outcome']=='cont')
            r = sum(1 for e in entries if e['outcome']=='err')
            tot = len(entries)
            disp_eff[label] = {
                'total':tot, 'kill':k, 'cont':c, 'err':r,
                'eff': round((k+c-r)/tot*100,1) if tot>0 else None,
            }

    return {
        'heatmap':      heatmap,
        'distribution': distribution,
        'totals':       totals,
        'total_sets':   sum(heatmap.values()),
        'displacement': displacement,
        'disp_summary': disp_summary,
        'disp_eff':     disp_eff,
        'setter_num':   setter_num,
    }


# ─────────────────────────────────────────────────────────────
# HEATMAP ATTACCHI PER ZONA
# ─────────────────────────────────────────────────────────────

def compute_attack_zone_stats(sd, players_by_num=None):
    """
    Heatmap degli attacchi per zona funzionale dell'attaccante.
    La zona di partenza è lo slot corrente → SLOT_TO_ZONE, poi corretta
    in base al ruolo: in prima linea C→3, B→4, O→2 (specializzazione).
    players_by_num: {numero: {'role': ...}} — se None, nessuna correzione.
    """
    events       = sd.get('events', [])
    heatmap      = {z: 0 for z in range(1, 7)}
    distribution = {z: {} for z in range(1, 7)}
    totals       = {}

    pbn          = players_by_num or {}
    our_serve    = sd.get('first_serve', 'us') == 'us'
    cur_lineup   = list(sd.get('lineup', []))
    setter_num   = sd.get('palleggiatore')

    def g_dist(zone, player):
        if player not in distribution[zone]:
            distribution[zone][player] = {'kill':0,'cont':0,'err':0,'total':0}
        return distribution[zone][player]

    def g_tot(player):
        if player not in totals:
            totals[player] = {'kill':0,'cont':0,'err':0,'total':0}
        return totals[player]

    def functional_zone(player_num, slot):
        """Restituisce la zona funzionale dell'attaccante in base al ruolo."""
        slot_zone = SLOT_TO_ZONE.get(slot)
        if slot_zone is None:
            return None
        # In seconda linea la zona è quella di rotazione
        if slot_zone in (1, 5, 6):
            return slot_zone
        # In prima linea: usa la zona specializzata per ruolo
        role = pbn.get(player_num, {}).get('role')
        return ROLE_FRONT_ZONE.get(role, slot_zone)

    for ev in events:
        t = ev.get('type')

        if t == 'setter_change':
            setter_num = ev.get('setter_num')
            continue

        # Attribuzione PRIMA della rotazione: il punto che chiude l'azione
        # fa ruotare la formazione, ma l'attacco è avvenuto nella rotazione precedente
        if t in ('point', 'stat'):
            action = ev.get('action', '')
            player = ev.get('player')
            if action in ('A', 'AN', 'AE', 'AB', 'ABN', 'AR') and player is not None:
                outcome = 'kill' if action == 'A' else ('cont' if action == 'AN' else 'err')

                # Trova la zona funzionale dell'attaccante
                zone = None
                if player in cur_lineup:
                    slot = cur_lineup.index(player) + 1
                    zone = functional_zone(player, slot)

                gt = g_tot(player)
                gt[outcome] = gt.get(outcome, 0) + 1
                gt['total'] = gt.get('total', 0) + 1

                if zone is not None:
                    heatmap[zone] += 1
                    gd = g_dist(zone, player)
                    gd[outcome] = gd.get(outcome, 0) + 1
                    gd['total'] = gd.get('total', 0) + 1

        if t == 'point':
            if ev.get('points_us', 0) > 0:
                if not our_serve:
                    cur_lineup = cur_lineup[1:] + cur_lineup[:1]
                    our_serve = True
            else:
                if our_serve:
                    our_serve = False

        elif t in ('substitution', 'libero_exchange'):
            n1 = ev.get('n1')
            n2 = ev.get('n2')
            if n1 and n2:
                if n1 in cur_lineup:
                    cur_lineup = [n2 if p==n1 else p for p in cur_lineup]
                elif n2 in cur_lineup:
                    cur_lineup = [n1 if p==n2 else p for p in cur_lineup]
            else:
                out = ev.get('player_out')
                inp = ev.get('player_in')
                if out and inp:
                    cur_lineup = [inp if p==out else p for p in cur_lineup]

    def add_eff(d):
        t = d.get('total', 0)
        d['eff']      = round((d.get('kill',0)+d.get('cont',0)-d.get('err',0))/t*100,1) if t>0 else None
        d['kill_pct'] = round(d.get('kill',0)/t*100,1) if t>0 else None
        return d

    for z in distribution:
        for p in distribution[z]: add_eff(distribution[z][p])
    for p in totals: add_eff(totals[p])

    return {
        'heatmap':      heatmap,
        'distribution': distribution,
        'totals':       totals,
    }


# ─────────────────────────────────────────────────────────────
# ANALISI PER ROTAZIONE
# ─────────────────────────────────────────────────────────────

def compute_rotation_stats(sd):
    """
    Calcola punti fatti/persi per ciascuna delle 6 rotazioni nel set.
    Identifico la rotazione dallo slot corrente del palleggiatore.
    Distingue side-out (punto in ricezione) e break (punto al servizio).

    Ritorna:
      rotations: {slot(1-6): {pts_scored, pts_lost, saldo,
                               side_out_won, side_out_tot,
                               break_won, break_tot}}
      summary:   {best_rot, worst_rot, side_out_pct, break_pct}
    """
    events     = sd.get('events', [])
    lineup     = list(sd.get('lineup', []))
    setter_num = sd.get('palleggiatore')
    our_serve  = sd.get('first_serve', 'us') == 'us'
    cur        = list(lineup)

    if not cur:
        return {'rotations': {}, 'summary': {}}

    # Inizializza struttura per 6 rotazioni
    rots = {i: {'pts_scored':0,'pts_lost':0,'saldo':0,
                'side_out_won':0,'side_out_tot':0,
                'break_won':0,'break_tot':0}
            for i in range(1,7)}

    def get_setter_slot():
        """Slot (1-based) del palleggiatore nella formazione corrente."""
        if setter_num and setter_num in cur:
            return cur.index(setter_num) + 1
        # Fallback: slot 1 (giocatore che serve)
        return 1

    for ev in events:
        t = ev.get('type')

        # Cambio palleggiatore in corsa
        if t == 'setter_change':
            setter_num = ev.get('setter_num')
            continue

        if t == 'point':
            slot = get_setter_slot()
            r    = rots[slot]

            if ev.get('points_us', 0) > 0:
                r['pts_scored'] += 1
                if our_serve:
                    # Break point (segniamo al nostro servizio)
                    r['break_tot']   += 1
                    r['break_won']   += 1
                else:
                    # Side-out (togliamo servizio all'avversario)
                    r['side_out_tot'] += 1
                    r['side_out_won'] += 1
                    # Rotazione: guadagnato il servizio
                    cur       = cur[1:] + cur[:1]
                    our_serve = True
            else:
                r['pts_lost'] += 1
                if our_serve:
                    r['break_tot'] += 1
                    our_serve = False
                else:
                    r['side_out_tot'] += 1

        elif t in ('substitution', 'libero_exchange'):
            n1 = ev.get('n1')
            n2 = ev.get('n2')
            out = inp = None
            if n1 and n2:
                if n1 in cur:   out, inp = n1, n2
                elif n2 in cur: out, inp = n2, n1
            else:
                out = ev.get('player_out')
                inp = ev.get('player_in')
            if out and inp:
                cur = [inp if p==out else p for p in cur]
                # Se esce il palleggiatore senza un comando PAL,
                # il riferimento di rotazione segue il subentrato
                if out == setter_num:
                    setter_num = inp

    # Calcola saldo e percentuali
    for slot, r in rots.items():
        r['saldo'] = r['pts_scored'] - r['pts_lost']
        r['so_pct'] = round(r['side_out_won']/r['side_out_tot']*100,1) \
                      if r['side_out_tot'] > 0 else None
        r['brk_pct']= round(r['break_won']  /r['break_tot']  *100,1) \
                      if r['break_tot']   > 0 else None

    # Best/worst per saldo (solo rotazioni con almeno 2 punti giocati)
    active = {s:r for s,r in rots.items()
              if r['pts_scored']+r['pts_lost'] >= 2}
    best  = max(active, key=lambda s: active[s]['saldo']) if active else None
    worst = min(active, key=lambda s: active[s]['saldo']) if active else None
    if best == worst:
        worst = None   # una sola rotazione attiva: nessuna "critica"

    # Totali side-out e break
    so_won = sum(r['side_out_won'] for r in rots.values())
    so_tot = sum(r['side_out_tot'] for r in rots.values())
    brk_won= sum(r['break_won']    for r in rots.values())
    brk_tot= sum(r['break_tot']    for r in rots.values())

    return {
        'rotations': rots,
        'summary': {
            'best_rot':    best,
            'worst_rot':   worst,
            'so_pct':      round(so_won/so_tot*100,1)  if so_tot  > 0 else None,
            'brk_pct':     round(brk_won/brk_tot*100,1)if brk_tot > 0 else None,
            'so_won':      so_won,  'so_tot': so_tot,
            'brk_won':     brk_won, 'brk_tot':brk_tot,
        },
        'rot_labels': ROT_LABELS,
        'rot_short':  ROT_SHORT,
        'rot_order':  ROT_ORDER,
    }


# ─────────────────────────────────────────────────────────────
# MINUTI GIOCATI
# ─────────────────────────────────────────────────────────────

def _ts_to_sec(ts):
    """Converte HH:MM:SS in secondi totali. None se non valido."""
    try:
        parts = ts.split(':')
        return int(parts[0])*3600 + int(parts[1])*60 + int(parts[2])
    except Exception:
        return None


def compute_minutes_played(sd):
    """
    Calcola i minuti effettivi giocati da ogni giocatore in un set.
    Traccia coppie (entrata, uscita) per gestire correttamente
    il libero e qualsiasi giocatore che entra/esce più volte.
    Ritorna dict {player_num: minuti_interi}.
    """
    events  = sd.get('events', [])
    lineup  = list(sd.get('lineup', []))
    if not lineup:
        return {}

    # Timestamp normalizzati per indice evento (HH:MM:SS è senza data:
    # se un set scavalca la mezzanotte i secondi ripartirebbero da 0)
    norm   = {}
    offset = 0
    prev   = None
    for i, e in enumerate(events):
        sec = _ts_to_sec(e.get('timestamp', ''))
        if sec is None:
            continue
        sec += offset
        if prev is not None and sec < prev:
            sec    += 86400
            offset += 86400
        norm[i] = sec
        prev    = sec
    if not norm:
        return {p: 1 for p in lineup}

    set_start = next(iter(norm.values()))
    set_end   = prev

    # Per ogni giocatore: lista di [entrata_sec, uscita_sec|None]
    # I titolari iniziano all'inizio del set
    intervals = {}
    for p in lineup:
        intervals[p] = [[set_start, None]]

    in_field = set(lineup)   # chi è fisicamente in campo ora

    for i, ev in enumerate(events):
        if ev.get('type') not in ('substitution', 'libero_exchange'):
            continue
        ts = norm.get(i, set_start)

        # Determina chi entra e chi esce
        if ev.get('type') == 'libero_exchange':
            n1, n2 = ev.get('n1'), ev.get('n2')
            if n1 is not None and n2 is not None:
                # Chi è in campo esce, l'altro entra
                out, inp = (n1, n2) if n1 in in_field else (n2, n1)
            elif ev.get('player_out') is not None:
                out, inp = ev.get('player_out'), ev.get('player_in')
            else:
                continue
        else:
            out = ev.get('player_out')
            inp = ev.get('player_in')

        # Chiudi l'ultimo intervallo aperto del giocatore uscente
        if out and out in in_field:
            ivs = intervals.setdefault(out, [])
            # Trova l'ultimo intervallo aperto (uscita = None)
            for iv in reversed(ivs):
                if iv[1] is None:
                    iv[1] = ts
                    break
            in_field.discard(out)

        # Apri nuovo intervallo per il giocatore entrante
        if inp:
            intervals.setdefault(inp, []).append([ts, None])
            in_field.add(inp)

    # Chiudi tutti gli intervalli ancora aperti a fine set
    for ivs in intervals.values():
        for iv in ivs:
            if iv[1] is None:
                iv[1] = set_end

    # Somma i secondi di ogni intervallo e converti in minuti
    result = {}
    for player, ivs in intervals.items():
        total_sec = sum(max(ex - en, 0) for en, ex in ivs)
        result[player] = max(round(total_sec / 60), 1)

    return result


# ─────────────────────────────────────────────────────────────
# TIMELINE PUNTI
# ─────────────────────────────────────────────────────────────

def compute_score_timeline(sd):
    """
    Costruisce la timeline punto-per-punto di un set.
    Ritorna parziali per fase, serie massime e dati SVG precomputati.
    """
    events   = sd.get('events', [])
    our_serve = sd.get('first_serve', 'us') == 'us'
    sn       = sd.get('set_number', 1)
    ruleset  = sd.get('ruleset', 'standard')

    pts = [{'n': 0, 'us': 0, 'them': 0, 'diff': 0}]
    key_moments = []
    score_us = score_them = 0
    cur_run_us = cur_run_them = 0
    max_run_us = max_run_them = 0
    max_run_us_at = max_run_them_at = (0, 0)

    for ev in events:
        t = ev.get('type')
        if t == 'point':
            scored = False
            if ev.get('points_us', 0) > 0:
                score_us += 1
                cur_run_us += 1
                cur_run_them = 0
                if cur_run_us > max_run_us:
                    max_run_us = cur_run_us
                    max_run_us_at = (score_us - cur_run_us, score_them)
                if not our_serve:
                    our_serve = True
                scored = True
            elif ev.get('points_them', 0) > 0:
                score_them += 1
                cur_run_them += 1
                cur_run_us = 0
                if cur_run_them > max_run_them:
                    max_run_them = cur_run_them
                    max_run_them_at = (score_us, score_them - cur_run_them)
                if our_serve:
                    our_serve = False
                scored = True
            if scored:
                pts.append({'n': len(pts), 'us': score_us, 'them': score_them,
                            'diff': score_us - score_them})
        elif t == 'timeout':
            n = len(pts) - 1
            if n >= 0:
                key_moments.append({
                    'n': n,
                    'type': 'T',
                    'label': 'T' if ev.get('side') == 'us' else 'TO',
                    'side': ev.get('side', 'us'),
                    'us': score_us,
                    'them': score_them,
                })

    total_pts = len(pts) - 1
    if total_pts == 0:
        return {'points': pts, 'key_moments': [], 'total_pts': 0,
                'max_run_us': 0, 'max_run_them': 0,
                'max_run_us_at': (0, 0), 'max_run_them_at': (0, 0),
                'phases': {}, 'svg': None}

    # ── Phase partials ────────────────────────────────────────────
    if ruleset == 'pgs':
        breaks = [6, 12]
    elif sn == 5:
        breaks = [5, 10]
    else:
        breaks = [8, 16]

    phases = {}
    prev_u = prev_t = 0
    boundaries = [0] + breaks
    for i, start in enumerate(boundaries):
        is_last = (i == len(boundaries) - 1)
        end = breaks[i] if not is_last else total_pts
        idx = min(end, total_pts)
        eu, et = pts[idx]['us'], pts[idx]['them']
        phases[i + 1] = {
            'us': eu - prev_u,
            'them': et - prev_t,
            'label': f"{start + 1}–fine" if is_last else f"{start + 1}–{end}",
        }
        prev_u, prev_t = eu, et

    # ── SVG geometry ──────────────────────────────────────────────
    W, H   = 520, 86
    MX, MY = 24, 10
    chart_w = W - 2 * MX
    chart_h = H - 2 * MY
    zero_y  = round(MY + chart_h / 2, 1)
    max_abs = max(abs(p['diff']) for p in pts) or 1
    amp     = chart_h / 2 - 3   # pixel amplitude

    def xof(n):
        return round(MX + n / total_pts * chart_w, 1)

    def yof(d):
        return round(zero_y - d / max_abs * amp, 1)

    coords = [(xof(p['n']), yof(p['diff'])) for p in pts]

    def zcross_x(a, b):
        x1, y1 = a; x2, y2 = b
        if y2 == y1:
            return x1
        return round(x1 + (zero_y - y1) / (y2 - y1) * (x2 - x1), 1)

    above_segs, below_segs = [], []
    cur_seg  = [coords[0]]
    is_above = coords[0][1] <= zero_y
    for i in range(1, len(coords)):
        cx, cy  = coords[i]
        now_above = cy <= zero_y
        if now_above != is_above:
            zx = zcross_x(coords[i - 1], (cx, cy))
            cur_seg.append((zx, zero_y))
            (above_segs if is_above else below_segs).append(cur_seg)
            cur_seg  = [(zx, zero_y), (cx, cy)]
            is_above = now_above
        else:
            cur_seg.append((cx, cy))
    (above_segs if is_above else below_segs).append(cur_seg)

    def fill_poly(seg):
        if len(seg) < 2:
            return ''
        return (' '.join(f"{x},{y}" for x, y in seg) +
                f" {seg[-1][0]},{zero_y} {seg[0][0]},{zero_y}")

    line_pts = ' '.join(f"{x},{y}" for x, y in coords)

    x_labels = [{'n': n, 'x': xof(n)} for n in range(0, total_pts + 1, 5)]
    if total_pts % 5 != 0:
        x_labels.append({'n': total_pts, 'x': xof(total_pts)})

    for km in key_moments:
        km['x'] = xof(km['n'])

    return {
        'points':          pts,
        'total_pts':       total_pts,
        'key_moments':     key_moments,
        'max_run_us':      max_run_us,
        'max_run_us_at':   max_run_us_at,
        'max_run_them':    max_run_them,
        'max_run_them_at': max_run_them_at,
        'phases':          phases,
        'svg': {
            'W': W, 'H': H,
            'MX': MX, 'MY': MY,
            'zero_y':     zero_y,
            'max_abs':    max_abs,
            'line_pts':   line_pts,
            'above_fills': [fill_poly(s) for s in above_segs if len(s) >= 2],
            'below_fills': [fill_poly(s) for s in below_segs if len(s) >= 2],
            'x_labels':   x_labels,
        },
    }


# ─────────────────────────────────────────────────────────────
# DISTRIBUZIONE ALZATE — "NUOVI CODICI" (P1/P2/PC)
# ─────────────────────────────────────────────────────────────

SETTER_TAG_LABELS = {'P1': '1ª linea', 'P2': '2ª linea', 'PC': 'Centrale (Z3)'}


def compute_setter_distribution_stats(sd):
    """
    Statistiche derivate dai tag di alzata della modalità "nuovi codici"
    (P1/P2/PC): collega ogni tag al successivo attacco dello stesso
    giocatore per calcolare kill/continua/errore e le percentuali di
    conversione ed efficienza per tipo di alzata.

    Un set che non usa i nuovi codici non genera mai questi eventi, quindi
    la funzione ritorna semplicemente struttura vuota (total_tags=0) — può
    essere chiamata su qualunque set senza controlli preventivi.

    Ritorna:
      by_type:   {codice: {tot, kills, cont, err, conv_pct, eff_pct}}
      by_player: {numero: {codice: {tot, kills, cont, err, conv_pct, eff_pct}}}
      total_tags: int
    """
    events = sd.get('events', [])
    by_type   = {c: {'tot': 0, 'kills': 0, 'cont': 0, 'err': 0} for c in SETTER_TAG_LABELS}
    by_player = {}
    pending   = {}   # player_num -> codice tag in attesa dell'esito

    def gp(player, code):
        d = by_player.setdefault(
            player, {c: {'tot': 0, 'kills': 0, 'cont': 0, 'err': 0} for c in SETTER_TAG_LABELS})
        return d[code]

    for ev in events:
        t      = ev.get('type')
        action = ev.get('action', '')
        player = ev.get('player')

        if t == 'stat' and action in SETTER_TAG_LABELS and player is not None:
            pending[player] = action
            by_type[action]['tot'] += 1
            gp(player, action)['tot'] += 1
            continue

        if t in ('point', 'stat') and action in ('A', 'AN', 'AE', 'AR', 'AB', 'ABN') and player is not None:
            code = pending.pop(player, None)
            if code:
                outcome = 'kills' if action == 'A' else ('cont' if action == 'AN' else 'err')
                by_type[code][outcome] += 1
                gp(player, code)[outcome] += 1

    def add_pct(d):
        t = d['tot']
        d['conv_pct'] = pct(d['kills'], t)
        d['eff_pct']  = pct(d['kills'] + d['cont'] - d['err'], t)
        return d

    for code in by_type:
        add_pct(by_type[code])
    for player, codes in by_player.items():
        for code in codes:
            add_pct(codes[code])

    return {
        'labels':     SETTER_TAG_LABELS,
        'by_type':    by_type,
        'by_player':  by_player,
        'total_tags': sum(d['tot'] for d in by_type.values()),
    }
