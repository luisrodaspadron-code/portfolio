import esbuild from "esbuild";
import { copyFile, mkdir, rm } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url)).replace(/\/scripts$/, "");
const dist = join(root, "dist");

await rm(dist, { recursive: true, force: true });
await mkdir(join(dist, "assets"), { recursive: true });
await copyFile(join(root, "index.html"), join(dist, "index.html"));

await esbuild.build({
  entryPoints: [join(root, "src/main.tsx")],
  outfile: join(dist, "assets/app.js"),
  bundle: true,
  format: "iife",
  platform: "browser",
  target: ["es2020"],
  sourcemap: true,
  minify: true,
  define: {
    "process.env.NODE_ENV": '"production"'
  },
  logLevel: "info"
});
