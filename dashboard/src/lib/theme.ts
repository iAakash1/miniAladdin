/**
 * The browser-chrome colour for each theme (`<meta name="theme-color">`).
 *
 * It is the page background, so the mobile address bar sits flush with the
 * page. The root viewport declares the dark value, and the theme switch used to
 * leave it there: a reader who chose the light theme got a black address bar
 * over a white page. These must equal `--p-base` in each theme, which
 * tests/contrast.test.ts checks.
 */
export const THEME_COLOR = { dark: '#0a0b0d', light: '#f3f4f6' } as const

export type ThemeName = keyof typeof THEME_COLOR

export function setThemeColor(theme: ThemeName): void {
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', THEME_COLOR[theme])
}
