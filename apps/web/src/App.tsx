import { useCallback, useEffect, useRef, useState } from "react";
import {
  createRun,
  getRun,
  listRuns,
  login,
  register,
  type Run,
  streamRun,
} from "./api.ts";
import { renderMarkdown } from "./markdown.ts";

const PHASES = ["planning", "searching", "verifying", "writing"] as const;
type Phase = (typeof PHASES)[number];
interface Source {
  url: string;
  title: string;
}

export function App() {
  const [token, setToken] = useState<string | null>(null);
  if (!token) return <AuthCard onAuthed={setToken} />;
  return <Studio token={token} onSignOut={() => setToken(null)} />;
}

function AuthCard({ onAuthed }: { onAuthed: (token: string) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "register") await register(email, password);
      onAuthed(await login(email, password));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <div className="brand">
          <span className="mark">◆</span> ATLAS <span className="sub">Research Studio</span>
        </div>
        <h1>{mode === "login" ? "Welcome back" : "Create your account"}</h1>
        <form onSubmit={submit} className="auth-form">
          <input
            type="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <input
            type="password"
            placeholder="Password (10+ characters)"
            value={password}
            minLength={10}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          {error && <p className="form-error">{error}</p>}
          <button type="submit" disabled={busy}>
            {busy ? "…" : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>
        <p className="auth-switch">
          {mode === "login" ? "New here?" : "Have an account?"}{" "}
          <button onClick={() => setMode(mode === "login" ? "register" : "login")}>
            {mode === "login" ? "Create one" : "Sign in"}
          </button>
        </p>
      </div>
    </div>
  );
}

function Studio({ token, onSignOut }: { token: string; onSignOut: () => void }) {
  const [question, setQuestion] = useState("");
  const [phase, setPhase] = useState<Phase | null>(null);
  const [status, setStatus] = useState("idle");
  const [subquestions, setSubquestions] = useState<string[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [report, setReport] = useState("");
  const [runs, setRuns] = useState<Run[]>([]);
  const [running, setRunning] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const refreshHistory = useCallback(() => {
    listRuns(token).then(setRuns).catch(() => {});
  }, [token]);
  useEffect(refreshHistory, [refreshHistory]);

  const reset = (q: string) => {
    setPhase(null);
    setStatus("queued");
    setSubquestions([]);
    setSources([]);
    setReport("");
    setQuestion(q);
  };

  const run = async (q: string) => {
    if (running || !q.trim()) return;
    setRunning(true);
    reset(q);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const created = await createRun(token, q.trim());
      await streamRun(
        token,
        created.id,
        (e) => {
          const d = e.data as Record<string, string & string[]>;
          if (e.event === "status") {
            setPhase(d.phase as Phase);
            setStatus(d.phase);
          } else if (e.event === "plan") {
            setSubquestions((d.subquestions as unknown as string[]) ?? []);
          } else if (e.event === "source") {
            setSources((s) => [...s, { url: d.url, title: d.title }]);
          } else if (e.event === "report") {
            setReport((d.markdown as unknown as string) ?? "");
          } else if (e.event === "done" || e.event === "cancelled") {
            setStatus(e.event);
            setRunning(false);
            refreshHistory();
          } else if (e.event === "error") {
            setStatus("error");
            setRunning(false);
          }
        },
        ctrl.signal,
      );
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "error");
      setRunning(false);
    }
  };

  const openRun = async (id: number) => {
    const detail = await getRun(token, id);
    reset(detail.question);
    setStatus(detail.status);
    setSources(detail.sources.map((s) => ({ url: s.url, title: s.title ?? s.url })));
    setReport(detail.report ?? "");
  };

  const active = phase !== null;
  const phaseIndex = phase ? PHASES.indexOf(phase) : -1;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="mark">◆</span> ATLAS <span className="sub">Research Studio</span>
        </div>
        <div className="meta">
          <span className="pill">FastAPI · LangGraph · Claude</span>
          <button className="pill ghost" onClick={onSignOut}>
            Sign out
          </button>
        </div>
      </header>

      <main className="layout">
        <section className="composer">
          <h1>
            Ask anything. <em>Get a cited answer,</em> watched live.
          </h1>
          <form
            className="ask"
            onSubmit={(e) => {
              e.preventDefault();
              run(question);
            }}
          >
            <textarea
              rows={2}
              maxLength={500}
              placeholder="e.g. How do mRNA vaccines work?"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
            />
            <button type="submit" disabled={running}>
              {running ? "Researching…" : "Run research →"}
            </button>
          </form>
        </section>

        {(active || report) && (
          <section className="stage">
            <div className="pipeline">
              <h3 className="panel-title">Agent pipeline</h3>
              <ol className="stages">
                {PHASES.map((p, i) => (
                  <li
                    key={p}
                    className={p === phase ? "active" : phaseIndex > i ? "done" : ""}
                  >
                    <span className="dot" />
                    <span className="t">{p[0].toUpperCase() + p.slice(1)}</span>
                  </li>
                ))}
              </ol>
              {subquestions.length > 0 && (
                <div className="subqs">
                  {subquestions.map((s, i) => (
                    <div key={i} className="sq">
                      {s}
                    </div>
                  ))}
                </div>
              )}
              <h3 className="panel-title src-title">
                Sources <span className="count">{sources.length}</span>
              </h3>
              <div className="sources">
                {sources.map((s, i) => (
                  <a
                    key={s.url}
                    id={`src-${i + 1}`}
                    className="source"
                    href={s.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <span className="idx">[{i + 1}]</span> {s.title}
                  </a>
                ))}
              </div>
            </div>

            <div className="report-wrap">
              <div className="report-head">
                <span className={`status-chip ${status}`}>{status}</span>
                <span className="qecho">{question}</span>
              </div>
              <article
                className="report"
                dangerouslySetInnerHTML={{
                  __html: report
                    ? renderMarkdown(report)
                    : '<p class="placeholder">The cited report will appear here.</p>',
                }}
              />
            </div>
          </section>
        )}

        <aside className="history">
          <h3 className="panel-title">Recent runs</h3>
          <div className="history-list">
            {runs.map((r) => (
              <button key={r.id} className="history-item" onClick={() => openRun(r.id)}>
                {r.question}
                <span className="when">
                  {r.status} · {new Date(r.created_at).toLocaleString()}
                </span>
              </button>
            ))}
          </div>
        </aside>
      </main>

      <footer className="foot">
        Atlas · production edition — FastAPI + LangGraph agents + Postgres, streamed over SSE
      </footer>
    </div>
  );
}
