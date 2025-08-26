self.importScripts("https://cdn.jsdelivr.net/npm/fuse.js@7");

function normalizeCard(raw) {
  const low = raw?.cardmarket?.prices?.lowPrice;
  return {
    id:        raw?.id ?? null,
    name:      raw?.name ?? "",
    set:       raw?.set ?? raw?.setName ?? null,
    number:    raw?.number ?? null,
    rarity:    raw?.rarity ?? null,
    image:     raw?.images?.small ?? null,
    priceLow:  Number.isFinite(low) ? low : 0,
    updatedAt: raw?.cardmarket?.updatedAt ?? null
  };
}

let fuse = null;
let indexedCount = 0;

async function fetchJson(url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
  return res.json();
}

self.onmessage = async (e) => {
  const { type, payload } = e.data || {};

  // optional health check
  if (type === "PING") {
    self.postMessage({ type: "PONG" });
    return;
  }

  // ---------- BUILD: Katalog laden & indexieren ----------
  if (type === "BUILD") {
    try {
      const files = payload?.files || [];
      const total = files.length;
      const all = [];
      indexedCount = 0;

      for (const url of files) {
        try {
          const json = await fetchJson(url);          // Array von Karten
          for (const card of json) all.push(normalizeCard(card));
        } catch (err) {
          // Datei darf fehlen/fehlerhaft sein – wir überspringen sie
          // und melden das optional an die UI
          self.postMessage({ type: "WARN", file: url, message: String(err) });
        } finally {
          indexedCount++;
          self.postMessage({ type: "PROGRESS", loaded: indexedCount, total });
        }
      }

      fuse = new Fuse(all, {
        keys: ["name", "set", "number", "rarity"],
        includeScore: true,
        threshold: 0.35,      // eher präzise
        ignoreLocation: true,
        minMatchCharLength: 2
      });

      self.postMessage({ type: "READY", count: all.length });
    } catch (err) {
      self.postMessage({ type: "ERROR", message: String(err) });
    }
    return;
  }

  // ---------- SEARCH: Abfrage gegen den Index ----------
  if (type === "SEARCH") {
    if (!fuse) {
      self.postMessage({ type: "NOT_READY" });
      return;
    }
    const q = String(payload?.query || "").trim();
    if (!q) {
      self.postMessage({ type: "RESULTS", items: [] });
      return;
    }
    const res = fuse.search(q, { limit: 50 });
    const items = res.map(r => ({ ...r.item, _score: r.score }));
    self.postMessage({ type: "RESULTS", items });
    return;
  }
};