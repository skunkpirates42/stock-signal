import type { ReactNode } from "react";

export interface CardProps {
  title?: ReactNode;
  titleVariant?: "heading" | "label";
  note?: ReactNode;
  className?: string;
  children?: ReactNode;
}

export default function Card({
  title,
  titleVariant = "heading",
  note,
  className,
  children,
}: CardProps) {
  return (
    <section className={className ? `card ${className}` : "card"}>
      {title && <h2 className={titleVariant === "label" ? "micro" : undefined}>{title}</h2>}
      {note && <p className="card-note">{note}</p>}
      {children}
    </section>
  );
}
