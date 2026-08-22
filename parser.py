"""
VolleyStat — Parser comandi e motore di stato del set.
Nessuna dipendenza da Flask o dal layer di storage.
"""
import re

# ─────────────────────────────────────────────────────────────
# TABELLA COMANDI
# ─────────────────────────────────────────────────────────────
COMMANDS = {
    # Servizio
    'S':   (1,0,'serve',    'Ace #{p}'),
    'SE':  (0,1,'serve',    'Errore servizio #{p}'),
    # Attacco
    'A':   (1,0,'attack',   'Kill #{p}'),
    'AN':  (0,0,'attack',   'Attacco in campo #{p}'),
    'AE':  (0,1,'attack',   'Errore attacco #{p}'),
    'AB':  (0,1,'attack',   'Murato — punto avversario #{p}'),
    'ABN': (0,0,'attack',   'Murato — palla in gioco #{p}'),
    # Muro
    'B':   (1,0,'block',    'Muro #{p}'),
    'BE':  (0,1,'block',    'Errore muro #{p}'),
    'BN':  (0,0,'block',    'Muro — palla in gioco #{p}'),
    # Ricezione (RE = ace subito = punto avversario)
    'RE':  (0,1,'reception','Ace subito #{p}'),
    # Difesa
    'DE':  (0,1,'defense',  'Errore difesa #{p}'),
}


def parse_command(raw):
    cmd = raw.strip().upper()
    if cmd == 'UNDO':
        return {'type': 'undo'}
    if cmd == 'T':
        return {'type':'timeout','side':'us','desc':'Timeout (noi)'}
    if cmd == 'TO':
        return {'type':'timeout','side':'them','desc':'Timeout (avversario)'}
    if cmd in ('AUTOLIB', 'LIBAUTO'):
        return {'type': 'toggle_auto_libero'}
    if cmd == 'P':
        return {'type':'point','action':'P','player':None,
                'points_us':1,'points_them':0,'category':'generic',
                'desc':'Punto — errore avversario'}
    if cmd == 'PE':
        return {'type':'point','action':'PE','player':None,
                'points_us':0,'points_them':1,'category':'generic',
                'desc':'Punto avversario — nostro errore'}

    # Posizione palleggiatore — W[zona]  es. W4 = palleggiatore in zona 4
    # Zone FIPAV standard: 1=dx dietro, 2=dx davanti, 3=centro davanti,
    #                      4=sx davanti, 5=sx dietro, 6=centro dietro
    w_m = re.match(r'^W([1-6])$', cmd)
    if w_m:
        zone = int(w_m.group(1))
        zone_names = {1:'destra dietro',2:'destra davanti',3:'centro davanti',
                      4:'sinistra davanti',5:'sinistra dietro',6:'centro dietro'}
        return {'type':'setter_pos','zone':zone,
                'desc':f'Palleggiatore zona {zone} ({zone_names[zone]})'}

    # Cambio palleggiatore in corsa — PAL[numero]  es. PAL10 = #10 è il nuovo palleggiatore
    pal_m = re.match(r'^PAL(\d+)$', cmd)
    if pal_m:
        new_setter = int(pal_m.group(1))
        return {'type':'setter_change', 'setter_num': new_setter,
                'desc': f'Palleggiatore: #{new_setter}'}

    sub = re.match(r'^SUB\s*(\d+)[/,\s]+(\d+)$', cmd)
    if sub:
        return {'type':'substitution','player_out':int(sub.group(1)),
                'player_in':int(sub.group(2)),
                'desc':f'Sostituzione: #{sub.group(1)} esce, #{sub.group(2)} entra'}

    # Cambio libero — LIB[num1]/[num2]  — bidirezionale
    lib = re.match(r'^LIB\s*(\d+)[/,\s]+(\d+)$', cmd)
    if lib:
        n1 = int(lib.group(1))
        n2 = int(lib.group(2))
        return {'type':'libero_exchange',
                'n1': n1, 'n2': n2,
                'desc':f'Cambio libero: #{n1} ↔ #{n2}'}

    # Ricezione: R+15 (permette att.), R-15 (non permette)
    r_m = re.match(r'^(R[+\-])(\d+)$', cmd)
    if r_m:
        mod, player = r_m.group(1), int(r_m.group(2))
        labels = {'R+': 'Ricezione positiva (att.)', 'R-': 'Ricezione negativa'}
        return {'type':'stat','action':mod,'player':player,
                'category':'reception','desc':f'{labels[mod]} #{player}'}

    # Difesa: D15
    d_m = re.match(r'^(D)(\d+)$', cmd)
    if d_m:
        player = int(d_m.group(2))
        return {'type':'stat','action':'D','player':player,
                'category':'defense','desc':f'Difesa #{player}'}

    # ORDINE CRITICO: ABN prima di AB, AN prima di A, BN prima di B, codici lunghi prima dei corti
    for code in ('ABN','AN','AB','AE','SE','BE','BN','RE','DE','S','A','B'):
        if cmd.startswith(code):
            rest = cmd[len(code):]
            if rest.isdigit() and rest:
                player = int(rest)
                pu, pt, cat, desc_t = COMMANDS[code]
                desc = desc_t.replace('{p}', str(player))
                # AN, ABN e BN = stat pura (nessun punto diretto)
                if code in ('AN', 'ABN', 'BN'):
                    return {'type':'stat','action':code,'player':player,
                            'category':cat,'desc':desc}
                return {'type':'point','action':code,'player':player,
                        'points_us':pu,'points_them':pt,'category':cat,'desc':desc}

    return {'type':'error','message':f'Comando non riconosciuto: "{raw}"'}


