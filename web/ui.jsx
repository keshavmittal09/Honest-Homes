// ============================================================
// Honest Homes — UI primitives
// ============================================================
const { useState, useEffect, useRef } = React;
const Icon = window.Icon;

const BAND_LABEL = { green: "Looks clean", amber: "Caution", red: "Serious flags", incomplete: "Incomplete data" };
const BAND_ICON = { green: "shield-check", amber: "calendar-clock", red: "ban", incomplete: "hourglass" };

// ---------- Source tag (the trust signature) ----------
function SourceTag({ source, asOf }) {
  return h("span", { className: "source-tag", title: `Source: ${source} — as of ${asOf}` },
    h(Icon, { name: "shield-check", size: 13, className: "seal" }),
    h("span", null, h("b", null, source)),
    asOf && h("span", { className: "asof" }, "· as of ", asOf)
  );
}

// ---------- Band badge ----------
function BandBadge({ band, label }) {
  return h("span", { className: `badge ${band}` },
    h("span", { className: "dot" }),
    h(Icon, { name: BAND_ICON[band], size: 13 }),
    label || BAND_LABEL[band]
  );
}

function ScoreChip({ score, band }) {
  if (score == null) return h("span", { className: "scorechip incomplete" }, "No score");
  return h("span", { className: `scorechip ${band}` },
    score.toFixed(1), h("span", { className: "out" }, "/10"));
}

// ---------- Project card ----------
function ProjectCard({ p, onOpen }) {
  return h("button", { className: "pcard fade-in", onClick: () => onOpen(p.id) },
    h("div", { className: "pcard-top" },
      h("div", null,
        h("h3", null, p.name),
        h("div", { className: "builder" }, p.builder)
      ),
      h(BandBadge, { band: p.band })
    ),
    h("div", { className: "meta" },
      h("span", { className: "row gap-8" }, h(Icon, { name: "pin", size: 13 }),
        [p.area || p.district, p.locality && p.locality !== p.district ? p.locality : null].filter(Boolean).join(" · ")),
      h("span", { className: "k" }, p.id),
      // distance sits inline; as an absolute overlay it landed on the band badge
      p.distanceKm != null && h("span", { className: "pcard-dist mono" }, p.distanceKm, " km")
    ),
    h("div", { className: "pcard-foot" },
      h("span", { className: "row gap-8 faint", style: { fontSize: 12.5 } },
        h(Icon, { name: "shield-check", size: 13, style: { color: "var(--brand)" } }),
        "MahaRERA"),
      h("div", { className: "row gap-12" },
        h(ScoreChip, { score: p.score, band: p.band }),
        h(Icon, { name: "arrow", size: 16, className: "faint" })
      )
    )
  );
}

// ---------- Trust gauge (animated semicircle) ----------
function polar(cx, cy, r, deg) {
  const a = (deg * Math.PI) / 180;
  return [cx + r * Math.cos(a), cy - r * Math.sin(a)];
}
function arcPath(cx, cy, r, startV, endV) {
  // value 0..10 maps to angle 180..0
  const a0 = 180 - (startV / 10) * 180;
  const a1 = 180 - (endV / 10) * 180;
  const [x0, y0] = polar(cx, cy, r, a0);
  const [x1, y1] = polar(cx, cy, r, a1);
  const large = Math.abs(a1 - a0) > 180 ? 1 : 0;
  return `M ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1}`;
}

