import { useState } from 'react'
import { Plus, X } from 'lucide-react'
import type { Tag } from '../types'

interface TagEditorProps {
  /** The album's current tag names. */
  tags: string[]
  /** The user's existing tags (for autocomplete suggestions). */
  suggestions: Tag[]
  onAdd: (name: string) => void
  onRemove: (name: string) => void
  disabled?: boolean
}

/**
 * Chip-based tag editor: × removal per chip, free-text input with
 * suggestions drawn from the user's existing tags.
 */
export function TagEditor({ tags, suggestions, onAdd, onRemove, disabled }: TagEditorProps) {
  const [input, setInput] = useState('')
  const query = input.trim().toLowerCase()

  function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!query || tags.includes(query)) return
    onAdd(query)
    setInput('')
  }

  const matches = (
    query
      ? suggestions.filter((t) => t.name.includes(query))
      : []
  )
    .map((t) => t.name)
    .filter((name) => !tags.includes(name))
    .slice(0, 6)

  return (
    <div className="tag-editor">
      <div className="tag-chip-row">
        {tags.length === 0 && <span className="muted">No tags yet.</span>}
        {tags.map((tag) => (
          <span key={tag} className="tag-chip">
            {tag}
            <button
              type="button"
              className="tag-chip-remove"
              aria-label={`Remove tag ${tag}`}
              disabled={disabled}
              onClick={() => onRemove(tag)}
            >
              <X size={12} aria-hidden />
            </button>
          </span>
        ))}
      </div>

      <form className="tag-add-form" onSubmit={submit}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Add a tag…"
          aria-label="Add a tag"
          disabled={disabled}
        />
        <button
          type="submit"
          className="btn btn-sm"
          disabled={disabled || !query || tags.includes(query)}
        >
          <Plus size={14} aria-hidden /> Add
        </button>
      </form>

      {matches.length > 0 && (
        <div className="tag-suggestions" role="group" aria-label="Suggested tags">
          {matches.map((name) => (
            <button
              key={name}
              type="button"
              className="tag-chip tag-chip-btn"
              disabled={disabled}
              onClick={() => {
                onAdd(name)
                setInput('')
              }}
            >
              {name}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
