import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Pill, statusText, type PillProps } from "./Pill";

const base: PillProps = {
  phase: "idle",
  enabled: true,
  connected: true,
  transcript: "",
  message: "",
  levels: [],
  problem: null,
  onToggle: () => {},
};

describe("statusText", () => {
  it.each<[Partial<PillProps>, string]>([
    [{ phase: "idle" }, "Say a command"],
    [{ phase: "listening" }, "Listening…"],
    [{ phase: "listening", transcript: "open red" }, "open red"],
    [{ phase: "working", transcript: "open reddit" }, "“open reddit”"],
    [{ phase: "working" }, "Working…"],
    [{ phase: "done", message: "scroll" }, "Done: scroll"],
    [{ phase: "error", message: "unresolved page step" }, "unresolved page step"],
    [{ phase: "error" }, "Something went wrong"],
    [{ phase: "off", enabled: false }, "AI assistant is off"],
    [{ phase: "idle", connected: false }, "Reconnecting to assistant…"],
    [{ phase: "off", connected: false }, "AI assistant is off"],
    [{ phase: "listening", problem: "Microphone blocked" }, "Microphone blocked"],
  ])("%j -> %s", (overrides, expected) => {
    expect(statusText({ ...base, ...overrides })).toBe(expected);
  });
});

describe("Pill", () => {
  it("exposes the toggle as an accessible switch reflecting enabled", () => {
    const { rerender } = render(<Pill {...base} />);
    const toggle = screen.getByRole("switch", { name: "AI assistant" });
    expect(toggle).toBeChecked();
    rerender(<Pill {...base} enabled={false} phase="off" />);
    expect(toggle).not.toBeChecked();
  });

  it("calls onToggle when the switch is clicked or activated by keyboard", async () => {
    const onToggle = vi.fn();
    const user = userEvent.setup();
    render(<Pill {...base} onToggle={onToggle} />);
    await user.click(screen.getByRole("switch"));
    screen.getByRole("switch").focus();
    await user.keyboard("{Enter}");
    await user.keyboard(" ");
    expect(onToggle).toHaveBeenCalledTimes(3);
  });

  it("announces the status text in a polite live region", () => {
    render(<Pill {...base} phase="listening" transcript="next tab" />);
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("next tab");
    expect(status).toHaveAttribute("aria-live", "polite");
  });

  it("shows a live waveform only while enabled and healthy", () => {
    const { rerender } = render(<Pill {...base} />);
    expect(screen.getByRole("img")).toHaveAccessibleName("Microphone input level");
    rerender(<Pill {...base} enabled={false} phase="off" />);
    expect(screen.getByRole("img")).toHaveAccessibleName("Microphone idle");
    rerender(<Pill {...base} problem="Microphone blocked" />);
    expect(screen.getByRole("img")).toHaveAccessibleName("Microphone idle");
  });

  it("styles by phase, and a problem always looks like an error", () => {
    const { container, rerender } = render(<Pill {...base} phase="working" />);
    expect(container.firstElementChild).toHaveAttribute("data-phase", "working");
    rerender(<Pill {...base} phase="listening" problem="Microphone blocked" />);
    expect(container.firstElementChild).toHaveAttribute("data-phase", "error");
  });
});
