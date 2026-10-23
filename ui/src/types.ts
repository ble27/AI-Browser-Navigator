/** Pill preferences the user can change while a page is open. */
export interface VoiceSettings {
  scroll: "small" | "medium" | "large";
  typing: "fast" | "steady";
  textSize: "default" | "large";
  highContrast: boolean;
}

export const defaultSettings: VoiceSettings = {
  scroll: "medium",
  typing: "fast",
  textSize: "default",
  highContrast: false,
};

/** True when `value` has every settings field and each value is allowed. */
export function isVoiceSettings(value: unknown): value is VoiceSettings {
  if (typeof value !== "object" || value === null) return false;
  const settings = value as Record<string, unknown>;
  return (
    (settings["scroll"] === "small" ||
      settings["scroll"] === "medium" ||
      settings["scroll"] === "large") &&
    (settings["typing"] === "fast" || settings["typing"] === "steady") &&
    (settings["textSize"] === "default" || settings["textSize"] === "large") &&
    typeof settings["highContrast"] === "boolean"
  );
}

/** Events streamed by the Python bridge at `/api/events`. */
export type AgentEvent =
  | { type: "state"; enabled: boolean; events: AgentEvent[]; settings?: VoiceSettings }
  | { type: "enabled"; enabled: boolean }
  | { type: "settings" } & VoiceSettings
  | { type: "transcript"; kind: "partial" | "final"; text: string }
  | { type: "log"; line: string }
  | { type: "step"; outcome: StepOutcome; label: string; detail: string };

export type StepOutcome = "done" | "skipped_paused" | "failed" | "cancelled";
