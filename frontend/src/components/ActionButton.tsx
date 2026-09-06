// Large, accessible, color-coded action button.

import type { ButtonHTMLAttributes } from "react"

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  color: "green" | "blue" | "orange" | "red" | "purple" | "ghost"
  icon: string
  label: string
  sublabel?: string
}

export function ActionButton({
  color,
  icon,
  label,
  sublabel,
  ...rest
}: Props) {
  return (
    <button
      type="button"
      className={`action-btn ${color}`}
      {...rest}
    >
      <span className="icon" aria-hidden="true">{icon}</span>
      <span className="label">
        {label}
        {sublabel && <span className="sublabel">{sublabel}</span>}
      </span>
    </button>
  )
}
