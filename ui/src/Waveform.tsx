import { BAR_COUNT, silentLevels } from "./audioLevels";

interface WaveformProps {
  /** Newest level last; values in [0, 1]. */
  levels?: readonly number[];
  /** Dim and flatten the bars when the mic is not live. */
  active: boolean;
}

const MIN_HEIGHT = 0.12;

const clamp = (value: number): number => (Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0);

/** Soundwave bars. Heights are the level history, mirrored around the centre line. */
export function Waveform({ levels = silentLevels(), active }: WaveformProps): JSX.Element {
  const padded = [...silentLevels(Math.max(0, BAR_COUNT - levels.length)), ...levels].slice(-BAR_COUNT);
  return (
    <div
      className="waveform"
      data-active={active}
      role="img"
      aria-label={active ? "Microphone input level" : "Microphone idle"}
    >
      {padded.map((level, index) => {
        const height = active ? Math.max(MIN_HEIGHT, clamp(level)) : MIN_HEIGHT;
        return (
          <span
            key={index}
            className="waveform__bar"
            data-testid="wave-bar"
            style={{ height: `${Math.round(height * 100)}%` }}
          />
        );
      })}
    </div>
  );
}
