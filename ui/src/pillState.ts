import type { AgentEvent } from "./types";

/** What the pill is showing right now. */
export type Phase = "off" | "idle" | "listening" | "working" | "done" | "error";

export interface PillState {
  enabled: boolean;
  connected: boolean;
  phase: Phase;
  /** Latest recognized words (interim while listening, final while working). */
  transcript: string;
  /** Short result text such as "click orders" or an error reason. */
  message: string;
}

export type PillAction =
  | { kind: "event"; event: AgentEvent }
  | { kind: "connection"; connected: boolean }
  | { kind: "settle" };

export const initialPillState: PillState = {
  enabled: true,
  connected: false,
  phase: "idle",
  transcript: "",
  message: "",
};

const withEnabled = (state: PillState, enabled: boolean): PillState =>
  enabled
    ? { ...state, enabled, phase: state.phase === "off" ? "idle" : state.phase }
    : { ...state, enabled, phase: "off", transcript: "", message: "" };

/** Pure reducer: every agent event maps to exactly one visible phase. */
export function pillReducer(state: PillState, action: PillAction): PillState {
  switch (action.kind) {
    case "connection":
      return { ...state, connected: action.connected };
    case "settle":
      // Only transient result phases fade back to idle; never override "off".
      return state.phase === "done" || state.phase === "error"
        ? { ...state, phase: "idle", transcript: "", message: "" }
        : state;
    case "event":
      return applyEvent(state, action.event);
  }
}

function applyEvent(state: PillState, event: AgentEvent): PillState {
  switch (event.type) {
    case "state":
      return withEnabled({ ...state, connected: true }, event.enabled);
    case "enabled":
      return withEnabled(state, event.enabled);
    case "transcript":
      if (!state.enabled) return state;
      return {
        ...state,
        phase: event.kind === "final" ? "working" : "listening",
        transcript: event.text,
        message: "",
      };
    case "step":
      if (!state.enabled) return state;
      return applyStep(state, event);
    case "log":
    case "settings":
      return state;
  }
}

function applyStep(state: PillState, event: Extract<AgentEvent, { type: "step" }>): PillState {
  switch (event.outcome) {
    case "done":
      // An earlier failure in the same utterance stays visible.
      return state.phase === "error" ? state : { ...state, phase: "done", message: event.label };
    case "failed":
      return { ...state, phase: "error", message: event.detail || event.label };
    case "skipped_paused":
      return { ...state, phase: "error", message: "Input paused" };
    case "cancelled":
      return state;
  }
}
