// Aube service worker — shell en cache, éditions en "réseau d'abord"
const VERSION = 'aube-v3';
const AUDIO = 'aube-audio';
const SHELL = ['./', 'index.html', 'manifest.webmanifest', 'icons/icon-192.png', 'icons/icon-512.png', 'icons/favicon.png'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== VERSION && k !== AUDIO).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  const sameOrigin = url.origin === self.location.origin;
  // podcast : servi depuis le cache s'il a été téléchargé (avec gestion des plages pour l'avance rapide)
  if (sameOrigin && url.pathname.includes('/podcast/')) {
    e.respondWith((async () => {
      const hit = await caches.open(AUDIO).then(c => c.match(url.origin + url.pathname));
      if (!hit) return fetch(req);
      const range = req.headers.get('range');
      if (!range) return hit;
      const buf = await hit.arrayBuffer();
      const m = /bytes=(\d*)-(\d*)/.exec(range) || [];
      const size = buf.byteLength;
      let start = m[1] ? parseInt(m[1], 10) : 0;
      let end = m[2] ? parseInt(m[2], 10) : size - 1;
      if (!m[1] && m[2]) { start = size - parseInt(m[2], 10); end = size - 1; }
      end = Math.min(end, size - 1);
      return new Response(buf.slice(start, end + 1), { status: 206, headers: {
        'Content-Type': hit.headers.get('Content-Type') || 'audio/ogg',
        'Content-Range': `bytes ${start}-${end}/${size}`,
        'Content-Length': String(end - start + 1), 'Accept-Ranges': 'bytes' } });
    })());
    return;
  }
  const isData = sameOrigin && (url.pathname.includes('/editions/') || req.mode === 'navigate' || url.pathname.endsWith('index.html'));
  if (isData) {
    // réseau d'abord, cache en secours (lecture hors connexion)
    const key = new Request(url.origin + url.pathname);
    e.respondWith(fetch(req).then(res => {
      if (res.ok) { const copy = res.clone(); caches.open(VERSION).then(c => c.put(key, copy)); }
      return res;
    }).catch(() => caches.match(key).then(r => r || caches.match('index.html'))));
    return;
  }
  // polices et icônes : cache d'abord
  if (sameOrigin || url.hostname.endsWith('gstatic.com') || url.hostname.endsWith('googleapis.com')) {
    e.respondWith(caches.match(req).then(r => r || fetch(req).then(res => {
      if (res.ok || res.type === 'opaque') { const copy = res.clone(); caches.open(VERSION).then(c => c.put(req, copy)); }
      return res;
    })));
  }
});
