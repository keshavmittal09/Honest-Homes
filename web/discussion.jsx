// ============================================================
// Honest Homes — What buyers say
// ============================================================
// The counterpart to the verdict: the record says what was filed, this says what
// happened. Deliberately styled apart from the sourced sections — a tinted panel
// with its own header — because the page's whole credibility rests on a reader
// never confusing "MahaRERA recorded this" with "someone typed this".
//
// Threaded, because the useful part of a property forum is the follow-up: one
// buyer says possession slipped, another asks by how long, the first answers.
// Nesting stops at three levels — deeper than that is unreadable on a phone and
// the exchange has almost always finished by then anyway.

const { useState: useStateD, useEffect: useEffectD } = React;

const REL_LABEL = {
  resident: "Lives here", buyer: "Booked a unit",
  considering: "Considering buying", visited: "Visited the site", other: "",
};
const REL_TONE = {
  resident: "var(--green)", buyer: "var(--brand)",
  considering: "var(--ink-3)", visited: "var(--ink-3)", other: "var(--ink-3)",
};

function timeAgo(iso) {
  if (!iso) return "";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  if (s < 2592000) return `${Math.round(s / 86400)} d ago`;
  return new Date(iso).toLocaleDateString("en-IN", { month: "short", year: "numeric" });
}

function countReplies(p) {
  return (p.replies || []).reduce((n, r) => n + 1 + countReplies(r), 0);
}

// ---- one post and everything under it --------------------------------------
function Post({ post, prompts, reraId, onChanged, hasLead, depth = 1 }) {
  const [replying, setReplying] = useStateD(false);
  const [collapsed, setCollapsed] = useStateD(false);
  const [reported, setReported] = useStateD(false);
  const prompt = (prompts || []).find(p => p.key === post.prompt);
  const kids = post.replies || [];
  const n = countReplies(post);

  return h("div", { style: depth > 1 ? {
      // The rule is the thread line. Indent shrinks with depth so a three-deep
      // exchange still has room to breathe on a 390px screen.
      marginLeft: depth === 2 ? 14 : 10,
      paddingLeft: depth === 2 ? 14 : 10,
      borderLeft: "2px solid var(--line)",
    } : {} },

    h("div", { style: { padding: depth > 1 ? "10px 0" : "14px 0",
                        borderTop: depth > 1 ? "none" : "1px solid var(--line)" } },
      h("div", { className: "row", style: { justifyContent: "space-between", gap: 10, alignItems: "baseline" } },
        h("div", { className: "row gap-8", style: { minWidth: 0, flexWrap: "wrap" } },
          h("span", { style: { fontWeight: 650, fontSize: 13.5 } }, post.author || "A buyer"),
          REL_LABEL[post.relation] && h("span", { className: "chip",
            style: { fontSize: 10.5, padding: "1px 8px", color: REL_TONE[post.relation], fontWeight: 700 } },
            REL_LABEL[post.relation])),
        h("span", { className: "faint", style: { fontSize: 11.5, flex: "none" } }, timeAgo(post.created_at))),

      depth === 1 && prompt && h("div", { className: "faint",
        style: { fontSize: 11.5, marginTop: 4, fontStyle: "italic" } }, prompt.ask),

      !collapsed && h("div", { style: { fontSize: 13.5, lineHeight: 1.6, marginTop: 7,
        whiteSpace: "pre-wrap", color: "var(--ink-2)" } }, post.body),

      h("div", { className: "row gap-8", style: { marginTop: 8, flexWrap: "wrap" } },
        hasLead && h("button", { className: "btn btn-quiet btn-sm",
          style: { fontSize: 11, padding: "3px 9px" },
          onClick: () => setReplying(r => !r) }, replying ? "Cancel" : "Reply"),
        n > 0 && h("button", { className: "btn btn-quiet btn-sm",
          style: { fontSize: 11, padding: "3px 9px" },
          onClick: () => setCollapsed(c => !c) },
          collapsed ? `Show ${n} ${n === 1 ? "reply" : "replies"}` : "Hide replies"),
        h("button", { className: "btn btn-quiet btn-sm",
          style: { fontSize: 11, padding: "3px 9px" }, disabled: reported,
          onClick: () => { setReported(true); window.HH.reportDiscussion(post.id, "flagged by a reader"); } },
          reported ? "Reported" : "Report")),

      replying && h("div", { style: { marginTop: 10 } },
        h(PostBox, { reraId, prompts, parentId: post.id, compact: true,
          onPosted: () => { setReplying(false); onChanged(); } }))),

    !collapsed && kids.map(k => h(Post, {
      key: k.id, post: k, prompts, reraId, onChanged, hasLead,
      depth: Math.min(depth + 1, 3),
    }))
  );
}

