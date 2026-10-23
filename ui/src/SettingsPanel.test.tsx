import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SettingsPanel } from "./SettingsPanel";
import { defaultSettings } from "./types";

describe("SettingsPanel", () => {
  it("reports the scroll, typing, and text choice the user picks", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<SettingsPanel value={defaultSettings} onChange={onChange} />);

    const scroll = screen.getByRole("group", { name: "Scroll distance" });
    await user.click(within(scroll).getByRole("radio", { name: "Large" }));
    expect(onChange).toHaveBeenLastCalledWith({ ...defaultSettings, scroll: "large" });

    const typing = screen.getByRole("group", { name: "Typing response" });
    await user.click(within(typing).getByRole("radio", { name: "Steady" }));
    expect(onChange).toHaveBeenLastCalledWith({ ...defaultSettings, typing: "steady" });

    const text = screen.getByRole("group", { name: "Text size" });
    await user.click(within(text).getByRole("radio", { name: "Large" }));
    expect(onChange).toHaveBeenLastCalledWith({ ...defaultSettings, textSize: "large" });
  });

  it("toggles high contrast without changing the other settings", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const value = { ...defaultSettings, scroll: "small" as const };
    render(<SettingsPanel value={value} onChange={onChange} />);
    await user.click(screen.getByRole("switch", { name: "High contrast" }));
    expect(onChange).toHaveBeenCalledWith({ ...value, highContrast: true });
  });
});
