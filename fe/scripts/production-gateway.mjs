import { createServer, request as requestUpstream } from "node:http";
import { URL, pathToFileURL } from "node:url";

const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

function headerEntries(headers) {
  return Object.entries(headers).filter(
    ([name, value]) => value !== undefined && !HOP_BY_HOP_HEADERS.has(name.toLowerCase()),
  );
}

export function resolveCombinedBackendTarget(value) {
  const target = new URL(value ?? "http://127.0.0.1:18001");
  if (target.protocol !== "http:" || !["127.0.0.1", "::1", "[::1]", "localhost"].includes(target.hostname)) {
    throw new Error("COMBINED_BACKEND_PROXY_TARGET must be an HTTP loopback URL");
  }
  if (target.pathname !== "/" || target.search || target.hash) {
    throw new Error("COMBINED_BACKEND_PROXY_TARGET must not include a path, query, or fragment");
  }
  return target;
}

function proxyError(response) {
  if (!response.headersSent) {
    response.writeHead(502, {
      "cache-control": "no-store",
      "content-type": "text/plain; charset=utf-8",
    });
  }
  response.end("The application is temporarily unavailable. Please try again later.");
}

function rejectRequestTarget(request, response) {
  request.resume();
  response.writeHead(400, {
    "cache-control": "no-store",
    "content-type": "text/plain; charset=utf-8",
  });
  response.end("Invalid request target.");
}

function isOriginFormRequestTarget(value) {
  return value.startsWith("/") && !value.startsWith("//");
}

/**
 * Keeps the legacy nginx :18000 upstream while making the combined backend the
 * only public route-policy owner. Unknown HTML paths therefore retain the
 * backend's real 404 instead of Vite preview's SPA 200 fallback.
 */
export function createProductionGateway({ target = "http://127.0.0.1:18001" } = {}) {
  const upstreamTarget = resolveCombinedBackendTarget(target);

  return createServer((request, response) => {
    const requestTarget = request.url ?? "/";
    if (!isOriginFormRequestTarget(requestTarget)) {
      rejectRequestTarget(request, response);
      return;
    }
    const upstreamUrl = new URL(requestTarget, upstreamTarget);
    if (upstreamUrl.origin !== upstreamTarget.origin) {
      rejectRequestTarget(request, response);
      return;
    }
    const headers = Object.fromEntries(headerEntries(request.headers));
    // The production listener is loopback-only. Nginx is therefore the sole public
    // ingress and owns the client address/protocol headers. Do not append the gateway
    // peer: that would replace every browser identity with 127.0.0.1 downstream.
    headers["x-forwarded-for"] ??= request.socket.remoteAddress ?? "127.0.0.1";
    headers["x-forwarded-proto"] ??= "http";

    const upstream = requestUpstream(
      upstreamUrl,
      // The AI analysis SSE stream keepalive-pings every 15s (ai/ai_graph/api.py
      // ANALYSIS_EVENT_KEEPALIVE_SECONDS); a 15s gateway timeout races that keepalive and
      // can drop a still-live stream, so this must stay comfortably above it.
      { method: request.method, headers, timeout: 65_000 },
      (upstreamResponse) => {
        response.writeHead(
          upstreamResponse.statusCode ?? 502,
          Object.fromEntries(headerEntries(upstreamResponse.headers)),
        );
        upstreamResponse.pipe(response);
      },
    );

    upstream.once("timeout", () => upstream.destroy(new Error("combined backend response timeout")));
    upstream.once("error", () => proxyError(response));
    request.pipe(upstream);
  });
}

function isEntrypoint() {
  return process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
}

if (isEntrypoint()) {
  const port = Number.parseInt(process.env.PORT ?? "18000", 10);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error("PORT must be an integer between 1 and 65535");
  }
  const host = process.env.HOST ?? "0.0.0.0";
  const server = createProductionGateway({ target: process.env.COMBINED_BACKEND_PROXY_TARGET });
  server.listen(port, host, () => {
    process.stdout.write(`QuantAgent production gateway listening on ${host}:${port}\n`);
  });
  const shutdown = () => server.close(() => process.exit(0));
  process.once("SIGTERM", shutdown);
  process.once("SIGINT", shutdown);
}
