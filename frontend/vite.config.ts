import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "./",
  define: {
    __APP_VERSION__: JSON.stringify(process.env.npm_package_version ?? "0.1.0"),
    __BUILD_ID__: JSON.stringify(process.env.GITHUB_SHA ?? "local"),
  },
  server: { host: "0.0.0.0" },
});
