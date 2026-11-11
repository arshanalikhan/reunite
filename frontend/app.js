/* Reunite frontend - React 18 + htm (no build step needed). */
const { useState, useEffect, useRef, useCallback } = React;
const html = htm.bind(React.createElement);

// ------------------------------------------------------------------ api
const auth = {
  get() { try { return JSON.parse(sessionStorage.getItem("reunite_staff") || "null"); } catch { return null; } },
  set(v) { try { v ? sessionStorage.setItem("reunite_staff", JSON.stringify(v)) : sessionStorage.removeItem("reunite_staff"); } catch {} },
};

async function api(path, opts = {}) {
  const s = auth.get();
  const headers = { ...(opts.headers || {}) };
  if (s) headers["X-Staff-Token"] = s.token;
  if (opts.json) { headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(opts.json); }
  const res = await fetch(path, { ...opts, headers });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && s) { auth.set(null); location.hash = "#staff"; location.reload(); }
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}
const photoUrl = (name) => name ? `/api/photos/${name}?t=${encodeURIComponent(auth.get()?.token || "")}` : null;
const initials = (n) => (n || "?").split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();
const ago = (ts) => {
  if (!ts) return "";
  const d = (Date.now() - new Date(ts.replace(" ", "T") + "Z").getTime()) / 1000;
  if (d < 60) return "just now";
  if (d < 3600) return `${Math.floor(d / 60)} min ago`;
  if (d < 86400) return `${Math.floor(d / 3600)} h ago`;
  return `${Math.floor(d / 86400)} d ago`;
};
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "");

// ------------------------------------------------------------------ shared ui
function PhotoInput({ file, onFile, allowCamera }) {
  const [over, setOver] = useState(false);
  const [cam, setCam] = useState(false);
  const [err, setErr] = useState("");
  const inp = useRef(), vid = useRef(), stream = useRef();
  const url = file ? URL.createObjectURL(file) : null;
  useEffect(() => () => url && URL.revokeObjectURL(url), [url]);
  useEffect(() => () => stopCam(), []);

  function stopCam() { stream.current?.getTracks().forEach((t) => t.stop()); stream.current = null; setCam(false); }
  async function startCam(e) {
    e.stopPropagation(); setErr("");
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
      setCam(true); onFile(null);
      setTimeout(() => { if (vid.current) { vid.current.srcObject = stream.current; vid.current.play(); } }, 0);
    } catch { setErr("Camera not available - upload a photo instead."); }
  }
  function snap(e) {
    e.stopPropagation();
    const v = vid.current, c = document.createElement("canvas");
    c.width = v.videoWidth; c.height = v.videoHeight; c.getContext("2d").drawImage(v, 0, 0);
    c.toBlob((b) => { onFile(new File([b], "capture.jpg", { type: "image/jpeg" })); stopCam(); }, "image/jpeg", 0.92);
  }
  return html`
    <div>
      <div class=${"drop" + (over ? " over" : "")}
        onClick=${() => !cam && inp.current.click()}
        onDragOver=${(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave=${() => setOver(false)}
        onDrop=${(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files[0]; f && onFile(f); }}>
        ${cam ? html`<video ref=${vid} playsinline muted></video>`
          : url ? html`<img src=${url} alt="Selected photo" />`
          : html`<div class="hint"><b>Drop a photo or click to upload</b>A clear, front-facing face works best. JPG or PNG.</div>`}
        <input ref=${inp} type="file" accept="image/*" hidden onChange=${(e) => e.target.files[0] && onFile(e.target.files[0])} />
      </div>
      <div class="row" style=${{ marginTop: 10 }}>
        ${allowCamera && !cam && html`<button type="button" class="btn ghost sm" onClick=${startCam}>Use camera</button>`}
        ${cam && html`<button type="button" class="btn lime sm" onClick=${snap}>Capture</button>
                      <button type="button" class="btn ghost sm" onClick=${stopCam}>Cancel</button>`}
        ${file && !cam && html`<button type="button" class="btn ghost sm" onClick=${() => onFile(null)}>Remove photo</button>`}
        ${err && html`<span class="err">${err}</span>`}
      </div>
    </div>`;
}

