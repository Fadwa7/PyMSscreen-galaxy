import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // react-select v5 ESM build has unresolved peer deps (@babel/runtime,
      // @emotion/react) that break Rollup. The CJS build bundles them internally.
      'react-select': 'react-select/dist/react-select.cjs.dev.js',
    },
  },
  build: {
    commonjsOptions: {
      include: [/node_modules/],
      transformMixedEsModules: true,
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://backend:5000',
        changeOrigin: true,
        secure: false,
      }
    }
  }
})
