#!/usr/bin/env python3
"""Genera dati demo per VolleyStat (squadra fittizia, atleti fittizi)."""
import json
import os
import random

random.seed(42)

BASE = "data/categorie/demo_serie_c"

PLAYERS = [
    {"id": 1,  "number": 4,  "name": "Sara Ferretti",   "role": "P", "active": True},
    {"id": 2,  "number": 8,  "name": "Chiara Moretti",  "role": "S", "active": True},
    {"id": 3,  "number": 11, "name": "Laura Bianchi",   "role": "C", "active": True},
    {"id": 4,  "number": 14, "name": "Anna Colombo",    "role": "O", "active": True},
    {"id": 5,  "number": 3,  "name": "Elena Rossi",     "role": "P", "active": True},
    {"id": 6,  "number": 7,  "name": "Marta Gallo",     "role": "S", "active": True},
    {"id": 7,  "number": 9,  "name": "Federica Vitali", "role": "C", "active": True},
    {"id": 8,  "number": 15, "name": "Giulia Lombardi", "role": "C", "active": True},
    {"id": 9,  "number": 6,  "name": "Sofia Martini",   "role": "S", "active": True},
    {"id": 10, "number": 12, "name": "Valentina Greco", "role": "L", "active": True},
    {"id": 11, "number": 2,  "name": "Alessia Romano",  "role": "O", "active": True},
    {"id": 12, "number": 17, "name": "Beatrice Conti",  "role": "C", "active": True},
]

MATCHES = [
    {
        "id": "20250915183000",
        "date": "2025-09-15", "time": "18:30",
        "opponent": "Cosma Volley ASD",
        "home": True, "location": "PalaDemo",
        "competition": "Serie C Demo",
        "ruleset": "standard", "status": "completed",
        "sets_us": 3, "sets_them": 1,
    },
    {
        "id": "20251003154500",
        "date": "2025-10-03", "time": "15:45",
        "opponent": "Polisportiva Novate",
        "home": False, "location": "Palazzetto Novate",
        "competition": "Serie C Demo",
        "ruleset": "standard", "status": "completed",
        "sets_us": 3, "sets_them": 0,
    },
    {
        "id": "20251018174500",
        "date": "2025-10-18", "time": "17:45",
        "opponent": "Briantea 84 Volley",
        "home": True, "location": "PalaDemo",
        "competition": "Serie C Demo",
        "ruleset": "standard", "status": "completed",
        "sets_us": 1, "sets_them": 3,
    },
]

# Formazione standard: posizioni 1-6, palleggiatore in P1
LINEUP  = [4, 8, 11, 14, 7, 9]
LIBERO  = 12
# Giocatrici che attaccano (non palleggiatore, non libero)
HITTERS = [8, 14, 7, 11, 9, 6]
# Giocatrici in ricezione
RCVRS   = [7, 8, 12]
# Zone setter (ruota ogni 6 punti circa)
SETTER_ZONES = [1, 6, 5, 4, 3, 2]

SETS_CONFIG = {
    "20250915183000": [
        (1, 25, 18, "us"),
        (2, 25, 22, "them"),
        (3, 20, 25, "us"),
        (4, 25, 17, "them"),
    ],
    "20251003154500": [
        (1, 25, 20, "us"),
        (2, 25, 19, "them"),
        (3, 25, 17, "us"),
    ],
    "20251018174500": [
        (1, 25, 21, "us"),
        (2, 18, 25, "them"),
        (3, 20, 25, "us"),
        (4, 15, 25, "them"),
    ],
}

CREATED_AT = {
    "20250915183000": "2025-09-15T18:30:00",
    "20251003154500": "2025-10-03T15:45:00",
    "20251018174500": "2025-10-18T17:45:00",
}

ZONE_NAMES = {
    1: "destra dietro",  2: "destra davanti", 3: "centro davanti",
    4: "sinistra davanti", 5: "sinistra dietro", 6: "centro dietro",
}

OUR_ACTIONS = [
    ("A",  "attack",  True,  lambda p: f"Kill #{p}"),
    ("A",  "attack",  True,  lambda p: f"Kill #{p}"),
    ("A",  "attack",  True,  lambda p: f"Kill #{p}"),
    ("S",  "serve",   True,  lambda p: f"Ace #{p}"),
    ("B",  "block",   True,  lambda p: f"Muro #{p}"),
    ("P",  "generic", False, lambda _: "Punto — errore avversario"),
    ("P",  "generic", False, lambda _: "Punto — errore avversario"),
]
THEIR_ACTIONS = [
    ("AE", "attack",    True,  lambda p: f"Errore attacco #{p}"),
    ("AE", "attack",    True,  lambda p: f"Errore attacco #{p}"),
    ("SE", "serve",     True,  lambda p: f"Errore servizio #{p}"),
    ("SE", "serve",     True,  lambda p: f"Errore servizio #{p}"),
    ("BE", "block",     True,  lambda p: f"Errore muro #{p}"),
    ("DE", "defense",   True,  lambda p: f"Errore difesa #{p}"),
    ("RE", "reception", True,  lambda p: f"Ace subito #{p}"),
    ("PE", "generic",   False, lambda _: "Punto avversario — nostro errore"),
]


