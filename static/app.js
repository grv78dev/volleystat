/* VolleyStat — app.js */
/* La maggior parte della logica interattiva è inline nei template */

// Chiudi modal cliccando fuori
document.querySelectorAll('.modal').forEach(m => {
  m.addEventListener('click', function(e) {
    if (e.target === this) this.style.display = 'none';
  });
});

// Escape per chiudere modal
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal').forEach(m => m.style.display = 'none');
  }
});

// Verifica l'abbinamento a 3 posizioni di distanza (1-4, 2-5, 3-6) tra
// palleggiatore/opposto e tra le due centrali/bande. Ritorna un array di
// messaggi di avviso (vuoto se la formazione è coerente). Usato dal court
// builder di "Avvia Set" e "Correggi formazione".
function checkFormationPairing(lineup) {
  const PAIRS = [[1, 4], [2, 5], [3, 6]];
  const VALID = new Set(['PO', 'OP', 'CC', 'BB']);
  const warnings = [];
  for (const [a, b] of PAIRS) {
    const pa = lineup[a], pb = lineup[b];
    if (!pa || !pb) continue;
    const ra = pa.role, rb = pb.role;
    if (!['P', 'O', 'C', 'B'].includes(ra) || !['P', 'O', 'C', 'B'].includes(rb)) continue;
    if (!VALID.has(ra + rb)) {
      warnings.push(`P${a} (#${pa.num} ${ra}) e P${b} (#${pb.num} ${rb})`);
    }
  }
  return warnings;
}
