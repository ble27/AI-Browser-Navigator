import { openEventStream, parseEvent, postTranscript, setEnabled, type EventSourceLike } from "./api";

class FakeSource implements EventSourceLike {
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent<string>) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  closed = false;
  close(): void {
    this.closed = true;
  }
  emit(data: string): void {
    this.onmessage?.({ data } as MessageEvent<string>);
  }
}

describe("parseEvent", () => {
  it.each([
    ['{"type":"transcript","kind":"final","text":"hi"}', "transcript"],
    ['{"type":"step","outcome":"done","label":"scroll","detail":"ok"}', "step"],
    ['{"type":"enabled","enabled":false}', "enabled"],
    ['{"type":"state","enabled":true,"events":[]}', "state"],
    ['{"type":"log","line":"x"}', "log"],
    [
      '{"type":"settings","scroll":"small","typing":"steady","textSize":"large","highContrast":true}',
      "settings",
    ],
  ])("accepts %s", (raw, type) => {
    expect(parseEvent(raw)?.type).toBe(type);
  });

  it.each([
    "not json",
    "null",
    "42",
    '{"type":"mystery"}',
    '{"type":"transcript","kind":"loud","text":"hi"}',
    '{"type":"transcript","kind":"final","text":5}',
    '{"type":"enabled","enabled":"yes"}',
    '{"type":"step","outcome":"done"}',
    '{"type":"settings","scroll":"huge","typing":"fast","textSize":"default","highContrast":false}',
    "",
  ])("rejects %s", (raw) => {
    expect(parseEvent(raw)).toBeNull();
  });
});

describe("openEventStream", () => {
  it("forwards valid events, drops junk, and reports connection state", () => {
    const source = new FakeSource();
    const events: string[] = [];
    const connection: boolean[] = [];
    const close = openEventStream(
      { onEvent: (e) => events.push(e.type), onConnection: (c) => connection.push(c) },
      () => source,
    );
    source.onopen?.(new Event("open"));
    source.emit('{"type":"log","line":"a"}');
    source.emit("garbage");
    source.onerror?.(new Event("error"));
    expect(events).toEqual(["log"]);
    expect(connection).toEqual([true, false]);
    close();
    expect(source.closed).toBe(true);
  });

  it("subscribes to the events endpoint", () => {
    let seen = "";
    openEventStream({ onEvent: () => {}, onConnection: () => {} }, (url) => {
      seen = url;
      return new FakeSource();
    });
    expect(seen).toBe("/api/events");
  });
});

describe("requests", () => {
  const okJson = (body: unknown): typeof fetch =>
    vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })) as unknown as typeof fetch;

  it("setEnabled posts the flag and returns the server's answer", async () => {
    const fetchImpl = okJson({ enabled: false });
    await expect(setEnabled(false, fetchImpl)).resolves.toBe(false);
    expect(fetchImpl).toHaveBeenCalledWith(
      "/api/enabled",
      expect.objectContaining({ method: "POST", body: '{"enabled":false}' }),
    );
  });

  it("setEnabled rejects on a server error", async () => {
    const fetchImpl = vi.fn(async () => new Response("", { status: 500 })) as unknown as typeof fetch;
    await expect(setEnabled(true, fetchImpl)).rejects.toThrow("500");
  });

  it("postTranscript sends kind and text to /transcript", async () => {
    const fetchImpl = vi.fn(async () => new Response(null, { status: 204 })) as unknown as typeof fetch;
    await postTranscript("final", "next tab", fetchImpl);
    expect(fetchImpl).toHaveBeenCalledWith(
      "/transcript",
      expect.objectContaining({ body: '{"kind":"final","text":"next tab"}' }),
    );
  });
});
