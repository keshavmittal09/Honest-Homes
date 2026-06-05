// ============================================================
// Honest Homes — data layer (single source of truth)
// One consistent async API for every screen. Handles two project kinds:
//   • SHOWCASE  — 3 illustrative projects (green/amber/red) so the full verdict
//                 design is demoable. Clearly labelled "illustrative".
//   • REAL      — the 44k+ live MahaRERA index, fetched from our backend. These
//                 honestly render in the "incomplete" band until reputation data
//                 lands (no faked scores).
// Everything goes through HH (below). No screen reads raw arrays synchronously.
// ============================================================

const AS_OF_FALLBACK = "June 2026";

// ---- Showcase projects (illustrative; never claimed as real) ----
const SHOWCASE = [
  {
    id: "DEMO-GREEN", showcase: true, band: "green", score: 8.7,
    name: "Suncrest Residences", builder: "Aravind Realty Pvt Ltd", builderId: "aravind",
    district: "Pune", locality: "Mulshi", pincode: "411057", status: "Registered", statusNote: "Active",
    registered: "14 Mar 2022", lastModified: "02 Apr 2026",
    promisedCompletion: "31 Dec 2025", revisedCompletion: null, actualCompletion: "18 Nov 2025",
    extensions: 0, complaints: 0, orders: 0, units: 248,
    headline: "Registered and in good standing. Delivered on time with no complaints or orders on record.",
    summary: "An illustrative CLEAN verdict — what a green result looks like once complaint and timeline data are ingested. Delivered ahead of schedule with a spotless compliance history.",
    signals: [
      { kind: "positive", impact: +3.0, icon: "shield-check", fact: "RERA-registered and currently active", detail: "Registration active since 2022 with no lapse.", source: "MahaRERA", asOf: AS_OF_FALLBACK },
      { kind: "positive", impact: +2.4, icon: "calendar-check", fact: "Delivered 43 days ahead of the promised date", detail: "Promised 31 Dec 2025 · occupancy recorded 18 Nov 2025.", source: "MahaRERA", asOf: AS_OF_FALLBACK },
      { kind: "positive", impact: +1.6, icon: "scale", fact: "No complaints filed with MahaRERA", detail: "Zero consumer complaints across the project's lifetime.", source: "MahaRERA Complaints Register", asOf: AS_OF_FALLBACK },
      { kind: "positive", impact: +1.2, icon: "gavel", fact: "No adjudicating-officer or tribunal orders", detail: "No orders, penalties or directions issued against this project.", source: "MahaRERA Orders", asOf: AS_OF_FALLBACK },
    ],
    timeline: [
      { label: "Registered", date: "Mar 2022", type: "start" },
      { label: "Promised", date: "Dec 2025", type: "promised" },
      { label: "Delivered", date: "Nov 2025", type: "delivered" },
    ],
    dataComplete: true,
  },
  {
    id: "DEMO-AMBER", showcase: true, band: "amber", score: 5.2,
    name: "Skyline Vista", builder: "Greenstone Developers", builderId: "greenstone",
    district: "Thane", locality: "Ghodbunder Road", pincode: "400607", status: "Registered", statusNote: "Extended twice",
    registered: "08 Jun 2020", lastModified: "21 Mar 2026",
    promisedCompletion: "30 Jun 2023", revisedCompletion: "31 Dec 2025", actualCompletion: null,
    extensions: 2, complaints: 3, orders: 1, units: 412,
    headline: "Completion has been pushed back twice and 3 complaints are on record. Registration is valid — proceed with caution.",
    summary: "An illustrative CAUTION verdict. Still registered and active, but the promised handover has slipped 2.5 years across two extension certificates, with three buyer complaints on file.",
    signals: [
      { kind: "positive", impact: +2.0, icon: "shield-check", fact: "RERA-registered and currently active", detail: "Registration valid; not revoked or suspended.", source: "MahaRERA", asOf: AS_OF_FALLBACK },
      { kind: "caution", impact: -1.8, icon: "calendar-clock", fact: "Completion revised twice — 2.5 years past original promise", detail: "30 Jun 2023 → 30 Jun 2024 → 31 Dec 2025.", source: "MahaRERA Extension Certificates", asOf: AS_OF_FALLBACK },
      { kind: "caution", impact: -1.4, icon: "scale", fact: "3 consumer complaints filed", detail: "Possession delay and amenity shortfalls. 1 resolved, 2 pending.", source: "MahaRERA Complaints Register", asOf: AS_OF_FALLBACK },
      { kind: "caution", impact: -0.9, icon: "gavel", fact: "1 adjudicating-officer order on record", detail: "Order directed delay-interest payment to a complainant (2024).", source: "MahaRERA Orders", asOf: AS_OF_FALLBACK },
    ],
    timeline: [
      { label: "Registered", date: "Jun 2020", type: "start" },
      { label: "Promised", date: "Jun 2023", type: "promised" },
      { label: "Revised", date: "Jun 2024", type: "revised" },
      { label: "Revised", date: "Dec 2025", type: "revised" },
      { label: "Today", date: "Jun 2026", type: "now" },
    ],
    dataComplete: true,
  },
  {
    id: "DEMO-RED", showcase: true, band: "red", score: 1.8,
    name: "Imperial Heights", builder: "Veracon Infra Pvt Ltd", builderId: "veracon",
    district: "Mumbai Suburban", locality: "Mira Road", pincode: "401107", status: "Revoked", statusNote: "Registration revoked",
    registered: "19 Jan 2019", lastModified: "07 Feb 2026",
    promisedCompletion: "31 Dec 2022", revisedCompletion: "31 Dec 2024", actualCompletion: null,
    extensions: 2, complaints: 11, orders: 4, units: 560, revoked: true,
    headline: "Registration has been REVOKED by MahaRERA. 11 complaints and 4 orders are on record. Treat with serious caution.",
    summary: "An illustrative SERIOUS-FLAGS verdict. Registration was revoked following missed deadlines, recovery warrants and a high volume of buyer complaints — among the most severe states MahaRERA records.",
    signals: [
      { kind: "severe", impact: -4.0, icon: "ban", fact: "MahaRERA registration REVOKED", detail: "Revoked on 07 Feb 2026 — among the most serious flags MahaRERA can apply.", source: "MahaRERA Revocation Order", asOf: AS_OF_FALLBACK },
      { kind: "severe", impact: -2.2, icon: "scale", fact: "11 consumer complaints filed", detail: "Possession delay, fund-diversion allegations, refund non-payment. 9 pending.", source: "MahaRERA Complaints Register", asOf: AS_OF_FALLBACK },
      { kind: "severe", impact: -1.6, icon: "gavel", fact: "4 orders including 2 recovery warrants", detail: "Recovery warrants issued to the Collector for refund recovery.", source: "MahaRERA Orders", asOf: AS_OF_FALLBACK },
      { kind: "severe", impact: -0.8, icon: "file-warning", fact: "Quarterly progress reports not filed since Q2 2024", detail: "QPR filings stopped — a common precursor to revocation.", source: "MahaRERA QPR", asOf: AS_OF_FALLBACK },
    ],
    timeline: [
      { label: "Registered", date: "Jan 2019", type: "start" },
      { label: "Promised", date: "Dec 2022", type: "promised" },
      { label: "Revised", date: "Dec 2024", type: "revised" },
      { label: "Revoked", date: "Feb 2026", type: "revoked" },
    ],
    dataComplete: true,
  },
];

