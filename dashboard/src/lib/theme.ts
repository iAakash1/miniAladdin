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

/**
 * Runs before first paint, inline in the document head. Dark is the default; an
 * explicit light choice wins.
 *
 * It lives here, and not in the layout, because the Content-Security-Policy has
 * to allow exactly this text: the policy carries its SHA-256 hash, so that the
 * one inline script the app writes itself is allowed without making the whole
 * document depend on a per-request nonce, and without `'unsafe-inline'`. A test
 * hashes what the layout renders and compares it with what the policy allows.
 */
export const THEME_SCRIPT = `(function(){var l=false;try{l=localStorage.getItem('omni-theme')==='light'}catch(e){}document.documentElement.dataset.theme=l?'light':'dark';var m=document.querySelector('meta[name="theme-color"]');if(m)m.setAttribute('content',l?'${THEME_COLOR.light}':'${THEME_COLOR.dark}')})()`
