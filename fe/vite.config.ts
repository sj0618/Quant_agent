import { fileURLToPath, URL } from "node:url";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

type ProxyTarget = {
  target: string;
  changeOrigin: boolean;
  xfwd: boolean;
  rewrite?: (path: string) => string;
};

type BackendProxyConfig = {
  mode: "split" | "combined";
  proxy: Record<"/api/v1" | "/ai-api", ProxyTarget>;
};

function trimTrailingSlash(value: string | undefined) {
  return value ? value.replace(/\/+$/, "") : "";
}

export function createBackendProxyConfig(env: Record<string, string | undefined>): BackendProxyConfig {
  const backendTarget = trimTrailingSlash(env.BACKEND_PROXY_TARGET) || "http://127.0.0.1:18002";
  const aiTarget = trimTrailingSlash(env.AI_BACKEND_PROXY_TARGET) || "http://127.0.0.1:18001";
  const combinedTarget = trimTrailingSlash(env.COMBINED_BACKEND_PROXY_TARGET);
  if (combinedTarget) {
    return {
      mode: "combined",
      proxy: {
        "/api/v1": {
          target: combinedTarget,
          changeOrigin: true,
          xfwd: true,
        },
        "/ai-api": {
          target: combinedTarget,
          changeOrigin: true,
          xfwd: true,
        },
      },
    };
  }
  return {
    mode: "split",
    proxy: {
      "/api/v1": {
        target: backendTarget,
        changeOrigin: true,
        xfwd: true,
      },
      "/ai-api": {
        target: aiTarget,
        changeOrigin: true,
        xfwd: true,
        rewrite: (path: string) => path.replace(/^\/ai-api/, ""),
      },
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const { mode: proxyMode, proxy } = createBackendProxyConfig(env);
  console.info(`[vite] backend proxy mode=${proxyMode}`);

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    server: {
      host: "0.0.0.0",
      port: 18000,
      allowedHosts: [
        "qt-agent.kro.kr",
      ],
      proxy,
    },
    preview: {
      host: "0.0.0.0",
      port: 18000,
      allowedHosts: [
        "qt-agent.kro.kr",
      ],
      proxy,
    },
  };
});
