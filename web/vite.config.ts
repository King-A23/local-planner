import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

function readDisplayName(): string {
  const text = readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), "src/constants.ts"),
    "utf8",
  );
  const match = text.match(/export const DISPLAY_NAME = "([^"]+)"/);
  if (!match) {
    throw new Error("DISPLAY_NAME missing from src/constants.ts");
  }
  return match[1];
}

export default defineConfig({
  define: {
    __APP_VERSION__: JSON.stringify(JSON.parse(readFileSync(
      new URL("./package.json", import.meta.url), "utf8",
    )).version),
  },
  plugins: [
    react(),
    {
      name: "html-display-name",
      transformIndexHtml(html) {
        return html.replace(
          /<title>[^<]*<\/title>/,
          `<title>${readDisplayName()}</title>`,
        );
      },
    },
  ],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8787",
      },
    },
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
  },
});
