import { useEffect, useRef, useState } from "react";

/** The slice of the Web Speech `SpeechRecognition` API we use. */
export interface RecognitionLike {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: RecognitionResultEvent) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}

export interface RecognitionResultEvent {
  resultIndex: number;
  results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }>;
}

export type RecognitionFactory = () => RecognitionLike | null;

type SpeechWindow = Window & {
  SpeechRecognition?: new () => RecognitionLike;
  webkitSpeechRecognition?: new () => RecognitionLike;
};

/** Build a recognizer from the browser, or `null` outside Chrome-like browsers. */
export const browserRecognitionFactory: RecognitionFactory = () => {
  const speechWindow = window as SpeechWindow;
  const Ctor = speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition;
  return Ctor === undefined ? null : new Ctor();
};

export interface SpeechRecognitionState {
  supported: boolean;
  error: string | null;
}

/** Errors that just mean "nothing heard" or "we stopped it"; not worth showing. */
const QUIET_ERRORS = new Set(["no-speech", "aborted"]);

/**
 * Run continuous speech recognition while `active`, reporting interim and
 * final text. Chrome ends sessions on its own after silence, so we restart
 * while still active. Stops completely when `active` turns false.
 */
export function useSpeechRecognition(
  active: boolean,
  onTranscript: (kind: "partial" | "final", text: string) => void,
  factory: RecognitionFactory = browserRecognitionFactory,
): SpeechRecognitionState {
  const [supported, setSupported] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const handlerRef = useRef(onTranscript);
  handlerRef.current = onTranscript;
  const factoryRef = useRef(factory);
  factoryRef.current = factory;

  useEffect(() => {
    if (!active) {
      setError(null);
      return;
    }
    const recognition = factoryRef.current();
    if (recognition === null) {
      setSupported(false);
      return;
    }
    setSupported(true);
    setError(null);
    let running = true;
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";

    recognition.onresult = (event) => {
      let finalText = "";
      let interim = "";
      for (let index = event.resultIndex; index < event.results.length; index++) {
        const result = event.results[index];
        if (result === undefined) continue;
        if (result.isFinal) finalText += result[0].transcript;
        else interim += result[0].transcript;
      }
      // Same precedence as the original control page: a final wins over interim.
      if (finalText.trim()) handlerRef.current("final", finalText.trim());
      else if (interim.trim()) handlerRef.current("partial", interim.trim());
    };
    recognition.onerror = (event) => {
      if (event.error === "not-allowed") {
        running = false;
        setError("Microphone blocked");
      } else if (!QUIET_ERRORS.has(event.error)) {
        setError(`Recognition error: ${event.error}`);
      }
    };
    recognition.onend = () => {
      if (!running) return;
      try {
        recognition.start();
      } catch {
        // Already running; Chrome throws if start() races a restart.
      }
    };

    try {
      recognition.start();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start recognition");
    }

    return () => {
      running = false;
      recognition.onresult = null;
      recognition.onerror = null;
      recognition.onend = null;
      recognition.stop();
    };
  }, [active]);

  return { supported, error };
}
