/** Events streamed by the Python bridge at `/api/events`. */
export type AgentEvent =
  | { type: "state"; enabled: boolean; events: AgentEvent[] }
  | { type: "enabled"; enabled: boolean }
  | { type: "transcript"; kind: "partial" | "final"; text: string }
  | { type: "log"; line: string }
  | { type: "step"; outcome: StepOutcome; label: string; detail: string };

export type StepOutcome = "done" | "skipped_paused" | "failed" | "cancelled";
