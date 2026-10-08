import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { CoverPicker } from './CoverPicker'

const mocks = vi.hoisted(() => ({
  normalizeCoverFile: vi.fn(),
}))

vi.mock('./coverNormalize', () => ({ normalizeCoverFile: mocks.normalizeCoverFile }))

/** Attach a file to a file input the way jsdom requires. */
function uploadFile(input: HTMLElement, file: File) {
  Object.defineProperty(input, 'files', { value: [file], configurable: true })
  fireEvent.change(input)
}

beforeEach(() => {
  mocks.normalizeCoverFile.mockReset()
  URL.createObjectURL = vi.fn(() => 'blob:preview') as typeof URL.createObjectURL
  URL.revokeObjectURL = vi.fn()
})

describe('CoverPicker', () => {
  it('offers a file upload and a phone-camera capture input', () => {
    render(<CoverPicker onChange={vi.fn()} />)

    const fileInput = screen.getByLabelText('Upload cover image')
    expect(fileInput).toHaveAttribute('type', 'file')
    expect(fileInput).toHaveAttribute('accept', 'image/*')

    const cameraInput = screen.getByLabelText('Take cover photo')
    expect(cameraInput).toHaveAttribute('type', 'file')
    expect(cameraInput).toHaveAttribute('accept', 'image/*')
    expect(cameraInput).toHaveAttribute('capture', 'environment')

    expect(screen.getByRole('button', { name: 'Upload image' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Take photo' })).toBeInTheDocument()
  })

  it('normalizes the picked file and reports the resulting blob', async () => {
    const onChange = vi.fn()
    mocks.normalizeCoverFile.mockResolvedValue(
      new Blob(['jpeg'], { type: 'image/jpeg' }),
    )
    render(<CoverPicker onChange={onChange} />)

    uploadFile(
      screen.getByLabelText('Upload cover image'),
      new File(['jpeg-bytes'], 'cover.jpg', { type: 'image/jpeg' }),
    )

    expect(await screen.findByAltText('Cover preview')).toBeInTheDocument()
    expect(mocks.normalizeCoverFile).toHaveBeenCalledWith(expect.any(File))
    expect(onChange).toHaveBeenCalledWith(expect.any(Blob))
  })

  it('removing the selection reports null and clears the preview', async () => {
    const onChange = vi.fn()
    mocks.normalizeCoverFile.mockResolvedValue(
      new Blob(['jpeg'], { type: 'image/jpeg' }),
    )
    render(<CoverPicker onChange={onChange} />)

    uploadFile(
      screen.getByLabelText('Upload cover image'),
      new File(['jpeg-bytes'], 'cover.jpg', { type: 'image/jpeg' }),
    )
    await screen.findByAltText('Cover preview')

    fireEvent.click(screen.getByRole('button', { name: 'Remove' }))
    expect(onChange).toHaveBeenLastCalledWith(null)
    expect(screen.queryByAltText('Cover preview')).not.toBeInTheDocument()
  })

  it('shows a readable error when the file cannot be normalized', async () => {
    const onChange = vi.fn()
    mocks.normalizeCoverFile.mockRejectedValue(new Error('decode failed'))
    render(<CoverPicker onChange={onChange} />)

    uploadFile(
      screen.getByLabelText('Upload cover image'),
      new File(['broken'], 'photo.heic', { type: 'image/heic' }),
    )

    expect(
      await screen.findByText(/Could not read that image/),
    ).toBeInTheDocument()
    expect(screen.queryByAltText('Cover preview')).not.toBeInTheDocument()
    expect(onChange).not.toHaveBeenCalled()
  })
})