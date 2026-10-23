import { act, renderHook } from "@testing-library/react";
import type { EventSourceLike } from "./api";
import { SETTLE_MS, useAgentStatus } from "./useAgentStatus";

class FakeSource implements EventSourceLike {
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent<string>) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  closed = false;
  close(): void {
    this.closed = true;
  }
  send(event: object): void {
    act(() => this.onmessage?.({ data: JSON.stringify(event) } as MessageEvent<string>));
  }
}

const setup = (request = vi.fn(async (enabled: boolean) => enabled)) => {
  const source = new FakeSource();
  const hook = renderHook(() => useAgentStatus({ streamFactory: () => source, setEnabledRequest: request }));
  return { source, request, ...hook };
};

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("useAgentStatus", () => {
  it("connects, then follows transcript and step events", () => {
    const { source, result } = setup();
    act(() => source.onopen?.(new Event("open")));
    expect(result.current.connected).toBe(true);
    source.send({ type: "transcript", kind: "partial", text: "open red" });
    expect(result.current).toMatchObject({ phase: "listening", transcript: "open red" });
    source.send({ type: "step", outcome: "done", label: "open url", detail: "dispatched" });
    expect(result.current).toMatchObject({ phase: "done", message: "open url" });
  });

  it("settles a finished result back to idle after the delay", () => {
    const { source, result } = setup();
    source.send({ type: "step", outcome: "done", label: "scroll", detail: "" });
    act(() => vi.advanceTimersByTime(SETTLE_MS - 1));
    expect(result.current.phase).toBe("done");
    act(() => vi.advanceTimersByTime(1));
    expect(result.current.phase).toBe("idle");
  });

  it("restarts the settle countdown when a newer result arrives", () => {
    const { source, result } = setup();
    source.send({ type: "step", outcome: "done", label: "a", detail: "" });
    act(() => vi.advanceTimersByTime(SETTLE_MS - 100));
    source.send({ type: "step", outcome: "failed", label: "b", detail: "boom" });
    act(() => vi.advanceTimersByTime(SETTLE_MS - 100));
    expect(result.current.phase).toBe("error");
    act(() => vi.advanceTimersByTime(100));
    expect(result.current.phase).toBe("idle");
  });

  it("toggle asks the bridge for the opposite state and applies the answer", async () => {
    const { result, request } = setup();
    await act(async () => result.current.toggle());
    expect(request).toHaveBeenCalledWith(false);
    expect(result.current).toMatchObject({ enabled: false, phase: "off" });
    await act(async () => result.current.toggle());
    expect(request).toHaveBeenLastCalledWith(true);
    expect(result.current.enabled).toBe(true);
  });

  it("keeps the old state and flags an error when the toggle request fails", async () => {
    const { result } = setup(vi.fn(async () => Promise.reject(new Error("down"))));
    await act(async () => result.current.toggle());
    expect(result.current.enabled).toBe(true);
    expect(result.current.toggleError).toBe(true);
  });

  it("follows an enabled change pushed from the server (e.g. another window)", () => {
    const { source, result } = setup();
    source.send({ type: "enabled", enabled: false });
    expect(result.current.phase).toBe("off");
  });

  it("closes the stream on unmount", () => {
    const { source, unmount } = setup();
    unmount();
    expect(source.closed).toBe(true);
  });

  it("posts only the four settings fields, so a second change is still accepted", async () => {
    const source = new FakeSource();
    const update = vi.fn(async (settings: object) => settings as never);
    const { result } = renderHook(() =>
      useAgentStatus({ streamFactory: () => source, updateSettingsRequest: update }),
    );
    // The bridge echoes every change as an event that carries a "type" key.
    source.send({
      type: "settings",
      scroll: "large",
      typing: "fast",
      textSize: "default",
      highContrast: false,
    });
    await act(async () => result.current.updateSettings({ ...result.current.settings, scroll: "small" }));
    expect(update).toHaveBeenLastCalledWith({
      scroll: "small",
      typing: "fast",
      textSize: "default",
      highContrast: false,
    });
    expect(result.current.settings).not.toHaveProperty("type");
  });
});
