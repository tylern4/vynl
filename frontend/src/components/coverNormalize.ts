/** Longest side (px) a cover is downscaled to before upload (issue #11). */
export const COVER_MAX_DIMENSION = 2000

/** JPEG quality used when normalizing covers before upload. */
export const COVER_JPEG_QUALITY = 0.9

function loadImageElement(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('Could not decode image'))
    img.src = src
  })
}

async function decodeSource(
  file: File,
): Promise<ImageBitmap | HTMLImageElement> {
  if (typeof createImageBitmap === 'function') {
    try {
      return await createImageBitmap(file)
    } catch {
      // Fall through to the <img> path (some HEIC/EXIF decoders fail via bitmap).
    }
  }
  const url = URL.createObjectURL(file)
  try {
    return await loadImageElement(url)
  } finally {
    URL.revokeObjectURL(url)
  }
}

/**
 * Normalize a user-picked cover to a JPEG `Blob` for the upload endpoint:
 * decode via `createImageBitmap` (with an `<img>` fallback), downscale to at
 * most `COVER_MAX_DIMENSION` on the longest side, and encode as `image/jpeg`
 * at `COVER_JPEG_QUALITY`. This handles iOS HEIC captures and huge originals
 * so the backend always receives a reasonable JPEG a phone can be asked for.
 */
export async function normalizeCoverFile(
  file: File,
  maxDimension = COVER_MAX_DIMENSION,
  quality = COVER_JPEG_QUALITY,
): Promise<Blob> {
  const source = await decodeSource(file)
  const width = source.width
  const height = source.height
  const scale = Math.min(1, maxDimension / Math.max(width, height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(width * scale))
  canvas.height = Math.max(1, Math.round(height * scale))
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Canvas is not available')
  ctx.drawImage(source, 0, 0, canvas.width, canvas.height)
  if (typeof (source as ImageBitmap).close === 'function') {
    ;(source as ImageBitmap).close()
  }
  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, 'image/jpeg', quality),
  )
  if (!blob) throw new Error('Could not encode the image as JPEG')
  return blob
}