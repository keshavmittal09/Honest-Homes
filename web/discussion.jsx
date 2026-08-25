// ============================================================
// Honest Homes — What buyers say
// ============================================================
// The counterpart to the verdict: the record says what was filed, this says what
// happened. Deliberately styled apart from the sourced sections — a tinted panel
// with its own header — because the page's whole credibility rests on a reader
// never confusing "MahaRERA recorded this" with "someone typed this".
//
// Posting reuses the lead-gate identity, so there is no second sign-up. Only a
// first name and initial are ever shown.

const { useState: useStateD, useEffect: useEffectD } = React;

const REL_TONE = {
  resident: "var(--green)", buyer: "var(--brand)",
  considering: "var(--ink-3)", visited: "var(--ink-3)", other: "var(--ink-3)",
};

function timeAgo(iso) {
  if (!iso) return "";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  if (s < 2592000) return `${Math.round(s / 86400)} d ago`;
  return new Date(iso).toLocaleDateString("en-IN", { month: "short", year: "numeric" });
}

function Post({ post, prompts, onReport }) {
  const [reported, setReported] = useStateD(false);
  const prompt = (prompts || []).find(p => p.key === post.prompt);
  const relLabel = { resident: "Lives here", buyer: "Booked a unit",
    considering: "Considering buying", visited: "Visited the site", other: "" }[post.relation];

  return h("div", { style: { padding: "14px 0", borderTop: "1px solid var(--line)" } },
    h("div", { className: "row", style: { justifyContent: "space-between", gap: 10, alignItems: "baseline" } },
      h("div", { className: "row gap-8", style: { minWidth: 0, flexWrap: "wrap" } },
        h("span", { style: { fontWeight: 650, fontSize: 13.5 } }, post.author || "A buyer"),
        relLabel && h("span", { className: "chip", style: { fontSize: 10.5, padding: "1px 8px", color: REL_TONE[post.relation], fontWeight: 700 } }, relLabel)),
      h("span", { className: "faint", style: { fontSize: 11.5, flex: "none" } }, timeAgo(post.created_at))),

    prompt && h("div", { className: "faint", style: { fontSize: 11.5, marginTop: 4, fontStyle: "italic" } },
      prompt.ask),

    h("div", { style: { fontSize: 13.5, lineHeight: 1.6, marginTop: 7, whiteSpace: "pre-wrap", color: "var(--ink-2)" } },
      post.body),

    h("button", {
      className: "btn btn-quiet btn-sm",
      style: { marginTop: 8, fontSize: 11, padding: "3px 9px" },
      disabled: reported,
      onClick: () => { setReported(true); onReport(post.id); },
    }, reported ? "Reported — thank you" : "Report")
  );
}

