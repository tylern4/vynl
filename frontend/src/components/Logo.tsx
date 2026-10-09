/**
 * vynl logo mark — a stylized vinyl record with its brand "V" cut into the
 * center label.
 *
 * An inline SVG so it picks up the live theme tokens: the record body uses
 * `currentColor` (resolved to `--accent-ink` by `.brand svg` / `.auth-title
 * svg`), the label uses `--accent`, and the "V" uses `--on-accent` — so the
 * mark re-tints itself for every palette in light and dark mode.
 */
export function Logo({ size = 26 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      role="img"
      aria-label="vynl"
    >
      {/* grooved record body */}
      <circle cx="16" cy="16" r="14" fill="currentColor" />
      <g fill="none" stroke="currentColor" strokeWidth="1" opacity="0.22">
        <circle cx="16" cy="16" r="11.6" />
        <circle cx="16" cy="16" r="10.4" />
        <circle cx="16" cy="16" r="9.2" />
      </g>
      {/* center label */}
      <circle cx="16" cy="16" r="6.6" fill="var(--accent)" />
      <circle
        cx="16"
        cy="16"
        r="6.6"
        stroke="var(--accent-dark)"
        strokeWidth="1"
      />
      {/* brand V — arm tips up at y=13, apex down at y=19.4 */}
      <path
        d="M12 13 L16 19.4 L20 13"
        stroke="var(--on-accent)"
        strokeWidth="1.9"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}