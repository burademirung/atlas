const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export interface Run {
  id: number;
  question: string;
  status: string;
  created_at: string;
}

export interface RunDetail extends Run {
  report: string | null;
  sources: { url: string; title: string | null; snippet: string | null }[];
}

export interface RunEvent {
  event: string;
  data: Record<string, unknown>;
}

class ApiError extends Error {}

async function json<T>(path: string, opts: RequestInit, token?: string): Promise<T> {
  const headers = new Headers(opts.headers);
  headers.set("content-type", "application/json");
  if (token) headers.set("authorization", `Bearer ${token}`);
  const resp = await fetch(`${BASE}${path}`, { ...opts, headers });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new ApiError((body as { title?: string }).title ?? `Request failed (${resp.status})`);
  }
  return (await resp.json()) as T;
}

export function register(email: string, password: string): Promise<{ id: number; email: string }> {
  return json("/v1/auth/register", { method: "POST", body: JSON.stringify({ email, password }) });
}

export async function login(email: string, password: string): Promise<string> {
  const r = await json<{ access_token: string }>("/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  return r.access_token;
}

export function createRun(token: string, question: string): Promise<Run> {
  return json("/v1/runs", { method: "POST", body: JSON.stringify({ question }) }, token);
}

export function listRuns(token: string): Promise<Run[]> {
  return json("/v1/runs", { method: "GET" }, token);
}

export function getRun(token: string, id: number): Promise<RunDetail> {
  return json(`/v1/runs/${id}`, { method: "GET" }, token);
}

/** Parse a single SSE frame (the text between two blank lines) into a RunEvent.
 *  Returns null for frames with no `data:` payload (e.g. keepalive comments) or
 *  when the data isn't valid JSON. Pure & exported so it can be unit-tested. */
export function parseSseFrame(frame: string): RunEvent | null {
  let event = "message";
  let data = "";
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return null;
  try {
    return { event, data: JSON.parse(data) as Record<string, unknown> };
  } catch {
    /* ignore keepalives / partial frames */
    return null;
  }
}

/** Stream a run's Server-Sent Events. EventSource can't send an auth header,
 *  so we parse the SSE body from a fetch stream ourselves. */
export async function streamRun(
  token: string,
  id: number,
  onEvent: (e: RunEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const resp = await fetch(`${BASE}/v1/runs/${id}/events`, {
    headers: { authorization: `Bearer ${token}` },
    signal,
  });
  if (!resp.body) throw new ApiError("No event stream");
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const e = parseSseFrame(frame);
      if (e) onEvent(e);
    }
  }
}
