// ============================================================
// Honest Homes — Landing + Results
// All data via window.HH (async). Loading + empty states handled.
// ============================================================
const { useState: useStateS, useEffect: useEffectS } = React;
const Icon_s = window.Icon;

// ---------------- LANDING ----------------
function Landing({ go, onSearch }) {
  const [q, setQ] = useStateS("");
  const [featured, setFeatured] = useStateS(window.HH.showcase);
  const [meta, setMeta] = useStateS(window.HH.meta());

  useEffectS(() => {
    window.HH.featured().then(({ showcase, real, meta }) => {
      setFeatured([...showcase, ...real.slice(0, 5)]);
      setMeta(meta);
    });
  }, []);

  return h("div", null,
    h("section", { className: "wrap hero fade-in" },
      h("span", { className: "tag-pill" },
        h("span", { className: "mini-dot", style: { background: "var(--green)" } }),
        h("span", { className: "mini-dot", style: { background: "var(--amber)", marginLeft: -4 } }),
        h("span", { className: "mini-dot", style: { background: "var(--red)", marginLeft: -4 } }),
        h("span", { style: { marginLeft: 4 } }, "Built on official MahaRERA records")
      ),
      h("h1", { className: "serif" }, "The honest verdict on a builder — ",
        h("span", { style: { color: "var(--brand)" } }, "before you buy.")),
      h("p", { className: "sub" },
        "Type a project or builder name. We pull the official government record — registration, complaints, legal orders, delays — and give you one sourced, plain-language verdict. No listings. No glossy photos. No spin."),

      h("form", { className: "searchbox", onSubmit: (e) => { e.preventDefault(); onSearch(q); } },
        h(Icon_s, { name: "search", size: 21, className: "mag" }),
        h("input", { value: q, onChange: e => setQ(e.target.value),
          "aria-label": "Search projects or builders",
          placeholder: "Try a project or builder name…  e.g. Lodha" }),
        h("button", { type: "submit", className: "btn btn-primary btn-lg" }, "Check it",
          h(Icon_s, { name: "arrow", size: 17 }))
      ),
      h("div", { className: "chips" },
        window.HH.exampleChips.map(c => h("button", { key: c, className: "chip", onClick: () => onSearch(c) }, c))
      ),
      h("div", { className: "creds" },
        h("span", { className: "c" }, h(Icon_s, { name: "shield-check", size: 15, style: { color: "var(--brand)" } }),
          "Sourced from ", h("b", null, "official MahaRERA")),
        h("span", { className: "div" }),
        h("span", { className: "c" }, h("b", null, (meta.indexed || 0).toLocaleString("en-IN")), " projects indexed"),
        h("span", { className: "div" }),
        h("span", { className: "c" }, h(Icon_s, { name: "calendar-check", size: 15 }), "Updated monthly")
      )
    ),

    h(HeroScene, { go, onSearch }),

    // featured grid — never a blank portal
    h("section", { className: "wrap section-pad" },
      h("div", { className: "results-head" },
        h("div", null,
          h("div", { className: "eyebrow" }, "On record"),
          h("h2", { className: "section-title", style: { marginTop: 6 } }, "Projects you can check right now")),
        h("button", { className: "btn btn-ghost btn-sm", onClick: () => onSearch("") },
          "Browse all", h(Icon_s, { name: "arrow", size: 15 }))
      ),
      h("div", { className: "grid grid-4" },
        featured.map(p => h(ProjectCard, { key: p.id, p, onOpen: go.verdict }))
      ),
      h("p", { className: "faint", style: { fontSize: 12.5, marginTop: 18, textAlign: "center" } },
        h(Icon_s, { name: "info", size: 13, style: { verticalAlign: "-2px", marginRight: 5 } }),
        "The first three are illustrative examples of clean, caution and flagged verdicts. The rest are live MahaRERA projects from our index.")
    ),

    // how it works strip
    h("section", { className: "wrap section-pad" },
      h("div", { className: "panel" },
        h("div", { className: "panel-b", style: { padding: "26px 30px" } },
          h("div", { className: "grid grid-3", style: { gap: 28 } },
            [["search", "We read the record", "Registration status, extension certificates, complaints and orders — straight from MahaRERA."],
             ["scale", "We weigh it honestly", "Each fact moves the score up or down with a visible, fixed rule. No opinions, no hidden ranking."],
             ["doc", "You get a sourced verdict", "One plain-language headline, every signal tagged with its source and date, and a report you can share."]
            ].map(([ic, t, d], i) =>
              h("div", { key: i, className: "row gap-16", style: { alignItems: "flex-start" } },
                h("div", { className: "ico", style: { width: 42, height: 42, borderRadius: 11, flex: "none", display: "grid", placeItems: "center", background: "var(--brand-tint)", color: "var(--brand)" } },
                  h(Icon_s, { name: ic, size: 20 })),
                h("div", null,
                  h("div", { style: { fontWeight: 700, fontSize: 15.5 } }, t),
                  h("div", { className: "muted", style: { fontSize: 13.5, marginTop: 4 } }, d))
              )
            )
          )
        )
      )
    )
  );
}

