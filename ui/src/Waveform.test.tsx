import { render, screen } from "@testing-library/react";
import { BAR_COUNT } from "./audioLevels";
import { Waveform } from "./Waveform";

const heights = (): string[] => screen.getAllByTestId("wave-bar").map((bar) => bar.style.height);

describe("Waveform", () => {
  it("always renders a fixed number of bars", () => {
    const { rerender } = render(<Waveform active levels={[0.5]} />);
    expect(screen.getAllByTestId("wave-bar")).toHaveLength(BAR_COUNT);
    rerender(<Waveform active levels={new Array(100).fill(0.5)} />);
    expect(screen.getAllByTestId("wave-bar")).toHaveLength(BAR_COUNT);
  });

  it("draws the newest level on the right edge", () => {
    render(<Waveform active levels={[0, 1]} />);
    const rendered = heights();
    expect(rendered[BAR_COUNT - 1]).toBe("100%");
    expect(rendered[BAR_COUNT - 2]).toBe("12%");
  });

  it("clamps out-of-range and non-finite levels", () => {
    render(<Waveform active levels={[5, -3, Number.NaN]} />);
    const rendered = heights();
    expect(rendered.slice(-3)).toEqual(["100%", "12%", "12%"]);
  });

  it("flattens and relabels when inactive", () => {
    render(<Waveform active={false} levels={[1, 1, 1]} />);
    expect(new Set(heights())).toEqual(new Set(["12%"]));
    expect(screen.getByRole("img")).toHaveAccessibleName("Microphone idle");
  });

  it("is labelled as the live input meter when active", () => {
    render(<Waveform active />);
    expect(screen.getByRole("img")).toHaveAccessibleName("Microphone input level");
  });
});
