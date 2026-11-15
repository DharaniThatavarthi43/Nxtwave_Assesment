import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("/node_modules/three/")) return "three";
          if (
            id.includes("/node_modules/@react-three/fiber/") ||
            id.includes("/node_modules/@react-three/drei/")
          ) {
            return "react-three";
          }
          if (
            id.includes("/node_modules/recharts/") ||
            id.includes("/node_modules/d3-")
          ) {
            return "charts";
          }
          return undefined;
        },
      },
    },
  },
  server: {
    strictPort: true,
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
