// ============================================================
// Honest Homes — app shell, routing, theme
// ============================================================
const { useState: useStateA, useEffect: useEffectA } = React;
const Icon_a = window.Icon;

// ---- URL <-> route -----------------------------------------------------------
// The app was pure in-memory state: every screen lived at "/", so the #/verdict/<id>
// links the Share menu hands out opened the homepage, the back button left the site,
// and nothing could be bookmarked or indexed.
function routeToPath(r) {
  if (!r || r.name === "home") return "/";
  if (r.name === "results") return "/search" + (r.q ? "/" + encodeURIComponent(r.q) : "");
  if (r.name === "verdict") return "/verdict/" + encodeURIComponent(r.id);
  if (r.name === "report") return "/report/" + encodeURIComponent(r.id);
  return "/";
}

// Real paths, not #fragments: a fragment never reaches the server, so no verdict
// could be indexed by Google or given its own WhatsApp preview. Legacy #/... links
// already shared are still understood.
function pathToRoute(pathname, hash) {
  let parts = (pathname || "/").split("/").filter(Boolean);
  if (!parts.length && hash) parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  if (!parts.length) return { name: "home" };
  const [what, arg] = parts;
  if (what === "verdict" && arg) return { name: "verdict", id: decodeURIComponent(arg) };
  if (what === "report" && arg) return { name: "report", id: decodeURIComponent(arg) };
  if (what === "search") return { name: "results", q: arg ? decodeURIComponent(arg) : "" };
  return { name: "home" };
}

function App() {
  const [theme, setTheme] = useStateA(() => localStorage.getItem("hh-theme") || "light");
  const [route, setRoute] = useStateA(() => pathToRoute(location.pathname, location.hash));
  const [query, setQuery] = useStateA(() => pathToRoute(location.pathname, location.hash).q || "");
  const [hist, setHist] = useStateA([]);

  // Keep the address bar in step, and honour the browser's back/forward buttons.
  useEffectA(() => {
    const want = routeToPath(route);
    if (location.pathname !== want || location.hash) {
      history.pushState(null, "", want);
    }
  }, [route]);

  useEffectA(() => {
    const onPop = () => {
      const r = pathToRoute(location.pathname, location.hash);
      setRoute(r);
      if (r.name === "results") setQuery(r.q || "");
    };
    window.addEventListener("popstate", onPop);
    window.addEventListener("hashchange", onPop);
    return () => {
      window.removeEventListener("popstate", onPop);
      window.removeEventListener("hashchange", onPop);
    };
  }, []);

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
    results: () => nav({ name: "results", q: query }),
    verdict: (id) => nav({ name: "verdict", id }),
    report: (id) => nav({ name: "report", id }),
    download: (id) => nav({ name: "report", id, print: true }),
    // Prefer the browser's own history so back behaves as the user expects even
    // when they arrived on a deep link.
    back: () => { if (hist.length) { history.back(); } else { setRoute({ name: "results", q: query }); } },
  };
  const onSearch = (q) => { setQuery(q); nav({ name: "results", q }); };

  let screen;
  if (route.name === "home") screen = h(Landing, { go, onSearch });
  else if (route.name === "results") screen = h(Results, { query, go, onSearch });
  else if (route.name === "verdict") screen = h(Verdict, { id: route.id, go });
  else if (route.name === "report") screen = h(Report, { id: route.id, go, print: route.print });

  const chrome = h("div", { className: "chrome" },
    h("div", { className: "brandmark", onClick: go.home },
      h("div", { className: "glyph" }, h(window.LogoMark, { size: 30 })),
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
