/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Schibsted Grotesk Variable"', 'system-ui', 'sans-serif'],
        mono: ['"Geist Mono Variable"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      colors: {
        kraken: {
          DEFAULT: '#7B61FF',
          light: '#9B85FF',
          dark: '#6248E5',
          subtle: '#7B61FF1A',
        },
        profit: '#22C55E',
        loss: '#EF4444',
        surface: {
          DEFAULT: '#0f0e14',
          raised: '#1a1823',
          border: '#2a2735',
          hover: '#252230',
        },
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