function TrustGauge({ score, band, size = 250, animate = true }) {
  const incomplete = score == null;
  const [val, setVal] = useState(animate ? 0 : (score || 0));
  useEffect(() => {
    if (incomplete || !animate) { setVal(score || 0); return; }
    let raf, start;
    const dur = 1100;
    const tick = (t) => {
      if (!start) start = t;
      const k = Math.min(1, (t - start) / dur);
      const eased = 1 - Math.pow(1 - k, 3);
      setVal(score * eased);
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [score, animate]);

  const w = size, hh = size * 0.62;
  const cx = w / 2, cy = size * 0.56, r = size * 0.42, sw = size * 0.078;
  const colorVar = incomplete ? "var(--ink-3)" : `var(--${band})`;

  // Needle: an OUTER pointer only. A full-length needle from the hub was drawn
  // straight through the score numeral (which sits inside the arc), so the digits
  // and the needle overlapped at every size.
  const ndeg = 180 - (val / 10) * 180;
  const [nx0, ny0] = polar(cx, cy, r * 0.66, ndeg);
  const [nx, ny] = polar(cx, cy, r - sw * 0.3, ndeg);

  return h("div", { className: "gauge-wrap" },
    h("svg", { width: w, height: hh + 6, viewBox: `0 0 ${w} ${hh + 6}` },
      // track
      h("path", { d: arcPath(cx, cy, r, 0, 10), fill: "none", stroke: "var(--gauge-track)",
        strokeWidth: sw, strokeLinecap: "round" }),
      // band segments (faint, always visible — shows the scale is fixed/honest)
      !incomplete && h("path", { d: arcPath(cx, cy, r, 0, 4), fill: "none", stroke: "var(--red)",
        strokeWidth: sw, strokeLinecap: "round", opacity: band === "red" ? 1 : .16 }),
      !incomplete && h("path", { d: arcPath(cx, cy, r, 4, 7), fill: "none", stroke: "var(--amber)",
        strokeWidth: sw, strokeLinecap: "butt", opacity: band === "amber" ? 1 : .16 }),
      !incomplete && h("path", { d: arcPath(cx, cy, r, 7, 10), fill: "none", stroke: "var(--green)",
        strokeWidth: sw, strokeLinecap: "round", opacity: band === "green" ? 1 : .16 }),
      incomplete && h("path", { d: arcPath(cx, cy, r, 0, 10), fill: "none", stroke: "var(--ink-3)",
        strokeWidth: sw, strokeLinecap: "round", strokeDasharray: "2 7", opacity: .5 }),
      // needle (outer pointer — never crosses the numeral)
      !incomplete && h("line", { x1: nx0, y1: ny0, x2: nx, y2: ny, stroke: colorVar, strokeWidth: 3, strokeLinecap: "round" }),
    ),
    h("div", { style: { marginTop: -size * 0.30, textAlign: "center" } },
      incomplete
        ? h("div", { className: "gauge-num", style: { fontSize: size * 0.16, color: colorVar } }, "N/A")
        : h("div", null,
            h("span", { className: "gauge-num", style: { fontSize: size * 0.28, color: colorVar } }, val.toFixed(1)),
            h("span", { className: "mono", style: { fontSize: size * 0.085, color: "var(--ink-3)", fontWeight: 600 } }, " /10")
          ),
      h("div", { style: { marginTop: 8 } }, h(BandBadge, { band: incomplete ? "incomplete" : band }))
    )
  );
}

// ---------- Signal row ----------
function ImpactTag({ impact }) {
  if (impact == null) return h("span", { className: "impact zero" }, "—");
  if (impact === 0) return h("span", { className: "impact zero" }, "0");
  const cls = impact > 0 ? "pos" : "neg";
  return h("span", { className: `impact ${cls}` }, (impact > 0 ? "+" : "") + impact.toFixed(1));
}
function SignalRow({ s }) {
  const [open, setOpen] = useState(false);
  return h("div", { className: `signal ${s.kind}` },
    h("div", { className: "ico" }, h(Icon, { name: s.icon, size: 19 })),
    h("div", null,
      h("div", { className: "fact" }, s.fact),
      h("div", { className: "detail" }, s.detail),
      h("div", { className: "src-row" },
        h(SourceTag, { source: s.source, asOf: s.asOf })
      )
    ),
    h(ImpactTag, { impact: s.impact })
  );
}

// ---------- Timeline ----------
function Timeline({ items, band }) {
  const n = (items || []).length;
  if (!n) return h("p", { className: "faint", style: { fontSize: 13 } }, "No dated milestones on record yet.");
  // With a single milestone, i/(n-1) is 0/0 = NaN and the node loses its position
  // entirely. Place a lone node in the middle of the track instead.
  const at = (i) => (n === 1 ? 50 : (i / (n - 1)) * 100);
  // slippage = between first promised and last revised/now
  const promisedIdx = items.findIndex(i => i.type === "promised");
  const lastIdx = n - 1;
  // Edge labels are centred on their node, so anchor the first/last inwards.
  const edge = (i) => (n > 1 && i === 0 ? " edge-start" : n > 1 && i === lastIdx ? " edge-end" : "");
  return h("div", { className: "timeline" },
    h("div", { className: "tl-track" },
      h("div", { className: "tl-fill", style: { width: "100%", background: "var(--gauge-track)" } }),
      (promisedIdx >= 0 && lastIdx > promisedIdx && (items[lastIdx].type === "revised" || items[lastIdx].type === "revoked" || items[lastIdx].type === "now")) &&
        h("div", { className: "tl-slip", style: {
          left: `${at(promisedIdx)}%`,
          width: `${at(lastIdx) - at(promisedIdx)}%`,
        } }, "delay / slippage"),
      items.map((it, i) =>
        h("div", { key: i, className: `tl-node ${it.type}${edge(i)}`, style: { left: `${at(i)}%` } },
          h("div", { className: "lab", style: i % 2 ? { bottom: 34 } : {} }, it.label),
          h("div", { className: "dot" }),
          h("div", { className: "dte" }, it.date)
        )
      )
    )
  );
}

// ---------- Skeleton loading card ----------
function SkeletonCard() {
  const bar = (w, h2) => h("div", { style: { height: h2, width: w, borderRadius: 6, background: "var(--surface-3)" } });
  return h("div", { className: "pcard", style: { pointerEvents: "none" } },
    h("div", { className: "pcard-top" },
      h("div", { className: "stack-10" }, bar("160px", 18), bar("110px", 13)),
      bar("84px", 24)),
    h("div", { style: { marginTop: 16 } }, bar("70%", 13)),
    h("div", { className: "pcard-foot" }, bar("80px", 13), bar("46px", 18))
  );
}

// ---------- Toast (for copy-link feedback etc.) ----------
function useToast() {
  const [msg, setMsg] = useState(null);
  const show = (m) => { setMsg(m); setTimeout(() => setMsg(null), 2200); };
  const node = msg && h("div", { className: "toast fade-in" }, h(Icon, { name: "check", size: 15 }), msg);
  return [node, show];
}

// ============================================================
// Contact / "request a project" config
// ------------------------------------------------------------
// HOW SUBMISSIONS REACH YOU — set ONE of these:
//   • formEndpoint: a Formspree/Tally/Formspark POST URL. When set, the in-app
//     form submits silently to it and you receive each request by email/dashboard.
//     (Recommended — survives Render's ephemeral filesystem.)
//   • If formEndpoint is "", the form falls back to opening the user's email app
//     addressed to `email` with everything pre-filled.
// whatsapp: optional digits-only number (e.g. "9198XXXXXXXX") to also offer a
//   "Chat on WhatsApp" shortcut. Leave "" to hide it.
// These are DEFAULTS only. At startup app.jsx fetches GET /api/config and
// overrides them from the server's env vars (.env locally / Render dashboard in
// prod), so you can change the email, form endpoint or WhatsApp without editing
// code. Kept on window so that runtime override mutates the same object the
// modal reads.
const HH_CONTACT = window.HH_CONTACT || (window.HH_CONTACT = {
  formEndpoint: "",
  email: "29925keshav@gmail.com",
  whatsapp: "",
});

// ---------- Share menu (multi-channel) ----------
function ShareMenu({ url, title, size = "sm" }) {
  const [open, setOpen] = useState(false);
  const [toast, showToast] = useToast();
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const onEsc = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onEsc);
    return () => { document.removeEventListener("mousedown", onDoc); document.removeEventListener("keydown", onEsc); };
  }, [open]);

  const enc = encodeURIComponent;
  const text = title || "The honest verdict on this builder";
  const channels = [
    { key: "whatsapp", label: "WhatsApp", icon: "whatsapp", href: `https://wa.me/?text=${enc(text + " " + url)}` },
    { key: "x",        label: "X (Twitter)", icon: "x-twitter", href: `https://twitter.com/intent/tweet?text=${enc(text)}&url=${enc(url)}` },
    { key: "telegram", label: "Telegram", icon: "telegram", href: `https://t.me/share/url?url=${enc(url)}&text=${enc(text)}` },
    { key: "facebook", label: "Facebook", icon: "facebook", href: `https://www.facebook.com/sharer/sharer.php?u=${enc(url)}` },
    { key: "email",    label: "Email", icon: "mail", href: `mailto:?subject=${enc(text)}&body=${enc(text + "\n\n" + url)}` },
  ];
  const copy = () => {
    const done = () => showToast("Link copied to clipboard");
    if (navigator.clipboard) navigator.clipboard.writeText(url).then(done, done); else done();
    setOpen(false);
  };
  const canNative = typeof navigator !== "undefined" && !!navigator.share;
  const native = () => { navigator.share({ title: text, url }).catch(() => {}); setOpen(false); };

  return h("div", { className: "sharewrap", ref },
    toast,
    h("button", { className: `btn btn-ghost btn-${size}`, onClick: () => setOpen(o => !o),
        "aria-haspopup": "menu", "aria-expanded": open },
      h(Icon, { name: "share", size: 15 }), "Share"),
    open && h("div", { className: "share-menu fade-in", role: "menu" },
      canNative && h("button", { className: "share-item", onClick: native, role: "menuitem" },
        h(Icon, { name: "more", size: 16 }), "Share via apps…"),
      channels.map(c => h("a", { key: c.key, className: "share-item", href: c.href,
          target: "_blank", rel: "noopener", role: "menuitem", onClick: () => setOpen(false) },
        h(Icon, { name: c.icon, size: 16 }), c.label)),
      h("button", { className: "share-item", onClick: copy, role: "menuitem" },
        h(Icon, { name: "copy", size: 16 }), "Copy link")
    )
  );
}