// ---- the box, used for both a new thread and a reply ------------------------
function PostBox({ reraId, prompts, relations, parentId, compact, onPosted }) {
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
      projectId: reraId, prompt, relation, body, parentId: parentId || null,
      name: lead.name, phone: lead.phone,
    });
    setBusy(false);
    if (!res || !res.ok) { setMsg((res && res.error) || "Could not post that. Please try again."); return; }
    setBody("");
    if (res.removed && res.removed.length) {
      setMsg(`Posted — we removed ${res.removed.join(" and ")}. Contact details stay off public posts.`);
    }
    onPosted();
  }

  return h("form", { onSubmit: submit, style: { marginTop: compact ? 0 : 4 } },
    // A reply inherits its thread's question, so the prompt chips only appear
    // when starting a new one.
    !compact && h("div", { className: "row gap-8", style: { flexWrap: "wrap", marginBottom: 9 } },
      (prompts || []).map(p => h("button", {
        key: p.key, type: "button", className: "chip",
        onClick: () => setPrompt(p.key),
        style: { fontSize: 11.5, cursor: "pointer", border: "none",
          background: prompt === p.key ? "var(--ink)" : "var(--surface-2)",
          color: prompt === p.key ? "var(--paper)" : "var(--ink-2)",
          fontWeight: prompt === p.key ? 700 : 500 },
      }, p.label))),

    !compact && active && h("div", { className: "faint", style: { fontSize: 12, marginBottom: 7 } }, active.ask),

    h("textarea", {
      value: body, onChange: e => setBody(e.target.value), rows: compact ? 3 : 4, maxLength: 2000,
      autoFocus: !!compact,
      placeholder: compact ? "Reply…"
        : "What actually happened? Specifics help — dates, what was promised, what was delivered.",
      style: { width: "100%", padding: "11px 13px", borderRadius: 10, border: "1px solid var(--line)",
        background: "var(--surface)", color: "var(--ink)", font: "inherit", fontSize: 13.5,
        lineHeight: 1.55, resize: "vertical" },
    }),

    h("div", { className: "row", style: { justifyContent: "space-between", gap: 10, marginTop: 9, flexWrap: "wrap" } },
      !compact
        ? h("div", { className: "row gap-8", style: { flexWrap: "wrap" } },
            h("span", { className: "faint", style: { fontSize: 11.5, alignSelf: "center" } }, "You are:"),
            (relations || []).map(r => h("button", {
              key: r.key, type: "button", className: "chip",
              onClick: () => setRelation(r.key),
              style: { fontSize: 11, cursor: "pointer", border: "none",
                background: relation === r.key ? "var(--brand)" : "var(--surface-2)",
                color: relation === r.key ? "var(--on-brand)" : "var(--ink-2)" },
            }, r.label)))
        : h("span"),
      h("button", { type: "submit", className: "btn btn-primary btn-sm", disabled: busy },
        busy ? "Posting…" : (compact ? "Reply" : "Post"))),

    msg && h("div", { className: "faint", style: { fontSize: 12, marginTop: 8 } }, msg),

    !compact && h("div", { className: "faint", style: { fontSize: 11, marginTop: 8, lineHeight: 1.55 } },
      "Posted as ", h("b", null, (lead.name || "").split(" ")[0]),
      " — your number is never shown. Keep it to what you saw yourself; ",
      "phone numbers, emails and links are stripped automatically.")
  );
}

