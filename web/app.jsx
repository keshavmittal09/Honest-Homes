// ============================================================
// Honest Homes — app shell, routing, theme
// ============================================================
const { useState: useStateA, useEffect: useEffectA } = React;
const Icon_a = window.Icon;

function App() {
  const [theme, setTheme] = useStateA(() => localStorage.getItem("hh-theme") || "light");
  const [route, setRoute] = useStateA({ name: "home" });
  const [query, setQuery] = useStateA("");
  const [hist, setHist] = useStateA([]);

  useEffectA(() => { document.documentElement.setAttribute("data-theme", theme); localStorage.setItem("hh-theme", theme); }, [theme]);

  // Pull public runtime config (contact email / form endpoint / whatsapp) from
  // the backend so it tracks env vars without a code change.
  useEffectA(() => {
    fetch("/api/config").then(r => r.json()).then(c => {
      if (c && c.contact) window.HH_CONTACT = Object.assign(window.HH_CONTACT || {}, c.contact);
    }).catch(() => {});
  }, []);

  // scroll to top on route change
  useEffectA(() => { window.scrollTo(0, 0); }, [route]);

  const nav = (r) => { setHist(hh => [...hh, route]); setRoute(r); };
  const go = {
    home: () => setRoute({ name: "home" }),
    results: () => nav({ name: "results" }),
    verdict: (id) => nav({ name: "verdict", id }),
    report: (id) => nav({ name: "report", id }),
    download: (id) => nav({ name: "report", id, print: true }),
    back: () => { setHist(hh => { if (hh.length) { setRoute(hh[hh.length - 1]); return hh.slice(0, -1); } setRoute({ name: "results" }); return hh; }); },
  };
  const onSearch = (q) => { setQuery(q); nav({ name: "results" }); };

  let screen;
  if (route.name === "home") screen = h(Landing, { go, onSearch });
  else if (route.name === "results") screen = h(Results, { query, go, onSearch });
  else if (route.name === "verdict") screen = h(Verdict, { id: route.id, go });
  else if (route.name === "report") screen = h(Report, { id: route.id, go, print: route.print });

  const chrome = h("div", { className: "chrome" },
    h("div", { className: "brandmark", onClick: go.home },
      h("div", { className: "glyph" }, h(Icon_a, { name: "shield-check", size: 19 })),
      h("div", { className: "wordmark" }, "Honest", h("span", null, "Homes"))),
    h("div", { className: "chrome-spacer" }),
    h("div", { className: "chrome-nav" },
      h("a", { className: route.name === "home" ? "on" : "", onClick: go.home }, "Search"),
      h("a", { className: route.name === "results" ? "on" : "", onClick: go.results }, "Browse")),
    // theme toggle
    h("div", { className: "seg" },
      h("button", { className: theme === "light" ? "on" : "", onClick: () => setTheme("light"), title: "Light" },
        h(Icon_a, { name: "sun", size: 15 })),
      h("button", { className: theme === "dark" ? "on" : "", onClick: () => setTheme("dark"), title: "Dark" },
        h(Icon_a, { name: "moon", size: 15 })))
  );

  return h("div", null, chrome, h("div", { className: "stage" }, screen), h(Footer, { go }));
}

ReactDOM.createRoot(document.getElementById("root")).render(h(App));