def gen_set(match_id, set_n, pts_us, pts_them, first_serve):
    eid   = 1
    # Orologio in secondi assoluti (HH:MM:SS), avanza 8-40s per evento
    t     = 18 * 3600 + 30 * 60 + (set_n - 1) * 25 * 60
    events = []

    def bump():
        nonlocal t
        t += random.randint(8, 40)
        return f"{t//3600%24:02d}:{t%3600//60:02d}:{t%60:02d}"

    def add(**kw):
        nonlocal eid
        events.append({"id": eid, "timestamp": bump(), **kw})
        eid += 1

    # Libero entra per la centrale in posizione di dietro
    add(type="substitution", player_out=9, player_in=LIBERO,
        desc=f"Sostituzione: #9 esce, #{LIBERO} entra")

    # Zona palleggiatore all'inizio del set
    z0 = SETTER_ZONES[0]
    add(type="setter_pos", zone=z0,
        desc=f"Palleggiatore zona {z0} ({ZONE_NAMES[z0]})")

    # Costruisce la sequenza di chi segna punto per punto
    winner = "us" if pts_us >= pts_them else "them"
    pool = ["us"] * pts_us + ["them"] * pts_them
    pool.remove(winner)  # riserva l'ultimo punto al vincitore
    random.shuffle(pool)
    seq = pool + [winner]

    zone_idx  = 0
    pts_since_zone = 0

    for scorer in seq:
        # Aggiorna zona palleggiatore ogni ~6 punti
        pts_since_zone += 1
        if pts_since_zone >= 6:
            pts_since_zone = 0
            zone_idx = (zone_idx + 1) % len(SETTER_ZONES)
            z = SETTER_ZONES[zone_idx]
            add(type="setter_pos", zone=z,
                desc=f"Palleggiatore zona {z} ({ZONE_NAMES[z]})")

        # Stat ricezione (probabilistico)
        if random.random() < 0.55:
            recv = random.choice(RCVRS)
            act  = random.choice(["R+", "R-"])
            desc = (f"Ricezione positiva (att.) #{recv}"
                    if act == "R+" else f"Ricezione negativa #{recv}")
            add(type="stat", action=act, player=recv,
                category="reception", desc=desc)

        # Stat attacco neutro (probabilistico)
        if random.random() < 0.35:
            att = random.choice(HITTERS)
            add(type="stat", action="AN", player=att,
                category="attack", desc=f"Attacco in campo #{att}")

        # Stat difesa (probabilistico)
        if random.random() < 0.20:
            dfn = random.choice(RCVRS + HITTERS)
            add(type="stat", action="D", player=dfn,
                category="defense", desc=f"Difesa #{dfn}")

        if scorer == "us":
            act, cat, needs_p, desc_fn = random.choice(OUR_ACTIONS)
            p = random.choice(HITTERS) if needs_p else None
            add(type="point", action=act, player=p,
                points_us=1, points_them=0,
                category=cat, desc=desc_fn(p))
        else:
            act, cat, needs_p, desc_fn = random.choice(THEIR_ACTIONS)
            p = random.choice(HITTERS + RCVRS) if needs_p else None
            add(type="point", action=act, player=p,
                points_us=0, points_them=1,
                category=cat, desc=desc_fn(p))

    return {
        "match_id":   match_id,
        "set_number": set_n,
        "lineup":     LINEUP,
        "libero":     LIBERO,
        "palleggiatore": 8,   # Chiara Moretti (S), in zona 2 a inizio set
        "first_serve": first_serve,
        "ruleset":    "standard",
        "events":     events,
        "created_at": CREATED_AT[match_id],
    }


def main():
    os.makedirs(f"{BASE}/sets", exist_ok=True)

    with open(f"{BASE}/info.json", "w", encoding="utf-8") as f:
        json.dump({
            "name":   "Serie C Demo",
            "short":  "SCD",
            "color":  "#7c3aed",
            "season": "2025/26",
            "order":  99,
        }, f, ensure_ascii=False, indent=2)

    with open(f"{BASE}/players.json", "w", encoding="utf-8") as f:
        json.dump({"players": PLAYERS}, f, ensure_ascii=False, indent=2)

    with open(f"{BASE}/matches.json", "w", encoding="utf-8") as f:
        json.dump({"matches": MATCHES}, f, ensure_ascii=False, indent=2)

    for match in MATCHES:
        mid = match["id"]
        for set_n, pts_us, pts_them, first_serve in SETS_CONFIG[mid]:
            sd    = gen_set(mid, set_n, pts_us, pts_them, first_serve)
            fname = f"{BASE}/sets/{mid}_{set_n}.json"
            with open(fname, "w", encoding="utf-8") as f:
                json.dump(sd, f, ensure_ascii=False, indent=2)
            total_pts = pts_us + pts_them
            print(f"  {fname}  ({pts_us}-{pts_them}, {len(sd['events'])} eventi)")

    print("\nDati demo generati con successo!")


if __name__ == "__main__":
    main()
