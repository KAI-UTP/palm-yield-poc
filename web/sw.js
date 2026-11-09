/* PalmYield offline support: the app opens without a signal in the field.
   App files and data: network first, cached copy when offline.
   Libraries and fonts from CDNs: cache first (they are versioned). */
const CACHE = "palmyield-v10";
const SHELL = ["./", "index.html", "styles.css?v=10", "engine.js?v=10", "ask.js?v=10", "app.js?v=10", "data/app.json?v=10", "icon.svg", "icon-192.png", "manifest.webmanifest"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.hostname.endsWith("googleapis.com") && url.pathname.includes("generateContent")) return; // AI calls: never cache
  const save = (res) => { if (res && (res.ok || res.type === "opaque")) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); } return res; };
  if (url.origin === location.origin) {
    e.respondWith(fetch(req).then(save).catch(() => caches.match(req).then((r) => r || caches.match("index.html"))));
  } else if (/cdnjs\.cloudflare\.com|cdn\.jsdelivr\.net|fonts\.(googleapis|gstatic)\.com|tile\.openstreetmap\.org|basemaps\.cartocdn\.com|arcgisonline\.com/.test(url.hostname)) {
    e.respondWith(caches.match(req).then((hit) => hit || fetch(req).then(save)));
  }
});
