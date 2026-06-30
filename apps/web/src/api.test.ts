import { describe, expect, it } from "vitest";

import { parseSseFrame } from "./api";

describe("parseSseFrame", () => {
  it("parses an event name and JSON data payload", () => {
    const frame = 'event: status\ndata: {"phase":"searching"}';
    expect(parseSseFrame(frame)).toEqual({ event: "status", data: { phase: "searching" } });
  });

  it("defaults the event name to 'message' when none is given", () => {
    const frame = 'data: {"delta":"hi"}';
    expect(parseSseFrame(frame)).toEqual({ event: "message", data: { delta: "hi" } });
  });

  it("concatenates multiple data: lines within a frame", () => {
    const frame = 'event: token\ndata: {"a":1,\ndata: "b":2}';
    expect(parseSseFrame(frame)).toEqual({ event: "token", data: { a: 1, b: 2 } });
  });

  it("returns null for a frame with no data (e.g. a keepalive comment)", () => {
    expect(parseSseFrame(": keepalive")).toBeNull();
    expect(parseSseFrame("event: ping")).toBeNull();
  });

  it("returns null when the data is not valid JSON", () => {
    expect(parseSseFrame("data: not-json")).toBeNull();
  });

  it("trims whitespace after the field colon", () => {
    const frame = 'event:   done   \ndata:   {"sources":3}   ';
    expect(parseSseFrame(frame)).toEqual({ event: "done", data: { sources: 3 } });
  });
});
