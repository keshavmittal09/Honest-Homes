// ============================================================
// Honest Homes — scroll scene: left story copy + right glass tower
// Building: front-perspective glass curtain-wall SVG — tall, slim,
// real face shading. Two layers (glass / blueprint) cross-fade by --p.
// ============================================================
const { useRef: useRefSC, useState: useStateSC, useEffect: useEffectSC } = React;
const Icon_sc = window.Icon;

function findScroller(el) {
  let n = el && el.parentElement;
  while (n && n !== document.body) {
    const oy = getComputedStyle(n).overflowY;
    if ((oy === "auto" || oy === "scroll") && n.scrollHeight > n.clientHeight + 4) return n;
    n = n.parentElement;
  }
  return window;
}

// ─── Building ───────────────────────────────────────────────
// Front-perspective: tall front face + slim right-side sliver + thin roof.
// Two <g> groups (.glass-layer / .bp-layer) stacked, opacities via CSS --p.
const BW = 164, BH = 360, SDX = 48, SDY = 14; // front W×H, side depth offset

function makeWindows() {
  const wins = [], WW = 33, WH = 25, GX = 7, GY = 5, MX = 10, MY = 14;
  let idx = 0;
  for (let xi = MX; xi + WW <= BW - MX; xi += WW + GX) {
    for (let yi = MY; yi + WH <= BH - MY; yi += WH + GY) {
      wins.push({ x: xi, y: yi, w: WW, h: WH, lit: (idx * 11 + 5) % 13 < 2 });
      idx++;
    }
  }
  return wins;
}
function makeFloors() {
  const floors = [], step = 30, MX = 10, MY = 14, WH = 25, GY = 5;
  for (let y = MY + WH + GY; y < BH - MY; y += step) floors.push(y);
  return floors;
}
const WINS = makeWindows();
const FLOORS = makeFloors();
const frontPts = `0,0 ${BW},0 ${BW},${BH} 0,${BH}`;
const sidePts = `${BW},0 ${BW + SDX},${-SDY} ${BW + SDX},${BH - SDY} ${BW},${BH}`;
const roofPts = `0,0 ${BW},0 ${BW + SDX},${-SDY} ${SDX},${-SDY}`;
const spireTip = `${BW / 2},${-72}`;

