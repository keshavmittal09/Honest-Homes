// ============================================================
// Honest Homes — UI primitives
// ============================================================
const { useState, useEffect, useRef } = React;
const Icon = window.Icon;

const BAND_LABEL = { green: "Looks clean", amber: "Caution", red: "Serious flags", incomplete: "Incomplete data" };
const BAND_ICON = { green: "shield-check", amber: "calendar-clock", red: "ban", incomplete: "hourglass" };

// ---------- Source tag (the trust signature) ----------
function SourceTag({ source, asOf }) {
  return h("span", { className: "source-tag", title: `Source: ${source} — as of ${asOf}` },
    h(Icon, { name: "shield-check", size: 13, className: "seal" }),
    h("span", null, h("b", null, source)),
    asOf && h("span", { className: "asof" }, "· as of ", asOf)
  );
}

// ---------- Band badge ----------
function BandBadge({ band, label }) {
  return h("span", { className: `badge ${band}` },
    h("span", { className: "dot" }),
    h(Icon, { name: BAND_ICON[band], size: 13 }),
    label || BAND_LABEL[band]
  );
}

function ScoreChip({ score, band }) {
  if (score == null) return h("span", { className: "scorechip incomplete" }, "No score");
  return h("span", { className: `scorechip ${band}` },
    score.toFixed(1), h("span", { className: "out" }, "/10"));
}

// ---------- Project card ----------
function ProjectCard({ p, onOpen }) {
  return h("button", { className: "pcard fade-in", onClick: () => onOpen(p.id) },
    h("div", { className: "pcard-top" },
      h("div", null,
        h("h3", null, p.name),
        h("div", { className: "builder" }, p.builder)
      ),
      h(BandBadge, { band: p.band })
    ),
    h("div", { className: "meta" },
      h("span", { className: "row gap-8" }, h(Icon, { name: "pin", size: 13 }),
        [p.district, p.locality && p.locality !== p.district ? p.locality : null].filter(Boolean).join(" · ")),
      h("span", { className: "k" }, p.id)
    ),
    h("div", { className: "pcard-foot" },
      h("span", { className: "row gap-8 faint", style: { fontSize: 12.5 } },
        h(Icon, { name: "shield-check", size: 13, style: { color: "var(--brand)" } }),
        "MahaRERA"),
      h("div", { className: "row gap-12" },
        h(ScoreChip, { score: p.score, band: p.band }),
        h(Icon, { name: "arrow", size: 16, className: "faint" })
      )
    )
  );
}

// ---------- Trust gauge (animated semicircle) ----------
function polar(cx, cy, r, deg) {
  const a = (deg * Math.PI) / 180;
  return [cx + r * Math.cos(a), cy - r * Math.sin(a)];
}
function arcPath(cx, cy, r, startV, endV) {
  // value 0..10 maps to angle 180..0
  const a0 = 180 - (startV / 10) * 180;
  const a1 = 180 - (endV / 10) * 180;
  const [x0, y0] = polar(cx, cy, r, a0);
  const [x1, y1] = polar(cx, cy, r, a1);
  const large = Math.abs(a1 - a0) > 180 ? 1 : 0;
  return `M ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1}`;
}

