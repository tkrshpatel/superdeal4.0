const CACHE = 'superdeal-shell-v4';
const SHELL = ['/', '/index.html', '/manifest.webmanifest', '/icon.svg'];
self.addEventListener('install', event => { event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener('activate', event => { event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('superdeal-shell-') && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  // Prices and affiliate redirects must never be served from an offline cache.
  if (/^\/(deals|go|health|api)(\/|$)/.test(url.pathname)) return;
  const staticAsset = !url.search && (SHELL.includes(url.pathname) || /^\/(assets|brand)\//.test(url.pathname));
  if (!staticAsset && event.request.mode !== 'navigate') return;
  event.respondWith(fetch(event.request).then(response => {
    const copy = response.clone();
    if (response.ok && staticAsset && event.request.destination !== 'document') caches.open(CACHE).then(cache => cache.put(event.request, copy));
    return response;
  }).catch(() => caches.match(event.request).then(cached => cached || (event.request.mode === 'navigate' ? caches.match('/index.html') : Response.error()))));
});