// ---------------- RESULTS / BROWSE ----------------
function Results({ query, go, onSearch }) {
  const [filter, setFilter] = useStateS("all");
  const [list, setList] = useStateS([]);
  const [loading, setLoading] = useStateS(true);
  const [loadingMore, setLoadingMore] = useStateS(false);
  const [total, setTotal] = useStateS(0);
  const [nextOffset, setNextOffset] = useStateS(0);
  const [hasMore, setHasMore] = useStateS(false);
  const [localQ, setLocalQ] = useStateS(query || "");

  useEffectS(() => { setLocalQ(query || ""); }, [query]);

  // initial / new-query load (resets the list)
  useEffectS(() => {
    let alive = true;
    setLoading(true); setFilter("all");
    window.HH.search(query || "", 0).then(res => {
      if (!alive) return;
      setList(res.cards); setTotal(res.total);
      setNextOffset(res.nextOffset); setHasMore(res.hasMore); setLoading(false);
    });
    return () => { alive = false; };
  }, [query]);

  const loadMore = () => {
    setLoadingMore(true);
    window.HH.search(query || "", nextOffset).then(res => {
      setList(prev => prev.concat(res.cards));
      setNextOffset(res.nextOffset); setHasMore(res.hasMore); setLoadingMore(false);
    });
  };

  const filtered = filter === "all" ? list : list.filter(p => p.band === filter);
  const counts = list.reduce((a, p) => { a[p.band] = (a[p.band] || 0) + 1; return a; }, {});

  return h("div", { className: "wrap fade-in", style: { paddingTop: 30, paddingBottom: 60 } },
    h("button", { className: "btn btn-quiet btn-sm", onClick: go.home, style: { marginBottom: 14 } },
      h(Icon_s, { name: "back", size: 15 }), "Home"),

    h("form", { className: "searchbox", style: { margin: "0 0 22px", maxWidth: 560 },
        onSubmit: e => { e.preventDefault(); onSearch(localQ); } },
      h(Icon_s, { name: "search", size: 19, className: "mag" }),
      h("input", { value: localQ, onChange: e => setLocalQ(e.target.value),
        "aria-label": "Refine search", placeholder: "Search projects or builders…" }),
      h("button", { type: "submit", className: "btn btn-primary btn-sm" }, "Search")
    ),

    h("div", { className: "results-head" },
      h("div", null,
        h("div", { className: "eyebrow" }, (query && query.trim()) ? `Results for "${query}"` : "All indexed projects"),
        h("h1", { className: "section-title", style: { marginTop: 6, fontSize: 30 } },
          loading ? "Searching…"
            : `${total.toLocaleString("en-IN")} project${total === 1 ? "" : "s"} on record`),
        !loading && filter === "all" && list.length < total &&
          h("div", { className: "faint", style: { fontSize: 12.5, marginTop: 4 } },
            `Showing ${list.length.toLocaleString("en-IN")} — scroll down to load more`)),
      h("div", { className: "filterbar" },
        [["all", "All"], ["green", "Clean"], ["amber", "Caution"], ["red", "Flagged"], ["incomplete", "Incomplete"]].map(([k, l]) => {
          const n = k === "all" ? list.length : (counts[k] || 0);
          return h("button", { key: k, className: "chip",
            onClick: () => setFilter(k),
            style: filter === k ? { background: "var(--brand)", color: "var(--on-brand)", borderColor: "var(--brand)" } : {} },
            k !== "all" && k !== "incomplete" && h("span", { style: { width: 7, height: 7, borderRadius: "50%", background: `var(--${k})`, display: "inline-block", marginRight: 6 } }),
            l, h("span", { style: { opacity: .6, marginLeft: 6, fontFamily: "var(--mono)", fontSize: 11 } }, n));
        })
      )
    ),

    loading
      ? h("div", { className: "grid grid-3" }, [0,1,2,3,4,5].map(i => h(SkeletonCard, { key: i })))
      : filtered.length
        ? h("div", null,
            h("div", { className: "grid grid-3" }, filtered.map(p => h(ProjectCard, { key: p.id, p, onOpen: go.verdict }))),
            // Load more only makes sense on the unfiltered list (filter is client-side on loaded rows)
            filter === "all" && hasMore && h("div", { style: { textAlign: "center", marginTop: 26 } },
              h("button", { className: "btn btn-ghost", onClick: loadMore, disabled: loadingMore },
                loadingMore ? "Loading…" : h("span", { className: "row gap-8" }, "Load more projects", h(Icon_s, { name: "arrow", size: 15 })))),
            filter !== "all" && hasMore && h("p", { className: "faint", style: { fontSize: 12.5, textAlign: "center", marginTop: 20 } },
              `Filtering the ${list.length} projects loaded so far. Switch to “All” and load more to filter the full set.`))
        : h(EmptyState, { query, filter, onClear: () => setFilter("all") })
  );
}

function EmptyState({ query, filter, onClear }) {
  return h("div", { className: "panel", style: { padding: "48px 30px", textAlign: "center" } },
    h("div", { style: { width: 54, height: 54, borderRadius: 14, margin: "0 auto 16px", display: "grid", placeItems: "center", background: "var(--surface-3)", color: "var(--ink-3)" } },
      h(Icon_s, { name: "search", size: 24 })),
    h("div", { className: "serif", style: { fontSize: 20, fontWeight: 600 } },
      filter !== "all" ? `No ${filter} projects in these results` : `No matches for “${query}”`),
    h("p", { className: "muted", style: { fontSize: 14, marginTop: 8, maxWidth: "52ch", marginInline: "auto" } },
      filter !== "all"
        ? "Try clearing the filter, or search a different name. Our index covers ~44,000 of Maharashtra's RERA projects."
        : "Our index covers ~44,000 MahaRERA projects. Try a builder name (e.g. Lodha, Godrej) or a district."),
    filter !== "all" && h("button", { className: "btn btn-ghost btn-sm", style: { marginTop: 16 }, onClick: onClear }, "Clear filter")
  );
}

Object.assign(window, { Landing, Results, EmptyState });