function TrustGauge({ score, band, size = 250, animate = true }) {
  const incomplete = score == null;
  const [val, setVal] = useState(animate ? 0 : (score || 0));
  useEffect(() => {
    if (incomplete || !animate) { setVal(score || 0); return; }
    let raf, start;
    const dur = 1100;
    const tick = (t) => {
      if (!start) start = t;
      const k = Math.min(1, (t - start) / dur);
      const eased = 1 - Math.pow(1 - k, 3);
      setVal(score * eased);
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [score, animate]);

  const w = size, hh = size * 0.62;
  const cx = w / 2, cy = size * 0.56, r = size * 0.42, sw = size * 0.078;
  const colorVar = incomplete ? "var(--ink-3)" : `var(--${band})`;

  // needle angle
  const ndeg = 180 - (val / 10) * 180;
  const [nx, ny] = polar(cx, cy, r - sw * 0.3, ndeg);

  return h("div", { className: "gauge-wrap" },
    h("svg", { width: w, height: hh + 6, viewBox: `0 0 ${w} ${hh + 6}` },
      // track
      h("path", { d: arcPath(cx, cy, r, 0, 10), fill: "none", stroke: "var(--gauge-track)",
        strokeWidth: sw, strokeLinecap: "round" }),
      // band segments (faint, always visible — shows the scale is fixed/honest)
      !incomplete && h("path", { d: arcPath(cx, cy, r, 0, 4), fill: "none", stroke: "var(--red)",
        strokeWidth: sw, strokeLinecap: "round", opacity: band === "red" ? 1 : .16 }),
      !incomplete && h("path", { d: arcPath(cx, cy, r, 4, 7), fill: "none", stroke: "var(--amber)",
        strokeWidth: sw, strokeLinecap: "butt", opacity: band === "amber" ? 1 : .16 }),
      !incomplete && h("path", { d: arcPath(cx, cy, r, 7, 10), fill: "none", stroke: "var(--green)",
        strokeWidth: sw, strokeLinecap: "round", opacity: band === "green" ? 1 : .16 }),
      incomplete && h("path", { d: arcPath(cx, cy, r, 0, 10), fill: "none", stroke: "var(--ink-3)",
        strokeWidth: sw, strokeLinecap: "round", strokeDasharray: "2 7", opacity: .5 }),
      // needle
      !incomplete && h("line", { x1: cx, y1: cy, x2: nx, y2: ny, stroke: colorVar, strokeWidth: 3, strokeLinecap: "round" }),
      !incomplete && h("circle", { cx, cy, r: 6, fill: "var(--surface)", stroke: colorVar, strokeWidth: 3 }),
    ),
    h("div", { style: { marginTop: -size * 0.30, textAlign: "center" } },
      incomplete
        ? h("div", { className: "gauge-num", style: { fontSize: size * 0.16, color: colorVar } }, "N/A")
        : h("div", null,
            h("span", { className: "gauge-num", style: { fontSize: size * 0.28, color: colorVar } }, val.toFixed(1)),
            h("span", { className: "mono", style: { fontSize: size * 0.085, color: "var(--ink-3)", fontWeight: 600 } }, " /10")
          ),
      h("div", { style: { marginTop: 8 } }, h(BandBadge, { band: incomplete ? "incomplete" : band }))
    )
  );
}

// ---------- Signal row ----------
function ImpactTag({ impact }) {
  if (impact == null) return h("span", { className: "impact zero" }, "—");
  if (impact === 0) return h("span", { className: "impact zero" }, "0");
  const cls = impact > 0 ? "pos" : "neg";
  return h("span", { className: `impact ${cls}` }, (impact > 0 ? "+" : "") + impact.toFixed(1));
}
function SignalRow({ s }) {
  const [open, setOpen] = useState(false);
  return h("div", { className: `signal ${s.kind}` },
    h("div", { className: "ico" }, h(Icon, { name: s.icon, size: 19 })),
    h("div", null,
      h("div", { className: "fact" }, s.fact),
      h("div", { className: "detail" }, s.detail),
      h("div", { className: "src-row" },
        h(SourceTag, { source: s.source, asOf: s.asOf })
      )
    ),
    h(ImpactTag, { impact: s.impact })
  );
}

// ---------- Timeline ----------
function Timeline({ items, band }) {
  const n = items.length;
  const fillColor = band === "red" ? "var(--red)" : band === "amber" ? "var(--amber)" : "var(--green)";
  // slippage = between first promised and last revised/now
  const promisedIdx = items.findIndex(i => i.type === "promised");
  const lastIdx = n - 1;
  return h("div", { className: "timeline" },
    h("div", { className: "tl-track" },
      h("div", { className: "tl-fill", style: { width: "100%", background: "var(--gauge-track)" } }),
      (promisedIdx >= 0 && lastIdx > promisedIdx && (items[lastIdx].type === "revised" || items[lastIdx].type === "revoked" || items[lastIdx].type === "now")) &&
        h("div", { className: "tl-slip", style: {
          left: `${(promisedIdx / (n - 1)) * 100}%`,
          width: `${((lastIdx - promisedIdx) / (n - 1)) * 100}%`,
        } }, "delay / slippage"),
      items.map((it, i) =>
        h("div", { key: i, className: `tl-node ${it.type}`, style: { left: `${(i / (n - 1)) * 100}%` } },
          h("div", { className: "lab", style: i % 2 ? { bottom: 34 } : {} }, it.label),
          h("div", { className: "dot" }),
          h("div", { className: "dte" }, it.date)
        )
      )
    )
  );
}

// ---------- Skeleton loading card ----------
function SkeletonCard() {
  const bar = (w, h2) => h("div", { style: { height: h2, width: w, borderRadius: 6, background: "var(--surface-3)" } });
  return h("div", { className: "pcard", style: { pointerEvents: "none" } },
    h("div", { className: "pcard-top" },
      h("div", { className: "stack-10" }, bar("160px", 18), bar("110px", 13)),
      bar("84px", 24)),
    h("div", { style: { marginTop: 16 } }, bar("70%", 13)),
    h("div", { className: "pcard-foot" }, bar("80px", 13), bar("46px", 18))
  );
}

// ---------- Toast (for copy-link feedback etc.) ----------
function useToast() {
  const [msg, setMsg] = useState(null);
  const show = (m) => { setMsg(m); setTimeout(() => setMsg(null), 2200); };
  const node = msg && h("div", { className: "toast fade-in" }, h(Icon, { name: "check", size: 15 }), msg);
  return [node, show];
}

Object.assign(window, { SourceTag, BandBadge, ScoreChip, ProjectCard, TrustGauge, SignalRow, ImpactTag, Timeline, SkeletonCard, useToast, BAND_LABEL, BAND_ICON });
