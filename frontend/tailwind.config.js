/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        kraken: {
          DEFAULT: '#7B61FF',
          light: '#9B85FF',
          dark: '#6248E5',
          subtle: '#7B61FF1A',
        },
        accent: {
          DEFAULT: '#5EEAD4',
          glow: 'rgba(94, 234, 212, 0.35)',
          subtle: 'rgba(94, 234, 212, 0.12)',
        },
        profit: '#22C55E',
        loss: '#EF4444',
        asset: {
          eth: '#5EEAD4',
          sol: '#7B61FF',
          ada: '#60A5FA',
          link: '#22D3EE',
        },
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

