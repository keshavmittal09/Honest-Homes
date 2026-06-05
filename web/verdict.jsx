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

function Verdict({ id, go }) {
  const [data, setData] = useStateV(null);
  const [loading, setLoading] = useStateV(true);
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
      h("p", { className: "muted", style: { marginTop: 16 } }, "We couldn't load that project from the current dataset. It may be outside our index."));
  }

  const p = data.project;
  const b = data.builder || { name: p.builder, others: [], note: "" };
  const incomplete = !p.dataComplete;
  const glow = incomplete ? "transparent" : `var(--${p.band}-tint)`;

  // Real, working external links.
  const reraUrl = p.detailUrl || "https://maharera.maharashtra.gov.in/projects-search-result";
  const mapUrl = p.mapUrl || `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent((p.name || "") + " " + (p.district || "") + " Maharashtra")}`;
  const asOf = p.dataAsOf || (p.signals && p.signals[0] && p.signals[0].asOf) || window.HH.meta().asOf;

  const shareLink = () => {
    const url = `${location.origin}${location.pathname}#/verdict/${encodeURIComponent(p.id)}`;
    const done = () => showToast("Link copied to clipboard");
    if (navigator.clipboard) navigator.clipboard.writeText(url).then(done, done); else done();
  };

  const flags = p.signals.filter(s => s.kind === "severe" || (s.kind === "caution" && (p.band === "amber" || p.band === "red")));

  return h("div", { className: "wrap fade-in", style: { paddingTop: 24, paddingBottom: 64, "--band-glow": glow } },
    toast,
    // top bar
    h("div", { className: "row", style: { justifyContent: "space-between", marginBottom: 18, flexWrap: "wrap", gap: 12 } },
      h("button", { className: "btn btn-quiet btn-sm", onClick: go.back },
        h(Icon_v, { name: "back", size: 15 }), "Back to results"),
      h("div", { className: "row gap-8" },
        h("button", { className: "btn btn-ghost btn-sm", onClick: shareLink },
          h(Icon_v, { name: "share", size: 15 }), "Copy link"),
        h("button", { className: "btn btn-primary btn-sm", onClick: () => go.report(p.id) },
          h(Icon_v, { name: "doc", size: 15 }), "Full report")
      )
    ),

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
    ),

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
