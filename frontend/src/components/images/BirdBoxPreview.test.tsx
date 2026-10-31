/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { LABEL_COLORS } from '@/constants/labelColors'
import { BirdBoxPreview } from './BirdBoxPreview'
import { birdBboxBorderCss } from './birdBboxStyle'
import type { BirdBoundingBox } from '@/types/api'

/** Real values from image 202242 (DSC_2095.NEF). */
const bbox: BirdBoundingBox = {
  x1: 884,
  y1: 377,
  x2: 2123,
  y2: 1672,
  conf: 0.9138,
  img_w: 3936,
  img_h: 2624,
}

function boundingBoxButton(): HTMLButtonElement {
  return screen.getByRole('button', { name: 'Bounding Box' }) as HTMLButtonElement
}

function parseRgba(css: string): { r: number; g: number; b: number; a: number } {
  const m = css.match(/^rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)$/)
  if (!m) throw new Error(`expected rgba(...), got ${css}`)
  return { r: +m[1], g: +m[2], b: +m[3], a: +m[4] }
}

function hexRgb(hex: string): { r: number; g: number; b: number } {
  const h = hex.replace('#', '')
  return {
    r: Number.parseInt(h.slice(0, 2), 16),
    g: Number.parseInt(h.slice(2, 4), 16),
    b: Number.parseInt(h.slice(4, 6), 16),
  }
}

describe('birdBboxBorderCss', () => {
  it('maps conf 0 to label red with alpha 0.35', () => {
    const { r, g, b, a } = parseRgba(birdBboxBorderCss(0))
    expect({ r, g, b }).toEqual(hexRgb(LABEL_COLORS.red))
    expect(a).toBeCloseTo(0.35, 5)
  })

  it('maps conf 0.5 to label yellow with mid alpha', () => {
    const { r, g, b, a } = parseRgba(birdBboxBorderCss(0.5))
    expect({ r, g, b }).toEqual(hexRgb(LABEL_COLORS.yellow))
    expect(a).toBeCloseTo(0.675, 5)
  })

  it('maps conf 1 to label green with alpha 1', () => {
    const { r, g, b, a } = parseRgba(birdBboxBorderCss(1))
    expect({ r, g, b }).toEqual(hexRgb(LABEL_COLORS.green))
    expect(a).toBeCloseTo(1, 5)
  })

  it('maps conf 0.25 to orange between red and yellow', () => {
    const { g } = parseRgba(birdBboxBorderCss(0.25))
    const red = hexRgb(LABEL_COLORS.red)
    const yellow = hexRgb(LABEL_COLORS.yellow)
    expect(g).toBeGreaterThan(red.g)
    expect(g).toBeLessThan(yellow.g)
  })

  it('maps conf 0.75 to yellow-green between yellow and green', () => {
    const { r } = parseRgba(birdBboxBorderCss(0.75))
    const yellow = hexRgb(LABEL_COLORS.yellow)
    const green = hexRgb(LABEL_COLORS.green)
    expect(r).toBeLessThan(yellow.r)
    expect(r).toBeGreaterThan(green.r)
  })
})

