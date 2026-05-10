import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// dev: 5175 with proxy → backend/services/web/server.py on 8080
//   /api, /recordings, /static 透传 HTTP；/ws 透传 WebSocket（必须 ws:true）
// prod: vite build → ../../backend/services/web/static/web-dist
//   base "/static/web-dist/" 因为 server.py 把 backend/services/web/static 挂在 /static 下；
//   产物 index.html 里的 <script src> 自动带这个前缀，浏览器请求落到 StaticFiles。
export default defineConfig(({ command }) => ({
  base: command === "build" ? "/static/web-dist/" : "/",
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5175,
    strictPort: true,
    // /api/manager 必须排在 /api 之前，proxy 按顺序匹配，否则会被 /api 兜底走错端口。
    // language 等全局 config 由 manager (9091) 拥有；其余 web 业务接口都在 server.py (8080)。
    proxy: {
      "/api/manager": "http://localhost:9091",
      "/api":         "http://localhost:8080",
      "/recordings":  "http://localhost:8080",
      "/static":      "http://localhost:8080",
      "/ws":          { target: "ws://localhost:8080", ws: true, changeOrigin: true },
    },
  },
  build: {
    outDir: path.resolve(__dirname, "../../backend/services/web/static/web-dist"),
    emptyOutDir: true,
    sourcemap: true,
  },
}));
