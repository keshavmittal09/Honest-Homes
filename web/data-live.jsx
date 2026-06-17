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
    // Returns { cards, total, offset, nextOffset, hasMore }.
    async search(q, offset = 0, limit = 30) {
      let real = [], realTotal = 0;
      try {
        const d = await _json(`/api/hh/search?q=${encodeURIComponent(q || "")}&offset=${offset}&limit=${limit}`);
        real = d.cards || [];
        realTotal = d.total || 0;
      } catch {}
      const hasMore = (offset + real.length) < realTotal;
      return { cards: real, total: realTotal, offset, nextOffset: offset + real.length, hasMore };
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