function Building() {
  return h("svg", { className: "bsvg", viewBox: `-12 -84 ${BW + SDX + 24} ${BH + 90}`, "aria-hidden": true },
    h("defs", null,
      h("linearGradient", { id: "gFront", x1: "0%", y1: "0%", x2: "90%", y2: "100%" },
        h("stop", { offset: "0%", stopColor: "#d6e8f6" }),
        h("stop", { offset: "50%", stopColor: "#a4bcce" }),
        h("stop", { offset: "100%", stopColor: "#82a0b5" })),
      h("linearGradient", { id: "gSide", x1: "0%", y1: "0%", x2: "0%", y2: "100%" },
        h("stop", { offset: "0%", stopColor: "#7590a6" }),
        h("stop", { offset: "100%", stopColor: "#536e82" })),
      h("linearGradient", { id: "gSheen", x1: "0%", y1: "0%", x2: "60%", y2: "100%" },
        h("stop", { offset: "0%", stopColor: "rgba(255,255,255,.52)" }),
        h("stop", { offset: "40%", stopColor: "rgba(255,255,255,.14)" }),
        h("stop", { offset: "100%", stopColor: "rgba(255,255,255,0)" })),
      h("linearGradient", { id: "gSpire", x1: "0%", y1: "100%", x2: "0%", y2: "0%" },
        h("stop", { offset: "0%", stopColor: "#7590a6" }),
        h("stop", { offset: "45%", stopColor: "#b0c8d8" }),
        h("stop", { offset: "100%", stopColor: "#d8eaf5", stopOpacity: 0.72 })),
      h("clipPath", { id: "frontClip" }, h("rect", { x: 0, y: 0, width: BW, height: BH }))
    ),

    // glass layer
    h("g", { className: "glass-layer" },
      h("ellipse", { className: "g-shadow", cx: BW / 2 + 14, cy: BH + 26, rx: 118, ry: 20 }),
      h("polygon", { fill: "url(#gSide)", stroke: "rgba(12,22,38,.18)", strokeWidth: .7, points: sidePts }),
      h("polygon", { className: "g-roof", stroke: "rgba(12,22,38,.12)", strokeWidth: .6, points: roofPts }),
      h("polygon", { fill: "url(#gFront)", stroke: "rgba(12,22,38,.14)", strokeWidth: .7, points: frontPts }),
      h("g", { clipPath: "url(#frontClip)" },
        FLOORS.map((fy, i) => h("line", { key: i, className: "g-floor-line", x1: 0, y1: fy, x2: BW, y2: fy })),
        WINS.map((w, i) => h("rect", { key: i, className: w.lit ? "g-win lit" : "g-win", x: w.x, y: w.y, width: w.w, height: w.h, rx: 1.5 })),
        h("polygon", { fill: "url(#gSheen)", points: frontPts, style: { pointerEvents: "none" } })
      ),
      h("line",   { className: "g-spire",      x1: BW / 2, y1: 0, x2: BW / 2, y2: -66 }),
      h("circle", { className: "g-spire-ball", cx: BW / 2, cy: -66, r: 2.5 })
    ),

    // blueprint layer
    h("g", { className: "bp-layer" },
      h("polygon", { className: "b-face", points: sidePts }),
      h("polygon", { className: "b-face", points: roofPts }),
      h("polygon", { className: "b-face", points: frontPts }),
      h("g", { clipPath: "url(#frontClip)" },
        FLOORS.map((fy, i) => h("line", { key: i, className: "b-floor", x1: 0, y1: fy, x2: BW, y2: fy })),
        WINS.map((w, i) => h("rect", { key: i, className: "b-win", x: w.x, y: w.y, width: w.w, height: w.h, rx: 1.5 }))
      ),
      h("line", { className: "b-spire", x1: BW / 2, y1: 0, x2: BW / 2, y2: -66 }),
      h("g", { className: "b-groundwrap" },
        [-3, -1, 1, 3, 5].map((i) => [
          h("line", { key: "bgh" + i, className: "b-grid", x1: -12, y1: BH + 30 + i * 12, x2: BW + SDX + 12, y2: BH + 30 + i * 12 }),
          h("line", { key: "bgv" + i, className: "b-grid", x1: (i + 5) * 28 - 24, y1: BH + 5, x2: (i + 5) * 28 - 24, y2: BH + 66 })
        ]).flat()
      )
    )
  );
}

