/** Number of bars drawn in the pill's soundwave. */
export const BAR_COUNT = 21;

/**
 * Loudness of one analyser frame.
 *
 * `AnalyserNode.getByteTimeDomainData` centres silence at 128, so we take the
 * RMS of the offset from 128. Speech rarely exceeds ~0.3 of full scale, hence
 * the gain before clamping so normal talking visibly fills the bars.
 *
 * @returns A level in [0, 1].
 */
export function computeLevel(samples: Uint8Array, gain = 3): number {
  if (samples.length === 0) return 0;
  let sum = 0;
  for (const sample of samples) {
    const centred = (sample - 128) / 128;
    sum += centred * centred;
  }
  return Math.min(1, Math.sqrt(sum / samples.length) * gain);
}

/** Append a level to a fixed-size scrolling history (oldest drops off). */
export function pushLevel(history: readonly number[], level: number, size = BAR_COUNT): number[] {
  const next = [...history, level];
  return next.length > size ? next.slice(next.length - size) : next;
}

/** A flat history, used when the mic is idle. */
export function silentLevels(size = BAR_COUNT): number[] {
  return new Array<number>(size).fill(0);
}

/** One live microphone level meter. */
export interface MicMeter {
  /** Current loudness in [0, 1]. */
  read(): number;
  /** Release the microphone. */
  stop(): void;
}

export type MicMeterFactory = () => Promise<MicMeter>;

/** Real meter backed by `getUserMedia` and an `AnalyserNode`. */
export const createMicMeter: MicMeterFactory = async () => {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const context = new AudioContext();
  const analyser = context.createAnalyser();
  analyser.fftSize = 256;
  context.createMediaStreamSource(stream).connect(analyser);
  const buffer = new Uint8Array(analyser.fftSize);
  return {
    read: () => {
      analyser.getByteTimeDomainData(buffer);
      return computeLevel(buffer);
    },
    stop: () => {
      stream.getTracks().forEach((track) => track.stop());
      void context.close();
    },
  };
};
