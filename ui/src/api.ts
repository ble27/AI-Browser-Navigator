import { isVoiceSettings, type AgentEvent, type VoiceSettings } from "./types";

/** Minimal slice of `EventSource` we depend on (easy to fake in tests). */
export interface EventSourceLike {
  onopen: ((ev: Event) => void) | null;
  onmessage: ((ev: MessageEvent<string>) => void) | null;
  onerror: ((ev: Event) => void) | null;
  close(): void;
}

export type EventSourceFactory = (url: string) => EventSourceLike;

export interface StreamHandlers {
  onEvent: (event: AgentEvent) => void;
  onConnection: (connected: boolean) => void;
}

const defaultFactory: EventSourceFactory = (url) => new EventSource(url);

/**
 * Subscribe to the bridge's SSE stream. The browser reconnects on its own, so
 * errors only flip the connection flag.
 *
 * @returns A function that closes the stream.
 */
export function openEventStream(
  handlers: StreamHandlers,
  factory: EventSourceFactory = defaultFactory,
  url = "/api/events",
): () => void {
  const source = factory(url);
  source.onopen = () => handlers.onConnection(true);
  source.onerror = () => handlers.onConnection(false);
  source.onmessage = (message) => {
    const event = parseEvent(message.data);
    if (event !== null) handlers.onEvent(event);
  };
  return () => source.close();
}

/** Parse one SSE payload, discarding anything that is not a known event. */
export function parseEvent(raw: string): AgentEvent | null {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof value !== "object" || value === null) return null;
  const event = value as Record<string, unknown>;
  switch (event["type"]) {
    case "state":
      if (typeof event["enabled"] !== "boolean") return null;
      if (event["settings"] !== undefined && !isVoiceSettings(event["settings"])) return null;
      return value as AgentEvent;
    case "settings":
      return isVoiceSettings(event) ? (value as AgentEvent) : null;
    case "enabled":
      return typeof event["enabled"] === "boolean" ? (value as AgentEvent) : null;
    case "transcript":
      return (event["kind"] === "partial" || event["kind"] === "final") &&
        typeof event["text"] === "string"
        ? (value as AgentEvent)
        : null;
    case "step":
      return typeof event["outcome"] === "string" &&
        typeof event["label"] === "string" &&
        typeof event["detail"] === "string"
        ? (value as AgentEvent)
        : null;
    case "log":
      return typeof event["line"] === "string" ? (value as AgentEvent) : null;
    default:
      return null;
  }
}

async function postJson(path: string, body: unknown, fetchImpl: typeof fetch): Promise<Response> {
  const response = await fetchImpl(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`${path} failed with ${response.status}`);
  return response;
}

/** Ask the bridge to turn the voice agent on or off. */
export async function setEnabled(
  enabled: boolean,
  fetchImpl: typeof fetch = fetch,
): Promise<boolean> {
  const response = await postJson("/api/enabled", { enabled }, fetchImpl);
  const body = (await response.json()) as { enabled?: unknown };
  return body.enabled === true;
}

/** Save pill accessibility settings. The bridge echoes them on the event stream. */
export async function updateSettings(
  settings: VoiceSettings,
  fetchImpl: typeof fetch = fetch,
): Promise<VoiceSettings> {
  const response = await postJson("/api/settings", settings, fetchImpl);
  const body: unknown = await response.json();
  if (!isVoiceSettings(body)) throw new Error("/api/settings returned an invalid body");
  return body;
}

/** Forward recognized speech to the agent pipeline. */
export async function postTranscript(
  kind: "partial" | "final",
  text: string,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  await postJson("/transcript", { kind, text }, fetchImpl);
}
