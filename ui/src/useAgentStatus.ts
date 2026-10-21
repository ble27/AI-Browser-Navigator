import { useCallback, useEffect, useReducer, useRef } from "react";
import { openEventStream, setEnabled as postEnabled, type EventSourceFactory } from "./api";
import { initialPillState, pillReducer, type PillState } from "./pillState";

/** How long a result ("done" / error) stays on screen before returning to idle. */
export const SETTLE_MS = 2500;

export interface AgentStatusOptions {
  streamFactory?: EventSourceFactory;
  setEnabledRequest?: (enabled: boolean) => Promise<boolean>;
  settleMs?: number;
}

export interface AgentStatus extends PillState {
  /** Flip the agent on/off via the bridge. */
  toggle: () => void;
  /** Set when the last toggle request could not reach the bridge. */
  toggleError: boolean;
}

/** Subscribe to the bridge, derive the pill's state, and expose the toggle. */
export function useAgentStatus(options: AgentStatusOptions = {}): AgentStatus {
  const { streamFactory, setEnabledRequest = postEnabled, settleMs = SETTLE_MS } = options;
  const [state, dispatch] = useReducer(pillReducer, initialPillState);
  const [toggleError, setToggleError] = useReducer((_: boolean, next: boolean) => next, false);
  const stateRef = useRef(state);
  stateRef.current = state;
  const requestRef = useRef(setEnabledRequest);
  requestRef.current = setEnabledRequest;

  useEffect(
    () =>
      openEventStream(
        {
          onEvent: (event) => dispatch({ kind: "event", event }),
          onConnection: (connected) => dispatch({ kind: "connection", connected }),
        },
        streamFactory,
      ),
    [streamFactory],
  );

  useEffect(() => {
    if (state.phase !== "done" && state.phase !== "error") return;
    const timer = setTimeout(() => dispatch({ kind: "settle" }), settleMs);
    return () => clearTimeout(timer);
  }, [state.phase, state.message, settleMs]);

  const toggle = useCallback(() => {
    const next = !stateRef.current.enabled;
    setToggleError(false);
    requestRef
      .current(next)
      .then((enabled) => dispatch({ kind: "event", event: { type: "enabled", enabled } }))
      .catch(() => setToggleError(true));
  }, []);

  return { ...state, toggle, toggleError };
}
