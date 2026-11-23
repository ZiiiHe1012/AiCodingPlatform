import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:4173",
      "/assets/codelab-backend.js": "http://127.0.0.1:4173",
    },
  },
  build: {
    outDir: "../dist",
    emptyOutDir: true,
    chunkSizeWarningLimit: 1600,
    rollupOptions: {
      output: {
        manualChunks: {
          "element-plus": ["element-plus"],
          monaco: ["monaco-editor"],
        },
      },
    },
  },
});
