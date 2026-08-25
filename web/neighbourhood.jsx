// ============================================================
// Honest Homes — What's around this project
// ============================================================
// A project can have 200+ mapped places within 5 km. Showing them would bury
// the verdict, which is what the page is actually for. So the information is
// staged: a one-line summary, then a grid of category tiles, and only the
// category you open lists its places. Nothing below the fold loads until asked.
//
// The grades are honest about what they are. A-E describes distance and choice
// -- facts from the map. Where a place carries a government ranking (NIRF) or a
// Wikidata entry, that is shown as its own badge and never folded into the
// grade, because one is our arithmetic and the other is someone's published
// assessment.

const Icon_n = window.Icon;
const { useState: useStateN, useEffect: useEffectN } = React;

const GRADE_TONE = {
  A: "var(--green)", B: "var(--green)", C: "var(--amber)",
  D: "var(--amber)", E: "var(--red)",
};

// A glyph per category. Emoji rather than an icon set: it survives any font
// stack, needs no sprite, and reads at 14px on a phone.
const CAT_ICON = {
  schools: "🏫", colleges: "🎓", hospitals: "🏥",
  pharmacies: "💊", malls: "🛍️", markets: "🥬",
  transport: "🚆", offices: "🏢", parks: "🌳",
  dining: "🍽️", banks: "🏧", fitness: "🏋️",
  entertainment: "🎬", worship: "🕌",
};

function metres(m) {
  if (m == null) return "—";
  return m < 1000 ? `${m} m` : `${(m / 1000).toFixed(1)} km`;
}

