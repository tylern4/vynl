import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { Tag } from '../types'
import { TagEditor } from './TagEditor'

const suggestions: Tag[] = [
  { id: 1, name: 'chill', album_count: 2 },
  { id: 2, name: 'summer', album_count: 1 },
]

describe('TagEditor', () => {
  it('renders current tags as removable chips', async () => {
    const user = userEvent.setup()
    const onRemove = vi.fn()
    render(<TagEditor tags={['art-rock']} suggestions={suggestions} onAdd={vi.fn()} onRemove={onRemove} />)

    expect(screen.getByText('art-rock')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Remove tag art-rock' }))
    expect(onRemove).toHaveBeenCalledWith('art-rock')
  })

  it('offers matching suggestions and adds on click', async () => {
    const user = userEvent.setup()
    const onAdd = vi.fn()
    render(<TagEditor tags={[]} suggestions={suggestions} onAdd={onAdd} onRemove={vi.fn()} />)

    await user.type(screen.getByLabelText('Add a tag'), 'ch')
    await user.click(screen.getByRole('button', { name: 'chill' }))
    expect(onAdd).toHaveBeenCalledWith('chill')
  })

  it('adds free text via the form', async () => {
    const user = userEvent.setup()
    const onAdd = vi.fn()
    render(<TagEditor tags={[]} suggestions={suggestions} onAdd={onAdd} onRemove={vi.fn()} />)

    await user.type(screen.getByLabelText('Add a tag'), 'moody')
    await user.click(screen.getByRole('button', { name: 'Add' }))
    expect(onAdd).toHaveBeenCalledWith('moody')
  })

  it('never suggests a tag already on the album', async () => {
    const user = userEvent.setup()
    render(<TagEditor tags={['chill']} suggestions={suggestions} onAdd={vi.fn()} onRemove={vi.fn()} />)

    await user.type(screen.getByLabelText('Add a tag'), 'ch')
    expect(screen.queryByRole('button', { name: 'chill' })).not.toBeInTheDocument()
  })
})