# ─────────────────────────────────────────────────────────────
# VOLLEYBALL LOGIC
# ─────────────────────────────────────────────────────────────
def compute_state(sd):
    if not sd:
        return None
    cur = list(sd['lineup'])
    score_us = score_them = 0
    our_serve = sd.get('first_serve','us') == 'us'
    to_us = to_them = 0
    for ev in sd.get('events',[]):
        t = ev.get('type')
        if t == 'point':
            if ev.get('points_us',0) > 0:
                score_us += ev['points_us']
                if not our_serve:
                    cur = cur[1:] + cur[:1]
                    our_serve = True
            else:
                score_them += ev.get('points_them',0)
                if our_serve:
                    our_serve = False
        elif t == 'substitution':
            out, inp = ev.get('player_out'), ev.get('player_in')
            cur = [inp if p==out else p for p in cur]
        elif t == 'libero_exchange':
            # Bidirezionale: chi è in campo esce, l'altro entra
            n1, n2 = ev.get('n1'), ev.get('n2')
            if n1 is not None and n2 is not None:
                if n1 in cur:      # n1 è in campo → esce, n2 entra
                    cur = [n2 if p==n1 else p for p in cur]
                elif n2 in cur:    # n2 è in campo → esce, n1 entra
                    cur = [n1 if p==n2 else p for p in cur]
            # Compatibilità con vecchio formato (player_in/player_out espliciti)
            elif ev.get('player_out') is not None:
                out, inp = ev.get('player_out'), ev.get('player_in')
                cur = [inp if p==out else p for p in cur]
        elif t == 'timeout':
            if ev.get('side') == 'us': to_us += 1
            else: to_them += 1
        # setter_change e setter_pos non modificano lo stato del set

    sn      = sd.get('set_number', 1)
    ruleset = sd.get('ruleset', 'standard')
    # PGS: tutti i set a 17, nessun tie-break
    # Standard: set 1-4 a 25, set 5 a 15
    if ruleset == 'pgs':
        limit = 17
    else:
        limit = 15 if sn == 5 else 25
    set_over = winner = None
    if score_us >= limit and score_us - score_them >= 2:
        set_over, winner = True, 'us'
    elif score_them >= limit and score_them - score_us >= 2:
        set_over, winner = True, 'them'

    return {'lineup':cur,'score_us':score_us,'score_them':score_them,
            'our_serve':our_serve,'server':cur[0] if cur and our_serve else None,
            'timeouts_us':to_us,'timeouts_them':to_them,
            'set_over':bool(set_over),'winner':winner,
            'ruleset':ruleset,'limit':limit,
            'auto_libero':bool(sd.get('auto_libero'))}
