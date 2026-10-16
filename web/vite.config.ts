import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Em desenvolvimento o front chama /api e o Vite repassa para o FastAPI (uvicorn api.main:app --port 8000).
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
