import esbuild from "esbuild";
import { copyFile, mkdir, readFile, stat } from "node:fs/promises";
import http from "node:http";
import { dirname, extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url)).replace(/\/scripts$/, "");
const dist = join(root, "dist");
const port = Number(process.env.PORT || 5173);
const backend = new URL(process.env.API_URL || "http://127.0.0.1:8000");

await mkdir(join(dist, "assets"), { recursive: true });
await copyFile(join(root, "index.html"), join(dist, "index.html"));

const context = await esbuild.context({
  entryPoints: [join(root, "src/main.tsx")],
  outfile: join(dist, "assets/app.js"),
  bundle: true,
  format: "iife",
  platform: "browser",
  target: ["es2020"],
  sourcemap: true,
  define: {
    "process.env.NODE_ENV": '"development"'
  },
  logLevel: "info"
});

await context.watch();

const mime = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".map": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".json": "application/json; charset=utf-8"
};

function proxyApi(req, res) {
  const target = new URL(req.url, backend);
  const proxyReq = http.request(
    {
      hostname: target.hostname,
      port: target.port || 80,
      path: `${target.pathname}${target.search}`,
      method: req.method,
      headers: { ...req.headers, host: target.host }
    },
    (proxyRes) => {
      res.writeHead(proxyRes.statusCode || 502, proxyRes.headers);
      proxyRes.pipe(res);
    }
  );
  proxyReq.on("error", (error) => {
    res.writeHead(502, { "content-type": "application/json" });
    res.end(JSON.stringify({ detail: error.message }));
  });
  req.pipe(proxyReq);
}

async function serveFile(req, res) {
  const requested = decodeURIComponent(new URL(req.url, `http://127.0.0.1:${port}`).pathname);
  const safe = normalize(requested).replace(/^(\.\.[/\\])+/, "").replace(/^[/\\]+/, "");
  const filePath = safe === "" ? join(dist, "index.html") : join(dist, safe);
  try {
    const info = await stat(filePath);
    const finalPath = info.isDirectory() ? join(dist, "index.html") : filePath;
    const body = await readFile(finalPath);
    res.writeHead(200, { "content-type": mime[extname(finalPath)] || "application/octet-stream" });
    res.end(body);
  } catch {
    const body = await readFile(join(dist, "index.html"));
    res.writeHead(200, { "content-type": mime[".html"] });
    res.end(body);
  }
}

const server = http.createServer((req, res) => {
  if (req.url?.startsWith("/api/")) {
    proxyApi(req, res);
    return;
  }
  serveFile(req, res);
});

server.listen(port, "127.0.0.1", () => {
  console.log(`Frontend running at http://127.0.0.1:${port}`);
});

process.on("SIGINT", async () => {
  await context.dispose();
  server.close(() => process.exit(0));
});