function Discussion({ reraId }) {
  const [threads, setThreads] = useStateD(null);
  const [meta, setMeta] = useStateD({ prompts: [], relations: [] });
  const hasLead = (() => { try { return !!JSON.parse(localStorage.getItem("hh-lead") || "null"); } catch { return false; } })();

  function load() { window.HH.discussion(reraId).then(d => setThreads(d.posts || [])); }
  useEffectD(() => {
    let alive = true;
    window.HH.discussionPrompts().then(m => { if (alive) setMeta(m); });
    window.HH.discussion(reraId).then(d => { if (alive) setThreads(d.posts || []); });
    return () => { alive = false; };
  }, [reraId]);

  const total = (threads || []).reduce((n, t) => n + 1 + countReplies(t), 0);

  return h("div", { className: "panel", style: { marginTop: 16, background: "var(--surface-2)" } },
    h("div", { className: "panel-h" },
      h("div", { style: { minWidth: 0 } },
        h("h2", null, "What buyers say"),
        h("div", { className: "faint", style: { fontSize: 12.5, marginTop: 3, lineHeight: 1.5 } },
          "Unverified accounts from visitors — ",
          h("b", null, "not part of the MahaRERA record"),
          " and not checked by us. Useful, but weigh it against the sourced sections above.")),
      total > 0 && h("div", { style: { textAlign: "right", flex: "none" } },
        h("div", { className: "mono", style: { fontSize: 22, fontWeight: 800, lineHeight: 1 } }, total),
        h("div", { className: "faint", style: { fontSize: 11 } }, total === 1 ? "post" : "posts"))),

    h("div", { className: "panel-b" },
      h(PostBox, { reraId, prompts: meta.prompts, relations: meta.relations, onPosted: load }),

      threads === null
        ? h("div", { className: "faint", style: { fontSize: 12.5, marginTop: 14 } }, "Loading…")
        : threads.length === 0
          ? h("div", { className: "faint", style: { fontSize: 13, marginTop: 16, lineHeight: 1.55 } },
              "No one has posted about this project yet. If you have visited, booked or live here, "
              + "you would be the first — and the most useful.")
          : h("div", { style: { marginTop: 10 } },
              threads.map(t => h(Post, { key: t.id, post: t, prompts: meta.prompts,
                reraId, onChanged: load, hasLead })))
    )
  );
}

window.Discussion = Discussion;


// ============================================================
// Landing-page strip: the newest posts across every project
// ============================================================
// Renders nothing at all when there are no posts. An empty "What buyers are
// saying" heading on a landing page advertises that nobody is saying anything,
// which is worse than not asking the question.

function RecentDiscussion({ go }) {
  const [posts, setPosts] = useStateD(null);
  useEffectD(() => {
    let alive = true;
    window.HH.recentDiscussion(6).then(d => { if (alive) setPosts(d.posts || []); });
    return () => { alive = false; };
  }, []);

  if (!posts || !posts.length) return null;

  return h("section", { className: "wrap section-pad" },
    h("div", { className: "results-head" },
      h("div", null,
        h("div", { className: "eyebrow" }, "From buyers"),
        h("h2", { className: "section-title", style: { marginTop: 6 } }, "What buyers are saying")),
      h("span", { className: "faint", style: { fontSize: 12.5, maxWidth: "42ch", textAlign: "right" } },
        "Unverified accounts from visitors, not the MahaRERA record")),

    // auto-FILL, not auto-fit: the shared .grid-3 collapses its empty tracks,
    // which stretches a single post across the whole page and makes one comment
    // look like a banner. Empty tracks are kept here so early posts sit at a
    // normal card width while the section fills up.
    h("div", { className: "grid",
      style: { gridTemplateColumns: "repeat(auto-fill, minmax(268px, 1fr))" } },
      posts.map(p => h("button", {
        key: p.id,
        className: "panel",
        onClick: () => go.verdict(p.rera_id),
        style: { textAlign: "left", cursor: "pointer", border: "1px solid var(--line)",
                 background: "var(--surface)", padding: 0, font: "inherit" },
      },
        h("div", { className: "panel-b", style: { padding: "16px 18px" } },
          h("div", { className: "row gap-8", style: { flexWrap: "wrap", marginBottom: 8 } },
            h("span", { style: { fontWeight: 650, fontSize: 13 } }, p.author || "A buyer"),
            REL_LABEL[p.relation] && h("span", { className: "chip",
              style: { fontSize: 10, padding: "1px 7px", color: REL_TONE[p.relation], fontWeight: 700 } },
              REL_LABEL[p.relation]),
            h("span", { className: "faint", style: { fontSize: 11, marginLeft: "auto" } },
              timeAgo(p.created_at))),

          h("div", { style: { fontSize: 13, lineHeight: 1.55, color: "var(--ink-2)",
              display: "-webkit-box", WebkitLineClamp: 4, WebkitBoxOrient: "vertical",
              overflow: "hidden" } }, p.body),

          h("div", { style: { marginTop: 10, paddingTop: 9, borderTop: "1px solid var(--line)" } },
            h("div", { style: { fontWeight: 650, fontSize: 12.5, color: "var(--brand)",
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } },
              p.projectName || p.rera_id),
            p.district && h("div", { className: "faint", style: { fontSize: 11, marginTop: 2 } }, p.district)))
      ))
    )
  );
}

window.RecentDiscussion = RecentDiscussion;
