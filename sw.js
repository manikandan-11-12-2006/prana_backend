// sw.js
const CACHE_NAME = "nayaruvi-cache-v1";

// Cache only FRONTEND assets (don't cache .pkl / .csv / python files)
const ASSETS_TO_CACHE = [
  "./",
  "./index.html",
  "./manifest.json",

  "./logo.png",
  "./n_logo.png",
  "./s.png"
];

// Install: cache core files
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS_TO_CACHE))
  );
  self.skipWaiting();
});

// Activate: remove old caches
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.map((key) => (key !== CACHE_NAME ? caches.delete(key) : null)))
    )
  );
  self.clients.claim();
});

// Fetch strategy:
// 1) API calls -> network-first (fresh data)
// 2) Static files -> cache-first
self.addEventListener("fetch", (event) => {
  const req = event.request;

  // only handle GET
  if (req.method !== "GET") return;

  const url = new URL(req.url);

  // ✅ If your Flask API is like /predict or /api/... then keep it fresh
  if (url.pathname.startsWith("/predict") || url.pathname.startsWith("/api")) {
    event.respondWith(
      fetch(req).catch(() => caches.match("./index.html"))
    );
    return;
  }

  // ✅ Static: cache-first
  event.respondWith(
    caches.match(req).then((cached) => {
      if (cached) return cached;

      return fetch(req)
        .then((res) => {
          // cache valid responses
          const copy = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
          return res;
        })
        .catch(() => caches.match("./index.html"));
    })
  );
});