// ─── ScrollScene ────────────────────────────────────────────
function ScrollScene({ go }) {
  const sceneRef = useRefSC(null);
  const rootRef = useRefSC(null);
  const [vh, setVh] = useStateSC(typeof window !== "undefined" ? window.innerHeight : 800);
  const [stage, setStage] = useStateSC(0);
  const stageRef = useRefSC(0);

  useEffectSC(() => {
    const sceneEl = sceneRef.current;
    const scroller = findScroller(sceneEl);
    const measure = () => setVh(scroller === window ? window.innerHeight : scroller.clientHeight);
    measure();
    let raf = 0;
    const update = () => {
      raf = 0;
      const rect = sceneEl.getBoundingClientRect();
      const sTop = scroller === window ? 0 : scroller.getBoundingClientRect().top;
      const vhNow = scroller === window ? window.innerHeight : scroller.clientHeight;
      const travel = rect.height - vhNow;
      const p = travel > 0 ? Math.min(1, Math.max(0, -(rect.top - sTop) / travel)) : 0;
      if (rootRef.current) rootRef.current.style.setProperty("--p", p.toFixed(4));
      const st = p < 0.34 ? 0 : p < 0.72 ? 1 : 2;
      if (st !== stageRef.current) {
        stageRef.current = st; setStage(st);
        if (rootRef.current) rootRef.current.style.setProperty("--scene-glow",
          st === 0 ? "transparent" : st === 1 ? "var(--brand-tint)" : "var(--red-tint)");
      }
    };
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(update); };
    const target = scroller === window ? window : scroller;
    target.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", () => { measure(); onScroll(); });
    update();
    return () => { target.removeEventListener("scroll", onScroll); };
  }, []);

  const steps = [
    { k: "01 — The brochure", h: ["Every tower looks ", "flawless", " in the brochure."],
      p: "Glossy renders, a sunset balcony, a launch-day price. None of it tells you whether the builder will actually hand over your home." },
    { k: "02 — The record", h: ["So we ", "x-ray", " the glossy facade."],
      p: "Underneath every project sits an official MahaRERA record — registration, revised deadlines, complaints, orders. We read all of it, line by line." },
    { k: "03 — The verdict", h: ["Then you get the ", "honest verdict", "."],
      p: "One sourced, plain-language score — never a black box. Take this tower: its registration was revoked. Here is exactly how we'd flag it." },
  ];
  const segFill = (i) => ({ width: `clamp(0%, calc((var(--p) - ${(i * 0.3334).toFixed(4)}) * 300%), 100%)` });

  return h("section", { className: "scene", ref: sceneRef, style: { height: vh * 2.4 } },
    h("div", { className: "scene-sticky scene-glow-shift", ref: rootRef, style: { height: vh } },

      // left copy
      h("div", { className: "scene-copy" },
        h("div", { className: "scene-progressbar" },
          [0, 1, 2].map(i => h("div", { key: i, className: "seg" }, h("i", { style: segFill(i) })))),
        h("div", { style: { position: "relative", minHeight: 240 } },
          steps.map((s, i) =>
            h("div", { key: i, className: "scene-step",
              style: { position: i === 0 ? "relative" : "absolute", inset: i === 0 ? "auto" : 0,
                opacity: stage === i ? 1 : 0, transform: stage === i ? "none" : "translateY(12px)",
                pointerEvents: stage === i ? "auto" : "none" } },
              h("div", { className: "scene-kicker" }, s.k),
              h("h2", { className: "scene-h" }, s.h[0], h("em", null, s.h[1]), s.h[2]),
              h("p", { className: "scene-p" }, s.p),
              i === 2 && h("button", { className: "btn btn-primary",
                  style: { marginTop: 24, opacity: `clamp(0, calc((var(--p) - 0.85) * 8), 1)` },
                  onClick: () => go.verdict("DEMO-RED") },
                "See the full verdict", h(Icon_sc, { name: "arrow", size: 16 }))))
        )
      ),

      // right building
      h("div", { className: "bldg-stage" },
        h("div", { className: "bldg" },
          h("div", { className: "bldg-float" }, h(Building))),
        // scan line
        h("div", { className: "sv-scan" }),
        // annotations
        h("div", { className: "ann", style: { "--s": 0.34, top: 52, left: 4 } },
          h("div", { className: "card" },
            h("div", { className: "t" }, h(Icon_sc, { name: "shield-check", size: 14 }), "P51800004321"),
            h("div", { className: "d" }, "MahaRERA · registered 2019")),
          h("div", { className: "stem right" })),
        h("div", { className: "ann amber", style: { "--s": 0.47, top: 188, right: 2 } },
          h("div", { className: "card" },
            h("div", { className: "t" }, h(Icon_sc, { name: "calendar-clock", size: 14 }), "Completion revised ×2"),
            h("div", { className: "d" }, "2022 → 2023 → 2024")),
          h("div", { className: "stem left" })),
        h("div", { className: "ann red", style: { "--s": 0.60, bottom: 68, left: 2 } },
          h("div", { className: "card" },
            h("div", { className: "t" }, h(Icon_sc, { name: "scale", size: 14 }), "11 complaints · 4 orders"),
            h("div", { className: "d" }, "incl. 2 recovery warrants")),
          h("div", { className: "stem right" })),
        h("div", { className: "stamp" }, "REVOKED"),
        h("div", { className: "vchip", "data-shown": stage === 2 ? "1" : "0" },
          h("button", { className: "card", onClick: () => go.verdict("DEMO-RED"), style: { cursor: "pointer" } },
            h("div", { className: "sc" }, "1.8", h("small", null, "/10")),
            h("div", null,
              h(BandBadge, { band: "red" }),
              h("div", { className: "vchip-link" }, "See full verdict", h(Icon_sc, { name: "arrow", size: 12 })))))
      )
    )
  );
}

window.ScrollScene = ScrollScene;
// Landing references HeroScene; new design renamed it to ScrollScene. Alias for compatibility.
window.HeroScene = ScrollScene;
