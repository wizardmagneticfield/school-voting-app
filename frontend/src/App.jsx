import { useEffect, useState } from "react";
import { api } from "./api.js";

export default function App() {
  const [user, setUser] = useState(undefined); // undefined = loading, null = logged out
  const [view, setView] = useState({ name: "list" });

  useEffect(() => {
    api("/me").then(setUser).catch(() => setUser(null));
  }, []);

  if (user === undefined) return <p className="center">Loading…</p>;
  if (!user) return <Auth onLogin={setUser} />;

  const logout = async () => {
    await api("/logout", { method: "POST" });
    setUser(null);
    setView({ name: "list" });
  };

  return (
    <div className="app">
      <header>
        <h1 onClick={() => setView({ name: "list" })}>School Elections</h1>
        <div className="row">
          {user.role === "admin" && (
            <button className="ghost" onClick={() => setView({ name: "admin" })}>Admin panel</button>
          )}
          <span className="muted">{user.name}</span>
          <button className="ghost" onClick={logout}>Log out</button>
        </div>
      </header>
      <main>
        {view.name === "list" && <ElectionList user={user} go={setView} />}
        {view.name === "vote" && <Ballot id={view.id} go={setView} />}
        {view.name === "results" && <Results id={view.id} go={setView} />}
        {view.name === "admin" && user.role === "admin" && <Admin go={setView} />}
      </main>
    </div>
  );
}

function Auth({ onLogin }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ student_id: "", name: "", password: "" });
  const [err, setErr] = useState("");
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    try {
      onLogin(await api(`/${mode}`, { method: "POST", body: form }));
    } catch (e) {
      setErr(e.message);
    }
  };

  return (
    <form className="card auth" onSubmit={submit}>
      <h1>School Elections</h1>
      <h2>{mode === "login" ? "Log in" : "Create account"}</h2>
      <input placeholder="Student ID" value={form.student_id} onChange={set("student_id")} />
      {mode === "register" && <input placeholder="Full name" value={form.name} onChange={set("name")} />}
      <input type="password" placeholder="Password (8+ characters)" value={form.password} onChange={set("password")} />
      {err && <p className="error">{err}</p>}
      <button type="submit">{mode === "login" ? "Log in" : "Register"}</button>
      <button type="button" className="link" onClick={() => setMode(mode === "login" ? "register" : "login")}>
        {mode === "login" ? "New here? Register" : "Have an account? Log in"}
      </button>
    </form>
  );
}

function ElectionList({ user, go }) {
  const [elections, setElections] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    api("/elections").then(setElections).catch((e) => setErr(e.message));
  }, []);
  if (err) return <p className="error">{err}</p>;
  if (!elections) return <p>Loading…</p>;
  if (!elections.length) return <p className="muted">No elections yet.</p>;

  return (
    <div className="grid">
      {elections.map((e) => (
        <div className="card" key={e.id}>
          <div className="row between">
            <h3>{e.title}</h3>
            <span className={`badge ${e.status}`}>{e.status}</span>
          </div>
          {e.description && <p className="muted">{e.description}</p>}
          {e.status === "open" && !e.has_voted && (
            <button onClick={() => go({ name: "vote", id: e.id })}>Vote</button>
          )}
          {e.has_voted && <p className="ok">✓ You voted</p>}
          {(e.status === "closed" || user.role === "admin") && (
            <button className="ghost" onClick={() => go({ name: "results", id: e.id })}>Results</button>
          )}
        </div>
      ))}
    </div>
  );
}

