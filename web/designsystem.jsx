// ============================================================
// Honest Homes — Design System & annotations view
// ============================================================
const Icon_d = window.Icon;

function Swatch({ varName, name, hex }) {
  return h("div", { className: "ds-swatch" },
    h("div", { className: "chip", style: { background: `var(${varName})` } }),
    h("div", { className: "meta" }, h("div", { className: "nm" }, name), h("div", { className: "hx" }, hex))
  );
}

function DSBlock({ title, sub, children }) {
  return h("div", { className: "panel", style: { marginBottom: 18 } },
    h("div", { className: "panel-h" }, h("div", null, h("h2", null, title),
      sub && h("div", { className: "faint", style: { fontSize: 12.5, marginTop: 3 } }, sub))),
    h("div", { className: "panel-b", style: { paddingTop: 18, paddingBottom: 22 } }, children)
  );
}

function DesignSystem({ go }) {
  const sampleSignal = window.HH.showcase[1].signals[1];
  const annos = [
    ["Sourcing is a visible feature, not fine print.", "Every fact carries a mono-type source tag with an ‘as of’ date. Trust is earned by showing your work — so the provenance lives next to the claim, in the typeface we reserve for official record data."],
    ["No marketing photography. Ever.", "We deliberately avoid happy-family hero imagery — that glossy lie is exactly what we exist to cut through. The aesthetic is a financial/medical report: paper, ink, type and data. Calm, not sold-to."],
    ["The score stays defensible.", "The gauge always shows the full fixed band (red/amber/green) so the scale can’t look rigged per-project. The base is 5.0 and every adjustment is an itemised, sourced signal — never a black-box opinion."],
    ["Never rely on colour alone (WCAG AA).", "Each trust band pairs its colour with an icon and a text label (‘Looks clean’, ‘Caution’, ‘Serious flags’). Colour-blind and high-contrast users get the verdict without depending on the hue."],
    ["Honesty about absence.", "When we only have index data we say so — ‘N/A’, not a fake number. Refusing to manufacture confidence is itself a trust signal, so the incomplete state is designed as carefully as the others."],
    ["Micro-interactions that build trust.", "The gauge needle eases in (1.1s) so the number feels measured, not flashed. Source tags brighten on hover to invite scrutiny. Nothing bounces or celebrates — the tone stays grave and credible."],
  ];

  return h("div", { className: "wrap fade-in", style: { paddingTop: 28, paddingBottom: 70 } },
    h("div", { className: "eyebrow" }, "Design system"),
    h("h1", { className: "section-title", style: { marginTop: 6, fontSize: 34 } }, "The Honest Homes system"),
    h("p", { className: "muted", style: { fontSize: 15, maxWidth: "62ch", marginTop: 8, marginBottom: 24 } },
      "A report-grade visual language built for trust: paper-and-ink surfaces, an authoritative type scale, fixed semantic trust colours, and components that always show their sources."),

    // annotations first — the "why"
    h(DSBlock, { title: "Key trust-building decisions", sub: "The reasoning behind the design" },
      h("div", { className: "grid", style: { gridTemplateColumns: "1fr 1fr", gap: 12 } },
        annos.map((a, i) => h("div", { key: i, className: "anno" },
          h("div", { className: "num" }, "0" + (i + 1)),
          h("div", null, h("div", { style: { fontWeight: 700, fontSize: 14 } }, a[0]),
            h("div", { className: "muted", style: { fontSize: 13, marginTop: 4, lineHeight: 1.5 } }, a[1])))))
    ),

    // colour
    h(DSBlock, { title: "Colour — semantic trust palette", sub: "Calm authority + fixed traffic-light bands. Tints carry text at AA." },
      h("div", { className: "grid grid-4", style: { marginBottom: 14 } },
        h(Swatch, { varName: "--brand", name: "Brand / ink-blue", hex: "Primary" }),
        h(Swatch, { varName: "--green", name: "Clean", hex: "Looks clean" }),
        h(Swatch, { varName: "--amber", name: "Caution", hex: "Proceed carefully" }),
        h(Swatch, { varName: "--red", name: "Serious", hex: "Flags on record" })),
      h("div", { className: "grid grid-4" },
        h(Swatch, { varName: "--paper", name: "Paper", hex: "App background" }),
        h(Swatch, { varName: "--surface", name: "Surface", hex: "Cards" }),
        h(Swatch, { varName: "--ink", name: "Ink", hex: "Primary text" }),
        h(Swatch, { varName: "--ink-3", name: "Faint ink", hex: "Meta / sources" }))
    ),

    // type
    h(DSBlock, { title: "Typography", sub: "Source Serif 4 · Hanken Grotesk · JetBrains Mono · Noto Sans Devanagari" },
      h("div", { className: "stack-14" },
        h("div", { style: { borderBottom: "1px solid var(--line)", paddingBottom: 14 } },
          h("div", { className: "eyebrow", style: { marginBottom: 6 } }, "Serif · headlines & verdicts"),
          h("div", { className: "serif", style: { fontSize: 32, fontWeight: 600, letterSpacing: "-.02em" } }, "The honest verdict on a builder")),
        h("div", { style: { borderBottom: "1px solid var(--line)", paddingBottom: 14 } },
          h("div", { className: "eyebrow", style: { marginBottom: 6 } }, "Sans · interface & body"),
          h("div", { style: { fontSize: 17 } }, "Registration is valid — proceed with caution. Three complaints are on record."),
          h("div", { className: "deva", style: { fontSize: 17, marginTop: 6 } }, "मराठी आणि हिंदी मजकूर सुवाच्य आहे — नोंदणी वैध आहे.")),
        h("div", null,
          h("div", { className: "eyebrow", style: { marginBottom: 6 } }, "Mono · record data, IDs, sources"),
          h("div", { className: "mono", style: { fontSize: 15 } }, "P51700009876 · as of 12 May 2026 · +2.4 / −1.8"))
      )
    ),

    // components
    h(DSBlock, { title: "Components", sub: "The reusable building blocks" },
      h("div", { className: "grid grid-2", style: { gap: 20, alignItems: "start" } },
        h("div", { className: "stack-20" },
          h("div", null, h("div", { className: "eyebrow", style: { marginBottom: 10 } }, "Trust bands"),
            h("div", { className: "row gap-8", style: { flexWrap: "wrap" } },
              h(BandBadge, { band: "green" }), h(BandBadge, { band: "amber" }),
              h(BandBadge, { band: "red" }), h(BandBadge, { band: "incomplete" }))),
          h("div", null, h("div", { className: "eyebrow", style: { marginBottom: 10 } }, "Source tag"),
            h(SourceTag, { source: "MahaRERA", asOf: "12 May 2026" })),
          h("div", null, h("div", { className: "eyebrow", style: { marginBottom: 10 } }, "Buttons"),
            h("div", { className: "row gap-8", style: { flexWrap: "wrap" } },
              h("button", { className: "btn btn-primary btn-sm" }, "Download report"),
              h("button", { className: "btn btn-ghost btn-sm" }, "Share"),
              h("button", { className: "btn btn-quiet btn-sm" }, "View on MahaRERA"))),
          h("div", null, h("div", { className: "eyebrow", style: { marginBottom: 10 } }, "Signal row"),
            h("div", { className: "panel", style: { padding: "2px 16px" } }, h(SignalRow, { s: sampleSignal })))
        ),
        h("div", { style: { display: "grid", placeItems: "center", padding: "10px 0" } },
          h("div", { className: "eyebrow", style: { marginBottom: 6, alignSelf: "start" } }, "Trust gauge"),
          h(TrustGauge, { score: 5.2, band: "amber", size: 240, animate: false }))
      )
    ),

    h("div", { className: "row gap-8", style: { justifyContent: "center", marginTop: 8 } },
      h("button", { className: "btn btn-primary", onClick: go.home }, "Back to the app", h(Icon_d, { name: "arrow", size: 16 })))
  );
}

window.DesignSystem = DesignSystem;
