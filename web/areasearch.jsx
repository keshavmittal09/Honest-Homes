// ============================================================
// Honest Homes — Area search
// ============================================================
// Buyers look for a place before they look for a building: "Kharghar", "Panvel",
// "410210". The index has no locality field, so areas are learned from the
// Tier-2 addresses and mapped onto every project sharing that pincode. This is
// the front of that: a search box that suggests real areas as you type, and a
// banner that tells you when a search matched a place rather than a name.

const { useState: useStateA, useEffect: useEffectA, useRef: useRefA } = React;

const AREA_ICON = { locality: "📍", pincode: "✉️", district: "🗺️" };
const AREA_WORD = { locality: "area", pincode: "pincode", district: "district" };

// A search box with area suggestions. Falls back to plain text submit, so it
// still works if the suggestions endpoint is unreachable.
function AreaSearchBox({ value, onChange, onSubmit, placeholder, autoFocus }) {
  const [areas, setAreas] = useStateA([]);
  const [open, setOpen] = useStateA(false);
  const [active, setActive] = useStateA(-1);
  const box = useRefA(null);

  useEffectA(() => {
    const q = (value || "").trim();
    if (q.length < 2) { setAreas([]); return; }
    let alive = true;
    // Debounced: a suggestion request per keystroke would be one per 40ms.
    const t = setTimeout(() => {
      window.HH.areas(q, 6).then(rows => { if (alive) { setAreas(rows); setActive(-1); } });
    }, 180);
    return () => { alive = false; clearTimeout(t); };
  }, [value]);

  // Close on an outside click, so the list never hangs over the results.
  useEffectA(() => {
    function away(e) { if (box.current && !box.current.contains(e.target)) setOpen(false); }
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, []);

  function pick(a) {
    setOpen(false);
    onChange(a.name);
    onSubmit(a.name);
  }

  function keyDown(e) {
    if (!open || !areas.length) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setActive(i => Math.min(i + 1, areas.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive(i => Math.max(i - 1, -1)); }
    else if (e.key === "Enter" && active >= 0) { e.preventDefault(); pick(areas[active]); }
    else if (e.key === "Escape") setOpen(false);
  }

  return h("div", { ref: box, style: { position: "relative", width: "100%" } },
    h("form", { className: "searchbox", style: { margin: 0 },
        onSubmit: e => { e.preventDefault(); setOpen(false); onSubmit(value); } },
      h(window.Icon, { name: "search", size: 19, className: "mag" }),
      h("input", {
        value: value || "",
        onChange: e => { onChange(e.target.value); setOpen(true); },
        onFocus: () => setOpen(true),
        onKeyDown: keyDown,
        autoFocus: !!autoFocus,
        "aria-label": "Search by project, builder or area",
        "aria-autocomplete": "list",
        placeholder: placeholder || "Project, builder, or area — try Kharghar",
      }),
      h("button", { type: "submit", className: "btn btn-primary btn-sm" }, "Search")),

    open && areas.length > 0 && h("div", {
      role: "listbox",
      style: { position: "absolute", top: "calc(100% + 6px)", left: 0, right: 0, zIndex: 40, background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 12, boxShadow: "0 12px 34px rgba(0,0,0,.14)", overflow: "hidden" },
    },
      h("div", { className: "faint", style: { fontSize: 10.5, padding: "8px 13px 6px", letterSpacing: ".06em", textTransform: "uppercase" } }, "Areas"),
      areas.map((a, i) => h("button", {
        key: a.key,
        role: "option",
        "aria-selected": i === active,
        onMouseEnter: () => setActive(i),
        onClick: () => pick(a),
        style: { width: "100%", display: "grid", gridTemplateColumns: "auto 1fr auto", gap: 10, alignItems: "center", padding: "10px 13px", background: i === active ? "var(--surface-2)" : "none", border: "none", cursor: "pointer", textAlign: "left", font: "inherit", color: "inherit" },
      },
        h("span", { style: { fontSize: 15 }, "aria-hidden": true }, AREA_ICON[a.kind] || "📍"),
        h("span", { style: { minWidth: 0 } },
          h("span", { style: { display: "block", fontWeight: 600, fontSize: 13.5, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" } }, a.name),
          h("span", { className: "faint", style: { display: "block", fontSize: 11.5 } }, AREA_WORD[a.kind] || a.kind)),
        h("span", { className: "mono faint", style: { fontSize: 11.5, flex: "none" } },
          a.count.toLocaleString("en-IN"))))
    )
  );
}

// Shown above results when the query matched a place. Without it, searching
// "Kharghar" and getting 156 projects whose names mostly do not say "Kharghar"
// looks like a broken search rather than a working one.
function AreaBanner({ area, total }) {
  if (!area) return null;
  return h("div", { style: { display: "flex", gap: 11, alignItems: "center", padding: "11px 14px", borderRadius: 10, background: "var(--surface-2)", borderLeft: "3px solid var(--brand)", marginBottom: 16 } },
    h("span", { style: { fontSize: 17 }, "aria-hidden": true }, AREA_ICON[area.kind] || "📍"),
    h("div", { style: { minWidth: 0 } },
      h("div", { style: { fontWeight: 650, fontSize: 13.5 } },
        total.toLocaleString("en-IN"), " project", total === 1 ? "" : "s", " in ", area.name),
      h("div", { className: "faint", style: { fontSize: 11.5, marginTop: 2 } },
        "Matched as ", /^[aeiou]/i.test(AREA_WORD[area.kind] || area.kind) ? "an " : "a ",
        AREA_WORD[area.kind] || area.kind,
        " — including projects whose names do not mention it."))
  );
}

window.AreaSearchBox = AreaSearchBox;
window.AreaBanner = AreaBanner;
