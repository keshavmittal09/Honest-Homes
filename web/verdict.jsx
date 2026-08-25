// ============================================================
// Honest Homes — Verdict screen (the hero)
// ============================================================
const Icon_v = window.Icon;
const { useState: useStateV, useEffect: useEffectV } = React;

function KV({ k, v, mono }) {
  return h("div", { className: "kv" },
    h("div", { className: "k" }, k),
    h("div", { className: `v ${mono ? "mono" : ""}` }, v)
  );
}

// Document categories in display order. This list must stay in step with
// DOC_CATEGORY_ORDER in engine/detail.py — a category missing here is filtered
// out of the panel entirely even though the API is serving it.
const DOC_ORDER = ["Complaint papers", "Approvals & certificates", "Agreements & legal",
  "Plans", "Professional certificates", "KYC & financial", "Other"];
const DOC_ICON = {
  "Commencement Certificate": "shield-check", "Occupancy Certificate": "shield-check",
  "Completion Certificate": "shield-check", "RERA Registration Certificate": "shield-check",
  "Agreement for Sale": "doc", "Building Approval (IOD)": "building",
  "Title & Search Report": "doc", "Title Report": "doc",
  "Complaint Order": "gavel", "Recovery Warrant": "gavel", "Hearing Record (Roznama)": "scale",
};

function SpecCell({ k, v, accent }) {
  return h("div", { className: "spec-cell" },
    h("div", { className: "spec-k" }, k),
    h("div", { className: `spec-v ${accent ? "accent" : ""}` }, (v === null || v === undefined || v === "") ? "—" : v));
}

// ---- One complaint, whole life-cycle ---------------------------------------
const DIRECTION = {
  buyer_vs_builder:     { t: "Buyer → Builder", cls: "red",   d: "A buyer filed this against the builder" },
  builder_vs_buyer:     { t: "Builder → Buyer", cls: "amber", d: "The builder filed this against a buyer" },
  business_vs_business: { t: "Business ↔ Business", cls: "amber", d: "Both parties are businesses" },
  unknown:              { t: "Parties unclear", cls: "", d: "Could not determine which side filed" },
};

function ComplaintRow({ c }) {
  const [open, setOpen] = useStateV(false);
  const dir = DIRECTION[c.direction] || DIRECTION.unknown;
  const nc = c.nonCompliance || [];
  const money = (v) => v ? "₹" + Number(v).toLocaleString("en-IN") : null;

  return h("div", { className: "cmpl" },
    h("button", { className: "cmpl-head", onClick: () => setOpen(o => !o), "aria-expanded": open },
      h("div", { style: { minWidth: 0, flex: 1 } },
        h("div", { className: "row gap-8", style: { flexWrap: "wrap" } },
          h("span", { className: "mono", style: { fontSize: 13, fontWeight: 700 } }, c.complaintNo),
          c.resolved === false
            ? h("span", { className: "badge red", style: { fontSize: 10.5 } }, h("span", { className: "dot" }), "UNRESOLVED")
            : h("span", { className: "badge green", style: { fontSize: 10.5 } }, h("span", { className: "dot" }), "Resolved"),
          c.warrant && h("span", { className: "badge red", style: { fontSize: 10.5 } },
            h(Icon_v, { name: "gavel", size: 11 }), "Recovery warrant")),
        h("div", { className: "cmpl-parties" },
          h("b", null, c.complainant || "—"), " vs ", h("b", null, c.respondent || "—")),
        h("div", { className: "faint", style: { fontSize: 12, marginTop: 3 } },
          h("span", { className: `cmpl-dir ${dir.cls}` }, dir.t),
          c.filedOn ? " · filed " + c.filedOn : "", c.status ? " · " + c.status : "")),
      h(Icon_v, { name: open ? "close" : "more", size: 15, className: "faint" })),

    open && h("div", { className: "cmpl-body" },
      h("div", { className: "faint", style: { fontSize: 12, marginBottom: 10 } }, dir.d, "."),
      c.order && h("div", { className: "cmpl-item" },
        h("b", null, "Order passed"), c.order.approvedOn ? ` on ${c.order.approvedOn}` : "",
        c.order.file && h("div", { className: "faint mono", style: { fontSize: 11.5, marginTop: 2 } }, c.order.file)),
      nc.length > 0 && h("div", { className: "cmpl-item" },
        h("b", null, `${nc.length} non-compliance application(s)`),
        " — the complainant reported the order was not followed.",
        nc.map((m, j) => h("div", { key: j, className: "faint", style: { fontSize: 11.5, marginTop: 3 } },
          m.appliedOn ? `applied ${m.appliedOn}` : "",
          m.roznamaOn ? ` · hearing record ${m.roznamaOn}` : "",
          m.roznamaFile ? ` · ${m.roznamaFile}` : ""))),
      c.warrant && h("div", { className: "cmpl-item danger" },
        h("b", null, "Recovery warrant issued"),
        c.warrant.amount ? ` — ${money(c.warrant.amount)} to recover` : "",
        c.warrant.district ? ` · ${c.warrant.district}` : "",
        h("div", { className: "faint", style: { fontSize: 11.5, marginTop: 2 } },
          "MahaRERA moved to recover after the order went uncomplied.",
          c.warrant.file ? " · " + c.warrant.file : "")),
      !c.order && !nc.length && !c.warrant &&
        h("div", { className: "faint", style: { fontSize: 12 } }, "No order or hearing record published yet.")));
}

