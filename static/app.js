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
