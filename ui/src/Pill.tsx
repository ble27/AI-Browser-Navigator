import type { Phase } from "./pillState";
import { Waveform } from "./Waveform";

export interface PillProps {
  phase: Phase;
  enabled: boolean;
  connected: boolean;
  transcript: string;
  message: string;
  levels: readonly number[];
  /** Mic / recognition problem to show instead of the normal status. */
  problem: string | null;
  onToggle: () => void;
  settingsOpen?: boolean;
  onOpenSettings?: () => void;
}

/** One line of status text for the current state. Problems and lost connection win. */
export function statusText({
  phase,
  connected,
  transcript,
  message,
  problem,
}: Pick<PillProps, "phase" | "connected" | "transcript" | "message" | "problem">): string {
  if (problem !== null) return problem;
  if (phase === "off") return "AI assistant is off";
  if (!connected) return "Reconnecting to assistant…";
  switch (phase) {
    case "listening":
      return transcript || "Listening…";
    case "working":
      return transcript ? `“${transcript}”` : "Working…";
    case "done":
      return `Done: ${message}`;
    case "error":
      return message || "Something went wrong";
    case "idle":
      return "Say a command";
  }
}

/** Dynamic-Island-style pill: on/off switch, live soundwave, and what was heard. */
export function Pill(props: PillProps): JSX.Element {
  const { phase, enabled, connected, levels, problem, onToggle, settingsOpen, onOpenSettings } =
    props;
  const live = enabled && problem === null;
  const text = statusText(props);
  const visualPhase = problem !== null ? "error" : phase;
  return (
    <div className="pill" data-phase={visualPhase} data-connected={connected}>
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        aria-label="AI assistant"
        className="pill__switch"
        onClick={onToggle}
      >
        <span className="pill__knob" />
      </button>
      <Waveform active={live && phase !== "off"} levels={levels} />
      <p className="pill__text" role="status" aria-live="polite">
        {text}
      </p>
      {onOpenSettings !== undefined ? (
        <button
          type="button"
          className="pill__settings"
          aria-expanded={settingsOpen === true}
          aria-controls="accessibility-settings"
          onClick={onOpenSettings}
        >
          Settings
        </button>
      ) : null}
    </div>
  );
}
