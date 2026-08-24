import assert from "node:assert/strict";
import { createServer, request } from "node:http";
import test from "node:test";

import { createProductionGateway, resolveCombinedBackendTarget } from "./production-gateway.mjs";

async function listen(server: ReturnType<typeof createServer>) {
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert.ok(address && typeof address !== "string");
  return address.port;
}

async function fetchFrom(port: number, path: string, headers: Record<string, string> = {}) {
  return new Promise<{ statusCode: number; body: string }>((resolve, reject) => {
    const clientRequest = request({ host: "127.0.0.1", port, path, headers }, (response) => {
      let body = "";
      response.setEncoding("utf8");
      response.on("data", (chunk) => {
        body += chunk;
      });
      response.on("end", () => resolve({ statusCode: response.statusCode ?? 0, body }));
    });
    clientRequest.once("error", reject);
    clientRequest.end();
  });
}

test("production gateway forwards the backend's real 404 and proxy headers", async (t) => {
  const receivedForwardedProto: Record<string, string | undefined> = {};
  const receivedForwardedFor: Record<string, string | undefined> = {};
  const upstream = createServer((request, response) => {
    const forwardedProto = request.headers["x-forwarded-proto"];
    receivedForwardedProto[request.url ?? "/"] = Array.isArray(forwardedProto)
      ? forwardedProto.join(",")
      : forwardedProto;
    const forwardedFor = request.headers["x-forwarded-for"];
    receivedForwardedFor[request.url ?? "/"] = Array.isArray(forwardedFor)
      ? forwardedFor.join(",")
      : forwardedFor;
    response.writeHead(request.url === "/missing" ? 404 : 200, {
      "content-type": "text/html; charset=utf-8",
    });
    response.end("<!doctype html><main>page shell</main>");
  });
  const upstreamPort = await listen(upstream);
  const gateway = createProductionGateway({ target: `http://127.0.0.1:${upstreamPort}` });
  const gatewayPort = await listen(gateway);
  t.after(() => gateway.close());
  t.after(() => upstream.close());

  const missing = await fetchFrom(gatewayPort, "/missing", {
    "x-forwarded-for": "198.51.100.9",
    "x-forwarded-proto": "https",
  });
  const known = await fetchFrom(gatewayPort, "/trust");

  assert.deepEqual(missing, { statusCode: 404, body: "<!doctype html><main>page shell</main>" });
  assert.deepEqual(known, { statusCode: 200, body: "<!doctype html><main>page shell</main>" });
  assert.equal(receivedForwardedProto["/missing"], "https");
  assert.equal(receivedForwardedProto["/trust"], "http");
  assert.equal(receivedForwardedFor["/missing"], "198.51.100.9");
  assert.equal(receivedForwardedFor["/trust"], "127.0.0.1");
});

test("production gateway refuses non-loopback upstreams", () => {
  assert.throws(() => resolveCombinedBackendTarget("https://example.test"), /loopback/);
  assert.throws(() => resolveCombinedBackendTarget("http://127.0.0.1:18001/api"), /path/);
});

test("production gateway rejects absolute and network-path request targets", async (t) => {
  let alternateReceived = false;
  const alternate = createServer((_request, response) => {
    alternateReceived = true;
    response.end("must not be reached");
  });
  const alternatePort = await listen(alternate);
  const configuredUpstream = createServer((_request, response) => response.end("configured upstream"));
  const configuredUpstreamPort = await listen(configuredUpstream);
  const gateway = createProductionGateway({ target: `http://127.0.0.1:${configuredUpstreamPort}` });
  const gatewayPort = await listen(gateway);
  t.after(() => gateway.close());
  t.after(() => configuredUpstream.close());
  t.after(() => alternate.close());

  const absolute = await fetchFrom(gatewayPort, `http://127.0.0.1:${alternatePort}/proof`);
  const networkPath = await fetchFrom(gatewayPort, `//127.0.0.1:${alternatePort}/proof`);

  assert.deepEqual(absolute, { statusCode: 400, body: "Invalid request target." });
  assert.deepEqual(networkPath, { statusCode: 400, body: "Invalid request target." });
  assert.equal(alternateReceived, false);
});
