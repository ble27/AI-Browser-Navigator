import type { VoiceSettings } from "./types";

export interface SettingsPanelProps {
  value: VoiceSettings;
  onChange: (settings: VoiceSettings) => void;
}

const SCROLL_OPTIONS = [
  ["small", "Small"],
  ["medium", "Medium"],
  ["large", "Large"],
] as const;

const TYPING_OPTIONS = [
  ["fast", "Fast"],
  ["steady", "Steady"],
] as const;

const TEXT_OPTIONS = [
  ["default", "Default"],
  ["large", "Large"],
] as const;

/** Accessibility controls for scroll distance, dictation timing, and the pill. */
export function SettingsPanel({ value, onChange }: SettingsPanelProps): JSX.Element {
  return (
    <form className="settings" id="accessibility-settings" aria-label="Accessibility settings">
      <ChoiceGroup
        legend="Scroll distance"
        name="scroll"
        options={SCROLL_OPTIONS}
        selected={value.scroll}
        onSelect={(scroll) => onChange({ ...value, scroll })}
      />
      <ChoiceGroup
        legend="Typing response"
        name="typing"
        options={TYPING_OPTIONS}
        selected={value.typing}
        onSelect={(typing) => onChange({ ...value, typing })}
      />
      <ChoiceGroup
        legend="Text size"
        name="textSize"
        options={TEXT_OPTIONS}
        selected={value.textSize}
        onSelect={(textSize) => onChange({ ...value, textSize })}
      />
      <label className="settings__contrast">
        <input
          type="checkbox"
          role="switch"
          checked={value.highContrast}
          onChange={(event) => onChange({ ...value, highContrast: event.target.checked })}
        />
        High contrast
      </label>
    </form>
  );
}

function ChoiceGroup<T extends string>({
  legend,
  name,
  options,
  selected,
  onSelect,
}: {
  legend: string;
  name: string;
  options: readonly (readonly [T, string])[];
  selected: T;
  onSelect: (value: T) => void;
}): JSX.Element {
  return (
    <fieldset className="settings__group">
      <legend>{legend}</legend>
      {options.map(([option, label]) => (
        <label key={option}>
          <input
            type="radio"
            name={name}
            value={option}
            checked={selected === option}
            onChange={() => onSelect(option)}
          />
          {label}
        </label>
      ))}
    </fieldset>
  );
}
