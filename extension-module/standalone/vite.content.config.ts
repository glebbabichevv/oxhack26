import { defineConfig } from 'vite';
import { resolve } from 'path';

// The browser-use content script, built exactly like the base extension's: one IIFE file.
export default defineConfig({
  envDir: resolve(__dirname, 'no-env'),
  esbuild: { pure: ['console.log', 'console.info', 'console.debug'] },
  publicDir: false,
  build: {
    outDir: 'dist',
    emptyOutDir: false,
    lib: { entry: resolve(__dirname, 'src/content/content.ts'), name: 'HorizonContent', fileName: () => 'content.js', formats: ['iife'] },
    rollupOptions: { output: { inlineDynamicImports: true, format: 'iife', entryFileNames: 'content.js' } },
  },
  resolve: { alias: { '@': resolve(__dirname, 'src') } },
});
