import type { ReactNode } from "react";

export function Slider(props: {
  label: string; value: number; min: number; max: number; step: number;
  onChange: (v: number) => void; unit?: string; hint?: string; digits?: number;
}) {
  const { label, value, min, max, step, onChange, unit = "", hint, digits = 2 } = props;
  return (
    <label className="field" title={hint}>
      <div className="field-row">
        <span>{label}</span>
        <span className="value">{Number(value).toFixed(digits)}{unit}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))} />
      {hint && <small className="hint">{hint}</small>}
    </label>
  );
}

export function Check({ label, checked, onChange, hint }:
  { label: string; checked: boolean; onChange: (v: boolean) => void; hint?: string }) {
  return (
    <label className="check" title={hint}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>{label}</span>
    </label>
  );
}

export function Color({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="color-field">
      <input type="color" value={value} onChange={(e) => onChange(e.target.value.toUpperCase())} />
      <span>{label}</span>
    </label>
  );
}

export function Section({ title, children, right }: { title: string; children: ReactNode; right?: ReactNode }) {
  return (
    <section className="section">
      <header><h3>{title}</h3>{right}</header>
      {children}
    </section>
  );
}

export function Segmented<T extends string>({ options, value, onChange }:
  { options: { value: T; label: ReactNode; title?: string }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="segmented">
      {options.map((o) => (
        <button key={o.value} title={o.title} className={o.value === value ? "active" : ""} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}