// A project can carry 85 complaints. Dumping them all makes a wall nobody reads,
// so lead with the ones that still matter — unresolved, warrants, most recent —
// and keep the rest one click away rather than hidden.
function ComplaintList({ complaints }) {
  const [all, setAll] = useStateV(false);
  const ranked = [...complaints].sort((a, b) => {
    const w = (c) => (c.warrant ? 2 : 0) + (c.resolved === false ? 1 : 0);
    return (w(b) - w(a)) || String(b.filedOn || "").localeCompare(String(a.filedOn || ""));
  });
  const shown = all ? ranked : ranked.slice(0, 6);
  const hidden = ranked.length - shown.length;
  return h(React.Fragment, null,
    shown.map((c, i) => h(ComplaintRow, { key: c.complaintNo || i, c })),
    hidden > 0 && h("button", { className: "btn btn-ghost btn-sm", style: { marginTop: 12 },
        onClick: () => setAll(true) },
      `Show all ${ranked.length} complaints`),
    all && ranked.length > 6 && h("button", { className: "btn btn-quiet btn-sm", style: { marginTop: 12 },
        onClick: () => setAll(false) }, "Show fewer"));
}

// ---- Complaints filed against THIS project (not the builder) ----------------
// The distinction matters: a complaint against this project is directly relevant
// to this flat, while a builder-level count is spread across every project they
// have ever registered.
function ProjectComplaints({ p, asOf }) {
  const d = p.detail || {};
  const pc = d.projectComplaints || {};
  const lit = d.litigation || {};
  if (pc.count == null) return null;             // no tier-2 record: say nothing

  const rows = pc.rows || [], orders = pc.orders || [];
  const misc = pc.nonCompliance || [], warrants = pc.warrants || [];
  const cases = lit.cases || [];
  const clean = pc.count === 0 && !cases.length;

  const stat = (n, label, danger) => h("div", { className: "tr-stat" },
    h("div", { className: "n", style: n && danger ? { color: `var(--${danger})` } : {} }, n),
    h("div", { className: "l" }, label));

  return h("div", { className: "panel", style: { marginTop: 16 } },
    h("div", { className: "panel-h" },
      h("h2", { className: "row gap-8" },
        h(Icon_v, { name: clean ? "shield-check" : "file-warning", size: 17,
          style: { color: clean ? "var(--green)" : "var(--red)" } }),
        "Complaints against this project"),
      h("span", { className: "faint", style: { fontSize: 12.5 } }, "This project only — not the builder")),
    h("div", { className: "panel-b", style: { paddingTop: 16 } },
      clean
        ? h("p", { className: "muted", style: { fontSize: 14, lineHeight: 1.55 } },
            "No consumer complaints and no declared court cases appear on this project's own ",
            "MahaRERA record. That is a fact about this project specifically — the builder may ",
            "still have complaints on its other projects (see Builder track record).")
        : h(React.Fragment, null,
            h("div", { className: "grid cmpl-stats", style: { gap: 10, marginBottom: 16 } },
              stat(pc.count, "Complaints", "red"),
              stat(pc.unresolved || 0, "Unresolved", "red"),
              stat(pc.byBuyer || 0, "By buyers", "amber"),
              stat(cases.length, "Court cases", "amber")),
            (pc.byBuilder || 0) > 0 && h("p", { className: "muted", style: { fontSize: 13, marginBottom: 12 } },
              h("b", null, pc.byBuilder, " of these were filed BY the builder"), " against buyers — the rest were filed against the builder."),
            h(ComplaintList, { complaints: pc.complaints || rows }),
            // Each complaint above carries its own order, hearing record and
            // warrant, so a flat list of every order filename would just repeat
            // that as an unreadable wall.
            misc.length > 0 && h("p", { className: "faint", style: { fontSize: 12.5, marginTop: 14 } },
              h("b", null, misc.length, " non-compliance application(s)"),
              " across all complaints — each is shown against its complaint above."),
            cases.length > 0 && h("div", { style: { marginTop: 14 } },
              h("div", { className: "doc-group-h" }, "Court cases declared by the promoter"),
              cases.map((c, i) => h("div", { key: i, className: "cmpl-row" },
                h("b", { style: { fontSize: 13.5 } }, (c.court || "Court").replace(/\b\w/g, m => m.toUpperCase())),
                c.caseNo && h("span", { className: "faint mono", style: { fontSize: 12, marginLeft: 8 } }, "case ", c.caseNo),
                c.remark && h("div", { className: "muted", style: { fontSize: 12.5, marginTop: 3 } }, c.remark))))
          ),
      h("div", { className: "src-row", style: { marginTop: 14, display: "flex" } },
        h(SourceTag, { source: "MahaRERA — this project's complaint record", asOf: d.capturedAt || asOf }))));
}

