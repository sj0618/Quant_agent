import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 18000,
    allowedHosts: [
      "qt-agent.kro.kr",
    ],
    proxy: {
      "/ai-api": {
        target: "http://127.0.0.1:18001",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/ai-api/, ""),
      },
    },
  },
});