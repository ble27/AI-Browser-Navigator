import { initialPillState, pillReducer, type PillState } from "./pillState";
import type { AgentEvent } from "./types";

const run = (events: AgentEvent[], from: PillState = initialPillState): PillState =>
  events.reduce((state, event) => pillReducer(state, { kind: "event", event }), from);

describe("pillReducer", () => {
  it("starts idle and enabled", () => {
    expect(initialPillState).toMatchObject({ enabled: true, phase: "idle", connected: false });
  });

  it("marks connected and adopts the server's enabled flag from the state event", () => {
    const state = run([{ type: "state", enabled: false, events: [] }]);
    expect(state).toMatchObject({ connected: true, enabled: false, phase: "off" });
  });

  it("shows interim words as listening and final words as working", () => {
    let state = run([{ type: "transcript", kind: "partial", text: "open red" }]);
    expect(state).toMatchObject({ phase: "listening", transcript: "open red" });
    state = run([{ type: "transcript", kind: "final", text: "open reddit" }], state);
    expect(state).toMatchObject({ phase: "working", transcript: "open reddit" });
  });

  it("reports a completed step", () => {
    const state = run([
      { type: "transcript", kind: "final", text: "scroll down" },
      { type: "step", outcome: "done", label: "scroll", detail: "dispatched" },
    ]);
    expect(state).toMatchObject({ phase: "done", message: "scroll" });
  });

  it("keeps an error visible even when a later step in the same burst succeeds", () => {
    const state = run([
      { type: "step", outcome: "failed", label: "click orders", detail: "unresolved page step" },
      { type: "step", outcome: "done", label: "scroll", detail: "dispatched" },
    ]);
    expect(state).toMatchObject({ phase: "error", message: "unresolved page step" });
  });

  it("surfaces safe-pause skips as an error and ignores cancelled steps", () => {
    expect(run([{ type: "step", outcome: "skipped_paused", label: "x", detail: "" }])).toMatchObject({
      phase: "error",
      message: "Input paused",
    });
    expect(run([{ type: "step", outcome: "cancelled", label: "x", detail: "" }]).phase).toBe("idle");
  });

  it("a new transcript clears a previous error", () => {
    const state = run([
      { type: "step", outcome: "failed", label: "a", detail: "boom" },
      { type: "transcript", kind: "partial", text: "next" },
    ]);
    expect(state).toMatchObject({ phase: "listening", message: "" });
  });

  it("turning off clears the display and ignores later speech or steps", () => {
    let state = run([
      { type: "transcript", kind: "partial", text: "hello" },
      { type: "enabled", enabled: false },
    ]);
    expect(state).toMatchObject({ phase: "off", transcript: "", enabled: false });
    state = run(
      [
        { type: "transcript", kind: "final", text: "open reddit" },
        { type: "step", outcome: "done", label: "open url", detail: "" },
      ],
      state,
    );
    expect(state.phase).toBe("off");
  });

  it("turning back on returns to idle", () => {
    const off = run([{ type: "enabled", enabled: false }]);
    expect(run([{ type: "enabled", enabled: true }], off)).toMatchObject({ phase: "idle", enabled: true });
  });

  it("settle returns done/error to idle but leaves other phases alone", () => {
    const done = run([{ type: "step", outcome: "done", label: "scroll", detail: "" }]);
    expect(pillReducer(done, { kind: "settle" })).toMatchObject({ phase: "idle", message: "" });
    const listening = run([{ type: "transcript", kind: "partial", text: "hi" }]);
    expect(pillReducer(listening, { kind: "settle" })).toBe(listening);
    const off = run([{ type: "enabled", enabled: false }]);
    expect(pillReducer(off, { kind: "settle" })).toBe(off);
  });

  it("tracks connection loss without changing the phase", () => {
    const state = pillReducer(initialPillState, { kind: "connection", connected: true });
    expect(pillReducer(state, { kind: "connection", connected: false })).toMatchObject({
      connected: false,
      phase: "idle",
    });
  });

  it("ignores log lines", () => {
    expect(run([{ type: "log", line: "[final] x" }])).toBe(initialPillState);
  });
});
