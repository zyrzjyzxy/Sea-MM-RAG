import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./"),
    },
  },
  server: {
    port: 3000,
    host: true,
    open: true
  },
  preview: {
    port: 3000,
    host: true
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor': ['react', 'react-dom'],
          'ui-vendor': ['lucide-react', 'sonner'],
          'radix-vendor': [
            '@radix-ui/react-dialog',
            '@radix-ui/react-accordion',
            '@radix-ui/react-dropdown-menu'
          ]
        }
      }
    }
  }
})