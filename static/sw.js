const CACHE = 'volleystat-v1';

const PRECACHE = [
  '/static/style.css',
  '/static/app.js',
  '/static/report_base.css',
  '/static/icons/icon.svg',
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(PRECACHE))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(k => k !== CACHE).map(k => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Solo GET e stessa origine
  if (request.method !== 'GET' || url.origin !== location.origin) return;

  // Polling live: mai in cache
  if (url.pathname.endsWith('/stato')) return;

  // Asset statici: cache-first, aggiorna in background
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(request).then(cached => {
        const networkFetch = fetch(request).then(response => {
          caches.open(CACHE).then(c => c.put(request, response.clone()));
          return response;
        });
        return cached || networkFetch;
      })
    );
    return;
  }

  // Pagine HTML: network-first, fallback alla cache
  event.respondWith(
    fetch(request)
      .then(response => {
        caches.open(CACHE).then(c => c.put(request, response.clone()));
        return response;
      })
      .catch(() => caches.match(request))
  );
});