// ---- Where the project actually is -----------------------------------------
function LocationMap({ p }) {
  // Coordinates come from the Tier-2 record. The index's map_url is empty
  // ("...&query=,") for all but one of 44,279 projects, so it is only a fallback.
  const geo = (p.detail || {}).geo;
  const m = geo ? null : /query=(-?\d+\.\d+),\s*(-?\d+\.\d+)/.exec(p.mapUrl || "");
  if (!geo && !m) return null;
  const lat = geo ? String(geo.lat) : m[1];
  const lng = geo ? String(geo.lng) : m[2];
  // Google's keyless embed — no API key, no billing, no quota to manage.
  const src = `https://www.google.com/maps?q=${lat},${lng}&z=15&output=embed`;
  return h("div", { className: "panel", style: { marginTop: 16 } },
    h("div", { className: "panel-h" },
      h("h2", { className: "row gap-8" }, h(Icon_v, { name: "pin", size: 17, className: "faint" }), "Location"),
      h("a", { className: "btn btn-ghost btn-sm", target: "_blank", rel: "noopener",
          href: `https://www.google.com/maps/search/?api=1&query=${lat},${lng}` },
        h(Icon_v, { name: "link", size: 14 }), "Open in Google Maps")),
    h("div", { className: "panel-b", style: { padding: 0 } },
      h("iframe", { className: "map-embed", src, loading: "lazy", title: "Project location",
        referrerPolicy: "no-referrer-when-downgrade", allowFullScreen: true })),
    h("div", { className: "panel-b", style: { paddingTop: 12 } },
      h("div", { className: "kvbar" },
        h(KV, { k: "District", v: p.district }),
        (p.plot && p.plot.village) && h(KV, { k: "Village", v: p.plot.village }),
        h(KV, { k: "Pincode", v: (p.plot && p.plot.pincode) || p.pincode || "—" }),
        h(KV, { k: "Coordinates", v: `${(+lat).toFixed(5)}, ${(+lng).toFixed(5)}`, mono: true })),
      // Plot identity as filed with MahaRERA — the CTS/survey number is what a
      // Development Plan remarks lookup is keyed on.
      p.plot && (p.plot.cts || p.plot.landArea) && h("div", { className: "kvbar", style: { marginTop: 10 } },
        p.plot.cts && h(KV, { k: "CTS / Survey no.", v: p.plot.cts, mono: true }),
        p.plot.landArea && h(KV, { k: "Plot area", v: `${p.plot.landArea.toLocaleString("en-IN")} sq.m` }),
        p.plot.builtUpArea && h(KV, { k: "Permissible built-up", v: `${p.plot.builtUpArea.toLocaleString("en-IN")} sq.m` })),
      h("div", { className: "src-row", style: { marginTop: 12, display: "flex" } },
        h(SourceTag, { source: "MahaRERA — registered project address", asOf: p.dataAsOf }))));
}

