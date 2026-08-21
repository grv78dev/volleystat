# ⬡ VolleyStat — Gestione Statistiche Pallavolo

Applicazione leggera per il rilevamento statistico delle partite di pallavolo.
Funziona **completamente offline**, si avvia nel browser.

---

## Installazione (Ubuntu / Linux)

```bash
# 1. Prima volta: installa le dipendenze
bash install.sh

# 2. Avvia l'applicazione
bash run.sh
```

Oppure manualmente:
```bash
pip3 install flask
python3 app.py
```

Il browser si apre automaticamente su `http://127.0.0.1:5000`

---

## Flusso di utilizzo

1. **Rosa** → Inserisci tutti gli atleti (numero, nome, ruolo)
2. **Calendario** → Pianifica le partite della stagione
3. **Giorno partita** → Apri la partita → Avvia Set → Inserisci formazione → Rileva statistiche
4. **Fine partita** → Visualizza statistiche → Stampa / Salva PDF

---

## Comandi di inserimento rapido

| Comando | Azione |
|---------|--------|
| `S81`   | Servizio ace del giocatore #81 |
| `SE81`  | Errore servizio del giocatore #81 |
| `A10`   | Attacco kill (punto) del #10 |
| `AE10`  | Errore attacco del #10 |
| `AB10`  | Attacco murato del #10 |
| `B7`    | Punto a muro del #7 |
| `BE7`   | Errore muro del #7 |
| `R+15`  | Ricezione ottima del #15 (voto 3) |
| `R15`   | Ricezione positiva del #15 (voto 2) |
| `R-15`  | Ricezione negativa del #15 (voto 1) |
| `RE15`  | Errore ricezione del #15 |
| `D5`    | Difesa positiva del #5 |
| `DE5`   | Errore difesa del #5 |
| `P`     | Punto (errore avversario generico) |
| `PE`    | Punto avversario (nostro errore generico) |
| `SUB10/12` | Sostituzione: #10 esce, #12 entra |
| `T`     | Timeout noi |
| `TO`    | Timeout avversario |
| `UNDO`  | Annulla l'ultimo evento |

**Tasti rapidi nell'input:**
- `↑ / ↓` → naviga nella cronologia comandi
- `Invio` → conferma comando
- Qualsiasi tasto sulla pagina → focus automatico sull'input

---

## Rotazione automatica

Quando si guadagna il servizio (punto mentre l'avversario batteva), il programma
aggiorna automaticamente la formazione a schermo:
- Il giocatore in **P2** passa a **P1** (diventa battitore)
- La rotazione è visualizzata in tempo reale sul campo

---

## Export PDF / Stampa

Al termine della partita (o durante):
- Clicca **🖨 Stampa / PDF** → si apre una pagina ottimizzata per la stampa
- Usa `Ctrl+P` → **Salva come PDF** nel menu di stampa del browser
- Il report include: riepilogo set, grafici punti/errori, tabella dettagliata per giocatore

---

## Dati

I dati sono salvati nella cartella `data/` come file JSON.
Backup: copia l'intera cartella `volleystat/` per preservare tutti i dati.

---

## Requisiti

- Python 3.8+
- Flask (unico pacchetto Python necessario)
- Browser web (Firefox, Chromium — già presenti su Ubuntu)
- Connessione internet: **non necessaria**
