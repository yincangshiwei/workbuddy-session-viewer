import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",  // 监听所有网卡，支持局域网 IP 访问
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:9877",
        changeOrigin: true,
      },
      "/shared": {
        target: "http://127.0.0.1:9877",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "../servers/static",
    emptyOutDir: true,
  },
});