function PostBox({ reraId, prompts, relations, onPosted }) {
  const lead = (() => { try { return JSON.parse(localStorage.getItem("hh-lead") || "null"); } catch { return null; } })();
  const [prompt, setPrompt] = useStateD("possession");
  const [relation, setRelation] = useStateD("resident");
  const [body, setBody] = useStateD("");
  const [busy, setBusy] = useStateD(false);
  const [msg, setMsg] = useStateD("");
  const active = (prompts || []).find(p => p.key === prompt);

  if (!lead || !lead.phone) {
    return h("div", { style: { padding: "14px 16px", borderRadius: 10, background: "var(--surface-2)", fontSize: 13, lineHeight: 1.55 } },
      "Unlock the report above to join the discussion — it uses the same name and number, so there is nothing extra to fill in.");
  }

  async function submit(e) {
    e.preventDefault();
    if (body.trim().length < 20) { setMsg("A little more detail — at least 20 characters."); return; }
    setBusy(true); setMsg("");
    const res = await window.HH.postDiscussion({
      projectId: reraId, prompt, relation, body,
      name: lead.name, phone: lead.phone,
    });
    setBusy(false);
    if (!res || !res.ok) { setMsg("Could not post that. Please try again."); return; }
    setBody("");
    setMsg(res.removed && res.removed.length
      ? `Posted — we removed ${res.removed.join(" and ")} from it. Contact details stay off public posts.`
      : "Posted — thank you, this helps the next buyer.");
    onPosted();
  }

  return h("form", { onSubmit: submit, style: { marginTop: 4 } },
    h("div", { className: "row gap-8", style: { flexWrap: "wrap", marginBottom: 9 } },
      (prompts || []).map(p => h("button", {
        key: p.key, type: "button", className: "chip",
        onClick: () => setPrompt(p.key),
        style: { fontSize: 11.5, cursor: "pointer", border: "none",
          background: prompt === p.key ? "var(--ink)" : "var(--surface-2)",
          color: prompt === p.key ? "var(--paper)" : "var(--ink-2)",
          fontWeight: prompt === p.key ? 700 : 500 },
      }, p.label))),

    active && h("div", { className: "faint", style: { fontSize: 12, marginBottom: 7 } }, active.ask),

    h("textarea", {
      value: body, onChange: e => setBody(e.target.value), rows: 4, maxLength: 2000,
      placeholder: "What actually happened? Specifics help — dates, what was promised, what was delivered.",
      style: { width: "100%", padding: "11px 13px", borderRadius: 10, border: "1px solid var(--line)", background: "var(--surface)", color: "var(--ink)", font: "inherit", fontSize: 13.5, lineHeight: 1.55, resize: "vertical" },
    }),

    h("div", { className: "row", style: { justifyContent: "space-between", gap: 10, marginTop: 9, flexWrap: "wrap" } },
      h("div", { className: "row gap-8", style: { flexWrap: "wrap" } },
        h("span", { className: "faint", style: { fontSize: 11.5, alignSelf: "center" } }, "You are:"),
        (relations || []).map(r => h("button", {
          key: r.key, type: "button", className: "chip",
          onClick: () => setRelation(r.key),
          style: { fontSize: 11, cursor: "pointer", border: "none",
            background: relation === r.key ? "var(--brand)" : "var(--surface-2)",
            color: relation === r.key ? "var(--on-brand)" : "var(--ink-2)" },
        }, r.label))),
      h("button", { type: "submit", className: "btn btn-primary btn-sm", disabled: busy },
        busy ? "Posting…" : "Post")),

    msg && h("div", { className: "faint", style: { fontSize: 12, marginTop: 8 } }, msg),

    h("div", { className: "faint", style: { fontSize: 11, marginTop: 8, lineHeight: 1.55 } },
      "Posted as ", h("b", null, (lead.name || "").split(" ")[0]),
      " — your number is never shown. Keep it to what you saw yourself; ",
      "phone numbers, emails and links are stripped automatically.")
  );
}

function Discussion({ reraId }) {
  const [posts, setPosts] = useStateD(null);
  const [meta, setMeta] = useStateD({ prompts: [], relations: [] });

  function load() {
    window.HH.discussion(reraId).then(d => setPosts(d.posts || []));
  }
  useEffectD(() => {
    let alive = true;
    window.HH.discussionPrompts().then(m => { if (alive) setMeta(m); });
    window.HH.discussion(reraId).then(d => { if (alive) setPosts(d.posts || []); });
    return () => { alive = false; };
  }, [reraId]);

  const report = (id) => window.HH.reportDiscussion(id, "flagged by a reader");

  return h("div", { className: "panel", style: { marginTop: 16, background: "var(--surface-2)" } },
    h("div", { className: "panel-h" },
      h("div", { style: { minWidth: 0 } },
        h("h2", null, "What buyers say"),
        h("div", { className: "faint", style: { fontSize: 12.5, marginTop: 3, lineHeight: 1.5 } },
          "Unverified accounts from visitors — ",
          h("b", null, "not part of the MahaRERA record"),
          " and not checked by us. Useful, but weigh it against the sourced sections above.")),
      posts && posts.length > 0 && h("div", { style: { textAlign: "right", flex: "none" } },
        h("div", { className: "mono", style: { fontSize: 22, fontWeight: 800, lineHeight: 1 } }, posts.length),
        h("div", { className: "faint", style: { fontSize: 11 } }, posts.length === 1 ? "post" : "posts"))),

    h("div", { className: "panel-b" },
      h(PostBox, { reraId, prompts: meta.prompts, relations: meta.relations, onPosted: load }),

      posts === null
        ? h("div", { className: "faint", style: { fontSize: 12.5, marginTop: 14 } }, "Loading…")
        : posts.length === 0
          ? h("div", { className: "faint", style: { fontSize: 13, marginTop: 16, lineHeight: 1.55 } },
              "No one has posted about this project yet. If you have visited, booked or live here, "
              + "you would be the first — and the most useful.")
          : h("div", { style: { marginTop: 10 } },
              posts.map(p => h(Post, { key: p.id || p.created_at, post: p, prompts: meta.prompts, onReport: report })))
    )
  );
}

window.Discussion = Discussion;