// The Tier-2 detail block: specs, sales/inventory, delays, documents.
function DetailSection({ p }) {
  const d = p.detail || {};
  const sp = d.specs || {};
  const exts = d.extensions || [];
  const u = d.units || {};
  const docs = d.documents || [];
  const delayed = sp.originalCompletion && sp.revisedCompletion && sp.revisedCompletion > sp.originalCompletion;
  const fee = sp.feesPayable ? "₹" + Number(sp.feesPayable).toLocaleString("en-IN") : "—";
  const total = u.total || 0, booked = u.booked || 0;
  const pct = total ? Math.round((booked / total) * 100) : 0;
  const mix = (u.mix || []).filter(m => m.count);

  // group documents by category + collect the key (important) ones, deduped by label
  const groups = {};
  docs.forEach(o => { (groups[o.category] = groups[o.category] || []).push(o); });
  // Feature one of each important kind. Dedupe on `kind` (the un-numbered label),
  // not `label` — repeats are numbered "(2 of 5)" and would each look unique.
  const keyDocs = [];
  const seenKey = new Set();
  docs.forEach(o => {
    const k = o.kind || o.label;
    if (o.important && !seenKey.has(k)) { seenKey.add(k); keyDocs.push(o); }
  });
  // The backend resolves each document to a href it has actually verified (our own
  // /api/hh/doc route when the file ships with the app, otherwise an external URL).
  // It is null when nothing can serve the file, so a link is never shown dead.
  const docHref = (o) => o.href;
  const canOpen = (o) => !!o.href;
  const anyOpen = docs.some(o => o.href);
  const docItem = (o, i) => {
    const inner = h("span", { className: "row gap-8", style: { minWidth: 0 } },
      h(Icon_v, { name: "doc", size: 15, className: "doc-ic" }),
      h("span", { className: "doc-name" }, o.label));
    return canOpen(o)
      ? h("a", { key: i, className: "doc-item", href: docHref(o), target: "_blank", rel: "noopener" },
          inner, h(Icon_v, { name: "link", size: 14, className: "faint" }))
      : h("div", { key: i, className: "doc-item disabled" }, inner);
  };

  return h(React.Fragment, null,
    // ---- Project snapshot ----
    h("div", { className: "panel", style: { marginTop: 16 } },
      h("div", { className: "panel-h" },
        h("h2", null, "Project snapshot"),
        h("span", { className: "faint", style: { fontSize: 12.5 } }, "Official MahaRERA registration · as of ", d.capturedAt)),
      h("div", { className: "panel-b" },
        h("div", { className: "spec-grid" },
          h(SpecCell, { k: "Type", v: sp.type }),
          h(SpecCell, { k: "Status", v: sp.status }),
          h(SpecCell, { k: "Current stage", v: sp.stage }),
          h(SpecCell, { k: "Registered on", v: sp.registeredOn }),
          h(SpecCell, { k: "Promised completion", v: sp.originalCompletion }),
          h(SpecCell, { k: "Revised completion", v: sp.revisedCompletion, accent: delayed }),
          h(SpecCell, { k: "Total units", v: total || "—" }),
          h(SpecCell, { k: "RERA fee", v: fee })
        ))),

    // ---- Sales & inventory ----
    total > 0 && h("div", { className: "panel", style: { marginTop: 16 } },
      h("div", { className: "panel-h" },
        h("h2", null, "Sales & inventory"),
        h("span", { className: "faint", style: { fontSize: 12.5 } }, "Booked vs total, per configuration")),
      h("div", { className: "panel-b" },
        h("div", { className: "sold-head" },
          h("div", null, h("span", { className: "sold-big" }, booked.toLocaleString("en-IN")),
            h("span", { className: "sold-small" }, " of ", total.toLocaleString("en-IN"), " units booked")),
          h("div", { className: "sold-pct" }, pct, "%")),
        h("div", { className: "sold-bar" }, h("div", { className: "sold-fill", style: { width: pct + "%" } })),
        mix.length > 0 && h("div", { className: "inv-wrap" },
          h("table", { className: "inv-table" },
            h("thead", null, h("tr", null,
              h("th", null, "Configuration"), h("th", null, "Carpet (sq.m)"),
              h("th", { className: "num" }, "Booked"), h("th", { className: "num" }, "Total"))),
            h("tbody", null, mix.map((m, i) => h("tr", { key: i },
              h("td", null, h("b", null, m.type || "Unit"),
                m.building && h("span", { className: "faint", style: { marginLeft: 7, fontSize: 11 } }, m.building)),
              h("td", null, m.carpetArea == null ? "—" : m.carpetArea),
              h("td", { className: "num" }, h("b", { style: m.booked ? { color: "var(--green)" } : {} }, m.booked)),
              h("td", { className: "num" }, m.count)))))),
        h("div", { className: "src-row", style: { marginTop: 12, display: "flex" } },
          h(SourceTag, { source: "MahaRERA — building & unit details", asOf: d.capturedAt })))),

    // ---- Delay / extension history ----
    exts.length > 0 && h("div", { className: "panel", style: { marginTop: 16 } },
      h("div", { className: "panel-h" },
        h("h2", { className: "row gap-8" }, h(Icon_v, { name: "calendar-clock", size: 17, style: { color: "var(--amber)" } }),
          `Completion revised ${exts.length} time${exts.length > 1 ? "s" : ""}`),
        h("span", { className: "faint", style: { fontSize: 12.5 } }, "Promised vs revised, with the builder's stated reason")),
      h("div", { className: "panel-b" },
        exts.map((e, i) => h("div", { key: i, className: "ext-row" },
          h("div", { className: "ext-dates mono" },
            (e.originalDate || "—"), " → ", h("b", { style: { color: "var(--amber)" } }, e.revisedDate || "—"),
            e.appNo && h("span", { className: "faint", style: { marginLeft: 8 } }, "· ", e.appNo)),
          e.reason && h("p", { className: "muted", style: { fontSize: 13, marginTop: 5, lineHeight: 1.55 } }, "“", e.reason, "”"))),
        h("div", { className: "src-row", style: { marginTop: 12, display: "flex" } },
          h(SourceTag, { source: "MahaRERA — extension certificates", asOf: d.capturedAt })))),

    // ---- Documents on record ----
    docs.length > 0 && h("div", { className: "panel", style: { marginTop: 16 } },
      h("div", { className: "panel-h" },
        h("h2", null, "Documents on record"),
        p.detailUrl && h("a", { className: "btn btn-ghost btn-sm", href: p.detailUrl, target: "_blank", rel: "noopener" },
          h(Icon_v, { name: "link", size: 14 }), "View on MahaRERA")),
      h("div", { className: "panel-b" },
        // Featured key documents
        keyDocs.length > 0 && h("div", { style: { marginBottom: 20 } },
          h("div", { className: "doc-group-h" }, "Key documents"),
          h("div", { className: "keydoc-grid" },
            keyDocs.map((o, i) => {
              const body = h(React.Fragment, null,
                h("div", { className: "keydoc-ic" }, h(Icon_v, { name: DOC_ICON[o.kind || o.label] || "doc", size: 19 })),
                h("div", { style: { minWidth: 0, flex: 1 } },
                  h("div", { className: "keydoc-label" }, o.kind || o.label),
                  h("div", { className: "keydoc-act" }, canOpen(o) ? "Open document" : "On MahaRERA record")));
              return canOpen(o)
                ? h("a", { key: i, className: "keydoc", href: docHref(o), target: "_blank", rel: "noopener" },
                    body, h(Icon_v, { name: "link", size: 16, className: "faint" }))
                : h("div", { key: i, className: "keydoc disabled" }, body);
            }))),
        // All documents, grouped
        h("div", { className: "doc-group-h" }, "All documents · ", d.documentCount),
        DOC_ORDER.filter(g => groups[g]).map(g => h("div", { key: g, className: "doc-group" },
          h("div", { className: "doc-subcat" }, g, h("span", { className: "faint" }, " · ", groups[g].length)),
          h("div", { className: "doc-grid" }, groups[g].map((o, i) => docItem(o, i))))),
        !anyOpen && h("p", { className: "faint", style: { fontSize: 12, marginTop: 6 } },
          "Open any of these on the official MahaRERA portal via the button above.")))
  );
}

// ============================================================
// Scoring v2 — category breakdown, confidence, and questions
// ============================================================

const V2_TONE = { positive: "var(--green)", caution: "var(--amber)", negative: "var(--red)", neutral: "var(--ink-3)" };

