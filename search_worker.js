self.importScripts("https://cdn.jsdelivr.net/npm/fuse.js@7");

// --- Hilfsfunktion: Karten-Objekte normalisieren ---
function normalizeCard(raw) {
  const low = raw?.cardmarket?.prices?.lowPrice;
  return {
    id: raw.id,
    name: raw.name,
    set: raw.set || raw.setName || null,
    number: raw.number,
    rarity: raw.rarity || null,
    image: raw?.images?.small || null,
    priceLow: typeof low === "number" ? low : 0,
    updatedAt: raw?.cardmarket?.updatedAt || null,
  };
}

let fuse = null;

// --- Nachrichten vom Haupt-Thread ---
self.onmessage = async (e) => {
  const { type, payload } = e.data || {};

  // === Index aufbauen ===
  if (type === "BUILD") {
    const files = payload?.files || [];
    const all = [];
    const total = files.length;

    // Status: Start
    self.postMessage({ type: "PROGRESS", loaded: 0, total });

    let loaded = 0;
    for (const url of files) {
      try {
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) {
          self.postMessage({
            type: "WARN",
            file: url,
            message: `HTTP ${res.status}`,
          });
        } else {
          const json = await res.json();
          if (Array.isArray(json)) {
            json.forEach((card) => all.push(normalizeCard(card)));
          } else {
            self.postMessage({
              type: "WARN",
              file: url,
              message: "Kein Array im JSON",
            });
          }
        }
      } catch (err) {
        self.postMessage({
          type: "WARN",
          file: url,
          message: String(err),
        });
      } finally {
        loaded++;
        self.postMessage({ type: "PROGRESS", loaded, total, file: url });
      }
    }

    try {
      fuse = new Fuse(all, {
        keys: ["name", "set", "number", "rarity"],
        includeScore: true,
        threshold: 0.35, // eher präzise
        ignoreLocation: true,
      });
    } catch (err) {
      self.postMessage({
        type: "ERROR",
        message: "Fuse-Init fehlgeschlagen: " + String(err),
      });
      return;
    }

    // Fertig
    self.postMessage({ type: "READY", count: all.length });
  }

  // === Suche ausführen ===
  if (type === "SEARCH") {
    if (!fuse) {
      self.postMessage({ type: "RESULTS", items: [] });
      return;
    }
    const q = String(payload?.query || "").trim();
    if (!q) {
      self.postMessage({ type: "RESULTS", items: [] });
      return;
    }
    const res = fuse.search(q, { limit: 50 });
    const items = res.map((r) => ({ ...r.item, _score: r.score }));
    self.postMessage({ type: "RESULTS", items });
  }
};
