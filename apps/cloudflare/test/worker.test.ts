import { describe, expect, it, vi } from "vitest";

import worker, { redactPII } from "../src/index.ts";

describe("redactPII", () => {
  it("masks US SSNs (dashed and run-together)", () => {
    expect(redactPII("my ssn is 123-45-6789")).toBe("my ssn is [redacted-ssn]");
    expect(redactPII("ssn 123456789 leaked")).toBe("ssn [redacted-ssn] leaked");
  });

  it("masks email addresses", () => {
    expect(redactPII("reach me at jane.doe@example.com please")).toBe(
      "reach me at [redacted-email] please",
    );
  });

  it("masks Luhn-valid credit-card numbers but leaves random long digit runs", () => {
    // 4242 4242 4242 4242 is a Luhn-valid test card.
    expect(redactPII("card 4242 4242 4242 4242")).toBe("card [redacted-cc]");
    // A non-Luhn 16-digit run (e.g. an order id) should survive.
    expect(redactPII("order 1234567890123456")).toBe("order 1234567890123456");
  });

  it("masks phone numbers in common formats", () => {
    expect(redactPII("call 555-123-4567")).toContain("[redacted-phone]");
    expect(redactPII("call +1 (555) 123-4567")).toContain("[redacted-phone]");
  });

  it("leaves text with no PII untouched", () => {
    const clean = "my passwords showed up in a data breach";
    expect(redactPII(clean)).toBe(clean);
  });
});

/** Minimal D1 mock that records every executed statement. */
function mockEnv() {
  const calls: { sql: string; bound?: unknown[] }[] = [];
  const makeStmt = (sql: string) => ({
    sql,
    bound: undefined as unknown[] | undefined,
    bind(...args: unknown[]) {
      this.bound = args;
      return this;
    },
    async run() {
      calls.push({ sql, bound: this.bound });
      return {};
    },
  });
  const DB = {
    prepare: vi.fn((sql: string) => makeStmt(sql)),
    batch: vi.fn(async (stmts: { sql: string; bound?: unknown[] }[]) => {
      for (const s of stmts) calls.push({ sql: s.sql, bound: s.bound });
      return [];
    }),
  };
  const env = {
    DB,
    ANTHROPIC_API_KEY: "test",
    ASSETS: { fetch: async () => new Response("asset", { status: 200 }) },
  } as unknown as import("../src/index.ts").Env;
  return { env, calls, DB };
}

describe("DELETE /api/runs/:id", () => {
  it("deletes the run and its sources and returns 204", async () => {
    const { env, calls, DB } = mockEnv();
    const req = new Request("https://example.com/api/runs/abc-123-uuid", { method: "DELETE" });
    const res = await worker.fetch(req, env);

    expect(res.status).toBe(204);
    expect(DB.batch).toHaveBeenCalledOnce();
    expect(calls.some((c) => /DELETE FROM sources WHERE run_id = \?/.test(c.sql))).toBe(true);
    expect(calls.some((c) => /DELETE FROM runs WHERE id = \?/.test(c.sql))).toBe(true);
    // Both statements bound to the path id.
    expect(calls.every((c) => c.bound?.[0] === "abc-123-uuid")).toBe(true);
  });

  it("applies security headers to the response", async () => {
    const { env } = mockEnv();
    const req = new Request("https://example.com/api/runs/abc-123-uuid", { method: "DELETE" });
    const res = await worker.fetch(req, env);

    expect(res.headers.get("content-security-policy")).toContain("default-src 'self'");
    expect(res.headers.get("x-content-type-options")).toBe("nosniff");
    expect(res.headers.get("x-frame-options")).toBe("DENY");
    expect(res.headers.get("strict-transport-security")).toContain("max-age=31536000");
  });
});

describe("scheduled() retention sweep", () => {
  it("purges runs/sources >30 days and stale rate_limits", async () => {
    const { env, calls, DB } = mockEnv();
    const waited: Promise<unknown>[] = [];
    const ctx = { waitUntil: (p: Promise<unknown>) => waited.push(p) } as unknown as ExecutionContext;

    await worker.scheduled?.({} as ScheduledController, env, ctx);
    await Promise.all(waited);

    expect(DB.batch).toHaveBeenCalledOnce();
    expect(calls.some((c) => /DELETE FROM runs WHERE created_at < /.test(c.sql))).toBe(true);
    expect(calls.some((c) => /DELETE FROM sources WHERE run_id IN/.test(c.sql))).toBe(true);
    expect(calls.some((c) => /DELETE FROM rate_limits WHERE day < /.test(c.sql))).toBe(true);
  });
});
