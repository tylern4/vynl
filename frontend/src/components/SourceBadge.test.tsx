import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SourceBadge } from './SourceBadge'

describe('SourceBadge', () => {
  it('labels every provider plus the manual source', () => {
    const { rerender } = render(<SourceBadge source="deezer" />)
    expect(screen.getByText('Deezer')).toBeInTheDocument()

    rerender(<SourceBadge source="musicbrainz" />)
    expect(screen.getByText('MusicBrainz')).toBeInTheDocument()

    rerender(<SourceBadge source="manual" />)
    expect(screen.getByText('Manual')).toBeInTheDocument()
    expect(screen.getByText('Manual')).toHaveClass('source-manual')
  })
})