// ---------- Contact modal: request-a-project OR ask-about-a-project ----------
function ContactModal({ onClose, type = "request", projectName = "", projectId = "",
    lockProject = false, prefill = "", heading, intro, requireMessage = false, cta = "Send request" }) {
  const saved = savedLead();
  const [name, setName] = useState(saved.name || "");
  const [contact, setContact] = useState(saved.phone || "");
  const [project, setProject] = useState(lockProject ? projectName : (prefill || ""));
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    const onEsc = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onEsc);
    return () => document.removeEventListener("keydown", onEsc);
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    if (!name.trim() || !contact.trim() || !project.trim()) {
      setErr("Please add your name, your phone, and the project."); return;
    }
    if (requireMessage && !message.trim()) { setErr("Please type your question."); return; }
    setBusy(true);
    try {
      const r = await submitEntry({ type, name: name.trim(), phone: contact.trim(),
        project: project.trim(), projectId, message: message.trim() });
      if (!r.ok) throw new Error("bad");
      try {
        localStorage.setItem("hh-lead", JSON.stringify(
          { name: name.trim(), phone: contact.trim(), ts: Date.now() }));
      } catch (_) {}
      setSent(true);
    } catch (_) {
      setErr("Couldn't send right now — please try again in a moment.");
    }
    setBusy(false);
  };

  const field = (label, node) => h("label", { className: "field" },
    h("span", { className: "field-l" }, label), node);
  const inquiry = type === "inquiry";
  const H = heading || (inquiry ? "Ask about this project" : "Can't find your project?");
  const I = intro || (inquiry
    ? "Ask anything about this project — pricing, availability, documents or possession. We'll get back to you."
    : "Tell us the project or builder you're looking for and we'll add it to our MahaRERA index and follow up.");

  return h("div", { className: "modal-overlay no-print", onMouseDown: onClose },
    h("div", { className: "modal", onMouseDown: e => e.stopPropagation(), role: "dialog", "aria-modal": "true" },
      h("button", { className: "modal-close", onClick: onClose, "aria-label": "Close" }, h(Icon, { name: "close", size: 17 })),
      sent
        ? h("div", { style: { textAlign: "center", padding: "14px 6px 6px" } },
            h("div", { className: "modal-ico ok" }, h(Icon, { name: "check", size: 26 })),
            h("h3", { className: "serif", style: { fontSize: 21, fontWeight: 600, marginTop: 12 } }, "Thanks — we're on it."),
            h("p", { className: "muted", style: { fontSize: 14, marginTop: 8, lineHeight: 1.55 } },
              inquiry ? "We've received your question about " : "We'll look into ",
              h("b", { style: { color: "var(--ink)" } }, project),
              inquiry ? " and will reach out shortly." : " and get back to you."),
            h("button", { className: "btn btn-primary", style: { marginTop: 18 }, onClick: onClose }, "Done"))
        : h("div", null,
            h("div", { className: "row gap-12", style: { alignItems: "flex-start", marginBottom: 4 } },
              h("div", { className: "modal-ico" }, h(Icon, { name: inquiry ? "help" : "message", size: 22 })),
              h("div", null,
                h("h3", { className: "serif", style: { fontSize: 21, fontWeight: 600 } }, H),
                h("p", { className: "muted", style: { fontSize: 13.5, marginTop: 4, lineHeight: 1.5 } }, I))),
            h("form", { onSubmit: submit, className: "modal-form" },
              lockProject
                ? field("Project", h("input", { value: project, readOnly: true, className: "ro" }))
                : field("Project or builder *", h("input", { value: project, onChange: e => setProject(e.target.value), placeholder: "e.g. Lodha Park, Worli" })),
              h("div", { className: "form-2col" },
                field("Your name *", h("input", { value: name, onChange: e => setName(e.target.value),
                  placeholder: "Full name", name: "name", autoComplete: "name" })),
                field("Phone *", h("input", { value: contact, onChange: e => setContact(e.target.value),
                  placeholder: "Mobile number", inputMode: "tel", name: "tel", autoComplete: "tel" }))),
              field(inquiry ? "Your question *" : "Anything else (optional)",
                h("textarea", { value: message, onChange: e => setMessage(e.target.value), rows: 3,
                  placeholder: inquiry ? "e.g. What's the price of a 2BHK? Is possession on track?" : "Location, RERA ID, or what you'd like to know" })),
              err && h("div", { className: "form-err" }, h(Icon, { name: "info", size: 14 }), err),
              h("div", { className: "modal-consent" }, "By submitting, you agree we may contact you about this enquiry. We don't share your number."),
              h("div", { className: "row gap-8", style: { marginTop: 6, justifyContent: "flex-end" } },
                HH_CONTACT.whatsapp && h("a", { className: "btn btn-ghost btn-sm", target: "_blank", rel: "noopener",
                    href: `https://wa.me/${HH_CONTACT.whatsapp}?text=${encodeURIComponent((inquiry ? "Question about " : "Looking for ") + (project || ""))}` },
                  h(Icon, { name: "whatsapp", size: 15 }), "WhatsApp"),
                h("button", { type: "submit", className: "btn btn-primary", disabled: busy },
                  busy ? "Sending…" : h("span", { className: "row gap-8" }, h(Icon, { name: "send", size: 15 }), cta))))
          )
    )
  );
}

