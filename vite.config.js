/**
 * Project:     Concordia AI
 * Name:        vite.config.js
 * Author:      Ian Kollipara <ian.kollipara@cune.edu>
 * Date:        2025-08-15
 * Description: Vite Configuration
 */

import { defineConfig } from "vite";
import tailwindcss from "@tailwindcss/vite";
import elm from "vite-plugin-elm";
import * as path from "node:path";

export default defineConfig({
  plugins: [tailwindcss(), elm()],
  base: "/static/",
  build: {
    manifest: "manifest.json",
    outDir: path.resolve("./static/dist"),
    rollupOptions: {
      input: path.resolve("./static/src/app.js"),
    }
  }
});
