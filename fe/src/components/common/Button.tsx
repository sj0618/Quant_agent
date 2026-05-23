import type { ButtonHTMLAttributes, ReactNode } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  variant?: "primary" | "secondary" | "ghost" | "dark";
}

export function Button({ children, variant = "secondary", className = "", type = "button", ...props }: ButtonProps) {
  return (
    <button className={["button", `button--${variant}`, className].filter(Boolean).join(" ")} type={type} {...props}>
      {children}
    </button>
  );
}
