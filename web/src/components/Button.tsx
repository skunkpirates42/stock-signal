import Link from "next/link";
import type { ReactNode } from "react";

interface ButtonAppearance {
  children: ReactNode;
  inline?: boolean;
  className?: string;
}

interface ActionButtonProps extends ButtonAppearance {
  href?: undefined;
  type?: "button" | "submit";
  onClick?: () => void;
  disabled?: boolean;
}

interface LinkButtonProps extends ButtonAppearance {
  href: string;
}

export type ButtonProps = ActionButtonProps | LinkButtonProps;

function buttonClassName({ inline, className }: ButtonAppearance) {
  return ["button", inline && "button-inline", className].filter(Boolean).join(" ");
}

export default function Button(props: ButtonProps) {
  if (props.href !== undefined) {
    return (
      <Link className={buttonClassName(props)} href={props.href}>
        {props.children}
      </Link>
    );
  }
  return (
    <button
      type={props.type ?? "button"}
      className={buttonClassName(props)}
      onClick={props.onClick}
      disabled={props.disabled}
    >
      {props.children}
    </button>
  );
}