// One weighted category: a bar showing how much of its weight survived, then
// the findings that took the points off. The bar is the audit trail — a reader
// should be able to add the impacts up and land on the earned figure.
function CategoryRow({ c }) {
  const pct = Math.round((c.pct != null ? c.pct : c.earned / c.weight) * 100);
  const tone = pct >= 85 ? "var(--green)" : pct >= 60 ? "var(--amber)" : "var(--red)";
  return h("div", { style: { padding: "14px 0", borderTop: "1px solid var(--line)" } },
    h("div", { className: "row", style: { justifyContent: "space-between", gap: 12, alignItems: "baseline" } },
      h("div", { style: { fontWeight: 650, fontSize: 14 } }, c.label),
      h("div", { className: "mono", style: { fontSize: 13, color: tone, fontWeight: 700, flex: "none" } },
        c.covered ? `${c.earned.toFixed(1)} / ${c.weight}` : `— / ${c.weight}`)),
    h("div", { style: { height: 6, borderRadius: 4, background: "var(--surface-2)", marginTop: 8, overflow: "hidden" } },
      h("div", { style: { height: "100%", width: `${c.covered ? pct : 0}%`, background: tone, borderRadius: 4, transition: "width .5s ease" } })),
    !c.covered && h("div", { className: "faint", style: { fontSize: 12, marginTop: 7 } },
      "Not assessed — no usable data. Excluded from the score rather than counted as clean."),
    c.findings.map((f, i) => h("div", { key: i, style: { display: "grid", gridTemplateColumns: "1fr auto", gap: 10, marginTop: 9, alignItems: "start" } },
      h("div", { style: { minWidth: 0 } },
        h("div", { style: { fontSize: 13, lineHeight: 1.45, color: "var(--ink-2)" } },
          h("span", { style: { color: V2_TONE[f.kind] || "var(--ink-3)", fontWeight: 700, marginRight: 6 } },
            f.kind === "positive" ? "✓" : f.kind === "neutral" ? "•" : "!"),
          f.text),
        f.benchmark && h("div", { className: "faint", style: { fontSize: 11.5, marginTop: 2 } }, "Benchmark: ", f.benchmark),
        h("div", { className: "mono", style: { fontSize: 10.5, color: "var(--ink-3)", marginTop: 3 } }, "↳ ", f.source)),
      h("div", { className: "mono", style: { fontSize: 12.5, fontWeight: 700, flex: "none", color: f.impact < 0 ? "var(--red)" : "var(--ink-3)" } },
        f.impact === 0 ? "0" : f.impact.toFixed(1)))),
    // Covers two kinds of caveat: data we have not collected, and a value we had
    // to infer. "Limitation" is honest about both without overclaiming either.
    c.note && h("div", { className: "faint", style: { fontSize: 11.5, marginTop: 9, fontStyle: "italic" } }, "Limitation: ", c.note)
  );
}

// How much of the framework we actually had data for. This is deliberately
// prominent: a high score at low confidence is a weaker claim than the number
// alone suggests, and hiding that would be the dishonest choice.
function ConfidenceBar({ confidence, suppressed, unrated }) {
  const pct = Math.round((confidence || 0) * 100);
  const tone = pct >= 80 ? "var(--green)" : pct >= 60 ? "var(--amber)" : "var(--red)";
  return h("div", { style: { padding: "13px 16px", borderRadius: 10, background: "var(--surface-2)", marginTop: 14 } },
    h("div", { className: "row", style: { justifyContent: "space-between", gap: 10, alignItems: "baseline" } },
      h("div", { style: { fontWeight: 650, fontSize: 13 } }, "Confidence in this assessment"),
      h("div", { className: "mono", style: { fontWeight: 700, color: tone, fontSize: 13 } }, pct, "%")),
    h("div", { style: { height: 6, borderRadius: 4, background: "var(--line)", marginTop: 8, overflow: "hidden" } },
      h("div", { style: { height: "100%", width: `${pct}%`, background: tone, borderRadius: 4 } })),
    h("div", { className: "faint", style: { fontSize: 12, marginTop: 8, lineHeight: 1.5 } },
      unrated
        ? "Zero because this project's own file has not been collected yet — not because anything is wrong with it. The builder assessment beside it is unaffected."
        : suppressed
        ? "Below our 60% threshold, so we publish the band only. A decimal here would imply a precision the record does not support."
        : "The share of our framework we had usable data for. Anything we could not check lowers this figure instead of quietly scoring as clean."));
}

// The findings that should turn into a conversation. This is the part a buyer
// actually takes to a site visit, so it is phrased as questions, not verdicts.
function AskSeller({ score }) {
  const qs = [];
  (score.categories || []).forEach(c => (c.findings || []).forEach(f => { if (f.question) qs.push(f); }));
  if (!qs.length) return null;
  return h("div", { className: "panel", style: { marginTop: 16 } },
    h("div", { className: "panel-h" },
      h("div", null,
        h("h2", null, "What to ask before you pay"),
        h("div", { className: "faint", style: { fontSize: 12.5, marginTop: 3 } },
          qs.length, " question", qs.length === 1 ? "" : "s", " drawn from the findings above"))),
    h("div", { className: "panel-b" },
      qs.map((f, i) => h("div", { key: i, style: { padding: "12px 0", borderTop: i ? "1px solid var(--line)" : "none" } },
        h("div", { style: { fontSize: 13.5, lineHeight: 1.5, fontWeight: 550 } },
          h("span", { style: { color: "var(--brand)", fontWeight: 700, marginRight: 7 } }, i + 1, "."), f.question),
        h("div", { className: "faint", style: { fontSize: 11.5, marginTop: 4, paddingLeft: 18 } }, "Because: ", f.text)))));
}

