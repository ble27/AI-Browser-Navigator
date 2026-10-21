import { BAR_COUNT, computeLevel, pushLevel, silentLevels } from "./audioLevels";

describe("computeLevel", () => {
  it("is zero for silence and for an empty frame", () => {
    expect(computeLevel(new Uint8Array(64).fill(128))).toBe(0);
    expect(computeLevel(new Uint8Array(0))).toBe(0);
  });

  it("clamps a full-scale square wave to 1", () => {
    const loud = Uint8Array.from({ length: 64 }, (_, i) => (i % 2 === 0 ? 0 : 255));
    expect(computeLevel(loud)).toBe(1);
  });

  it("scales quiet speech into a visible range", () => {
    const quiet = Uint8Array.from({ length: 64 }, (_, i) => (i % 2 === 0 ? 128 + 16 : 128 - 16));
    const level = computeLevel(quiet);
    expect(level).toBeGreaterThan(0.2);
    expect(level).toBeLessThan(1);
  });

  it("is louder for bigger swings", () => {
    const wave = (amp: number): Uint8Array =>
      Uint8Array.from({ length: 64 }, (_, i) => 128 + (i % 2 === 0 ? amp : -amp));
    expect(computeLevel(wave(30))).toBeGreaterThan(computeLevel(wave(10)));
  });
});

describe("pushLevel", () => {
  it("appends and drops the oldest beyond the size", () => {
    expect(pushLevel([1, 2, 3], 4, 3)).toEqual([2, 3, 4]);
    expect(pushLevel([1], 2, 3)).toEqual([1, 2]);
  });

  it("does not mutate its input", () => {
    const history = [0.1];
    pushLevel(history, 0.2);
    expect(history).toEqual([0.1]);
  });
});

describe("silentLevels", () => {
  it("defaults to one flat frame of bars", () => {
    expect(silentLevels()).toHaveLength(BAR_COUNT);
    expect(silentLevels(3)).toEqual([0, 0, 0]);
  });
});
