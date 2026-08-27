import type { ReactNode } from "react";

export interface HeroStatProps {
  label: string;
  value: string;
  tone: "positive" | "negative";
  qualifier: ReactNode;
  children?: ReactNode;
}

export default function HeroStat({ label, value, tone, qualifier, children }: HeroStatProps) {
  return (
    <header className="hero">
      <p className="micro">{label}</p>
      <p className={`hero-value num tone-${tone}`}>{value}</p>
      <p className="hero-qualifier">{qualifier}</p>
      {children}
    </header>
  );
}
