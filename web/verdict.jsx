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

// Document categories in display order (labels come from the parser).
const DOC_ORDER = ["Approvals & certificates", "Agreements & legal", "Plans",
  "Professional certificates", "KYC & financial", "Other"];
const DOC_ICON = {
  "Commencement Certificate": "shield-check", "Occupancy Certificate": "shield-check",
  "Completion Certificate": "shield-check", "RERA Registration Certificate": "shield-check",
  "Agreement for Sale": "doc", "Building Approval (IOD)": "building", "Title Report": "doc",
};

function SpecCell({ k, v, accent }) {
  return h("div", { className: "spec-cell" },
    h("div", { className: "spec-k" }, k),
    h("div", { className: `spec-v ${accent ? "accent" : ""}` }, (v === null || v === undefined || v === "") ? "—" : v));
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
  const keyDocs = [];
  const seenKey = new Set();
  docs.forEach(o => { if (o.important && !seenKey.has(o.label)) { seenKey.add(o.label); keyDocs.push(o); } });
  const docHref = (o) => `/api/hh/doc/${encodeURIComponent(p.id)}/${encodeURIComponent(o.file)}`;
  const docItem = (o, i) => {
    const inner = h("span", { className: "row gap-8", style: { minWidth: 0 } },
      h(Icon_v, { name: "doc", size: 15, className: "doc-ic" }),
      h("span", { className: "doc-name" }, o.label));
    return d.documentsAvailable
      ? h("a", { key: i, className: "doc-item", href: docHref(o), target: "_blank", rel: "noopener" },
          inner, h(Icon_v, { name: "download", size: 14, className: "faint" }))
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
                h("div", { className: "keydoc-ic" }, h(Icon_v, { name: DOC_ICON[o.label] || "doc", size: 19 })),
                h("div", { style: { minWidth: 0, flex: 1 } },
                  h("div", { className: "keydoc-label" }, o.label),
                  h("div", { className: "keydoc-act" }, d.documentsAvailable ? "Download PDF" : "On MahaRERA record")));
              return d.documentsAvailable
                ? h("a", { key: i, className: "keydoc", href: docHref(o), target: "_blank", rel: "noopener" },
                    body, h(Icon_v, { name: "download", size: 16, className: "faint" }))
                : h("div", { key: i, className: "keydoc disabled" }, body);
            }))),
        // All documents, grouped
        h("div", { className: "doc-group-h" }, "All documents · ", d.documentCount),
        DOC_ORDER.filter(g => groups[g]).map(g => h("div", { key: g, className: "doc-group" },
          h("div", { className: "doc-subcat" }, g, h("span", { className: "faint" }, " · ", groups[g].length)),
          h("div", { className: "doc-grid" }, groups[g].map((o, i) => docItem(o, i))))),
        !d.documentsAvailable && h("p", { className: "faint", style: { fontSize: 12, marginTop: 6 } },
          "Open any of these on the official MahaRERA portal via the button above.")))
  );
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

  const shareUrl = `${location.origin}${location.pathname}#/verdict/${encodeURIComponent(p.id)}`;
  const shareTitle = `Honest Homes verdict — ${p.name} (${p.builder})`;

  const flags = p.signals.filter(s => s.kind === "severe" || (s.kind === "caution" && (p.band === "amber" || p.band === "red")));

  return h("div", { className: "wrap fade-in", style: { paddingTop: 24, paddingBottom: 64, "--band-glow": glow } },
    toast,
    // top bar
    h("div", { className: "row", style: { justifyContent: "space-between", marginBottom: 18, flexWrap: "wrap", gap: 12 } },
      h("button", { className: "btn btn-quiet btn-sm", onClick: go.back },
        h(Icon_v, { name: "back", size: 15 }), "Back to results"),
      h("div", { className: "row gap-8" },
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
        h("p", { className: "muted", style: { fontSize: 15, lineHeight: 1.6, marginTop: -6 } }, p.summary),
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
      h("div", { className: "grid", style: { gridTemplateColumns: flags.length > 1 ? "1fr 1fr" : "1fr", gap: 14 } },
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
      !incomplete && h("div", { style: { padding: "14px 22px", borderTop: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" } },
        h("span", { className: "faint", style: { fontSize: 12.5 } }, "Base score 5.0 · adjusted by signals above"),
        h("span", { className: "row gap-8" },
          h("span", { className: "faint", style: { fontSize: 13 } }, "Final verdict"),
          h(ScoreChip, { score: p.score, band: p.band })))
    )),

    // ---------- TWO COLUMN: track record + timeline ----------
    h("div", { className: "grid", style: { gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 16 } },
      // builder track record
      h("div", { className: "panel" },
        h("div", { className: "panel-h" }, h("h2", null, "Builder track record"),
          h("span", { className: "row gap-8" }, h(Icon_v, { name: "building", size: 15, className: "faint" }))),
        h("div", { className: "panel-b", style: { paddingTop: 16 } },
          h("div", { className: "row gap-8", style: { marginBottom: 14 } },
            h("div", null,
              h("div", { style: { fontWeight: 700, fontSize: 16 } }, b.name),
              h("div", { className: "faint", style: { fontSize: 12.5 } }, `Active since ${b.since} · ${b.totalProjects} projects on record`))),
          h("div", { className: "grid", style: { gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginBottom: 6 } },
            h("div", { className: "tr-stat" }, h("div", { className: "n" }, b.delivered), h("div", { className: "l" }, "Delivered")),
            h("div", { className: "tr-stat" }, h("div", { className: "n", style: b.delayed ? { color: "var(--amber)" } : {} }, b.delayed == null ? "—" : b.delayed), h("div", { className: "l" }, "Delayed")),
            h("div", { className: "tr-stat" }, h("div", { className: "n", style: b.revoked ? { color: "var(--red)" } : {} }, b.revoked), h("div", { className: "l" }, "Revoked"))),
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

    // ---------- TIER-2 DETAIL (specs, delays, documents) ----------
    p.hasDetail && h(DetailSection, { p }),

    // ---------- DISCLAIMER ----------
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