const Bar = ({ v }) => html`<div class="bar"><i style=${{ width: `${Math.max(4, Math.min(100, v))}%` }}></i></div>`;
const MethodChip = ({ m }) => html`<span class=${"chip " + (m === "text" ? "" : "purple")}>${m === "text" ? "Text match" : m === "face" ? "Face match" : "Face + details"}</span>`;
const Field = ({ label, children }) => html`<label class="f">${label}${children}</label>`;

function Toast({ msg, onDone }) {
  useEffect(() => { if (msg) { const t = setTimeout(onDone, 4200); return () => clearTimeout(t); } }, [msg]);
  return msg ? html`<div class="toast">${msg}</div>` : null;
}

// ------------------------------------------------------------------ public: family search
function FamilySearch({ go }) {
  const [file, setFile] = useState(null);
  const [f, setF] = useState({ name: "", age: "", gender: "", last_seen: "", marks: "", seeker_name: "", seeker_phone: "", relation: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [res, setRes] = useState(null);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault(); setErr(""); setBusy(true); setRes(null);
    const fd = new FormData();
    Object.entries(f).forEach(([k, v]) => v && fd.append(k, v));
    if (file) fd.append("photo", file);
    try { setRes(await api("/api/search", { method: "POST", body: fd })); }
    catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  }

  return html`
    <div class="hero">
      <div>
        <div class="eyebrow">AI-powered disaster family reunification</div>
        <h1>Find your family in minutes, not weeks.</h1>
        <p class="lead">Upload a photo or describe the person you are looking for. Reunite searches every connected relief camp at once. No login needed.</p>
        <div class="steps">
          <div class="step"><div class="num">01</div><b>Camps register</b>Every arrival is photographed and logged at intake.</div>
          <div class="step"><div class="num">02</div><b>You search</b>With a photo, or just a description.</div>
          <div class="step"><div class="num">03</div><b>Match & notify</b>A volunteer verifies, then contacts you.</div>
        </div>
        <div class="notice" style=${{ marginTop: 22 }}>
          <b class="l">Public search shows no photos or personal details.</b> You see which camp may have your relative and how confident the match is. Only verified relief staff see full records.
        </div>
        ${res && html`<${SearchResults} res=${res} go=${go} />`}
      </div>

      <form class="card stack" onSubmit=${submit}>
        <div class="row between"><h2>Search all camps</h2><span class="chip lime">3 camps connected</span></div>
        <${PhotoInput} file=${file} onFile=${setFile} />
        ${!file && html`<button type="button" class="btn ghost sm" style=${{ alignSelf: "flex-start" }} onClick=${async () => {
          const b = await (await fetch("demo/family_photo_of_child.jpg")).blob();
          setFile(new File([b], "family_photo_of_child.jpg", { type: "image/jpeg" }));
          setF({ ...f, gender: "female", age: "5", seeker_name: f.seeker_name || "Rina Das", seeker_phone: f.seeker_phone || "98xxxxxx10" });
        }}>Try the demo photo (Assam scenario)</button>`}
        <div class="grid g2">
          <${Field} label="Their name"><input value=${f.name} onInput=${set("name")} placeholder="If known" /><//>
          <${Field} label="Approx. age"><input type="number" min="0" max="120" value=${f.age} onInput=${set("age")} /><//>
          <${Field} label="Gender">
            <select value=${f.gender} onChange=${set("gender")}><option value="">Unknown</option><option value="female">Female</option><option value="male">Male</option><option value="other">Other</option></select>
          <//>
          <${Field} label="Last seen at"><input value=${f.last_seen} onInput=${set("last_seen")} placeholder="Village, district" /><//>
        </div>
        <${Field} label="Clothing / identifying marks"><textarea value=${f.marks} onInput=${set("marks")} placeholder="e.g. red frock, mole on left cheek"></textarea><//>
        <div class="grid g2">
          <${Field} label="Your name"><input value=${f.seeker_name} onInput=${set("seeker_name")} /><//>
          <${Field} label="Your phone (for alerts)"><input value=${f.seeker_phone} onInput=${set("seeker_phone")} /><//>
        </div>
        ${err && html`<div class="err">${err}</div>`}
        <button class="btn lime" disabled=${busy}>${busy ? html`<span class="spin"></span> Searching every camp…` : "Search every camp"}</button>
        <div class="small muted">Your search stays open: if your relative is registered later, the camp is alerted automatically.</div>
      </form>
    </div>`;
}

function SearchResults({ res, go }) {
  const top = res.results[0];
  return html`
    <div class="card" style=${{ marginTop: 22 }}>
      <div class="row between">
        <div><div class="eyebrow purple">Your report</div><h2 style=${{ margin: "4px 0" }}>${res.report_ref}</h2></div>
        <button class="btn ghost sm" onClick=${() => go("track", res.report_ref)}>Track this report</button>
      </div>
      ${res.face_found === false && html`<div class="notice" style=${{ marginTop: 12 }}>No face could be detected in the photo, so we searched by the details you gave. Try a clearer, front-facing photo.</div>`}
      <div class="stack" style=${{ marginTop: 14 }}>
        ${res.results.length === 0 && html`<div class="empty">No likely match yet. Your report is saved, and every new arrival at every camp will be checked against it.</div>`}
        ${res.results.map((r, i) => html`
          <div class=${"result" + (i === 0 && r.confidence >= 70 ? " top" : "")} key=${i}>
            <div>
              <div class="row"><b>${r.person.camp}</b><span class="muted small">${r.person.district} district</span></div>
              <div class="row small muted" style=${{ marginTop: 6 }}>
                <span>${cap(r.person.gender) || "Gender unknown"}${r.person.age != null ? `, about ${r.person.age}` : ""}</span>
                <${MethodChip} m=${r.method} />
                ${r.confidence >= 70 ? html`<span class="chip lime">Likely match</span>` : html`<span class="chip">Possible</span>`}
              </div>
              <${Bar} v=${r.confidence} />
            </div>
            <div class="conf">${Math.round(r.confidence)}%<small>confidence</small></div>
          </div>`)}
      </div>
      ${top && html`<div class="notice small" style=${{ marginTop: 14 }}>A volunteer at the camp has been alerted and will verify the match before contacting you. Exact location is shared once verified.</div>`}
    </div>`;
}

// ------------------------------------------------------------------ public: track
function Track({ initial }) {
  const [ref, setRef] = useState(initial || "");
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const check = useCallback(async (r) => {
    setErr("");
    try { setData(await api(`/api/reports/${encodeURIComponent((r || ref).trim())}`)); } catch (e) { setData(null); setErr(e.message); }
  }, [ref]);
  useEffect(() => { if (initial) check(initial); }, [initial]);
  useEffect(() => { if (!data || data.found) return; const t = setInterval(() => check(data.ref), 5000); return () => clearInterval(t); }, [data]);

  return html`
    <div style=${{ maxWidth: 680 }}>
      <div class="eyebrow">Track a report</div>
      <h1 style=${{ fontSize: 44 }}>Has my relative been found?</h1>
      <form class="row" onSubmit=${(e) => { e.preventDefault(); check(); }}>
        <label class="f" style=${{ flex: 1 }}><input value=${ref} onInput=${(e) => setRef(e.target.value)} placeholder="RPT-XXXXXX" /></label>
        <button class="btn lime">Check status</button>
      </form>
      ${err && html`<p class="err">${err}</p>`}
      ${data && (data.found ? html`
        <div class="card lime" style=${{ marginTop: 20 }}>
          <div class="eyebrow" style=${{ color: "#000" }}>Verified match</div>
          <h2 style=${{ fontSize: 34, margin: "8px 0" }}>Found at ${data.found.camp}</h2>
          <p style=${{ fontSize: 17, margin: 0 }}>${data.found.district} district${data.found.tent ? `, Tent ${data.found.tent}` : ""}. Confidence ${Math.round(data.found.confidence)}%, confirmed by a camp volunteer.</p>
          <p style=${{ marginTop: 14, marginBottom: 0 }}>Bring this reference (<b>${data.ref}</b>) and an ID to the camp help desk.</p>
        </div>` : html`
        <div class="card" style=${{ marginTop: 20 }}>
          <div class="row between"><h2>${data.ref}</h2><span class="live">Watching all camps</span></div>
          <p class="muted">${data.pending_candidates
            ? `${data.pending_candidates} possible match${data.pending_candidates > 1 ? "es are" : " is"} waiting for a volunteer to verify.`
            : "No match yet. Every new registration at every camp is checked against your report automatically."}</p>
        </div>`)}
    </div>`;
}

// ------------------------------------------------------------------ staff: login
function StaffLogin({ onLogin }) {
  const [pin, setPin] = useState("");
  const [err, setErr] = useState("");
  async function submit(e) {
    e.preventDefault(); setErr("");
    try { const d = await api("/api/login", { method: "POST", json: { pin } }); auth.set(d); onLogin(d); }
    catch (e) { setErr(e.message); }
  }
  return html`
    <div class="grid g2" style=${{ alignItems: "center", maxWidth: 960 }}>
      <div>
        <div class="eyebrow">Verified relief staff</div>
        <h1 style=${{ fontSize: 44 }}>Camp volunteer sign-in</h1>
        <p class="lead">Full photos and records are visible only to verified relief organisations and camp volunteers.</p>
      </div>
      <form class="card stack" onSubmit=${submit}>
        <${Field} label="Staff PIN"><input type="password" inputmode="numeric" value=${pin} onInput=${(e) => setPin(e.target.value)} autofocus /><//>
        ${err && html`<div class="err">${err}</div>`}
        <button class="btn lime">Sign in</button>
        <div class="notice small">
          <b class="l">Prototype demo PINs</b><br />
          1111 Silchar Camp A · 2222 Dhubri Camp B · 3333 Barpeta Camp C<br />
          0000 NGO / district authority (all camps)
        </div>
      </form>
    </div>`;
}

// ------------------------------------------------------------------ staff: dashboard
function Dashboard({ session, tick, go }) {
  const all = session.scope === "*";
  const [stats, setStats] = useState(null);
  const [camps, setCamps] = useState([]);
  const [people, setPeople] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [flt, setFlt] = useState({ q: "", gender: "", age: "", status: "", camp: "" });
  const set = (k) => (e) => setFlt({ ...flt, [k]: e.target.value });

  useEffect(() => {
    api("/api/stats").then(setStats).catch(() => {});
    api("/api/camps").then(setCamps).catch(() => {});
    api("/api/alerts").then(setAlerts).catch(() => {});
  }, [tick]);
  useEffect(() => {
    const p = new URLSearchParams();
    if (flt.q) p.set("q", flt.q);
    if (flt.gender) p.set("gender", flt.gender);
    if (flt.status) p.set("status", flt.status);
    if (flt.camp) p.set("camp", flt.camp);
    if (flt.age === "child") p.set("age_max", "13");
    if (flt.age === "adult") { p.set("age_min", "14"); p.set("age_max", "59"); }
    if (flt.age === "elderly") p.set("age_min", "60");
    const t = setTimeout(() => api(`/api/people?${p}`).then(setPeople).catch(() => {}), 150);
    return () => clearTimeout(t);
  }, [flt, tick]);

  const title = all ? "All camps · Assam floods 2026" : session.camp?.name;
  return html`
    <div class="stack">
      <div class="row between">
        <div><div class="eyebrow">Camp dashboard</div><h2 style=${{ fontSize: 30 }}>${title}</h2></div>
        <div class="row">
          <span class="live">Live</span>
          <button class="btn lime" onClick=${() => go("register")}>+ Register arrival</button>
        </div>
      </div>

      ${stats && html`<div class="stats">
        <div class="stat"><div class="n">${stats.registered}</div><div class="l">Registered</div></div>
        <div class="stat"><div class="n">${stats.with_face}</div><div class="l">Face-searchable</div></div>
        <div class="stat"><div class="n">${stats.children}</div><div class="l">Children under 14</div></div>
        <div class="stat"><div class="n">${stats.elderly}</div><div class="l">Elderly 60+</div></div>
        <div class="stat hl" style=${{ cursor: "pointer" }} onClick=${() => go("matches")}><div class="n">${stats.pending}</div><div class="l">Matches to verify →</div></div>
        <div class="stat"><div class="n" style=${{ color: "var(--green)" }}>${stats.reunited}</div><div class="l">Reunited</div></div>
      </div>`}

      ${all && html`<div class="grid g3">
        ${camps.map((c) => html`<div class="camp" key=${c.id}>
          <div class="row between"><b>${c.name}</b><span class="chip">${c.code}</span></div>
          <div class="small muted" style=${{ marginTop: 4 }}>${c.district} district · ${c.registered} registered / ${c.capacity} capacity</div>
          <div class="cap"><i style=${{ width: `${Math.max(2, (c.registered / c.capacity) * 100)}%` }}></i></div>
        </div>`)}
      </div>`}

      <div class="grid g-side">
        <div class="stack">
          <div class="filters">
            <label class="f"><input placeholder="Search name, ID, village, marks…" value=${flt.q} onInput=${set("q")} /></label>
            <label class="f"><select value=${flt.gender} onChange=${set("gender")}><option value="">Any gender</option><option value="female">Female</option><option value="male">Male</option></select></label>
            <label class="f"><select value=${flt.age} onChange=${set("age")}><option value="">Any age</option><option value="child">Children</option><option value="adult">Adults</option><option value="elderly">Elderly 60+</option></select></label>
            <label class="f"><select value=${flt.status} onChange=${set("status")}><option value="">Any status</option><option value="registered">In camp</option><option value="reunited">Reunited</option></select></label>
            ${all ? html`<label class="f"><select value=${flt.camp} onChange=${set("camp")}><option value="">All camps</option>${camps.map((c) => html`<option value=${c.code}>${c.code}</option>`)}</select></label>` : html`<div></div>`}
          </div>
          <div class="small muted">${people.length} people</div>
          <div class="people">
            ${people.map((p) => html`<div class="person" key=${p.id}>
              <div class="ph">
                ${p.photo ? html`<img src=${photoUrl(p.photo)} alt="" />` : initials(p.name)}
                <span class="tag">${p.status === "reunited" ? html`<span class="chip green">Reunited</span>` : p.has_face ? html`<span class="chip purple">Face</span>` : null}</span>
              </div>
              <div class="meta">
                <div class="nm">${p.name || "Unidentified"}</div>
                <div class="sub">${cap(p.gender)}, ${p.age ?? "?"} · ${p.ref}<br />${all ? p.camp_code + " · " : ""}Tent ${p.tent || "-"} · ${p.origin || "origin unknown"}</div>
              </div>
            </div>`)}
          </div>
          ${people.length === 0 && html`<div class="empty">No one matches these filters.</div>`}
        </div>

        <div class="card">
          <div class="row between"><h3>Real-time alerts</h3><span class="live">Live</span></div>
          <div class="alerts">
            ${alerts.map((a) => html`<div class=${"alert " + a.kind} key=${a.id}>
              <div class="ic">${{ match: "◎", verified: "✓", rejected: "✕", intake: "+" }[a.kind] || "•"}</div>
              <div>${a.message}<div class="t">${a.camp_name || ""} · ${ago(a.created_at)}</div></div>
            </div>`)}
          </div>
        </div>
      </div>
    </div>`;
}

// ------------------------------------------------------------------ staff: register
function Register({ session, onDone }) {
  const all = session.scope === "*";
  const blank = { name: "", age: "", gender: "", origin: "", marks: "", tent: "", camp: "CAMP-A", consent: false };
  const [file, setFile] = useState(null);
  const [f, setF] = useState(blank);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [res, setRes] = useState(null);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  async function submit(e) {
    e.preventDefault(); setErr("");
    if (!f.consent) return setErr("Record consent before registering.");
    setBusy(true);
    const fd = new FormData();
    Object.entries(f).forEach(([k, v]) => v !== "" && fd.append(k, String(v)));
    if (file) fd.append("photo", file);
    try {
      const d = await api("/api/people", { method: "POST", body: fd });
      setRes(d); setF({ ...blank, camp: f.camp }); setFile(null); onDone(d);
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  return html`
    <div class="grid g2" style=${{ alignItems: "start" }}>
      <div>
        <div class="eyebrow">Intake · ${all ? "any camp" : session.camp?.name}</div>
        <h1 style=${{ fontSize: 44 }}>Register an arrival</h1>
        <p class="lead">Photo, approximate age, gender and origin. The person is searchable across every camp the second you save, and checked against every open family report.</p>
        ${res && html`<div class="card" style=${{ marginTop: 20 }}>
          <div class="row between"><div><div class="eyebrow purple">Registered</div><h2>${res.person.ref}</h2></div>
            ${res.face_found === true ? html`<span class="chip purple">Face indexed</span>` : res.face_found === false ? html`<span class="chip amber">No face detected</span>` : html`<span class="chip">No photo</span>`}</div>
          ${res.intake_matches.length
            ? html`<div class="notice" style=${{ marginTop: 12 }}><b class="l">${res.intake_matches.length} open family report${res.intake_matches.length > 1 ? "s" : ""} matched at intake.</b> Top: ${res.intake_matches[0].report_ref} at ${Math.round(res.intake_matches[0].confidence)}%. Review it under Matches.</div>`
            : html`<p class="muted small">No open family reports match yet. They will be alerted if a relative searches.</p>`}
        </div>`}
      </div>
      <form class="card stack" onSubmit=${submit}>
        <${PhotoInput} file=${file} onFile=${setFile} allowCamera=${true} />
        <div class="grid g2">
          <${Field} label="Name"><input value=${f.name} onInput=${set("name")} placeholder="Leave blank if unknown" /><//>
          <${Field} label="Approx. age"><input type="number" min="0" max="120" value=${f.age} onInput=${set("age")} /><//>
          <${Field} label="Gender">
            <select value=${f.gender} onChange=${set("gender")}><option value="">Unknown</option><option value="female">Female</option><option value="male">Male</option><option value="other">Other</option></select>
          <//>
          <${Field} label="Origin (village, district)"><input value=${f.origin} onInput=${set("origin")} /><//>
          ${all && html`<${Field} label="Camp"><select value=${f.camp} onChange=${set("camp")}><option>CAMP-A</option><option>CAMP-B</option><option>CAMP-C</option></select><//>`}
          <${Field} label="Tent / bed"><input value=${f.tent} onInput=${set("tent")} /><//>
        </div>
        <${Field} label="Clothing / identifying marks"><textarea value=${f.marks} onInput=${set("marks")}></textarea><//>
        <label class="check"><input type="checkbox" checked=${f.consent} onChange=${set("consent")} />
          <span>The person (or guardian, for a child) agreed to be registered and made searchable so their family can find them.</span></label>
        ${err && html`<div class="err">${err}</div>`}
        <button class="btn lime" disabled=${busy}>${busy ? html`<span class="spin"></span> Registering…` : "Register & match"}</button>
      </form>
    </div>`;
}

// ------------------------------------------------------------------ staff: verify matches
function Matches({ session, tick, onChange }) {
  const [status, setStatus] = useState("pending");
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(null);
  useEffect(() => { api(`/api/matches?status=${status}`).then(setRows).catch(() => {}); }, [status, tick]);

  async function decide(m, decision) {
    setBusy(m.id);
    try { await api(`/api/matches/${m.id}/decision`, { method: "POST", json: { decision } }); onChange(decision === "verified" ? `Verified. ${m.seeker_name || "The family"} has been notified: ${m.camp_name}, Tent ${m.tent || "-"}.` : "Candidate rejected."); }
    finally { setBusy(null); }
  }

  return html`
    <div class="stack">
      <div class="row between">
        <div><div class="eyebrow">AI suggests, people confirm</div><h2 style=${{ fontSize: 30 }}>Matches to verify</h2></div>
        <div class="nav">${["pending", "verified", "rejected"].map((s) => html`<button class=${status === s ? "on" : ""} onClick=${() => setStatus(s)}>${cap(s)}</button>`)}</div>
      </div>
      ${rows.length === 0 && html`<div class="empty">${status === "pending" ? "No matches waiting. New ones appear here the moment a family search or a camp registration produces a candidate." : `No ${status} matches.`}</div>`}
      ${rows.map((m) => {
        const strong = m.confidence >= 70;
        return html`<div class="card" key=${m.id}>
          <div class="row between" style=${{ marginBottom: 14 }}>
            <div class="row"><b>Report ${m.report_ref}</b><span class="muted small">${m.relation ? `${m.relation} ` : ""}${m.seeker_name || "Anonymous"} is searching</span></div>
            <div class="row"><${MethodChip} m=${m.method} />${m.face_score != null && html`<span class="chip">Face ${Math.round(m.face_score)}%</span>`}${m.text_score != null && html`<span class="chip">Details ${Math.round(m.text_score)}%</span>`}</div>
          </div>
          <div class="compare">
            <div class="face">${m.r_photo ? html`<img src=${photoUrl(m.r_photo)} alt="" />` : html`<div style=${{ padding: 20 }}>No photo given<br /><span class="small">Text description only</span></div>`}
              <div class="cap">Family's photo / description</div></div>
            <div>
              <div class=${"verdict" + (strong ? "" : " mid")}>
                <div class="lbl">Match confidence</div>
                <div class="big">${Math.round(m.confidence)}%</div>
                <div class="lbl" style=${{ marginTop: 6 }}>${m.camp_name}</div>
              </div>
              <div class="pill">📍 Location: ${m.camp_code}, Tent ${m.tent || "-"}</div>
              <div class="pill">📞 ${m.seeker_phone || "No phone given"}</div>
              ${m.status === "verified" && html`<div class="pill" style=${{ color: "var(--green)" }}>✓ Family notified</div>`}
            </div>
            <div class="face">${m.p_photo ? html`<img src=${photoUrl(m.p_photo)} alt="" />` : html`<div style=${{ padding: 20, fontSize: 42, fontWeight: 800, color: "#c4b5fd" }}>${initials(m.p_name)}</div>`}
              <div class="cap">${m.p_ref} · registered at ${m.camp_code}</div></div>
          </div>
          <table class="cmp">
            <thead><tr><th></th><th>Family says</th><th>Camp record</th></tr></thead>
            <tbody>
              <tr><td class="muted">Name</td><td>${m.r_name || "-"}</td><td>${m.p_name || "Unidentified"}</td></tr>
              <tr><td class="muted">Age / gender</td><td>${m.r_age ?? "?"} · ${m.r_gender || "?"}</td><td>${m.p_age ?? "?"} · ${m.p_gender || "?"}</td></tr>
              <tr><td class="muted">Place</td><td>${m.last_seen || "-"}</td><td>${m.p_origin || "-"}</td></tr>
              <tr><td class="muted">Marks</td><td>${m.r_marks || "-"}</td><td>${m.p_marks || "-"}</td></tr>
            </tbody>
          </table>
          ${m.status === "pending" && html`<div class="row" style=${{ marginTop: 16, justifyContent: "flex-end" }}>
            <button class="btn red sm" disabled=${busy === m.id} onClick=${() => decide(m, "rejected")}>Not the same person</button>
            <button class="btn lime" disabled=${busy === m.id} onClick=${() => decide(m, "verified")}>Verify & notify family</button>
          </div>`}
        </div>`;
      })}
    </div>`;
}

// ------------------------------------------------------------------ app shell
function App() {
  const parse = () => { const [v, arg] = location.hash.slice(1).split("/"); return { view: v || "search", arg }; };
  const [route, setRoute] = useState(parse());
  const [session, setSession] = useState(auth.get());
  const [tick, setTick] = useState(0);
  const [pending, setPending] = useState(0);
  const [engine, setEngine] = useState("");
  const [toast, setToast] = useState("");

  useEffect(() => { const h = () => setRoute(parse()); addEventListener("hashchange", h); return () => removeEventListener("hashchange", h); }, []);
  useEffect(() => { api("/api/health").then((d) => setEngine(d.face_engine)).catch(() => {}); }, []);
  // Live updates for staff: poll every 4s.
  useEffect(() => { if (!session) return; const t = setInterval(() => setTick((x) => x + 1), 4000); return () => clearInterval(t); }, [session]);
  useEffect(() => { if (session) api("/api/stats").then((s) => setPending(s.pending)).catch(() => {}); }, [session, tick]);

  const go = (v, arg) => { location.hash = arg ? `${v}/${arg}` : v; scrollTo(0, 0); };
  const staffView = ["dashboard", "register", "matches"].includes(route.view);
  const view = staffView && !session ? "staff" : route.view === "staff" && session ? "dashboard" : route.view;
  const refresh = (msg) => { setTick((x) => x + 1); msg && setToast(msg); };

  const tabs = [["search", "Find family"], ["track", "Track report"]];
  const staffTabs = [["dashboard", "Dashboard"], ["register", "Register arrival"], ["matches", "Verify matches"]];

  return html`
    <header class="topbar">
      <div class="logo" onClick=${() => go("search")}><span class="dot"></span>REUNITE</div>
      <nav class="nav">
        ${tabs.map(([k, l]) => html`<button key=${k} class=${view === k ? "on" : ""} onClick=${() => go(k)}>${l}</button>`)}
        ${session ? staffTabs.map(([k, l]) => html`<button key=${k} class=${view === k ? "on" : ""} onClick=${() => go(k)}>${l}${k === "matches" && pending > 0 ? html`<span class="badge">${pending}</span>` : null}</button>`)
          : html`<button class=${view === "staff" ? "on" : ""} onClick=${() => go("staff")}>Camp staff</button>`}
      </nav>
      <div class="spacer"></div>
      <div class="who">
        ${engine && html`<span class="engine">AI engine: <b>${engine === "none" ? "text only" : engine}</b></span>`}
        ${session && html`<span>${session.scope === "*" ? "NGO · all camps" : session.camp?.name}</span>
          <button class="btn ghost sm" onClick=${() => { auth.set(null); setSession(null); go("search"); }}>Sign out</button>`}
      </div>
    </header>
    <main>
      ${view === "search" && html`<${FamilySearch} go=${go} />`}
      ${view === "track" && html`<${Track} initial=${route.arg} key=${route.arg || "t"} />`}
      ${view === "staff" && html`<${StaffLogin} onLogin=${(d) => { setSession(d); go(staffView ? route.view : "dashboard"); }} />`}
      ${view === "dashboard" && html`<${Dashboard} session=${session} tick=${tick} go=${go} />`}
      ${view === "register" && html`<${Register} session=${session} onDone=${(d) => refresh(d.intake_matches.length ? `Registered ${d.person.ref}. ${d.intake_matches.length} family report(s) matched at intake.` : `Registered ${d.person.ref}.`)} />`}
      ${view === "matches" && html`<${Matches} session=${session} tick=${tick} onChange=${refresh} />`}
    </main>
    <${Toast} msg=${toast} onDone=${() => setToast("")} />`;
}

ReactDOM.createRoot(document.getElementById("root")).render(html`<${App} />`);