// One place. Kept to two lines: what it is and how far, then the badges that
// carry real authority.
function PlaceRow({ p }) {
  // Every place gets a map link. A distance is only useful if the reader can
  // see where the thing actually is — "1.2 km" means nothing without knowing
  // which direction. Google Maps is what people in India actually navigate
  // with; the OSM link is the source we derived the point from.
  const gmaps = p.lat != null && p.lon != null
    ? `https://www.google.com/maps/search/?api=1&query=${p.lat},${p.lon}`
    : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(p.name || "")}`;

  return h("div", { style: { display: "grid", gridTemplateColumns: "1fr auto", gap: 10, padding: "9px 0", borderTop: "1px solid var(--line)", alignItems: "start" } },
    h("div", { style: { minWidth: 0 } },
      h("a", {
        href: gmaps, target: "_blank", rel: "noopener noreferrer",
        style: { fontSize: 13.5, fontWeight: 550, lineHeight: 1.35, color: "var(--ink)", textDecoration: "none", borderBottom: "1px dotted var(--line-2, var(--line))" },
        title: "Open in Google Maps",
      }, p.name),
      h("div", { className: "faint", style: { fontSize: 11.5, marginTop: 2, display: "flex", gap: 8, flexWrap: "wrap" } },
        p.kind && h("span", null, p.kind.replace(/_/g, " ")),
        p.operator && h("span", null, "· ", p.operator),
        p.openingHours && h("span", null, "· ", p.openingHours))),
    h("div", { style: { textAlign: "right", flex: "none" } },
      h("div", { className: "mono", style: { fontSize: 12.5, fontWeight: 700 } }, metres(p.distanceM)),
      p.walkMinutes && h("div", { className: "faint", style: { fontSize: 11 } }, "~", p.walkMinutes, " min walk"),
      h("a", { href: gmaps, target: "_blank", rel: "noopener noreferrer",
               className: "faint", style: { fontSize: 10.5, textDecoration: "none", display: "inline-block", marginTop: 3 } },
        "Map ↗")),
    // Badges span both columns so a long ranking label never squeezes the name.
    (p.nirf || p.wikidata) && h("div", { style: { gridColumn: "1 / -1", display: "flex", gap: 6, flexWrap: "wrap", marginTop: 2 } },
      p.nirf && h("span", { className: "chip", style: { fontSize: 10.5, padding: "2px 8px", background: "var(--green-tint, var(--surface-2))", color: "var(--green)", fontWeight: 700 } },
        "NIRF #", p.nirf.rank, " ", p.nirf.category, " ", p.nirf.year),
      p.wikidata && h("a", { className: "chip", href: p.wikidata.url, target: "_blank", rel: "noopener noreferrer", style: { fontSize: 10.5, padding: "2px 8px", textDecoration: "none" } },
        "Notable institution"))
  );
}

// One category: a tile that opens. Closed it is a single line; open it lists
// the nearest few and can fetch the rest.
function CategoryTile({ cat, reraId }) {
  const [open, setOpen] = useStateN(false);
  const [all, setAll] = useStateN(null);
  const [loading, setLoading] = useStateN(false);
  const tone = GRADE_TONE[cat.grade] || "var(--ink-3)";
  const places = all || cat.places || [];

  async function showAll() {
    setLoading(true);
    const rows = await window.HH.amenityCategory(reraId, cat.key);
    setAll(rows);
    setLoading(false);
  }

  return h("div", { className: "panel", style: { padding: 0, overflow: "hidden" } },
    h("button", {
      onClick: () => setOpen(!open),
      "aria-expanded": open,
      style: { width: "100%", background: "none", border: "none", cursor: "pointer", textAlign: "left", padding: "13px 15px", display: "grid", gridTemplateColumns: "auto 1fr auto", gap: 11, alignItems: "center", font: "inherit", color: "inherit" },
    },
      h("span", { style: { fontSize: 19, lineHeight: 1 }, "aria-hidden": true }, CAT_ICON[cat.key] || "📍"),
      h("span", { style: { minWidth: 0 } },
        h("span", { style: { display: "block", fontWeight: 650, fontSize: 13.5 } }, cat.label),
        h("span", { className: "faint", style: { display: "block", fontSize: 11.5, marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" } },
          cat.count, cat.count === 1 ? " place · " : " places · ", "nearest ", metres(cat.nearestM))),
      h("span", { style: { display: "flex", alignItems: "center", gap: 9, flex: "none" } },
        h("span", { className: "mono", style: { fontWeight: 800, fontSize: 15, color: tone } }, cat.grade),
        h("span", { className: "faint", style: { fontSize: 11, transform: open ? "rotate(90deg)" : "none", transition: "transform .15s" } }, "›"))
    ),
    open && h("div", { style: { padding: "0 15px 13px" } },
      h("div", { className: "faint", style: { fontSize: 11.5, paddingBottom: 3 } }, cat.gradeNote),
      places.map((p, i) => h(PlaceRow, { key: p.osm || i, p })),
      !all && cat.more > 0 && h("button", {
        className: "btn btn-quiet btn-sm", onClick: showAll, disabled: loading,
        style: { marginTop: 10, width: "100%" },
      }, loading ? "Loading…" : `Show all ${cat.count}`))
  );
}

// The map. Two views, one at a time — showing both at once doubles the page
// weight for a comparison nobody makes.
function NeighbourhoodMap({ reraId, maps }) {
  const [view, setView] = useStateN(maps.satellite ? "satellite" : "street");
  if (!maps.street && !maps.satellite) return null;
  return h("div", { style: { marginTop: 14 } },
    h("div", { className: "row", style: { gap: 6, marginBottom: 8 } },
      ["street", "satellite"].map(k => maps[k] && h("button", {
        key: k, className: "chip", onClick: () => setView(k),
        style: { fontSize: 11.5, fontWeight: view === k ? 700 : 500, background: view === k ? "var(--ink)" : "var(--surface-2)", color: view === k ? "var(--paper)" : "var(--ink-2)", cursor: "pointer", border: "none" },
      }, k === "street" ? "Street map" : "Satellite"))),
    // The source image is a square 3x3 tile mosaic. Shown at its natural ratio
    // it runs ~800px tall and buries the rest of the panel, so it is cropped to
    // a band centred on the marker — enough to place the project, not so much
    // that the map becomes the page.
    h("div", { style: { position: "relative", height: 300, borderRadius: 10, overflow: "hidden", border: "1px solid var(--line)" } },
      h("img", {
        src: `/api/hh/amenity-map/${encodeURIComponent(reraId)}/${view}.jpg`,
        alt: `${view} map of the area around this project`,
        loading: "lazy",
        style: { width: "100%", height: "100%", objectFit: "cover", display: "block" },
      })),
    h("div", { className: "faint", style: { fontSize: 10.5, marginTop: 5 } },
      view === "satellite" ? "Imagery © Esri, Maxar" : "© OpenStreetMap contributors",
      " · the marker is the project's registered location")
  );
}

function Neighbourhood({ reraId }) {
  const [data, setData] = useStateN(null);
  const [open, setOpen] = useStateN(false);

  useEffectN(() => {
    let alive = true;
    window.HH.amenities(reraId).then(d => { if (alive) setData(d); });
    return () => { alive = false; };
  }, [reraId]);

  // Absent is the common case while collection is still running, and it must
  // read as "not checked yet", never as "there is nothing here".
  if (!data) return null;
  if (!data.available) {
    return h("div", { className: "panel", style: { marginTop: 16 } },
      h("div", { className: "panel-h" },
        h("div", null,
          h("h2", null, "What's around this project"),
          h("div", { className: "faint", style: { fontSize: 12.5, marginTop: 3 } },
            "We have not mapped this project's surroundings yet — this is a gap in our collection, not a finding about the area."))));
  }

  const o = data.overall || {};

  // The project's coordinates did not survive validation, so we never searched
  // its real surroundings. Showing the grade the arithmetic produced — "E,
  // poorly served" — would state as fact that a Navi Mumbai tower has nothing
  // near it, when what actually happened is that MahaRERA geo-tagged it in the
  // wrong district.
  if (o.known === false || !o.grade) {
    return h("div", { className: "panel", style: { marginTop: 16 } },
      h("div", { className: "panel-h" },
        h("div", null,
          h("h2", null, "What's around this project"),
          h("div", { className: "faint", style: { fontSize: 12.5, marginTop: 3, lineHeight: 1.55, maxWidth: "72ch" } },
            "MahaRERA has not published usable coordinates for this project, so we have not assessed its surroundings. ",
            h("b", null, "This says nothing about the neighbourhood"),
            " — only that we cannot confirm where the building stands."))));
  }

  const tone = GRADE_TONE[o.grade] || "var(--ink-3)";
  const top = (data.categories || []).slice(0, 3).map(c => c.label).join(", ");

  return h("div", { className: "panel", style: { marginTop: 16 } },
    h("div", { className: "panel-h" },
      h("div", { style: { minWidth: 0 } },
        h("h2", null, "What's around this project"),
        h("div", { className: "faint", style: { fontSize: 12.5, marginTop: 3 } },
          data.totalPlaces, " places mapped within ", (data.radiusM / 1000).toFixed(0), " km")),
      h("div", { style: { textAlign: "right", flex: "none" } },
        h("div", { className: "mono", style: { fontSize: 26, fontWeight: 800, lineHeight: 1, color: tone } }, o.grade),
        h("div", { style: { fontSize: 11.5, fontWeight: 650, marginTop: 3 } }, o.label))),

    h("div", { className: "panel-b" },
      // The summary line does the work when the section stays closed.
      h("div", { style: { fontSize: 13.5, lineHeight: 1.55, color: "var(--ink-2)" } },
        "Best served for ", h("b", { style: { color: "var(--ink)" } }, top || "everyday needs"),
        ". ", o.basis, "."),

      h(NeighbourhoodMap, { reraId, maps: data.maps || {} }),

      h("button", {
        className: "btn btn-quiet btn-sm", onClick: () => setOpen(!open),
        style: { marginTop: 13, width: "100%" },
      }, open ? "Hide the full breakdown"
             : `See all ${(data.categories || []).length} categories`),

      open && h("div", { style: { display: "grid", gap: 8, marginTop: 12 } },
        (data.categories || []).map(c => h(CategoryTile, { key: c.key, cat: c, reraId }))),

      open && data.notes && h("div", { className: "faint", style: { fontSize: 11, marginTop: 12, lineHeight: 1.6 } },
        h("div", null, "Distances: ", data.notes.distance),
        h("div", { style: { marginTop: 4 } }, "Ratings: ", data.notes.quality),
        h("div", { style: { marginTop: 4 } }, "Source: ", data.notes.source))
    )
  );
}

window.Neighbourhood = Neighbourhood;