function Ballot({ id, go }) {
  const [election, setElection] = useState(null);
  const [choice, setChoice] = useState(null);
  const [err, setErr] = useState("");
  const [done, setDone] = useState(false);

  useEffect(() => {
    api(`/elections/${id}`).then(setElection).catch((e) => setErr(e.message));
  }, [id]);

  const submit = async () => {
    if (!window.confirm("Votes can't be changed. Submit your vote?")) return;
    try {
      await api(`/elections/${id}/vote`, { method: "POST", body: { candidate_id: choice } });
      setDone(true);
    } catch (e) {
      setErr(e.message);
    }
  };

  if (err) return <p className="error">{err}</p>;
  if (!election) return <p>Loading…</p>;
  if (done || election.has_voted)
    return (
      <div className="card">
        <h2>Thanks for voting!</h2>
        <button onClick={() => go({ name: "list" })}>Back to elections</button>
      </div>
    );

  return (
    <div className="card">
      <h2>{election.title}</h2>
      {election.candidates.map((c) => (
        <label key={c.id} className={`option ${choice === c.id ? "selected" : ""}`}>
          <input type="radio" name="candidate" checked={choice === c.id} onChange={() => setChoice(c.id)} />
          <span>{c.name}</span>
        </label>
      ))}
      <div className="row">
        <button disabled={!choice} onClick={submit}>Submit vote</button>
        <button className="ghost" onClick={() => go({ name: "list" })}>Cancel</button>
      </div>
    </div>
  );
}

function Results({ id, go }) {
  const [r, setR] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    api(`/elections/${id}/results`).then(setR).catch((e) => setErr(e.message));
  }, [id]);
  if (err) return <p className="error">{err}</p>;
  if (!r) return <p>Loading…</p>;

  const max = Math.max(1, ...r.candidates.map((c) => c.votes));
  return (
    <div className="card">
      <h2>{r.title}</h2>
      <p className="muted">{r.total_votes} votes · {r.status}</p>
      {r.candidates.map((c) => (
        <div key={c.id} className="result">
          <div className="row between">
            <span>{c.name}</span>
            <span>{c.votes} ({r.total_votes ? Math.round((100 * c.votes) / r.total_votes) : 0}%)</span>
          </div>
          <div className="bar"><div style={{ width: `${(100 * c.votes) / max}%` }} /></div>
        </div>
      ))}
      <button className="ghost" onClick={() => go({ name: "list" })}>Back</button>
    </div>
  );
}

function Admin({ go }) {
  const [elections, setElections] = useState([]);
  const [stats, setStats] = useState(null);
  const [form, setForm] = useState({ title: "", description: "", candidates: "" });
  const [msg, setMsg] = useState("");

  const load = () => {
    api("/elections").then(setElections).catch((e) => setMsg(e.message));
    api("/admin/stats").then(setStats).catch((e) => setMsg(e.message));
  };
  useEffect(load, []);

  const create = async (e) => {
    e.preventDefault();
    try {
      await api("/admin/elections", {
        method: "POST",
        body: { ...form, candidates: form.candidates.split("\n") },
      });
      setForm({ title: "", description: "", candidates: "" });
      setMsg("Election created as a draft.");
      load();
    } catch (e) {
      setMsg(e.message);
    }
  };

  const advance = async (e) => {
    const next = { draft: "open", open: "closed" }[e.status];
    if (!window.confirm(`Move "${e.title}" to ${next}? This can't be undone.`)) return;
    try {
      await api(`/admin/elections/${e.id}/status`, { method: "PATCH", body: { status: next } });
      load();
    } catch (err) {
      setMsg(err.message);
    }
  };

  return (
    <>
      {stats && (
        <div className="stats">
          <div className="card"><b>{stats.students}</b><span>students</span></div>
          <div className="card"><b>{stats.voters}</b><span>have voted</span></div>
          <div className="card"><b>{stats.votes}</b><span>votes cast</span></div>
        </div>
      )}
      <form className="card" onSubmit={create}>
        <h2>New election</h2>
        <input placeholder="Title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        <input placeholder="Description (optional)" value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })} />
        <textarea rows={4} placeholder="Candidates, one per line" value={form.candidates}
          onChange={(e) => setForm({ ...form, candidates: e.target.value })} />
        {msg && <p className="muted">{msg}</p>}
        <button type="submit">Create</button>
      </form>
      <div className="card">
        <h2>Manage elections</h2>
        {elections.map((e) => (
          <div key={e.id} className="row between manage">
            <span>{e.title} <span className={`badge ${e.status}`}>{e.status}</span></span>
            <div className="row">
              {e.status !== "closed" && (
                <button onClick={() => advance(e)}>{e.status === "draft" ? "Open voting" : "Close voting"}</button>
              )}
              <button className="ghost" onClick={() => go({ name: "results", id: e.id })}>Results</button>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
