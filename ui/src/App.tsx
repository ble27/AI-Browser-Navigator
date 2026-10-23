import { useCallback, useEffect, useState } from "react";
import { postTranscript } from "./api";
import { Pill } from "./Pill";
import { SettingsPanel } from "./SettingsPanel";
import { useAgentStatus } from "./useAgentStatus";
import { useMicLevels } from "./useMicLevels";
import { useSpeechRecognition } from "./useSpeechRecognition";
import "./pill.css";

/** Wires the browser's mic and speech recognizer to the Python agent bridge. */
export function App(): JSX.Element {
  const status = useAgentStatus();
  const { enabled, connected, settings } = status;
  const [settingsOpen, setSettingsOpen] = useState(false);

  useEffect(() => {
    // jsdom's resizeTo only logs that it is unimplemented.
    if (navigator.userAgent.includes("jsdom")) return;
    try {
      window.resizeTo(460, settingsOpen ? 520 : 180);
    } catch {
      // Some embedded windows do not allow the page to resize itself.
    }
  }, [settingsOpen]);

  const forward = useCallback((kind: "partial" | "final", text: string) => {
    // Failures are non-fatal: the next interim result retries naturally, and the
    // SSE connection indicator already tells the user when the bridge is gone.
    void postTranscript(kind, text).catch(() => undefined);
  }, []);

  const speech = useSpeechRecognition(enabled && connected, forward);
  const mic = useMicLevels(enabled && connected);

  // A problem only matters while the assistant is meant to be listening.
  const problem = !enabled
    ? null
    : !speech.supported
      ? "Speech recognition needs Google Chrome"
      : (speech.error ?? mic.error);

  return (
    <div
      className="island"
      data-text-size={settings.textSize}
      data-contrast={settings.highContrast ? "high" : "default"}
    >
      <Pill
        phase={status.phase}
        enabled={enabled}
        connected={connected}
        transcript={status.transcript}
        message={status.toggleError ? "Could not reach the assistant" : status.message}
        levels={mic.levels}
        problem={problem}
        onToggle={status.toggle}
        settingsOpen={settingsOpen}
        onOpenSettings={() => setSettingsOpen((open) => !open)}
      />
      {settingsOpen ? (
        <SettingsPanel value={settings} onChange={status.updateSettings} />
      ) : null}
    </div>
  );
}
