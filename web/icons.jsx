// ============================================================
// Honest Homes — icon set (stroke SVG, currentColor)
// ============================================================
const { createElement: h } = React;

const PATHS = {
  search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16ZM21 21l-4.3-4.3",
  "shield-check": "M12 3l7 3v6c0 4.4-3 7.7-7 9-4-1.3-7-4.6-7-9V6l7-3Z|M9 12l2 2 4-4",
  "calendar-check": "M7 3v3M17 3v3M4 8h16M5 6h14a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1Z|M9 14l2 2 4-4",
  "calendar-clock": "M21 9V6a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v13a1 1 0 0 0 1 1h7M7 3v3M17 3v3M3 9h18|M18 15v3l2 1",
  scale: "M12 3v18M7 7h10M7 7l-3 7h6l-3-7Zm10 0l-3 7h6l-3-7ZM6 21h12",
  gavel: "M14 13l-7 7-3-3 7-7M14.5 6.5l3 3M11 10l6-6 3 3-6 6-3-3ZM13 21h7",
  ban: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM5.6 5.6l12.8 12.8",
  "file-warning": "M14 3v5h5M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8l-5-5Z|M12 11v3M12 17.5v.01",
  file: "M14 3v5h5M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8l-5-5Z",
  hourglass: "M7 3h10M7 21h10M7 3c0 5 5 5 5 9s-5 4-5 9M17 3c0 5-5 5-5 9s5 4 5 9",
  download: "M12 3v12M7 11l5 4 5-4M5 21h14",
  share: "M4 12v7a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-7M16 6l-4-4-4 4M12 2v13",
  sun: "M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10ZM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
  moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z",
  monitor: "M3 4h18a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1ZM8 21h8M12 17v4",
  phone: "M7 2h10a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1ZM11 18h2",
  pin: "M12 21s7-5.6 7-11a7 7 0 1 0-14 0c0 5.4 7 11 7 11ZM12 12.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z",
  info: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 11v5M12 7.5v.01",
  arrow: "M5 12h14M13 6l6 6-6 6",
  back: "M19 12H5M11 18l-6-6 6-6",
  check: "M5 12l5 5 9-11",
  building: "M4 21V5a1 1 0 0 1 1-1h9a1 1 0 0 1 1 1v16M15 21V9h4a1 1 0 0 1 1 1v11M4 21h17M8 8h3M8 12h3M8 16h3",
  link: "M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1.5 1.5M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1.5-1.5",
  doc: "M14 3v5h5M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8l-5-5ZM8 13h8M8 17h6M8 9h2",
  trending: "M3 17l6-6 4 4 8-8M21 7v5h-5",
  layers: "M12 3l9 5-9 5-9-5 9-5ZM3 13l9 5 9-5M3 17l9 5 9-5",
  bolt: "M13 2L4 14h6l-1 8 9-12h-6l1-8Z",
  print: "M6 9V3h12v6M6 18H4a1 1 0 0 1-1-1v-5a1 1 0 0 1 1-1h16a1 1 0 0 1 1 1v5a1 1 0 0 1-1 1h-2M6 14h12v7H6v-7Z",
  mail: "M4 5h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z|M3.5 6.5l8.5 6 8.5-6",
  copy: "M9 9h10a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V10a1 1 0 0 1 1-1Z|M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1",
  whatsapp: "M3.5 20.5l1.3-4A8.5 8.5 0 1 1 8 19.2l-4.5 1.3Z|M9 8.5c-.3 0-.7.1-.9.5-.3.6-.9 1.4-.3 2.7.5 1.3 2.4 3.5 5 4.2 1.4.4 1.9.2 2.4-.1.4-.3.7-1 .6-1.4l-1.7-.8c-.2-.1-.4 0-.6.2l-.4.6c-.1.1-.3.2-.5.1-.7-.3-1.6-.9-2.2-2-.1-.2 0-.4.1-.5l.4-.5c.1-.2.1-.4.1-.6L9.7 9c-.2-.4-.4-.5-.7-.5Z",
  telegram: "M22 4L3 11l5.5 2L11 20l3-4 4.5 3.2z|M8.5 13L18 7",
  "x-twitter": "M5 5l14 14M19 5L5 19",
  facebook: "M13.5 22v-8h2.6l.4-3h-3V9.1c0-.9.3-1.5 1.6-1.5H16.6V5a22 22 0 0 0-2.4-.1C11.8 4.9 10.5 6.2 10.5 8.7V11H8v3h2.5v8z",
  instagram: "M7 3.5h10A3.5 3.5 0 0 1 20.5 7v10a3.5 3.5 0 0 1-3.5 3.5H7A3.5 3.5 0 0 1 3.5 17V7A3.5 3.5 0 0 1 7 3.5Z|M12 8.3a3.7 3.7 0 1 0 0 7.4 3.7 3.7 0 0 0 0-7.4Z|M17 6.6v.01",
  message: "M21 11.5a8.5 8.5 0 0 1-12.5 7.5L3 21l2-5.5A8.5 8.5 0 1 1 21 11.5Z",
  send: "M22 2L11 13M22 2l-7 20-4-9-9-4 20-7Z",
  more: "M5 12h.01M12 12h.01M19 12h.01",
  close: "M6 6l12 12M18 6L6 18",
  help: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z|M9.6 9.5a2.5 2.5 0 0 1 4.6 1.3c0 1.7-2.2 2-2.2 3.2M12 17.5v.01",
};

