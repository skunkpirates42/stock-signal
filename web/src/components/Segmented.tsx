export interface SegmentedOption<T extends string> {
  value: T | undefined;
  label: string;
}

export interface SegmentedProps<T extends string> {
  options: SegmentedOption<T>[];
  value: T | undefined;
  onChange: (value: T | undefined) => void;
  label: string;
}

export default function Segmented<T extends string>({ options, value, onChange, label }: SegmentedProps<T>) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.label}
          type="button"
          className={`segmented-option${option.value === value ? " segmented-option-active" : ""}`}
          aria-pressed={option.value === value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
