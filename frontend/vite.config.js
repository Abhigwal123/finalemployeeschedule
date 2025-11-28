import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react({
    include: '**/*.{jsx,js}',
  })],
  esbuild: {
    loader: 'jsx',
    include: /src\/.*\.jsx?$/,
    exclude: [],
  },
  optimizeDeps: {
    esbuildOptions: {
      loader: {
        '.js': 'jsx',
      },
    },
  },
  build: {
    // Use inline source maps instead of eval for CSP compliance
    sourcemap: 'inline',
  },
  server: {
    port: 5173,
    host: "localhost", // CRITICAL: Use localhost (not 0.0.0.0) to match backend CORS origin
    strictPort: false, // Allow port fallback if 5173 is busy
    // Proxy API requests to backend server (for local dev only)
    // In Docker, nginx handles proxying
    proxy: {
      '/api': {
        target: process.env.VITE_API_BASE_URL?.replace('/api/v1', '') || 'http://localhost:8081',
        changeOrigin: true,
        secure: false,
        configure: (proxy, _options) => {
          proxy.on('proxyReq', (proxyReq, req, _res) => {
            // Preserve original origin header
            if (req.headers.origin) {
              proxyReq.setHeader('Origin', req.headers.origin);
            }
          });
        },
      },
    },
  },
  // Configure to minimize eval usage in development
  css: {
    devSourcemap: false,
  },
  // Use classic mode for React Fast Refresh to avoid eval issues
  define: {
    // Ensure we're in development mode
    'process.env.NODE_ENV': JSON.stringify(process.env.NODE_ENV || 'development'),
  },
})

