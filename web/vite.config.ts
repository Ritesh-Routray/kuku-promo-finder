import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: process.env.VITE_STATIC === "1" ? "./" : "/",
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:7860" } },
});