// The two scores sit side by side and are never averaged: one asks "is this
// building in trouble", the other "is this company". A good builder can run a
// troubled project, and the reverse is just as common.
function ScoreBreakdown({ project, builder, confidence, suppressed }) {
  if (!project) return null;
  const pane = (s, title, sub) => !s ? null : h("div", { className: "panel", style: { flex: "1 1 320px", minWidth: 0 } },
    h("div", { className: "panel-h" },
      h("div", { style: { minWidth: 0 } },
        h("h2", null, title),
        h("div", { className: "faint", style: { fontSize: 12.5, marginTop: 3 } }, sub)),
      h("div", { style: { textAlign: "right", flex: "none" } },
        h("div", { className: "mono", style: { fontSize: 26, fontWeight: 700, lineHeight: 1 } },
          s.publishable === false ? "—" : Math.round(s.total),
          h("span", { className: "faint", style: { fontSize: 13, fontWeight: 400 } }, "/100")),
        h("div", { style: { fontSize: 11.5, fontWeight: 650, marginTop: 3 } }, s.bandLabel))),
    h("div", { className: "panel-b", style: { paddingTop: 4 } },
      s.cappedBy && h("div", { style: { padding: "10px 13px", borderRadius: 8, background: "var(--red-bg, var(--surface-2))", borderLeft: "3px solid var(--red)", fontSize: 12.5, margin: "10px 0 4px" } },
        "Score capped: ", s.cappedBy, " overrides every other category."),
      // Five identical "not assessed" rows say the same thing five times. One
      // sentence is clearer, and states plainly that this is a gap in our
      // collection rather than a finding about the project.
      s.band === "unrated"
        ? h("div", { style: { fontSize: 13, lineHeight: 1.55, color: "var(--ink-2)", padding: "12px 0 4px" } },
            "We have not pulled this project's own MahaRERA file yet, so it is not scored. ",
            h("b", null, "This is not a finding against the project"),
            " — it means we have nothing to report either way. The builder's record on the right is real and comes from the state-wide registers.")
        : s.categories.map((c, i) => h(CategoryRow, { key: i, c }))));

  return h("div", null,
    h("div", { className: "row", style: { gap: 16, marginTop: 16, flexWrap: "wrap", alignItems: "flex-start" } },
      pane(project, "This project, scored", "Delivery, legal standing, disclosure, finance, land"),
      pane(builder, "This builder, scored", "Track record across every project we hold")),
    h(ConfidenceBar, { confidence, suppressed, unrated: project.band === "unrated" }));
}

