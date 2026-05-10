import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// dev: 5174 with API proxy → manager.py on 9091, base "/" for clean URLs
// prod: vite build → ../../backend/services/web/static/manager-dist
//       base "/static/manager-dist/" 是因为 manager.py 已经把整个 backend/services/web/static/
//       目录挂在 /static 下；这样产物 index.html 里的 <script src> 会带正确前缀，
//       浏览器请求 /static/manager-dist/assets/*.js 直接命中 StaticFiles。
export default defineConfig(({ command }) => ({
  base: command === "build" ? "/static/manager-dist/" : "/",
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5174,
    strictPort: true,
    proxy: {
      "/api": "http://localhost:9091",
    },
  },
  build: {
    outDir: path.resolve(__dirname, "../../backend/services/web/static/manager-dist"),
    emptyOutDir: true,
    sourcemap: true,
  },
}));
