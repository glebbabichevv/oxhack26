import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

// Panel (React) + background service worker. The content script has its own single-file build
// (vite.content.config.ts) so strict-CSP pages can run it.
export default defineConfig({
  plugins: [react()],
  envDir: resolve(__dirname, 'no-env'), // never read a .env: Horizon has no keys and talks to no Argos server
  esbuild: { pure: ['console.log', 'console.info', 'console.debug'] },
  publicDir: 'public',
  build: {
    outDir: 'dist',
    modulePreload: false,
    rollupOptions: {
      input: {
        panel: resolve(__dirname, 'panel.html'),
        background: resolve(__dirname, 'src/background/background.ts'),
      },
      output: {
        entryFileNames: '[name].js',
        chunkFileNames: 'chunks/[name]-[hash].js',
        assetFileNames: 'assets/[name].[ext]',
        format: 'es',
      },
    },
  },
  resolve: { alias: { '@': resolve(__dirname, 'src') } },
});