function Icon({ name, size = 18, sw = 1.75, fill = false, style, className }) {
  const d = PATHS[name];
  if (!d) return null;
  const segs = d.split("|");
  return h(
    "svg",
    { width: size, height: size, viewBox: "0 0 24 24", fill: "none",
      stroke: "currentColor", strokeWidth: sw, strokeLinecap: "round",
      strokeLinejoin: "round", style, className, "aria-hidden": true },
    segs.map((s, i) => h("path", { key: i, d: s }))
  );
}

window.Icon = Icon;

// ---------- Brand mark ----------
// The real logo artwork, lifted off its grey backdrop. It reads properly from
// about 40px up; below that the painted towers collapse into a smudge, so small
// renders fall back to a flat two-tower derivative of the same shape (which is
// also what the 16/32px favicons use).
function LogoMark({ size = 36, className, style }) {
  if (size >= 34) {
    return h("img", {
      src: "/static/img/logo-mark.png",
      width: size, height: size, className,
      alt: "Honest Homes",
      style: Object.assign({ objectFit: "contain", display: "block" }, style),
    });
  }
  return h("svg", {
    width: size, height: size, viewBox: "4 2 56 57", className, style,
    role: "img", "aria-label": "Honest Homes",
  },
    h("rect", { x: 10, y: 18, width: 15, height: 34, fill: "var(--brand)" }),
    h("rect", { x: 39, y: 12, width: 15, height: 40, fill: "var(--brand-2)" }),
    h("rect", { x: 25, y: 30, width: 14, height: 8, fill: "var(--brand)" }),
    h("rect", { x: 45.5, y: 4, width: 3, height: 8, fill: "var(--brand-2)" }),
    h("rect", { x: 8, y: 52, width: 48, height: 2.5, rx: 1, fill: "var(--brand)", opacity: .35 }),
    [[13,22],[18.5,22],[13,41],[18.5,41]].map(([x, y], i) =>
      h("rect", { key: "l"+i, x, y, width: 3.5, height: 3.5, rx: .6, fill: "var(--paper)" })),
    [[42,17],[47.5,17],[42,24],[47.5,24],[42,41],[47.5,41]].map(([x, y], i) =>
      h("rect", { key: "r"+i, x, y, width: 3.5, height: 3.5, rx: .6, fill: "var(--paper)" }))
  );
}

window.LogoMark = LogoMark;