function Verdict({ id, go }) {
  const [data, setData] = useStateV(null);
  const [loading, setLoading] = useStateV(true);
  const [unlocked, setUnlocked] = useStateV(() => window.hasLead());
  const [toast, showToast] = window.useToast();
  useEffectV(() => {
    let alive = true;
    setLoading(true);
    window.HH.project(id).then(d => { if (alive) { setData(d); setLoading(false); } });
    return () => { alive = false; };
  }, [id]);

  if (loading) {
    return h("div", { className: "wrap", style: { paddingTop: 70 } },
      h("div", { className: "verdict-hero", style: { opacity: .5 } },
        h("div", { style: { display: "grid", placeItems: "center" } }, h(TrustGauge, { score: null, band: "incomplete", size: 240, animate: false })),
        h("div", { className: "faint", style: { alignSelf: "center" } }, "Compiling the honest verdict…")));
  }
  if (!data || !data.project) {
    return h("div", { className: "wrap", style: { paddingTop: 80, textAlign: "center" } },
      h("button", { className: "btn btn-quiet btn-sm", onClick: go.back }, h(Icon_v, { name: "back", size: 15 }), "Back"),
      h("p", { className: "muted", style: { marginTop: 16, marginBottom: 16 } }, "We couldn't load that project from the current dataset. It may be outside our index."),
      h(ContactButton, { prefill: id, label: "Tell us about this project", variant: "btn-primary", size: "md" }));
  }

  const p = data.project;
  const b = data.builder || { name: p.builder, others: [], note: "" };
  const incomplete = !p.dataComplete;
  const glow = incomplete ? "transparent" : `var(--${p.band}-tint)`;

  // Real, working external links.
  const reraUrl = p.detailUrl || "https://maharera.maharashtra.gov.in/projects-search-result";
  const mapUrl = p.mapUrl || `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent((p.name || "") + " " + (p.district || "") + " Maharashtra")}`;
  const asOf = p.dataAsOf || (p.signals && p.signals[0] && p.signals[0].asOf) || window.HH.meta().asOf;

  const shareUrl = `${location.origin}/verdict/${encodeURIComponent(p.id)}`;
  const shareTitle = `Honest Homes verdict — ${p.name} (${p.builder})`;

  const flags = p.signals.filter(s => s.kind === "severe" || (s.kind === "caution" && (p.band === "amber" || p.band === "red")));

  return h("div", { className: "wrap fade-in", style: { paddingTop: 24, paddingBottom: 64, "--band-glow": glow } },
    toast,
    // top bar
    h("div", { className: "row", style: { justifyContent: "space-between", marginBottom: 18, flexWrap: "wrap", gap: 12 } },
      h("button", { className: "btn btn-quiet btn-sm", onClick: go.back },
        h(Icon_v, { name: "back", size: 15 }), "Back to results"),
      h("div", { className: "row gap-8", style: { flexWrap: "wrap", justifyContent: "flex-end" } },
        h(InquiryButton, { project: p, label: "Ask a question", variant: "btn-ghost", size: "sm" }),
        unlocked
          ? h(React.Fragment, null,
              h(ShareMenu, { url: shareUrl, title: shareTitle }),
              h("button", { className: "btn btn-primary btn-sm", onClick: () => go.download(p.id) },
                h(Icon_v, { name: "download", size: 15 }), "Download report"))
          : h("span", { className: "faint", style: { fontSize: 12.5, display: "inline-flex", alignItems: "center", gap: 6 } },
              h(Icon_v, { name: "shield-check", size: 13 }), "Unlock to share & download")
      )
    ),

    h(LeadGate, { project: p, active: !unlocked, onUnlock: () => setUnlocked(true) },
    // ---------- VERDICT HERO ----------
    h("div", { className: "verdict-hero" },
      h("div", { style: { display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" } },
        h(TrustGauge, { score: p.score, band: p.band, size: 270 }),
        h("div", { className: "source-tag", style: { marginTop: 18 } },
          h(Icon_v, { name: "shield-check", size: 13, className: "seal" }),
          h("span", null, "Verdict compiled ", h("b", null, asOf))
        )
      ),
      h("div", { className: "stack-20" },
        h("div", null,
          h("div", { className: "eyebrow", style: { marginBottom: 10 } }, "Verdict · ", p.id),
          h("h1", { className: "verdict-headline" }, p.headline)
        ),
        h("p", { className: "verdict-summary" }, p.summary),
        h("div", { className: "kvbar" },
          h(KV, { k: "Project", v: p.name }),
          h(KV, { k: "Builder", v: p.builder }),
          h(KV, { k: "RERA status", v: p.statusNote }),
          h(KV, { k: "District", v: `${p.district} · ${p.pincode}` })
        ),
        h("div", { className: "row gap-12", style: { flexWrap: "wrap" } },
          h("a", { className: "btn btn-ghost btn-sm", href: reraUrl, target: "_blank", rel: "noopener" },
            h(Icon_v, { name: "link", size: 14 }), "View on MahaRERA portal"),
          h("a", { className: "btn btn-quiet btn-sm", href: mapUrl, target: "_blank", rel: "noopener" },
            h(Icon_v, { name: "pin", size: 14 }), "Map location")
        )
      )
    ),

    // ---------- INCOMPLETE banner ----------
    incomplete && h("div", { className: "incomplete-banner", style: { marginTop: 22 } },
      h("div", { className: "ib-ico" }, h(Icon_v, { name: "hourglass", size: 26 })),
      h("div", null,
        h("div", { style: { fontWeight: 700, fontSize: 16 } }, "We won't fake a score we can't defend."),
        h("p", { className: "muted", style: { fontSize: 14, marginTop: 6, lineHeight: 1.55, maxWidth: "70ch" } },
          "We can confirm this project is RERA-registered from the official index, but its detailed delay history and complaint records are not yet in our dataset. Rather than show false confidence, we're telling you what we don't yet know. Verify complaints and orders directly on the MahaRERA portal before relying on this."),
        h("div", { className: "row gap-8", style: { marginTop: 12 } },
          h("a", { className: "btn btn-ghost btn-sm", href: reraUrl, target: "_blank", rel: "noopener" },
            h(Icon_v, { name: "link", size: 14 }), "Open MahaRERA record"))
      )
    ),

    // ---------- RED FLAG callouts ----------
    !incomplete && flags.length > 0 && h("div", { style: { marginTop: 22 } },
      h("div", { className: `grid ${flags.length > 1 ? "grid-2up" : ""}`, style: { gap: 14 } },
        flags.slice(0, 4).map((f, i) =>
          h("div", { key: i, className: `flag ${f.kind === "severe" ? "" : "amber"}` },
            h("div", { className: "fico" }, h(Icon_v, { name: f.kind === "severe" ? "ban" : "info", size: 20 })),
            h("div", null, h("h4", null, f.fact), h("p", null, f.detail))
          )
        )
      )
    ),

    // ---------- WHY THIS VERDICT ----------
    h("div", { className: "panel", style: { marginTop: 22 } },
      h("div", { className: "panel-h" },
        h("div", null,
          h("h2", null, "Why this verdict"),
          h("div", { className: "faint", style: { fontSize: 12.5, marginTop: 3 } },
            "Every signal below is a fact from the public record, with its source. Nothing is opinion.")),
        !incomplete && h(ScoreChip, { score: p.score, band: p.band })
      ),
      h("div", { className: "panel-b" },
        p.signals.map((s, i) => h(SignalRow, { key: i, s }))
      ),
      !incomplete && h("div", { style: { padding: "14px 22px", borderTop: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" } },
        h("span", { className: "faint", style: { fontSize: 12.5 } },
          "Scored across five weighted categories · see the full breakdown below"),
        h("span", { className: "row gap-8" },
          h("span", { className: "faint", style: { fontSize: 13 } }, "Final verdict"),
          h(ScoreChip, { score: p.score, band: p.band })))
    ),

    // ---------- SCORING v2: category breakdown + confidence ----------
    p.projectScore && h(ScoreBreakdown, {
      project: p.projectScore, builder: p.builderScore,
      confidence: p.confidence, suppressed: p.scoreSuppressed,
    }),
    p.projectScore && h(AskSeller, { score: p.projectScore }),

    // ---------- TWO COLUMN: track record + timeline ----------
    h("div", { className: "grid grid-2up", style: { gap: 16, marginTop: 16 } },
      // builder track record
      h("div", { className: "panel" },
        h("div", { className: "panel-h" }, h("h2", null, "Builder track record"),
          h("span", { className: "row gap-8" }, h(Icon_v, { name: "building", size: 15, className: "faint" }))),
        h("div", { className: "panel-b", style: { paddingTop: 16 } },
          h("div", { className: "row gap-8", style: { marginBottom: 14 } },
            h("div", { style: { minWidth: 0 } },
              h("div", { style: { fontWeight: 700, fontSize: 16, overflowWrap: "anywhere" } }, b.name),
              h("div", { className: "faint", style: { fontSize: 12.5 } },
                b.totalProjects ? `${b.totalProjects} project(s) in the MahaRERA index` : "Project count not available"))),
          // Only counts the public record actually supports. "Delivered"/"Delayed"
          // are not in the index, so we don't show tiles for them.
          h("div", { className: "grid", style: { gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginBottom: 6 } },
            h("div", { className: "tr-stat" }, h("div", { className: "n" }, b.totalProjects == null ? "—" : b.totalProjects), h("div", { className: "l" }, "Projects")),
            h("div", { className: "tr-stat" }, h("div", { className: "n", style: b.complaints ? { color: "var(--amber)" } : {} }, b.complaints == null ? "—" : b.complaints), h("div", { className: "l" }, "Complaints")),
            h("div", { className: "tr-stat" }, h("div", { className: "n", style: b.revoked ? { color: "var(--red)" } : {} }, b.revoked == null ? "—" : b.revoked), h("div", { className: "l" }, "Revoked"))),
          h("p", { className: "muted", style: { fontSize: 13, margin: "12px 2px", lineHeight: 1.5 } }, b.note),
          (b.others && b.others.length > 0) && h("div", { style: { marginTop: 4 } },
            b.others.map((o, i) =>
              h("button", { key: i, className: "tr-row", style: { width: "100%", textAlign: "left", background: "none", cursor: "pointer" },
                  onClick: () => go.verdict(o.id) },
                h("div", null,
                  h("div", { style: { fontWeight: 600, fontSize: 14 } }, o.name),
                  h("div", { className: "faint mono", style: { fontSize: 11 } }, o.id, " · ", o.district)),
                h("span", { className: `badge ${o.band}`, style: { fontSize: 11 } },
                  h("span", { className: "dot" }), o.status))
            )),
          h("div", { className: "src-row", style: { marginTop: 12, display: "flex" } },
            h(SourceTag, { source: "MahaRERA — promoter index", asOf: asOf }))
        )
      ),
      // timeline
      h("div", { className: "panel" },
        h("div", { className: "panel-h" }, h("h2", null, "Completion timeline"),
          h("span", { className: "faint", style: { fontSize: 12.5 } }, "Promised vs revised")),
        h("div", { className: "panel-b", style: { paddingTop: 20, paddingBottom: 24 } },
          h(Timeline, { items: p.timeline, band: p.band }),
          h("div", { style: { marginTop: 28 } },
            h("div", { className: "kvbar" },
              h(KV, { k: "Promised", v: p.promisedCompletion, mono: true }),
              p.revisedCompletion && h(KV, { k: "Latest revision", v: p.revisedCompletion, mono: true }),
              h(KV, { k: p.actualCompletion ? "Delivered" : "Extensions", v: p.actualCompletion || `${p.extensions == null ? "—" : p.extensions} filed`, mono: true })
            )),
          h("div", { className: "src-row", style: { marginTop: 14, display: "flex", gap: 7, flexWrap: "wrap" } },
            h(SourceTag, { source: "MahaRERA — extension certificates", asOf: asOf }))
        )
      )
    ),

    // ---------- COMPLAINTS AGAINST THIS PROJECT ----------
    p.hasDetail && h(ProjectComplaints, { p, asOf }),

    // ---------- LOCATION ----------
    h(LocationMap, { p }),

    // ---------- WHAT'S AROUND IT ----------
    // Sits after location and before the registration detail: a buyer asks
    // "where is it, and what is near it" before they ask about fee receipts.
    window.Neighbourhood && h(window.Neighbourhood, { reraId: p.id }),

    // ---------- TIER-2 DETAIL (specs, delays, documents) ----------
    p.hasDetail && h(DetailSection, { p }),

    // ---------- WHAT BUYERS SAY ----------
    // Last on the page on purpose: unverified accounts should be read after the
    // sourced record, not instead of it.
    window.Discussion && h(window.Discussion, { reraId: p.id })),
    // ^ the lead gate closes HERE, not after the score panel. Everything of value
    //   — track record, timeline, snapshot, sales, and every document link — must
    //   sit inside it, otherwise a visitor just scrolls past the blur and reads it
    //   all without ever entering a name.

    // ---------- DISCLAIMER (deliberately outside the gate: it's boilerplate) ----------
    h("div", { className: "disclaimer", style: { marginTop: 18 } },
      h("div", { className: "dico" }, h(Icon_v, { name: "info", size: 19 })),
      h("div", null,
        h("b", null, "How to read this. "),
        "Honest Homes summarises the public MahaRERA record to help you ask better questions. It reflects data as of ",
        asOf, " and is information, not legal or financial advice. Records can change and our dataset can lag. ",
        "Always confirm the live status on the official ", h("a", { href: reraUrl, target: "_blank", rel: "noopener", style: { color: "var(--brand)", fontWeight: 600 } }, "MahaRERA portal"),
        " and consult a lawyer before any purchase.")
    )
  );
}

window.Verdict = Verdict;
