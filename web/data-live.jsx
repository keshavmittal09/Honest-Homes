// ============================================================
// Honest Homes — data layer (single source of truth)
// One consistent async API for every screen. All projects are REAL: the 44k+
// live MahaRERA index, fetched from our backend. Projects render in the
// "incomplete" band until reputation/detail data lands — we never fake a score.
// Everything goes through HH (below). No screen reads raw arrays synchronously.
// ============================================================

const AS_OF_FALLBACK = "June 2026";
const EXAMPLE_CHIPS = ["Lodha", "Godrej", "Runwal", "Pune", "Thane"];

// ============================================================
// HH — the one data layer every screen calls. All async.
// ============================================================
const HH = (() => {
  let meta = { asOf: AS_OF_FALLBACK, indexed: 0 };
  const fullCache = new Map();   // id -> { project, builder }
  const amenCache = new Map();   // id -> neighbourhood directory
  let promptCache = null;        // discussion prompts (same for every project)

  async function _json(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }

  return {
    showcase: [],
    showcaseIds: [],
    exampleChips: EXAMPLE_CHIPS,
    meta: () => meta,

    // Landing featured = a few real projects from the index.
    async featured() {
      try {
        const d = await _json("/api/hh/featured");
        meta = { asOf: d.as_of || AS_OF_FALLBACK, indexed: d.indexed || 0 };
        return { real: d.cards || [], meta };
      } catch {
        return { real: [], meta };
      }
    },

    // Paginated search/browse over the real MahaRERA index (API).
    // Returns { cards, total, offset, nextOffset, hasMore, area }.
    // `area` is set when the query named a place rather than a project, so the
    // results header can say "156 projects in Kharghar" instead of leaving the
    // visitor to guess why a name search returned a whole locality.
    async search(q, offset = 0, limit = 30) {
      let real = [], realTotal = 0, area = null;
      try {
        const d = await _json(`/api/hh/search?q=${encodeURIComponent(q || "")}&offset=${offset}&limit=${limit}`);
        real = d.cards || [];
        realTotal = d.total || 0;
        area = d.area || null;
      } catch {}
      const hasMore = (offset + real.length) < realTotal;
      return { cards: real, total: realTotal, offset, nextOffset: offset + real.length, hasMore, area };
    },

    // Area suggestions for the search box (localities, pincodes, districts).
    async areas(q, limit = 8) {
      try {
        const d = await _json(`/api/hh/areas?q=${encodeURIComponent(q || "")}&limit=${limit}`);
        return d.areas || [];
      } catch { return []; }
    },

    // Neighbourhood directory for one project. Cached: it is ~20 KB and the
    // verdict page may mount it more than once.
    async amenities(id) {
      if (amenCache.has(id)) return amenCache.get(id);
      try {
        const d = await _json("/api/hh/amenities/" + encodeURIComponent(id));
        amenCache.set(id, d);
        return d;
      } catch { return { available: false }; }
    },

    // Every place in one category — the "show all N" expansion.
    async amenityCategory(id, key) {
      try {
        const d = await _json(`/api/hh/amenities/${encodeURIComponent(id)}/${encodeURIComponent(key)}`);
        return d.places || [];
      } catch { return []; }
    },

    // --- buyer discussion -------------------------------------------------
    async discussionPrompts() {
      if (promptCache) return promptCache;
      try {
        promptCache = await _json("/api/hh/discussion/prompts");
        return promptCache;
      } catch { return { prompts: [], relations: [] }; }
    },

    async discussion(id) {
      try { return await _json("/api/hh/discussion/" + encodeURIComponent(id)); }
      catch { return { posts: [], count: 0 }; }
    },

    async postDiscussion(payload) {
      try {
        const r = await fetch("/api/hh/discussion", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        // A 400 carries the reason the post was rejected; surface it rather
        // than showing the visitor a generic failure.
        const d = await r.json().catch(() => ({}));
        if (!r.ok) return { ok: false, error: d.detail || "could not post" };
        return d;
      } catch { return { ok: false, error: "network" }; }
    },

    async reportDiscussion(id, reason) {
      try {
        await fetch("/api/hh/discussion/report", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id, reason }),
        });
      } catch {}
    },

    // Projects nearest a point. Only the deep-collected set carries coordinates,
    // so the response also reports how many were searched.
    async nearby(lat, lng, km = 10) {
      try {
        return await _json(`/api/hh/nearby?lat=${lat}&lng=${lng}&km=${km}`);
      } catch {
        return { cards: [], searched: 0, found: 0, radiusKm: km };
      }
    },

    // Full project (verdict/report). Cached.
    async project(id) {
      if (fullCache.has(id)) return fullCache.get(id);
      try {
        const d = await _json("/api/hh/project/" + encodeURIComponent(id));
        const out = { project: d.project, builder: d.builder };
        fullCache.set(id, out);
        return out;
      } catch { return null; }
    },
  };
})();

window.HH = HH;
// Back-compat for any component still referencing HH_DATA.* for static bits.
window.HH_DATA = { AS_OF: AS_OF_FALLBACK, EXAMPLE_CHIPS, showcaseIds: [] };
