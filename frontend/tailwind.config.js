/** @type {import('tailwindcss').Config} */
import plugin from 'tailwindcss/plugin'

// The look is a code editor's: Tokyo Night in the dark, Tokyo Night Day in the light.
//
// Every colour the app uses is a CSS variable, so components are written once, for light
// mode, and dark mode swaps the variables. A shade means the same job in both: 100 is a
// tinted fill (chips, bar tracks), 200 a border, 400 a solid bar, 700 text on a tint.
// Accent scales are mixed from one base colour per hue; the neutrals are set by hand,
// because they carry the editor's character (blue-grey surfaces, lavender text).
const SHADES = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950]

const NEUTRAL = {
  light: ['#f4f5f9', '#eceef4', '#dde0ea', '#c3c8d8', '#8e94b0', '#6b7194',
          '#555b7d', '#414868', '#343b58', '#1f2335', '#16161e'],
  dark:  ['#1a1b26', '#2a2f45', '#343a55', '#414868', '#787fa8', '#9aa5ce',
          '#a9b1d6', '#b8c1ec', '#c0caf5', '#d4dbfa', '#e4e9ff'],
}
const SURFACE = { light: '#ffffff', dark: '#24283b' }   // cards ("white")
const INK = '#1f2335'

const ACCENTS = {
  //         light (Day)  dark (Night)
  emerald: ['#3d9a50', '#9ece6a'],
  sky:     ['#2e7de9', '#7aa2f7'],
  indigo:  ['#9854f1', '#bb9af7'],
  purple:  ['#7847bd', '#9d7cd8'],
  amber:   ['#c08a1e', '#e0af68'],
  orange:  ['#e2721b', '#ff9e64'],
  red:     ['#f52a65', '#f7768e'],
  rose:    ['#e8366b', '#ff7a93'],
  cyan:    ['#007197', '#7dcfff'],
}

const rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16))
const mix = (a, b, t) => {
  const [x, y] = [rgb(a), rgb(b)]
  return '#' + x.map((v, i) => Math.round(v + (y[i] - v) * t).toString(16).padStart(2, '0')).join('')
}
const channels = (hex) => rgb(hex).join(' ')

// Light: tints of the base towards white, shades towards ink.
const lightScale = (base) => [
  mix('#ffffff', base, 0.07), mix('#ffffff', base, 0.14), mix('#ffffff', base, 0.26),
  mix('#ffffff', base, 0.45), mix('#ffffff', base, 0.72), base,
  mix(base, INK, 0.15), mix(base, INK, 0.32), mix(base, INK, 0.5), mix(base, INK, 0.65),
  mix(base, INK, 0.8),
]
// Dark: low shades are the hue glowing faintly through the card, high shades get lighter,
// so text-x-700 on bg-x-100 reads as bright text on a dim tint.
const darkScale = (base) => [
  mix(SURFACE.dark, base, 0.1), mix(SURFACE.dark, base, 0.18), mix(SURFACE.dark, base, 0.3),
  mix(SURFACE.dark, base, 0.7), base, mix(base, '#ffffff', 0.05),
  mix(base, '#ffffff', 0.12), mix(base, '#ffffff', 0.22), mix(base, '#ffffff', 0.35),
  mix(base, '#ffffff', 0.5), mix(base, '#ffffff', 0.65),
]

const HUES = ['slate', ...Object.keys(ACCENTS)]

const themed = Object.fromEntries(HUES.map((h) => [h, Object.fromEntries(
  SHADES.map((s) => [s, `rgb(var(--c-${h}-${s}) / <alpha-value>)`]),
)]))

function palette(mode) {
  const scales = {
    slate: NEUTRAL[mode],
    ...Object.fromEntries(Object.entries(ACCENTS).map(([h, [l, d]]) =>
      [h, mode === 'dark' ? darkScale(d) : lightScale(l)])),
  }
  const vars = {}
  for (const [h, scale] of Object.entries(scales)) {
    SHADES.forEach((s, i) => { vars[`--c-${h}-${s}`] = channels(scale[i]) })
  }
  vars['--c-white'] = channels(SURFACE[mode])
  return vars
}

export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: { ...themed, white: 'rgb(var(--c-white) / <alpha-value>)' },
      fontFamily: {
        sans: ['"Inter Variable"', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono Variable"', '"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      // Editor-tight corners: every existing rounded-lg / rounded-xl gets smaller
      borderRadius: { md: '5px', lg: '6px', xl: '8px', '2xl': '10px' },
    },
  },
  plugins: [
    plugin(({ addBase }) => addBase({
      ':root': palette('light'),
      // color-scheme also darkens native widgets: inputs, selects, scrollbars, the datalist
      '.dark': { ...palette('dark'), colorScheme: 'dark' },
    })),
  ],
}
