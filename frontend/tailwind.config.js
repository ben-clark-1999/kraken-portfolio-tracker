/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    fontFamily: {
      sans: ['"Geist"', 'system-ui', '-apple-system', 'sans-serif'],
      mono: ['"Geist Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
    },
    fontSize: {
      xs: ['0.6875rem', { lineHeight: '1rem' }],        // 11px — metadata
      sm: ['0.8125rem', { lineHeight: '1.25rem' }],     // 13px — table headers, captions
      base: ['0.875rem', { lineHeight: '1.375rem' }],   // 14px — table cells, secondary
      md: ['1rem', { lineHeight: '1.5rem' }],           // 16px — body, UI labels
      lg: ['1.25rem', { lineHeight: '1.75rem' }],       // 20px — section headings
      xl: ['1.5rem', { lineHeight: '2rem' }],           // 24px — page titles
      display: ['2.5rem', { lineHeight: '1.1' }],       // 40px — hero number
      hero: ['3.5rem', { lineHeight: '1', letterSpacing: '-0.02em' }], // 56px — portfolio value
    },
    extend: {
      colors: {
        // Brand accent — used as punctuation, not decoration
        kraken: {
          DEFAULT: '#7B61FF',
          light: '#9B85FF',
          dark: '#6248E5',
          subtle: '#7B61FF1A', // 10% opacity for tinted backgrounds
        },
        // Semantic P&L — always paired with +/- prefix
        profit: '#22C55E',
        loss: '#EF4444',
        // Asset identity colors
        asset: {
          eth: '#627EEA',
          sol: '#9945FF',
          ada: '#06B6D4',
        },
        // Purple-tinted neutral surfaces (brand cohesion)
        surface: {
          DEFAULT: '#0f0e14',   // main page bg
          raised: '#1a1823',    // cards, elevated panels
          border: '#2a2735',    // borders, dividers
          hover: '#252230',     // hover state on raised
        },
        // Text colors (slightly warm to complement purple surfaces)
        txt: {
          primary: '#f0eef5',
          secondary: '#9691a8',
          muted: '#5f5a70',
        },
      },
    },
  },
  plugins: [],
}
