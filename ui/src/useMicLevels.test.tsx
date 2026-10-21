import { act, renderHook } from "@testing-library/react";
import type { MicMeter } from "./audioLevels";
import { useMicLevels } from "./useMicLevels";

function fakeMeter(values: number[]): MicMeter & { stopped: boolean } {
  let index = 0;
  return {
    stopped: false,
    read() {
      return values[Math.min(index++, values.length - 1)] ?? 0;
    },
    stop() {
      this.stopped = true;
    },
  };
}

const flushPromises = async (): Promise<void> => {
  await act(async () => {
    await Promise.resolve();
  });
};

const frame = (): void => {
  act(() => {
    vi.advanceTimersToNextFrame();
  });
};

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["requestAnimationFrame", "cancelAnimationFrame"] });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useMicLevels", () => {
  it("stays flat and never opens the mic while inactive", () => {
    const factory = vi.fn();
    const { result } = renderHook(() => useMicLevels(false, factory, 4));
    expect(result.current.levels).toEqual([0, 0, 0, 0]);
    expect(factory).not.toHaveBeenCalled();
  });

  it("scrolls live levels in on each frame, even with an inline factory", async () => {
    const meter = fakeMeter([0.2, 0.8]);
    const factory = vi.fn(async () => meter);
    const { result } = renderHook(() => useMicLevels(true, async () => factory(), 3));
    await flushPromises();
    frame();
    frame();
    expect(result.current.levels).toEqual([0, 0.2, 0.8]);
    expect(factory).toHaveBeenCalledTimes(1);
  });

  it("releases the mic and flattens when turned off", async () => {
    const meter = fakeMeter([0.5]);
    const { result, rerender } = renderHook(({ on }) => useMicLevels(on, async () => meter, 3), {
      initialProps: { on: true },
    });
    await flushPromises();
    frame();
    expect(result.current.levels).toEqual([0, 0, 0.5]);
    rerender({ on: false });
    expect(meter.stopped).toBe(true);
    expect(result.current.levels).toEqual([0, 0, 0]);
    frame();
    expect(result.current.levels).toEqual([0, 0, 0]);
  });

  it("releases a mic that finishes opening after the hook was turned off", async () => {
    const meter = fakeMeter([0.5]);
    let resolve: (value: typeof meter) => void = () => {};
    const { rerender, result } = renderHook(
      ({ on }) => useMicLevels(on, () => new Promise<typeof meter>((r) => (resolve = r)), 3),
      { initialProps: { on: true } },
    );
    rerender({ on: false });
    await act(async () => resolve(meter));
    expect(meter.stopped).toBe(true);
    frame();
    expect(result.current.levels).toEqual([0, 0, 0]);
  });

  it("reports a permission error instead of throwing", async () => {
    const { result } = renderHook(() =>
      useMicLevels(true, () => Promise.reject(new Error("Permission denied")), 3),
    );
    await flushPromises();
    expect(result.current.error).toBe("Permission denied");
  });

  it("clears a previous error once turned off", async () => {
    const { result, rerender } = renderHook(
      ({ on }) => useMicLevels(on, () => Promise.reject(new Error("Permission denied")), 3),
      { initialProps: { on: true } },
    );
    await flushPromises();
    rerender({ on: false });
    expect(result.current.error).toBeNull();
  });
});