const BUILDERS = {
  aravind:   { name: "Aravind Realty Pvt Ltd", since: 2011, totalProjects: 9, delivered: 7, delayed: 0, revoked: 0,
    note: "Illustrative track record — consistent on-time delivery across a decade.",
    others: [
      { id: "DEMO-GREEN", name: "Suncrest Residences", district: "Pune", band: "green", status: "Delivered on time" },
    ] },
  greenstone:{ name: "Greenstone Developers", since: 2014, totalProjects: 6, delivered: 3, delayed: 3, revoked: 0,
    note: "Illustrative track record — a pattern of extensions; 3 of 6 projects revised.",
    others: [
      { id: "DEMO-AMBER", name: "Skyline Vista", district: "Thane", band: "amber", status: "Extended ×2" },
    ] },
  veracon:   { name: "Veracon Infra Pvt Ltd", since: 2016, totalProjects: 5, delivered: 1, delayed: 4, revoked: 2,
    note: "Illustrative track record — two revocations and a heavy complaint load. High-risk promoter.",
    others: [
      { id: "DEMO-RED", name: "Imperial Heights", district: "Mumbai Suburban", band: "red", status: "REVOKED" },
    ] },
};

const SHOWCASE_BY_ID = Object.fromEntries(SHOWCASE.map(p => [p.id, p]));
const EXAMPLE_CHIPS = ["Lodha", "Godrej", "Runwal", "Pune", "Thane"];

// ============================================================
// HH — the one data layer every screen calls. All async.
// ============================================================
const HH = (() => {
  let meta = { asOf: AS_OF_FALLBACK, indexed: 0 };
  const fullCache = new Map();   // id -> { project, builder }
  SHOWCASE.forEach(p => fullCache.set(p.id, { project: p, builder: BUILDERS[p.builderId] }));

  async function _json(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }

  return {
    showcase: SHOWCASE,
    showcaseIds: SHOWCASE.map(p => p.id),
    exampleChips: EXAMPLE_CHIPS,
    meta: () => meta,

    // Landing featured = showcase trio + a few real projects.
    async featured() {
      try {
        const d = await _json("/api/hh/featured");
        meta = { asOf: d.as_of || AS_OF_FALLBACK, indexed: d.indexed || 0 };
        return { showcase: SHOWCASE, real: d.cards || [], meta };
      } catch {
        return { showcase: SHOWCASE, real: [], meta };
      }
    },

    // Paginated search across showcase (local, first page only) + real (API).
    // Returns { cards, total, offset, hasMore }. Showcase cards are prepended on the
    // first page so the green/amber/red examples are always visible.
    async search(q, offset = 0, limit = 30) {
      const query = (q || "").trim().toLowerCase();
      const localHits = offset > 0 ? [] : (query
        ? SHOWCASE.filter(p =>
            p.name.toLowerCase().includes(query) ||
            p.builder.toLowerCase().includes(query) ||
            p.district.toLowerCase().includes(query) ||
            p.id.toLowerCase().includes(query))
        : SHOWCASE.slice());
      let real = [], realTotal = 0;
      try {
        const d = await _json(`/api/hh/search?q=${encodeURIComponent(q || "")}&offset=${offset}&limit=${limit}`);
        real = d.cards || [];
        realTotal = d.total || 0;
      } catch {}
      const cards = [...localHits, ...real];
      const hasMore = (offset + real.length) < realTotal;   // more real rows on server
      const total = realTotal + localHits.length;            // for the "X on record" label
      return { cards, total, offset, nextOffset: offset + real.length, hasMore };
    },

    // Full project (verdict/report). Cached. Showcase served locally.
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
window.HH_DATA = { AS_OF: AS_OF_FALLBACK, EXAMPLE_CHIPS, showcaseIds: HH.showcaseIds };