describe('BirdBoxPreview', () => {
  afterEach(() => {
    cleanup()
  })

  it('hides the overlay until its button is pressed', () => {
    render(<BirdBoxPreview src="/source-image?path=a.NEF" alt="a.NEF" bbox={bbox} />)

    expect(screen.queryByTestId('bird-bbox-overlay')).toBeNull()
    fireEvent.click(boundingBoxButton())
    expect(screen.getByTestId('bird-bbox-overlay')).not.toBeNull()
  })

  it('positions the box as a fraction of the detector image size', () => {
    render(<BirdBoxPreview src="/source-image?path=a.NEF" alt="a.NEF" bbox={bbox} />)
    fireEvent.click(boundingBoxButton())

    const overlay = screen.getByTestId('bird-bbox-overlay')
    expect(overlay.style.left).toBe(`${(884 / 3936) * 100}%`)
    expect(overlay.style.top).toBe(`${(377 / 2624) * 100}%`)
    expect(overlay.style.width).toBe(`${((2123 - 884) / 3936) * 100}%`)
    expect(overlay.style.height).toBe(`${((1672 - 377) / 2624) * 100}%`)
  })

  it('distinguishes the subject frame from the autofocus target', () => {
    render(<BirdBoxPreview src="/source-image?path=a.NEF" alt="a.NEF" bbox={bbox} />)
    fireEvent.click(boundingBoxButton())

    const overlay = screen.getByTestId('bird-bbox-overlay')
    expect(overlay.className).toContain('subject')
  })

  it('disables the control when the image has not been scanned', () => {
    render(<BirdBoxPreview src="/source-image?path=a.NEF" alt="a.NEF" bbox={null} />)

    expect(boundingBoxButton().disabled).toBe(true)
    expect(boundingBoxButton().title).toContain('not scanned')
    expect(screen.queryByTestId('bird-bbox-overlay')).toBeNull()
  })

  it('treats the not-detected sentinel as undrawable', () => {
    render(
      <BirdBoxPreview src="/source-image?path=a.NEF" alt="a.NEF" bbox={{ detected: false }} />,
    )

    expect(boundingBoxButton().disabled).toBe(true)
    expect(boundingBoxButton().title).toContain('no bird')
    expect(screen.queryByTestId('bird-bbox-overlay')).toBeNull()
  })

  it('shows scan-failed label when the sentinel includes an error', () => {
    render(
      <BirdBoxPreview
        src="/source-image?path=a.NEF"
        alt="a.NEF"
        bbox={{ detected: false, error: 'detector_unavailable' }}
      />,
    )

    expect(boundingBoxButton().disabled).toBe(true)
    expect(boundingBoxButton().title).toContain('scan failed: detector_unavailable')
  })

  it('treats a box with zero reference dimensions as undrawable', () => {
    render(
      <BirdBoxPreview src="/source-image?path=a.NEF" alt="a.NEF" bbox={{ ...bbox, img_w: 0, img_h: 0 }} />,
    )

    expect(boundingBoxButton().disabled).toBe(true)
    expect(boundingBoxButton().title).toContain('not scanned')
    expect(screen.queryByTestId('bird-bbox-overlay')).toBeNull()
  })

  it('offers three icon-only controls with availability and pressed state', () => {
    render(<BirdBoxPreview src="/preview" alt="test" bbox={bbox} />)
    expect(screen.queryByRole('checkbox')).toBeNull()
    for (const name of ['Bounding Box', 'Eyes', 'Focus Point']) {
      const control = screen.getByRole('button', { name }) as HTMLButtonElement
      expect(control.textContent).toBe('')
      expect(control.getAttribute('aria-pressed')).toBe('false')
    }
    expect((screen.getByRole('button', { name: 'Eyes' }) as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByRole('button', { name: 'Focus Point' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('toggles eyes and camera AF independently, using the cropped display coordinates', () => {
    render(<BirdBoxPreview src="/preview" alt="test" bbox={bbox}
      eyes={{ display_width: 1000, display_height: 800, points: [{ name: 'left_eye', x: .4, y: .3, confidence: .95 }] }}
      af={{ mode: 'Wide (L)', in_focus: false, box: { left: .1, top: .1, width: .1, height: .1 }, crop_box: { left: .3, top: .2, width: .2, height: .25 } }} />)
    fireEvent.click(screen.getByRole('button', { name: 'Eyes' }))
    const eye = screen.getByTestId('eye-keypoint-marker')
    expect(eye.style.left).toBe('40%')
    expect(eye.style.top).toBe('30%')
    expect(screen.queryByTestId('af-reticle-overlay')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Focus Point' }))
    const af = screen.getByTestId('af-reticle-overlay')
    expect(af.style.left).toBe('30%')
    expect(af.style.top).toBe('20%')
    expect(af.style.width).toBe('20%')
    expect(screen.getByText('UNCONFIRMED')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Eyes' }))
    expect(screen.queryByTestId('eye-keypoint-marker')).toBeNull()
    expect(screen.getByTestId('af-reticle-overlay')).toBeTruthy()
  })
})
