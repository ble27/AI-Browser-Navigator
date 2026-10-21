import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent<string>) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }
  close(): void {}
  send(event: object): void {
    act(() => this.onmessage?.({ data: JSON.stringify(event) } as MessageEvent<string>));
  }
  open(): void {
    act(() => this.onopen?.(new Event("open")));
  }
}

class FakeRecognition {
  static instances: FakeRecognition[] = [];
  continuous = false;
  interimResults = false;
  lang = "";
  onresult: ((event: unknown) => void) | null = null;
  onerror: ((event: { error: string }) => void) | null = null;
  onend: (() => void) | null = null;
  started = false;
  constructor() {
    FakeRecognition.instances.push(this);
  }
  start(): void {
    this.started = true;
  }
  stop(): void {
    this.started = false;
  }
  hear(text: string, isFinal: boolean): void {
    act(() =>
      this.onresult?.({ resultIndex: 0, results: [{ isFinal, 0: { transcript: text } }] }),
    );
  }
}

const fetchMock = vi.fn();

beforeEach(() => {
  FakeEventSource.instances = [];
  FakeRecognition.instances = [];
  fetchMock.mockReset();
  fetchMock.mockImplementation(
    async (url: string, init?: RequestInit) =>
      new Response(url === "/api/enabled" ? init?.body : null, {
        status: url === "/api/enabled" ? 200 : 204,
      }),
  );
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("requestAnimationFrame", () => 0);
  vi.stubGlobal("cancelAnimationFrame", () => undefined);
  Object.defineProperty(window, "webkitSpeechRecognition", {
    configurable: true,
    value: FakeRecognition,
  });
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: () => Promise.reject(new Error("no mic in tests")) },
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  Reflect.deleteProperty(window, "webkitSpeechRecognition");
});

const connect = (): FakeEventSource => {
  const source = FakeEventSource.instances[0];
  if (source === undefined) throw new Error("no event stream opened");
  source.open();
  source.send({ type: "state", enabled: true, events: [] });
  return source;
};

describe("App", () => {
  it("shows reconnecting until the bridge stream is up, then asks to speak", () => {
    render(<App />);
    expect(screen.getByRole("status")).toHaveTextContent("Reconnecting");
    connect();
    expect(screen.getByRole("status")).toHaveTextContent("Say a command");
  });

  it("forwards recognized speech to the pipeline and shows the server's echo", async () => {
    render(<App />);
    const source = connect();
    const recognition = FakeRecognition.instances[0];
    expect(recognition?.started).toBe(true);
    recognition?.hear("open reddit", true);
    expect(fetchMock).toHaveBeenCalledWith(
      "/transcript",
      expect.objectContaining({ body: '{"kind":"final","text":"open reddit"}' }),
    );
    source.send({ type: "transcript", kind: "final", text: "open reddit" });
    expect(screen.getByRole("status")).toHaveTextContent("“open reddit”");
    source.send({ type: "step", outcome: "done", label: "open url", detail: "dispatched" });
    expect(screen.getByRole("status")).toHaveTextContent("Done: open url");
  });

  it("toggling off stops recognition and tells the bridge", async () => {
    const user = userEvent.setup();
    render(<App />);
    connect();
    await user.click(screen.getByRole("switch", { name: "AI assistant" }));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/enabled",
      expect.objectContaining({ body: '{"enabled":false}' }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("AI assistant is off");
    expect(screen.getByRole("switch")).not.toBeChecked();
    expect(FakeRecognition.instances[0]?.started).toBe(false);
  });

  it("surfaces a blocked microphone", () => {
    render(<App />);
    connect();
    act(() => FakeRecognition.instances[0]?.onerror?.({ error: "not-allowed" }));
    expect(screen.getByRole("status")).toHaveTextContent("Microphone blocked");
  });

  it("explains when the browser has no speech recognition", () => {
    Reflect.deleteProperty(window, "webkitSpeechRecognition");
    render(<App />);
    connect();
    expect(screen.getByRole("status")).toHaveTextContent("Speech recognition needs Google Chrome");
  });

  it("does not listen while the bridge is unreachable", () => {
    render(<App />);
    expect(FakeRecognition.instances).toHaveLength(0);
  });
});
