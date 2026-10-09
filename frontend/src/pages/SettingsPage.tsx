import { Link } from 'react-router-dom'
import { Moon, Sun, Users } from 'lucide-react'
import { useAuth } from '../auth'
import { PALETTES, useTheme } from '../theme'

function SwatchStrip({
  colors,
  label,
}: {
  colors: { bg: string; surface: string; accent: string; text: string }
  label: string
}) {
  return (
    <span className="palette-swatches" aria-hidden="true">
      <span
        className="palette-swatch"
        style={{ background: colors.bg }}
        title={`${label} background`}
      />
      <span
        className="palette-swatch"
        style={{ background: colors.surface }}
        title={`${label} surface`}
      />
      <span
        className="palette-swatch"
        style={{ background: colors.accent }}
        title={`${label} accent`}
      />
      <span
        className="palette-swatch"
        style={{ background: colors.text }}
        title={`${label} text`}
      />
    </span>
  )
}

/** Theme settings: palette grid + light/dark toggle. Changes persist instantly. */
export function SettingsPage() {
  const { mode, palette, setMode, setPalette } = useTheme()
  const { user } = useAuth()

  return (
    <div className="page-inner">
      <div className="page-head">
        <h1>Settings</h1>
        <p className="muted">Colors apply instantly and stick for your next visit.</p>
      </div>

      <section className="settings-section" aria-labelledby="palette-heading">
        <h2 id="palette-heading">Palette</h2>
        <p>
          Eight curated palettes, each styled for both light and dark mode. Select one to
          make it your shelf’s look.
        </p>
        <div
          className="palette-grid"
          role="group"
          aria-label="Choose a palette"
          aria-live="polite"
        >
          {PALETTES.map((p) => {
            const current = palette === p.id
            return (
              <button
                key={p.id}
                type="button"
                className={`palette-card${current ? ' is-current' : ''}`}
                aria-pressed={current}
                aria-label={`${p.label} palette${current ? ' (current)' : ''}`}
                onClick={() => setPalette(p.id)}
              >
                <SwatchStrip colors={p.light} label={`${p.label} light`} />
                <SwatchStrip colors={p.dark} label={`${p.label} dark`} />
                <span className="palette-name">
                  {p.label}
                  {current && <span className="palette-current">Current</span>}
                </span>
              </button>
            )
          })}
        </div>
      </section>

      <section className="settings-section" aria-labelledby="mode-heading">
        <h2 id="mode-heading">Appearance mode</h2>
        <p>
          Pick a light or dark look here — the sun/moon button in the top bar flips the
          mode from anywhere.
        </p>
        <div className="mode-toggle" role="group" aria-label="Color mode">
          <button
            type="button"
            className={mode === 'light' ? 'is-active' : ''}
            aria-pressed={mode === 'light'}
            onClick={() => setMode('light')}
          >
            <Sun size={15} aria-hidden /> Light
          </button>
          <button
            type="button"
            className={mode === 'dark' ? 'is-active' : ''}
            aria-pressed={mode === 'dark'}
            onClick={() => setMode('dark')}
          >
            <Moon size={15} aria-hidden /> Dark
          </button>
        </div>
      </section>

      {user?.role === 'admin' && (
        <section className="settings-section" aria-labelledby="admin-heading">
          <h2 id="admin-heading">Administration</h2>
          <p>
            Add users, approve or deny pending signups, change roles, and reset
            passwords.
          </p>
          <Link to="/admin" className="btn btn-primary">
            <Users size={15} aria-hidden /> Manage users
          </Link>
        </section>
      )}
    </div>
  )
}