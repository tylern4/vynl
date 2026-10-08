import { useEffect, useRef, useState } from 'react'
import { Camera, ImagePlus, Trash2 } from 'lucide-react'
import { normalizeCoverFile } from './coverNormalize'

interface CoverPickerProps {
  /** Fired whenever the normalized cover changes; `null` when removed. */
  onChange: (blob: Blob | null) => void
  disabled?: boolean
}

/**
 * Reusable cover chooser (issue #11): file upload + phone camera capture,
 * both normalized to a ~2000 px JPEG before the caller uploads it. Shows the
 * normalized preview plus remove/retake controls and a busy state while
 * processing. The parent owns the selected blob (via `onChange`) so it can
 * upload it after album creation or on demand.
 */
export function CoverPicker({ onChange, disabled = false }: CoverPickerProps) {
  const fileRef = useRef<HTMLInputElement>(null)
  const cameraRef = useRef<HTMLInputElement>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Revoke the previous preview object URL when it is replaced or unmounted.
  useEffect(() => {
    if (!previewUrl) return
    return () => URL.revokeObjectURL(previewUrl)
  }, [previewUrl])

  async function pick(file: File | undefined) {
    if (!file || disabled) return
    setBusy(true)
    setError(null)
    try {
      const blob = await normalizeCoverFile(file)
      setPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev)
        return URL.createObjectURL(blob)
      })
      onChange(blob)
    } catch {
      setError('Could not read that image — try a JPEG or PNG.')
    } finally {
      setBusy(false)
      // Reset the inputs so choosing the same file again re-fires change.
      if (fileRef.current) fileRef.current.value = ''
      if (cameraRef.current) cameraRef.current.value = ''
    }
  }

  function removeCover() {
    setPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev)
      return null
    })
    setError(null)
    onChange(null)
  }

  return (
    <div className="cover-picker">
      <div className="cover-picker-controls">
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          aria-label="Upload cover image"
          className="visually-hidden"
          disabled={disabled || busy}
          onChange={(e) => pick(e.target.files?.[0])}
        />
        <input
          ref={cameraRef}
          type="file"
          accept="image/*"
          capture="environment"
          aria-label="Take cover photo"
          className="visually-hidden"
          disabled={disabled || busy}
          onChange={(e) => pick(e.target.files?.[0])}
        />
        <button
          type="button"
          className="btn btn-sm"
          disabled={disabled || busy}
          onClick={() => fileRef.current?.click()}
        >
          <ImagePlus size={14} aria-hidden /> Upload image
        </button>
        <button
          type="button"
          className="btn btn-sm"
          disabled={disabled || busy}
          onClick={() => cameraRef.current?.click()}
        >
          <Camera size={14} aria-hidden /> Take photo
        </button>
        {previewUrl && (
          <button
            type="button"
            className="btn btn-sm btn-danger"
            disabled={disabled || busy}
            onClick={removeCover}
          >
            <Trash2 size={14} aria-hidden /> Remove
          </button>
        )}
      </div>

      {busy && (
        <span className="cover-picker-status" role="status">
          <span className="spinner" aria-hidden /> Processing…
        </span>
      )}
      {error && (
        <span className="result-hint" role="alert">
          {error}
        </span>
      )}
      {previewUrl && (
        <img src={previewUrl} alt="Cover preview" className="cover-preview" />
      )}
    </div>
  )
}