/* AutoTax.cloud — Service Worker v1 */
const CACHE_NAME = "autotax-v2";
const OFFLINE_URL = "/offline.html";

const PRECACHE = [
  "/app",
  "/landing.html",
  "/style.css",
  "/app.js",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  OFFLINE_URL,
];

// ── Install: önceden cache'le ──────────────────────────
self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

// ── Activate: eski cache'leri temizle ─────────────────
self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// ── Fetch: Network-first, fallback cache ──────────────
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);

  // API istekleri: network only (cache'leme)
  if (url.pathname.startsWith("/api/")) {
    e.respondWith(
      fetch(e.request).catch(() =>
        new Response(JSON.stringify({ error: "Çevrimdışısınız" }), {
          headers: { "Content-Type": "application/json" },
          status: 503,
        })
      )
    );
    return;
  }

  // Dosya yükleme: network only
  if (e.request.method !== "GET") return;

  // Navigasyon: offline sayfası göster
  if (e.request.mode === "navigate") {
    e.respondWith(
      fetch(e.request).catch(() => caches.match(OFFLINE_URL))
    );
    return;
  }

  // Statik: cache-first
  e.respondWith(
    caches.match(e.request).then((cached) => {
      if (cached) return cached;
      return fetch(e.request).then((resp) => {
        if (resp && resp.status === 200 && resp.type === "basic") {
          const clone = resp.clone();
          caches.open(CACHE_NAME).then((c) => c.put(e.request, clone));
        }
        return resp;
      });
    })
  );
});

// ── Push bildirimleri (gelecek için hazır) ────────────
self.addEventListener("push", (e) => {
  const data = e.data ? e.data.json() : { title: "AutoTax", body: "Bildirim" };
  e.waitUntil(
    self.registration.showNotification(data.title || "AutoTax.cloud", {
      body:  data.body  || "",
      icon:  "/static/icons/icon-192.png",
      badge: "/static/icons/icon-96.png",
    })
  );
});
