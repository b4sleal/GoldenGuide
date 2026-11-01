/// <reference types="vitest/config" />
import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// Dev server only. Production assets are served same-origin by Nginx (docker/frontend) or FastAPI.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "GG_");
  // The backend container's published port (docker-compose BACKEND_PORT).
  const backend = env.GG_BACKEND_ORIGIN ?? "http://localhost:8082";
  // The backend accepts one public origin (SITE_ORIGIN) for its Host allow-list and same-origin
  // check, so dev requests are presented as coming from it. Dev only: never do this in a real proxy.
  const site = new URL(env.GG_SITE_ORIGIN ?? "http://localhost:8080");

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
    },
    server: {
      port: 5173,
      strictPort: true,
      // Explicitly admit the configured public hostname when Nginx forwards its original Host.
      allowedHosts: [site.hostname],
      watch: {
        usePolling: env.GG_WATCH_POLLING === "true",
        // A bind-mounted pnpm store can add tens of thousands of watchers and stall page loads.
        ignored: [/(^|[\\/])\.pnpm-store([\\/]|$)/],
      },
      proxy: {
        "/api": {
          target: backend,
          headers: { host: site.host, origin: site.origin },
        },
      },
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
      include: ["src/**/*.test.{ts,tsx}"],
      css: false,
      reporters: ['default'],

    },
  };
});
