import { defineConfig, devices } from "@playwright/test";

// The site as GitHub Pages serves it: built with the /gimphoto base path and
// served from a folder of that name.
const PORT = 4311;
const ROOT = "../work/site-e2e/root";

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  outputDir: "../work/site-e2e/results",
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${PORT}`, reducedMotion: "reduce", locale: "en-US" },
  webServer: {
    command: `SITE_BASE_PATH=/gimphoto npm run build && rm -rf ${ROOT} && mkdir -p ${ROOT} && cp -r out ${ROOT}/gimphoto && python3 -m http.server ${PORT} --bind 127.0.0.1 --directory ${ROOT}`,
    url: `http://127.0.0.1:${PORT}/gimphoto/`,
    reuseExistingServer: false,
    timeout: 300_000,
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } } },
    { name: "mobile", use: { ...devices["Pixel 7"], viewport: { width: 375, height: 812 }, deviceScaleFactor: 1 } },
  ],
});
