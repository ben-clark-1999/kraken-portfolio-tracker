import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Override with `VITE_API_TARGET=https://<your-host>.up.railway.app npm run dev`
// to run the local frontend against a deployed backend.
const API_TARGET = process.env.VITE_API_TARGET ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
