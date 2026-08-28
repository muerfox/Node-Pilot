import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vite";

// Bare-metal `npm run dev` talks to a controller on localhost:8000; the
// docker-compose `nodepilot-frontend` service instead sets this to the
// controller's service name (http://nodepilot-web:8000) since
// "localhost" inside that container would mean the frontend container
// itself.
const apiProxyTarget = process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    host: true,
    proxy: {
      // Local dev convenience: `npm run dev` can talk to a controller
      // running via `docker compose up` on :8000 without CORS headaches.
      "/api": { target: apiProxyTarget, changeOrigin: true },
      "/ws": { target: apiProxyTarget.replace("http", "ws"), ws: true },
    },
  },
});
