// ============================================================
// Honest Homes — app shell, routing, theme + device toggles
// ============================================================
const { useState: useStateA, useEffect: useEffectA } = React;
const Icon_a = window.Icon;

function App() {
  const [theme, setTheme] = useStateA(() => localStorage.getItem("hh-theme") || "light");
  const [device, setDevice] = useStateA(() => localStorage.getItem("hh-device") || "desktop");
  const [route, setRoute] = useStateA({ name: "home" });
  const [query, setQuery] = useStateA("");
  const [hist, setHist] = useStateA([]);

  useEffectA(() => { document.documentElement.setAttribute("data-theme", theme); localStorage.setItem("hh-theme", theme); }, [theme]);
  useEffectA(() => { localStorage.setItem("hh-device", device); }, [device]);

  // scroll the scroll-container to top on route change
  useEffectA(() => {
    const el = device === "mobile" ? document.querySelector(".device .screen") : window;
    if (el) el.scrollTo ? el.scrollTo(0, 0) : (el.scrollTop = 0);
  }, [route, device]);

  const nav = (r) => { setHist(hh => [...hh, route]); setRoute(r); };
  const go = {
    home: () => setRoute({ name: "home" }),
    results: () => nav({ name: "results" }),
    verdict: (id) => nav({ name: "verdict", id }),
    report: (id) => nav({ name: "report", id }),
    ds: () => nav({ name: "ds" }),
    back: () => { setHist(hh => { if (hh.length) { setRoute(hh[hh.length - 1]); return hh.slice(0, -1); } setRoute({ name: "results" }); return hh; }); },
  };
  const onSearch = (q) => { setQuery(q); nav({ name: "results" }); };

  let screen;
  if (route.name === "home") screen = h(Landing, { go, onSearch });
  else if (route.name === "results") screen = h(Results, { query, go, onSearch });
  else if (route.name === "verdict") screen = h(Verdict, { id: route.id, go });
  else if (route.name === "report") screen = h(Report, { id: route.id, go });
  else if (route.name === "ds") screen = h(DesignSystem, { go });

  const chrome = h("div", { className: "chrome" },
    h("div", { className: "brandmark", onClick: go.home },
      h("div", { className: "glyph" }, h(Icon_a, { name: "shield-check", size: 19 })),
      h("div", { className: "wordmark" }, "Honest", h("span", null, "Homes"))),
    h("div", { className: "chrome-spacer" }),
    h("div", { className: "chrome-nav", style: device === "mobile" ? { display: "none" } : {} },
      h("a", { className: route.name === "home" ? "on" : "", onClick: go.home }, "Search"),
      h("a", { className: route.name === "results" ? "on" : "", onClick: go.results }, "Browse"),
      h("a", { className: route.name === "ds" ? "on" : "", onClick: go.ds }, "Design system")),
    // device toggle
    h("div", { className: "seg" },
      h("button", { className: device === "desktop" ? "on" : "", onClick: () => setDevice("desktop"), title: "Desktop" },
        h(Icon_a, { name: "monitor", size: 15 })),
      h("button", { className: device === "mobile" ? "on" : "", onClick: () => setDevice("mobile"), title: "Mobile" },
        h(Icon_a, { name: "phone", size: 15 }))),
    // theme toggle
    h("div", { className: "seg" },
      h("button", { className: theme === "light" ? "on" : "", onClick: () => setTheme("light"), title: "Light" },
        h(Icon_a, { name: "sun", size: 15 })),
      h("button", { className: theme === "dark" ? "on" : "", onClick: () => setTheme("dark"), title: "Dark" },
        h(Icon_a, { name: "moon", size: 15 })))
  );

  if (device === "mobile") {
    return h("div", null, chrome,
      h("div", { className: "stage mobile" },
        h("div", { className: "device" },
          h("div", { className: "screen" },
            h("div", { className: "notch" }),
            // compact in-device top bar
            h("div", { style: { position: "sticky", top: 0, zIndex: 40, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 16px 10px", paddingTop: 44, background: "color-mix(in srgb, var(--surface) 90%, transparent)", backdropFilter: "blur(10px)", borderBottom: "1px solid var(--line)" } },
              h("div", { className: "brandmark", onClick: go.home },
                h("div", { className: "glyph", style: { width: 26, height: 26 } }, h(Icon_a, { name: "shield-check", size: 15 })),
                h("div", { className: "wordmark", style: { fontSize: 16 } }, "Honest", h("span", null, "Homes"))),
              route.name !== "home" && h("button", { className: "btn btn-quiet btn-sm", onClick: go.back }, h(Icon_a, { name: "back", size: 15 }))),
            screen
          )))
    );
  }

  return h("div", null, chrome, h("div", { className: "stage" }, screen));
}

ReactDOM.createRoot(document.getElementById("root")).render(h(App));
