// fe/docs/email-template/daily-digest.sample.html 을 다시 만든다. BE가 FE dev 서버를 띄우지 않고도
// 실제 이메일 HTML 파일 하나를 열어볼 수 있게 하는 용도.
//   node fe/scripts/generate-daily-digest-email.mjs
//
// node 22는 .tsx 를 직접 못 읽으므로(ERR_UNKNOWN_FILE_EXTENSION) vite 의 ssrLoadModule 로 로드한다.
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");
const outputPath = resolve(root, "docs/email-template/daily-digest.sample.html");

const server = await createServer({
  configFile: false,
  root,
  logLevel: "warn",
  server: { middlewareMode: true },
  // ssrLoadModule 만 쓰므로 index.html 기준 의존성 스캔은 불필요하다. 켜두면 스캔이 백그라운드로
  // 돌다가 server.close() 와 경합해서 무해한 에러를 뱉는다.
  optimizeDeps: { noDiscovery: true },
});

try {
  const { renderDailyDigestEmailHtml, dailyDigestEmailSubject } = await server.ssrLoadModule(
    "/src/features/reports/DailyDigestEmail.tsx",
  );
  const { dailyDigestReport } = await server.ssrLoadModule("/src/mocks/dailyDigest.mock.ts");

  // 절대 주소를 일부러 넣는다. BE가 운영에서 넘겨야 하는 값이고, 커밋된 샘플의 링크도 눌러진다.
  const html = renderDailyDigestEmailHtml({ digest: dailyDigestReport, baseUrl: "http://quant-agent.kro.kr:38000" });

  mkdirSync(dirname(outputPath), { recursive: true });
  writeFileSync(outputPath, html, "utf8");

  console.log(`subject: ${dailyDigestEmailSubject(dailyDigestReport)}`);
  console.log(`wrote:   ${outputPath} (${html.length} bytes)`);
} finally {
  await server.close();
}
