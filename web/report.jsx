// ============================================================
// Honest Homes — Shareable report (print-ready, letterhead)
// ============================================================
const Icon_r = window.Icon;
const { useState: useStateR, useEffect: useEffectR } = React;

function RptRow({ s }) {
  const sign = s.impact == null ? "—" : s.impact === 0 ? "0" : (s.impact > 0 ? "+" : "") + s.impact.toFixed(1);
  const col = s.impact == null || s.impact === 0 ? "var(--ink-3)" : s.impact > 0 ? "var(--green)" : "var(--red)";
  return h("div", { style: { display: "grid", gridTemplateColumns: "1fr auto", gap: 12, padding: "12px 0", borderTop: "1px solid var(--line)", alignItems: "start" } },
    h("div", null,
      h("div", { style: { fontWeight: 600, fontSize: 13.5 } }, s.fact),
      h("div", { className: "muted", style: { fontSize: 12, marginTop: 3 } }, s.detail),
      h("div", { className: "mono", style: { fontSize: 10.5, color: "var(--ink-3)", marginTop: 5 } },
        "↳ Source: ", s.source, " · as of ", s.asOf)),
    h("div", { className: "mono", style: { fontWeight: 700, fontSize: 14, color: col } }, sign)
  );
}

function Report({ id, go }) {
  const [data, setData] = useStateR(null);
  const [loading, setLoading] = useStateR(true);
  const [toast, showToast] = window.useToast();
  useEffectR(() => {
    let alive = true;
    setLoading(true);
    window.HH.project(id).then(d => { if (alive) { setData(d); setLoading(false); } });
    return () => { alive = false; };
  }, [id]);

  if (loading) {
    return h("div", { style: { padding: "60px 16px", textAlign: "center" } },
      h("div", { className: "faint" }, "Preparing report…"));
  }
  if (!data || !data.project) {
    return h("div", { style: { padding: "60px 16px", textAlign: "center" } },
      h("button", { className: "btn btn-quiet btn-sm", onClick: go.back }, h(Icon_r, { name: "back", size: 15 }), "Back"),
      h("p", { className: "muted", style: { marginTop: 16 } }, "Could not load this report."));
  }

  const p = data.project;
  const b = data.builder || { name: p.builder, others: [], note: "" };
  const AS_OF = p.dataAsOf || (p.signals && p.signals[0] && p.signals[0].asOf) || window.HH.meta().asOf;
  const incomplete = !p.dataComplete;
  const bandWord = { green: "CLEAN", amber: "CAUTION", red: "SERIOUS FLAGS", incomplete: "INCOMPLETE" }[p.band];
  const reraUrl = p.detailUrl || "https://maharera.maharashtra.gov.in/projects-search-result";

  const copyLink = () => {
    const url = `${location.origin}${location.pathname}#/report/${encodeURIComponent(p.id)}`;
    const done = () => showToast("Report link copied");
    if (navigator.clipboard) navigator.clipboard.writeText(url).then(done, done); else done();
  };

  return h("div", { style: { padding: "26px 16px 70px", background: "var(--paper)" } },
    toast,
    // toolbar (screen only — hidden when printing)
    h("div", { className: "report-toolbar no-print" },
      h("button", { className: "btn btn-quiet btn-sm", onClick: () => go.verdict(p.id) },
        h(Icon_r, { name: "back", size: 15 }), "Back to verdict"),
      h("div", { className: "row gap-8" },
        h("button", { className: "btn btn-ghost btn-sm", onClick: copyLink },
          h(Icon_r, { name: "share", size: 15 }), "Copy link"),
        h("button", { className: "btn btn-primary btn-sm", onClick: () => window.print() },
          h(Icon_r, { name: "download", size: 15 }), "Download / Print PDF"))
    ),

    // PAGE
    h("div", { className: "page", id: "report-page" },
      h("div", { className: "report-watermark serif" }, "HONEST HOMES"),
      // letterhead
      h("div", { className: "letterhead" },
        h("div", { className: "row gap-12" },
          h("div", { className: "glyph", style: { width: 38, height: 38, display: "grid", placeItems: "center", borderRadius: 10, background: "var(--brand)", color: "var(--on-brand)" } },
            h(Icon_r, { name: "shield-check", size: 22 })),
          h("div", null,
            h("div", { className: "serif", style: { fontWeight: 600, fontSize: 21, lineHeight: 1 } }, "Honest Homes"),
            h("div", { className: "faint", style: { fontSize: 12, marginTop: 3 } }, "Independent due-diligence report"))),
        h("div", { className: "report-seal" },
          h("div", null, "REPORT REF · HH-", p.id),
          h("div", null, "GENERATED · ", AS_OF),
          h("div", null, "SOURCE · MahaRERA public records"))
      ),

      // title block
      h("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 20, marginTop: 26 } },
        h("div", null,
          h("div", { className: "eyebrow" }, "Trust assessment for"),
          h("h1", { className: "serif", style: { fontSize: 30, fontWeight: 600, letterSpacing: "-.02em", marginTop: 6 } }, p.name),
          h("div", { className: "muted", style: { fontSize: 14, marginTop: 2 } }, "by ", p.builder, " · ", p.district, " · ", p.pincode),
          h("div", { className: "mono", style: { fontSize: 12, color: "var(--ink-3)", marginTop: 6 } }, "RERA ID ", p.id)),
        h("div", { style: { textAlign: "center", flex: "none" } },
          incomplete
            ? h("div", { className: "serif", style: { fontSize: 30, fontWeight: 700, color: "var(--ink-3)" } }, "N/A")
            : h("div", { className: "mono", style: { fontSize: 44, fontWeight: 700, lineHeight: 1, color: `var(--${p.band})` } }, p.score.toFixed(1),
                h("span", { style: { fontSize: 18, color: "var(--ink-3)" } }, "/10")),
          h("div", { style: { marginTop: 8, display: "inline-flex" } }, h(BandBadge, { band: p.band })))
      ),

      // verdict statement
      h("div", { style: { marginTop: 22, padding: "18px 20px", borderRadius: 10, borderLeft: `4px solid var(--${incomplete ? "ink-3" : p.band})`, background: "var(--surface-2)" } },
        h("div", { className: "eyebrow", style: { marginBottom: 8 } }, "Verdict — ", bandWord),
        h("div", { className: "serif", style: { fontSize: 18, fontWeight: 600, lineHeight: 1.35 } }, p.headline)),

      // record snapshot
      h("div", { className: "rsection-h" }, "Official record snapshot"),
      h("div", { style: { display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 0, border: "1px solid var(--line)", borderRadius: 8, overflow: "hidden" } },
        [["Registration status", p.statusNote || "Registered"], ["Registered on", p.registered || "—"], ["Record last modified", p.lastModified || "—"],
         ["Promised completion", p.promisedCompletion || "—"], ["Latest revision", p.revisedCompletion || "—"],
         ["Complaints on record", p.complaints == null ? "Not yet ingested" : String(p.complaints)],
         ["RERA orders", p.orders == null ? "Not yet ingested" : String(p.orders)],
         ["Extension certificates", p.extensions == null ? "Not yet ingested" : String(p.extensions)],
         ["Units", p.units == null ? "—" : String(p.units)]
        ].map(([k, v], i) =>
          h("div", { key: i, style: { padding: "11px 14px", borderRight: i % 3 !== 2 ? "1px solid var(--line)" : "none", borderTop: i > 2 ? "1px solid var(--line)" : "none" } },
            h("div", { className: "mono", style: { fontSize: 9.5, letterSpacing: ".06em", textTransform: "uppercase", color: "var(--ink-3)" } }, k),
            h("div", { style: { fontWeight: 600, fontSize: 13.5, marginTop: 3 } }, v)))
      ),

      // why this verdict
      h("div", { className: "rsection-h" }, "Why this verdict — every signal, sourced"),
      h("div", null, p.signals.map((s, i) => h(RptRow, { key: i, s }))),

      // builder
      h("div", { className: "rsection-h" }, "Builder track record"),
      h("div", { className: "muted", style: { fontSize: 13, lineHeight: 1.55 } },
        h("b", { style: { color: "var(--ink)" } }, b.name), " — active since ", b.since, ". ",
        `Of ${b.totalProjects} projects on record, ${b.delivered} delivered`,
        b.delayed != null ? `, ${b.delayed} delayed` : "", b.revoked ? `, ${b.revoked} revoked` : "", ". ", b.note),

      // footer disclaimer
      h("div", { style: { marginTop: 30, paddingTop: 16, borderTop: "2px solid var(--ink)", display: "flex", justifyContent: "space-between", gap: 20, alignItems: "flex-end" } },
        h("div", { className: "faint", style: { fontSize: 10.5, lineHeight: 1.5, maxWidth: "62ch" } },
          h("b", null, "Disclaimer. "),
          "This report summarises publicly available MahaRERA records as of ", AS_OF, ". It is information, not legal or financial advice. Records may change after this date. Verify the live status at maharera.maharashtra.gov.in and consult a qualified advisor before any transaction."),
        h("div", { className: "mono", style: { fontSize: 10, color: "var(--ink-3)", textAlign: "right", flex: "none" } },
          h("div", { style: { fontWeight: 700, color: "var(--brand)" } }, "honesthomes.in"),
          h("div", null, "Page 1 of 1")))
    )
  );
}

window.Report = Report;
