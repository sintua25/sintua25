import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Tauri memuat dev server ini; port tetap supaya cocok dengan tauri.conf.json.
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: { port: 1420, strictPort: true },
  envPrefix: ["VITE_", "TAURI_ENV_"],
  build: { target: "es2022", sourcemap: false },
  test: { environment: "node" },
});
