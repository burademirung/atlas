/**
 * Atlas Research — Cloudflare-native edition (Claude + web search).
 *
 * A single Worker that runs a real research agent on Claude Opus 4.8 with the
 * native `web_search` server tool: Claude plans, searches the live web, grounds
 * its answer in real sources, and streams a cited Markdown report. Progress
 * (planning → searching → sources → writing) streams to the browser over SSE;
 * finished runs persist to Cloudflare D1.
 *
 * Requires the ANTHROPIC_API_KEY secret (wrangler secret put ANTHROPIC_API_KEY).
 */

const MODEL = "claude-opus-4-8";
const ANTHROPIC_URL = "https://api.anthropic.com/v1/messages";
const ANTHROPIC_VERSION = "2023-06-01";

const SYSTEM = `You are a meticulous research analyst. Use the web_search tool to gather current,
authoritative sources before answering. Then write a clear, well-structured report in Markdown that
answers the question using only what the sources support. Cite claims inline with [n] where n refers
to the nth source you searched, in the order you first cite them. Use short sections with ## headings.
If the evidence is thin or conflicting, say so. Do not invent sources or citations. End with a brief
"## Sources" list mapping each [n] to its title.`;

export interface Env {
  AI: Ai;
  DB: D1Database;
  ASSETS: Fetcher;
  ANTHROPIC_API_KEY: string;
}

interface Source {
  url: string;
  title: string;
}

type Send = (event: string, data: unknown) => void;

const json = (data: unknown, status = 200): Response =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/api/health") {
      return json({ status: "ok", model: MODEL, key: env.ANTHROPIC_API_KEY ? "set" : "missing" });
    }

    if (url.pathname === "/api/research" && request.method === "POST") {
      return handleResearch(request, env);
    }

    if (url.pathname === "/api/runs" && request.method === "GET") {
      const { results } = await env.DB.prepare(
        "SELECT id, question, status, created_at FROM runs ORDER BY created_at DESC LIMIT 25",
      ).all();
      return json({ runs: results });
    }

    const runMatch = url.pathname.match(/^\/api\/runs\/([\w-]+)$/);
    if (runMatch && request.method === "GET") {
      const id = runMatch[1];
      const run = await env.DB.prepare("SELECT * FROM runs WHERE id = ?").bind(id).first();
      if (!run) return json({ error: "not found" }, 404);
      const { results: sources } = await env.DB.prepare(
        "SELECT url, title, snippet FROM sources WHERE run_id = ?",
      )
        .bind(id)
        .all();
      return json({ run, sources });
    }

    return env.ASSETS.fetch(request);
  },
} satisfies ExportedHandler<Env>;

function handleResearch(request: Request, env: Env): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const send: Send = (event, data) =>
        controller.enqueue(
          encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`),
        );
      try {
        const body = (await request.json().catch(() => ({}))) as { question?: string };
        const question = (body.question ?? "").trim();
        if (!question) {
          send("error", { message: "A research question is required." });
          return;
        }
        if (question.length > 500) {
          send("error", { message: "Question too long (max 500 chars)." });
          return;
        }
        if (!env.ANTHROPIC_API_KEY) {
          send("error", { message: "Server missing ANTHROPIC_API_KEY." });
          return;
        }
        await runResearch(env, question, send);
      } catch (err) {
        send("error", { message: err instanceof Error ? err.message : String(err) });
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "content-type": "text/event-stream; charset=utf-8",
      "cache-control": "no-cache, no-transform",
      "x-accel-buffering": "no",
      connection: "keep-alive",
    },
  });
}

async function runResearch(env: Env, question: string, send: Send): Promise<void> {
  const runId = crypto.randomUUID();
  send("run", { id: runId, question });
  send("status", { phase: "planning", label: "Claude is planning the research" });

  const upstream = await fetch(ANTHROPIC_URL, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": env.ANTHROPIC_API_KEY,
      "anthropic-version": ANTHROPIC_VERSION,
    },
    body: JSON.stringify({
      model: MODEL,
      max_tokens: 6000,
      stream: true,
      system: SYSTEM,
      tools: [{ type: "web_search_20260209", name: "web_search", max_uses: 5 }],
      messages: [{ role: "user", content: question }],
    }),
  });

  if (!upstream.ok || !upstream.body) {
    const detail = await upstream.text().catch(() => "");
    send("error", { message: `Claude API error ${upstream.status}: ${detail.slice(0, 300)}` });
    return;
  }

  const seen = new Set<string>();
  const sources: Source[] = [];
  let report = "";
  let writing = false;
  const blocks = new Map<number, { type: string; buf: string }>();

  const reader = upstream.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const dataLine = frame.split("\n").find((l) => l.startsWith("data:"));
      if (!dataLine) continue;
      let evt: AnthropicEvent;
      try {
        evt = JSON.parse(dataLine.slice(5).trim()) as AnthropicEvent;
      } catch {
        continue;
      }

      if (evt.type === "content_block_start" && evt.content_block) {
        const cb = evt.content_block;
        blocks.set(evt.index ?? 0, { type: cb.type, buf: "" });
        if (cb.type === "server_tool_use" && cb.name === "web_search") {
          send("status", { phase: "searching", label: "Searching the web" });
          send("agent", { agent: "searcher" });
        } else if (cb.type === "web_search_tool_result") {
          send("status", { phase: "verifying", label: "Grounding against sources" });
          for (const r of cb.content ?? []) {
            if (r.type !== "web_search_result" || !r.url) continue;
            if (seen.has(r.url)) continue;
            seen.add(r.url);
            const s = { url: r.url, title: r.title ?? r.url };
            sources.push(s);
            send("source", { url: s.url, title: s.title, snippet: "" });
          }
        }
      } else if (evt.type === "content_block_delta" && evt.delta) {
        const d = evt.delta;
        if (d.type === "text_delta" && d.text) {
          if (!writing) {
            writing = true;
            send("status", { phase: "writing", label: "Writer composing the cited report" });
          }
          report += d.text;
          send("token", { delta: d.text });
        } else if (d.type === "input_json_delta" && d.partial_json) {
          const b = blocks.get(evt.index ?? 0);
          if (b) b.buf += d.partial_json;
        }
      } else if (evt.type === "content_block_stop") {
        const b = blocks.get(evt.index ?? 0);
        if (b && b.type === "server_tool_use" && b.buf) {
          try {
            const input = JSON.parse(b.buf) as { query?: string };
            if (input.query) send("agent", { agent: "searcher", query: input.query });
          } catch {
            /* ignore partial json */
          }
        }
      } else if (evt.type === "error") {
        send("error", { message: evt.error?.message ?? "stream error" });
        return;
      }
    }
  }

  await env.DB.prepare(
    "INSERT INTO runs (id, question, status, report, model) VALUES (?, ?, 'done', ?, ?)",
  )
    .bind(runId, question, report, MODEL)
    .run();
  if (sources.length > 0) {
    const stmt = env.DB.prepare(
      "INSERT INTO sources (run_id, url, title, snippet) VALUES (?, ?, ?, ?)",
    );
    await env.DB.batch(sources.map((s) => stmt.bind(runId, s.url, s.title, "")));
  }

  send("done", { id: runId, sources: sources.length });
}

interface AnthropicEvent {
  type: string;
  index?: number;
  content_block?: {
    type: string;
    name?: string;
    content?: { type: string; url?: string; title?: string }[];
  };
  delta?: { type: string; text?: string; partial_json?: string };
  error?: { message?: string };
}
