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

Il browser si apre automaticamente su `http://127.0.0.1:8000`

---

## Installazione (Windows)

VolleyStat gira anche su Windows: il codice Python è identico, cambiano solo
gli script di avvio (`.bat` invece di `.sh`).

### Guida passo passo

1. **Installa Python** (se non è già presente)
   - Vai su https://www.python.org/downloads/windows/ e scarica l'ultima versione di Python 3.
   - Avvia l'installer. **Nella prima schermata spunta la casella
     "Add python.exe to PATH"** in basso, poi clicca "Install Now".
   - Verifica l'installazione aprendo il **Prompt dei comandi** (cerca "cmd"
     nel menu Start) e digitando:
     ```
     python --version
     ```
     Deve rispondere con qualcosa tipo `Python 3.12.x`. Se dice "comando non
     riconosciuto", riavvia il PC (serve a ricaricare il PATH) e riprova.

2. **Scarica VolleyStat**
   - Se hai Git: `git clone <url-del-repo>` da Prompt dei comandi.
   - Altrimenti scarica lo ZIP da GitHub ("Code" → "Download ZIP") ed estrailo
     in una cartella, ad esempio `C:\VolleyStat`.

3. **Installa le dipendenze**
   - Apri la cartella `VolleyStat` in Esplora File.
   - Fai **doppio click su `install.bat`**.
   - Lo script controlla che Python sia installato, crea un ambiente virtuale
     nella sotto-cartella `.venv` e installa Flask al suo interno. Se qualcosa
     manca (Python non trovato, modulo `venv` non disponibile, installazione
     di Flask fallita) lo script si ferma e mostra un messaggio d'errore
     chiaro con l'indicazione di cosa fare.
   - A installazione riuscita vedrai "Installazione completata!".

4. **Avvia l'applicazione**
   - Fai **doppio click su `run.bat`**.
   - Si apre una finestra nera (il server) e il browser predefinito su
     `http://127.0.0.1:8000`.
   - Per usarlo da tablet/altri PC sulla stessa rete Wi-Fi, usa l'indirizzo IP
     mostrato nella finestra del server (es. `http://192.168.1.50:8000`).
   - Per chiudere il programma: torna sulla finestra nera e premi `Ctrl+C`,
     oppure chiudila direttamente.

Oppure manualmente da Prompt dei comandi, nella cartella del progetto:
```bat
python -m venv .venv
.venv\Scripts\pip install flask
.venv\Scripts\python app.py
```

### Note

- Se Windows Defender / il firewall chiede il permesso per Python alla prima
  esecuzione, consenti l'accesso alle **reti private** (serve per farlo
  raggiungere da tablet sulla stessa rete Wi-Fi/LAN).
- `install.bat` e `run.bat` sono equivalenti a `install.sh` e `run.sh`: fanno
  esattamente le stesse operazioni (creazione venv, installazione Flask,
  avvio del server), solo con la sintassi Windows.

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

- Python 3.8+ (Windows, macOS o Linux)
- Flask (unico pacchetto Python necessario, installato automaticamente da
  `install.sh` / `install.bat`)
- Browser web (Firefox, Chrome, Edge — uno di questi è già presente su
  qualsiasi PC moderno)
- Connessione internet: **non necessaria** per l'uso quotidiano (solo per il
  primo download di Python/Flask)
