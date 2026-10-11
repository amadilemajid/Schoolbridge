/**
 * SchoolBridge Service Worker
 * Provides offline caching for Ugandan schools on low-bandwidth or intermittent
 * 2G/3G connections. Critical for rural schools without reliable internet access.
 *
 * Strategy:
 *  - Cache First: Static assets (JS, CSS, icons, fonts)
 *  - Network First with Fallback: API responses (attendance, marks)
 *  - Offline Page: Shown when navigation requests fail and no cache exists
 */

const SW_VERSION = 'sb-v1.0.2-force-purge';
const STATIC_CACHE = `${SW_VERSION}-static`;
const API_CACHE = `${SW_VERSION}-api`;

// Static assets to pre-cache on install
const PRECACHE_URLS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/favicon.svg',
];

// API route patterns to cache with network-first strategy
const API_CACHE_PATTERNS = [
  '/api/v1/schools/',
  '/api/v1/students/students/',
  '/api/v1/attendance/register/',
  '/api/v1/results/marks-entry/',
  '/api/v1/academics/timetables/',
];

// ─── Install: Pre-cache static shell ─────────────────────────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(PRECACHE_URLS))
  );
  self.skipWaiting();
});

// ─── Activate: Clean up stale caches from previous SW versions ───────────────
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== STATIC_CACHE && k !== API_CACHE)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// ─── Fetch: Route-based caching strategy ─────────────────────────────────────
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET and cross-origin requests
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;

  // API routes: Network First with cache fallback
  const isApiRequest = API_CACHE_PATTERNS.some((p) => url.pathname.startsWith(p));
  if (isApiRequest) {
    event.respondWith(networkFirstWithCache(request, API_CACHE));
    return;
  }

  // Static assets: Cache First
  event.respondWith(cacheFirstWithNetwork(request, STATIC_CACHE));
});

// ─── Strategy: Network First (API data — freshness preferred) ────────────────
async function networkFirstWithCache(request, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const networkResponse = await fetch(request, { signal: AbortSignal.timeout(8000) });
    if (networkResponse.ok) {
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch {
    // Network failed — serve stale cache data with offline header
    const cached = await cache.match(request);
    if (cached) {
      const headers = new Headers(cached.headers);
      headers.set('X-SchoolBridge-Offline', 'true');
      return new Response(cached.body, { status: 200, headers });
    }
    return new Response(
      JSON.stringify({ detail: 'Offline — data unavailable. Check your internet connection.' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    );
  }
}

// ─── Strategy: Cache First (Static shell — speed preferred) ──────────────────
async function cacheFirstWithNetwork(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;

  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch {
    // Navigate to cached index.html for SPA client-side routing support
    if (request.mode === 'navigate') {
      const indexFallback = await cache.match('/index.html');
      if (indexFallback) return indexFallback;
    }
    return new Response('SchoolBridge — Offline Mode', { status: 503 });
  }
}
