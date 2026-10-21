import { useEffect, useRef, useState } from "react";
import { BAR_COUNT, createMicMeter, pushLevel, silentLevels, type MicMeterFactory } from "./audioLevels";

export interface MicLevels {
  levels: number[];
  /** Set when the microphone could not be opened (e.g. permission denied). */
  error: string | null;
}

/**
 * Sample the microphone into a scrolling level history while `active`.
 * Releases the mic and resets to a flat line as soon as `active` turns false.
 */
export function useMicLevels(
  active: boolean,
  factory: MicMeterFactory = createMicMeter,
  size = BAR_COUNT,
): MicLevels {
  const [levels, setLevels] = useState<number[]>(() => silentLevels(size));
  const [error, setError] = useState<string | null>(null);
  // Read through a ref so a caller passing an inline factory cannot make the
  // effect restart (and reopen the mic) on every render.
  const factoryRef = useRef(factory);
  factoryRef.current = factory;

  useEffect(() => {
    if (!active) {
      setLevels(silentLevels(size));
      return;
    }
    let cancelled = false;
    let frame = 0;
    let stop: (() => void) | null = null;

    factoryRef.current()
      .then((meter) => {
        if (cancelled) {
          meter.stop();
          return;
        }
        stop = () => meter.stop();
        setError(null);
        const tick = (): void => {
          setLevels((previous) => pushLevel(previous, meter.read(), size));
          frame = requestAnimationFrame(tick);
        };
        frame = requestAnimationFrame(tick);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Microphone unavailable");
      });

    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
      stop?.();
    };
  }, [active, size]);

  return { levels, error };
}