// Request a project (global). Opens the contact modal in "request" mode.
function ContactButton({ prefill, label = "Request a project", variant = "btn-ghost", size = "sm", icon = "message" }) {
  const [open, setOpen] = useState(false);
  return h(React.Fragment, null,
    h("button", { className: `btn ${variant} btn-${size}`, onClick: () => setOpen(true) },
      h(Icon, { name: icon, size: 15 }), label),
    open && h(ContactModal, { prefill, onClose: () => setOpen(false) })
  );
}

// Ask a question about a specific project. Opens the modal in "inquiry" mode.
function InquiryButton({ project, label = "Ask about this project", variant = "btn-ghost", size = "sm" }) {
  const [open, setOpen] = useState(false);
  return h(React.Fragment, null,
    h("button", { className: `btn ${variant} btn-${size}`, onClick: () => setOpen(true) },
      h(Icon, { name: "help", size: 15 }), label),
    open && h(ContactModal, { type: "inquiry", lockProject: true, requireMessage: true, cta: "Send question",
      projectName: (project && project.name) || "", projectId: (project && project.id) || "",
      onClose: () => setOpen(false) })
  );
}

// ---------- Unified submission pipeline ----------
// Every user submission (unlock lead, project request, project inquiry) goes
// through here. Posts to your form endpoint (Formspree etc.) when configured —
// durable — else to the backend /api/lead (leads.jsonl + Render logs).
async function submitEntry(entry) {
  const project = entry.project;
  const payload = {
    type: entry.type || "lead",
    name: entry.name || "",
    phone: entry.phone || "",
    project: (project && project.name) || (typeof project === "string" ? project : "") || "",
    projectId: entry.projectId || (project && project.id) || "",
    message: entry.message || "",
    _subject: `Honest Homes — ${entry.type || "lead"}`,
  };
  const useForm = !!HH_CONTACT.formEndpoint;
  return fetch(useForm ? HH_CONTACT.formEndpoint : "/api/lead", {
    method: "POST",
    headers: useForm
      ? { "Content-Type": "application/json", "Accept": "application/json" }
      : { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

async function submitLead({ name, phone, project }) {
  return submitEntry({ type: "unlock", name, phone, project });
}

// Has this visitor already unlocked? (gate once per visitor, not per project)
function hasLead() {
  try { return !!localStorage.getItem("hh-lead"); } catch (_) { return false; }
}

// What this visitor already told us. Reused to prefill every later form — asking
// the same person for their name and number a third time is pure friction.
function savedLead() {
  try { return JSON.parse(localStorage.getItem("hh-lead") || "{}") || {}; }
  catch (_) { return {}; }
}

// ---------- Lead gate (blurs children until name+phone submitted) ----------
function LeadGate({ project, active = true, onUnlock, children }) {
  const saved = savedLead();
  const [name, setName] = useState(saved.name || "");
  const [phone, setPhone] = useState(saved.phone || "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  // Already unlocked this visit — render the content normally, no blur.
  if (!active) return h(React.Fragment, null, children);

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    const digits = phone.replace(/\D/g, "");
    if (!name.trim()) { setErr("Please enter your name."); return; }
    if (digits.length < 10) { setErr("Please enter a valid phone number."); return; }
    setBusy(true);
    try { await submitLead({ name: name.trim(), phone: phone.trim(), project }); } catch (_) {}
    try { localStorage.setItem("hh-lead", JSON.stringify({ name: name.trim(), phone: phone.trim(), ts: Date.now() })); } catch (_) {}
    setBusy(false);
    onUnlock();
  };

  const pname = (project && project.name) || "this project";
  return h("div", { className: "gate-wrap" },
    h("div", { className: "gate-blur", "aria-hidden": true }, children),
    h("div", { className: "gate-overlay" },
      h("div", { className: "gate-card" },
        h("div", { className: "gate-ico" }, h(Icon, { name: "shield-check", size: 26 })),
        h("h3", { className: "serif", style: { fontSize: 22, fontWeight: 600, marginTop: 12 } }, "Unlock the honest verdict"),
        h("p", { className: "muted", style: { fontSize: 13.5, marginTop: 8, lineHeight: 1.5, maxWidth: "40ch", marginInline: "auto" } },
          "Enter your details to see the full MahaRERA trust verdict for ", h("b", { style: { color: "var(--ink)" } }, pname),
          ". It's free — we'll only reach out about this project or important builder updates."),
        h("form", { className: "gate-form", onSubmit: submit },
          h("input", { value: name, onChange: e => setName(e.target.value), placeholder: "Your name",
            "aria-label": "Your name", name: "name", autoComplete: "name" }),
          h("input", { value: phone, onChange: e => setPhone(e.target.value), placeholder: "Phone number",
            inputMode: "tel", "aria-label": "Phone number", name: "tel", autoComplete: "tel" }),
          err && h("div", { className: "form-err", style: { justifyContent: "center" } }, h(Icon, { name: "info", size: 14 }), err),
          h("button", { type: "submit", className: "btn btn-primary btn-lg", disabled: busy, style: { width: "100%", justifyContent: "center" } },
            busy ? "Unlocking…" : h("span", { className: "row gap-8" }, h(Icon, { name: "shield-check", size: 16 }), "Unlock verdict"))),
        h("div", { className: "gate-fine" }, h(Icon, { name: "shield-check", size: 12 }), "We respect your privacy. No spam — unsubscribe anytime.")
      )
    )
  );
}

// ---------- Global footer (consistent CTA on every screen) ----------
function Footer({ go }) {
  return h("footer", { className: "site-footer no-print" },
    h("div", { className: "wrap footer-inner" },
      h("div", { className: "footer-brand" },
        h("div", { className: "brandmark", onClick: go.home, style: { cursor: "pointer" } },
          h("div", { className: "glyph", style: { width: 34, height: 34 } }, h(window.LogoMark, { size: 34 })),
          h("div", { className: "wordmark", style: { fontSize: 17 } }, "Honest", h("span", null, "Homes"))),
        h("p", { className: "faint", style: { fontSize: 12.5, marginTop: 10, maxWidth: "42ch", lineHeight: 1.55 } },
          "Plain-language trust verdicts on Maharashtra builders, sourced from official MahaRERA public records. Information, not legal advice.")),
      h("div", { className: "footer-col" },
        h("div", { className: "footer-h" }, "Explore"),
        h("button", { className: "footer-link", onClick: go.home }, "Search a project"),
        h("button", { className: "footer-link", onClick: go.results }, "Browse all projects")),
      h("div", { className: "footer-col footer-cta" },
        h("div", { className: "footer-h" }, "Missing a project?"),
        h("p", { className: "faint", style: { fontSize: 12.5, lineHeight: 1.5, marginBottom: 12 } },
          "Can't find the project or builder you're checking? Tell us and we'll add it to our index."),
        h(ContactButton, { label: "Request a project", variant: "btn-primary", size: "sm" }))
    ),
    h("div", { className: "wrap footer-base" },
      h("span", { className: "row gap-8" }, h(Icon, { name: "shield-check", size: 13, style: { color: "var(--brand)" } }),
        "Built on official MahaRERA records · Updated monthly"),
      h("span", { className: "faint" }, "© ", new Date().getFullYear(), " Honest Homes"))
  );
}

Object.assign(window, { savedLead, SourceTag, BandBadge, ScoreChip, ProjectCard, TrustGauge, SignalRow, ImpactTag, Timeline, SkeletonCard, useToast, BAND_LABEL, BAND_ICON, ShareMenu, ContactModal, ContactButton, InquiryButton, submitEntry, submitLead, hasLead, LeadGate, Footer });
