import { act, renderHook } from "@testing-library/react";
import { useSpeechRecognition, type RecognitionLike, type RecognitionResultEvent } from "./useSpeechRecognition";

class FakeRecognition implements RecognitionLike {
  continuous = false;
  interimResults = false;
  lang = "";
  onresult: ((event: RecognitionResultEvent) => void) | null = null;
  onerror: ((event: { error: string }) => void) | null = null;
  onend: (() => void) | null = null;
  starts = 0;
  stops = 0;
  failNextStart = false;
  start(): void {
    if (this.failNextStart) {
      this.failNextStart = false;
      throw new Error("already started");
    }
    this.starts++;
  }
  stop(): void {
    this.stops++;
  }
  hear(...parts: Array<[string, boolean]>): void {
    act(() =>
      this.onresult?.({
        resultIndex: 0,
        results: parts.map(([transcript, isFinal]) => ({ isFinal, 0: { transcript } })),
      }),
    );
  }
}

describe("useSpeechRecognition", () => {
  it("configures and starts a continuous interim recognizer only while active", () => {
    const rec = new FakeRecognition();
    const { rerender } = renderHook(({ on }) => useSpeechRecognition(on, vi.fn(), () => rec), {
      initialProps: { on: false },
    });
    expect(rec.starts).toBe(0);
    rerender({ on: true });
    expect(rec).toMatchObject({ continuous: true, interimResults: true, lang: "en-US", starts: 1 });
    rerender({ on: false });
    expect(rec.stops).toBe(1);
  });

  it("reports interim as partial and final as final, trimmed", () => {
    const rec = new FakeRecognition();
    const seen: Array<[string, string]> = [];
    renderHook(() => useSpeechRecognition(true, (k, t) => seen.push([k, t]), () => rec));
    rec.hear([" open red", false]);
    rec.hear([" open reddit ", true]);
    expect(seen).toEqual([
      ["partial", "open red"],
      ["final", "open reddit"],
    ]);
  });

  it("prefers the final text when a result batch holds both", () => {
    const rec = new FakeRecognition();
    const seen: string[] = [];
    renderHook(() => useSpeechRecognition(true, (k) => seen.push(k), () => rec));
    rec.hear(["done", true], ["next", false]);
    expect(seen).toEqual(["final"]);
  });

  it("ignores blank results", () => {
    const rec = new FakeRecognition();
    const onTranscript = vi.fn();
    renderHook(() => useSpeechRecognition(true, onTranscript, () => rec));
    rec.hear(["   ", false]);
    expect(onTranscript).not.toHaveBeenCalled();
  });

  it("restarts after Chrome ends the session, and survives a racing start()", () => {
    const rec = new FakeRecognition();
    renderHook(() => useSpeechRecognition(true, vi.fn(), () => rec));
    act(() => rec.onend?.());
    expect(rec.starts).toBe(2);
    rec.failNextStart = true;
    expect(() => act(() => rec.onend?.())).not.toThrow();
  });

  it("does not restart after being deactivated", () => {
    const rec = new FakeRecognition();
    const { rerender } = renderHook(({ on }) => useSpeechRecognition(on, vi.fn(), () => rec), {
      initialProps: { on: true },
    });
    const end = rec.onend;
    rerender({ on: false });
    end?.();
    expect(rec.starts).toBe(1);
  });

  it("surfaces a blocked microphone and stops restarting", () => {
    const rec = new FakeRecognition();
    const { result } = renderHook(() => useSpeechRecognition(true, vi.fn(), () => rec));
    act(() => rec.onerror?.({ error: "not-allowed" }));
    expect(result.current.error).toBe("Microphone blocked");
    act(() => rec.onend?.());
    expect(rec.starts).toBe(1);
  });

  it("clears a previous error once turned off", () => {
    const rec = new FakeRecognition();
    const { result, rerender } = renderHook(({ on }) => useSpeechRecognition(on, vi.fn(), () => rec), {
      initialProps: { on: true },
    });
    act(() => rec.onerror?.({ error: "not-allowed" }));
    rerender({ on: false });
    expect(result.current.error).toBeNull();
  });

  it("stays quiet for no-speech and aborted but reports other errors", () => {
    const rec = new FakeRecognition();
    const { result } = renderHook(() => useSpeechRecognition(true, vi.fn(), () => rec));
    act(() => rec.onerror?.({ error: "no-speech" }));
    act(() => rec.onerror?.({ error: "aborted" }));
    expect(result.current.error).toBeNull();
    act(() => rec.onerror?.({ error: "network" }));
    expect(result.current.error).toBe("Recognition error: network");
  });

  it("flags unsupported browsers", () => {
    const { result } = renderHook(() => useSpeechRecognition(true, vi.fn(), () => null));
    expect(result.current.supported).toBe(false);
  });

  it("uses the latest callback without restarting recognition", () => {
    const rec = new FakeRecognition();
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = renderHook(({ cb }) => useSpeechRecognition(true, cb, () => rec), {
      initialProps: { cb: first },
    });
    rerender({ cb: second });
    rec.hear(["hi", true]);
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledWith("final", "hi");
    expect(rec.starts).toBe(1);
  });
});
