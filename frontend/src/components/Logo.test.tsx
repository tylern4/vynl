import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { Logo } from './Logo'

describe('Logo', () => {
  it('renders an SVG record mark labelled "vynl"', () => {
    const { container } = render(<Logo size={30} />)
    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
    expect(svg).toHaveAttribute('width', '30')
    expect(svg).toHaveAttribute('height', '30')
    expect(svg).toHaveAttribute('role', 'img')
    expect(svg?.getAttribute('aria-label')).toBe('vynl')
    // the record body + grooves + center label + brand V are all present
    expect(container.querySelectorAll('circle').length).toBeGreaterThanOrEqual(5)
    expect(container.querySelector('path')).not.toBeNull()
  })

  it('defaults to 26px (top-bar size)', () => {
    const { container } = render(<Logo />)
    expect(container.querySelector('svg')).toHaveAttribute('width', '26')
  })

  it('draws the "V" pointing down (apex is the lowest point)', () => {
    const { container } = render(<Logo />)
    const d = container.querySelector('path')?.getAttribute('d') ?? ''
    const nums = d.match(/-?[\d.]+/g)?.map(Number) ?? []
    expect(nums).toHaveLength(6) // M x1 y1 L x2 y2 L x3 y3
    const [, arm1Y, , apexY, , arm2Y] = nums
    // apex must be below both arm tips, otherwise the V renders upside-down
    expect(apexY).toBeGreaterThan(arm1Y)
    expect(apexY).toBeGreaterThan(arm2Y)
  })
})