import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import {
  openEventStream,
  setEnabled as postEnabled,
  updateSettings as postSettings,
  type EventSourceFactory,
} from "./api";
import { initialPillState, pillReducer, type PillState } from "./pillState";
import { defaultSettings, isVoiceSettings, pickSettings, type VoiceSettings } from "./types";

/** How long a result ("done" / error) stays on screen before returning to idle. */
export const SETTLE_MS = 2500;

export interface AgentStatusOptions {
  streamFactory?: EventSourceFactory;
  setEnabledRequest?: (enabled: boolean) => Promise<boolean>;
  updateSettingsRequest?: (settings: VoiceSettings) => Promise<VoiceSettings>;
  settleMs?: number;
}

export interface AgentStatus extends PillState {
  /** Flip the agent on/off via the bridge. */
  toggle: () => void;
  /** Set when the last toggle request could not reach the bridge. */
  toggleError: boolean;
  settings: VoiceSettings;
  /** Save a new settings object. Reverts locally if the bridge rejects it. */
  updateSettings: (settings: VoiceSettings) => void;
}

/** Subscribe to the bridge, derive the pill's state, and expose the toggle. */
export function useAgentStatus(options: AgentStatusOptions = {}): AgentStatus {
  const {
    streamFactory,
    setEnabledRequest = postEnabled,
    updateSettingsRequest = postSettings,
    settleMs = SETTLE_MS,
  } = options;
  const [state, dispatch] = useReducer(pillReducer, initialPillState);
  const [settings, setSettings] = useState(defaultSettings);
  const [toggleError, setToggleError] = useReducer((_: boolean, next: boolean) => next, false);
  const settingsRef = useRef(settings);
  settingsRef.current = settings;
  const stateRef = useRef(state);
  stateRef.current = state;
  const requestRef = useRef(setEnabledRequest);
  requestRef.current = setEnabledRequest;

  useEffect(
    () =>
      openEventStream(
        {
          onEvent: (event) => {
            dispatch({ kind: "event", event });
            if (event.type === "settings") setSettings(pickSettings(event));
            if (event.type === "state" && isVoiceSettings(event.settings)) {
              setSettings(pickSettings(event.settings));
            }
          },
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

  const updateSettings = useCallback((next: VoiceSettings) => {
    const previous = settingsRef.current;
    const clean = pickSettings(next);
    setSettings(clean);
    void updateSettingsRequest(clean).catch(() => setSettings(previous));
  }, [updateSettingsRequest]);

  return { ...state, toggle, toggleError, settings, updateSettings };
}
