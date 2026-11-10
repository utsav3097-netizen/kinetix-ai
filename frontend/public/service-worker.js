const CACHE_VERSION = 'kinetix-public-v1';
const OFFLINE_URL = '/offline.html';
const PUBLIC_ICONS = [
  '/icons/kinetix.svg',
  '/icons/kinetix-192.png',
  '/icons/kinetix-512.png',
  '/icons/kinetix-maskable-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_VERSION);
    await cache.addAll([OFFLINE_URL, ...PUBLIC_ICONS]);
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if (key !== CACHE_VERSION) await caches.delete(key);
    }
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (url.pathname === '/api' || url.pathname.startsWith('/api/')) return;

  if (request.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        return await fetch(request);
      } catch {
        return (await caches.match(OFFLINE_URL)) || Response.error();
      }
    })());
    return;
  }

  const isHashedAsset = /^\/assets\/.+-[A-Za-z0-9_-]{8,}\.[^/]+$/.test(url.pathname);
  const isPublicIcon = url.pathname.startsWith('/icons/');
  if (!isHashedAsset && !isPublicIcon) return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE_VERSION);
    const cached = await cache.match(request);
    if (cached) return cached;
    const response = await fetch(request);
    if (response.ok && response.type === 'basic') await cache.put(request, response.clone());
    return response;
  })());
});
