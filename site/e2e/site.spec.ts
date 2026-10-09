// GIMPhoto's site as published, in Chromium at desktop and phone width.
// Nothing outside this machine is called: GitHub's API is answered here
// (the fonts are self-hosted by the build).
import { mkdirSync } from "node:fs";
import AxeBuilder from "@axe-core/playwright";
import { type Page, expect, test } from "@playwright/test";

const BASE = "/gimphoto";
const SHOTS = "../work/site-e2e/screenshots";

const GITHUB: Record<string, unknown> = {
  "repos/diegochagas/gimphoto": { stargazers_count: 1234 },
  "repos/diegochagas/gimphoto/releases/latest": { tag_name: "v3.2.6-1" },
  "repos/diegochagas/gimphoto/issues": [
    { number: 66, title: "PhotoCraft comparison", body: "tracking", html_url: "https://github.com/x/66" },
    { number: 71, title: "Vibrance adjustment (Image › Adjustments › Vibrance)", body: "Part of #66", html_url: "https://github.com/x/71", reactions: { "+1": 3 } },
    { number: 72, title: "Photo Filter adjustment", body: "Part of #66 (priority high)", html_url: "https://github.com/x/72", reactions: { "+1": 0 } },
    { number: 90, title: "A pull request", body: "Part of #66", pull_request: {}, html_url: "https://github.com/x/90" },
    { number: 140, title: "Project site", body: "no parent", html_url: "https://github.com/x/140" },
  ],
};

async function offline(page: Page) {
  await page.route("https://api.github.com/**", (route) => {
    const body = GITHUB[new URL(route.request().url()).pathname.slice(1)];
    return body ? route.fulfill({ json: body }) : route.fulfill({ status: 404, json: {} });
  });
}

function watchErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (msg) => { if (msg.type() === "error") errors.push(msg.text()); });
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("requestfailed", (request) => errors.push(`${request.url()}: ${request.failure()?.errorText}`));
  page.on("response", (response) => {
    if (response.status() >= 400 && !response.url().includes("api.github.com")) errors.push(`${response.url()}: ${response.status()}`);
  });
  page.on("request", (request) => {
    const host = new URL(request.url()).hostname;
    if (!["127.0.0.1", "api.github.com"].includes(host) && !request.url().startsWith("data:")) errors.push(`outside request: ${request.url()}`);
  });
  return errors;
}

async function noSideScroll(page: Page) {
  const { scroll, client } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
  expect(scroll, "no horizontal scroll").toBeLessThanOrEqual(client);
}

async function imagesLoad(page: Page) {
  const sources = await page.locator("main img").evaluateAll((imgs) => imgs.map((i) => (i as HTMLImageElement).src));
  for (const src of sources.filter((s) => !s.startsWith("data:"))) expect((await page.request.get(src)).status(), src).toBe(200);
}

test.beforeEach(async ({ page }) => {
  // a fresh visitor: no saved language (once per test, so a reload keeps it)
  await page.addInitScript(() => {
    try {
      if (!sessionStorage.getItem("e2e-fresh")) {
        localStorage.clear();
        sessionStorage.setItem("e2e-fresh", "1");
      }
    } catch { /* none */ }
  });
});

test("the home page loads every part, with no errors and nothing from outside", async ({ page }) => {
  await offline(page);
  const errors = watchErrors(page);
  await page.goto(`${BASE}/`);
  await expect(page.locator("h1")).toContainText("Photoshop's tools.");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.locator(".feature")).toHaveCount(10);
  const cards = page.locator(".catalogue .card");
  expect(await cards.count()).toBeGreaterThanOrEqual(20);
  await expect(page.locator("[data-stat=features]")).toHaveText(String(await cards.count()));
  await expect(page.locator(".stats [data-stat=stars]")).toHaveText("1.2k");
  await expect(page.locator(".badge [data-stat=release]")).toHaveText("v3.2.6-1");
  await expect(page.locator(".stats [data-stat=roadmap]")).toHaveText("2");
  await imagesLoad(page);
  await noSideScroll(page);
  expect(errors).toEqual([]);
});

test("search engines and link previews get what they need", async ({ page }) => {
  await offline(page);
  await page.goto(`${BASE}/`);
  await expect(page).toHaveTitle(/GIMPhoto/);
  await expect(page.locator('meta[name="description"]')).toHaveAttribute("content", /GIMP/);
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", "https://diegochagas.github.io/gimphoto/");
  await expect(page.locator('link[rel="alternate"][hreflang="pt-BR"]')).toHaveAttribute("href", "https://diegochagas.github.io/gimphoto/pt/");
  for (const property of ["og:title", "og:description", "og:image", "og:url"]) {
    await expect(page.locator(`meta[property="${property}"]`)).toHaveAttribute("content", /.+/);
  }
  for (const path of ["/robots.txt", "/sitemap.xml", "/og.png", "/favicon.png", "/icon.svg"]) {
    expect((await page.request.get(`${BASE}${path}`)).status(), path).toBe(200);
  }
});

test("the language switch goes to the Portuguese page and is remembered", async ({ page }) => {
  await offline(page);
  await page.goto(`${BASE}/`);
  await page.locator("a.lang").click();
  await expect(page).toHaveURL(`${BASE}/pt/`);
  await expect(page.locator("h1")).toContainText("As ferramentas do Photoshop.");
  await expect(page.locator("html")).toHaveAttribute("lang", "pt-BR");
  await expect(page.locator(".feature h3").first()).toHaveText("Estilos de camada, no botão fx");
  // the English home sends this visitor to Portuguese now
  await page.goto(`${BASE}/`);
  await expect(page).toHaveURL(`${BASE}/pt/`);
  await page.locator("a.lang").click();
  await expect(page).toHaveURL(`${BASE}/`);
  await page.reload();
  await expect(page.locator("h1")).toContainText("Photoshop's tools.");
});

test("a Portuguese browser's first visit opens the Portuguese page", async ({ browser }) => {
  const context = await browser.newContext({ locale: "pt-BR" });
  const page = await context.newPage();
  await offline(page);
  await page.goto(`${BASE}/`);
  await expect(page).toHaveURL(`${BASE}/pt/`);
  await context.close();
});

test("without JavaScript every part is still there and visible", async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto(`${BASE}/`);
  await expect(page.locator("h1")).toContainText("Photoshop's tools.");
  await expect(page.locator(".feature").first()).toBeVisible();
  await expect(page.locator(".catalogue .card").first()).toBeVisible();
  await page.goto(`${BASE}/features/fill-layers/`);
  await expect(page.locator("[data-tests]")).toContainText("Smoke test");
  await context.close();
});

test("the roadmap lists the open feature issues with their votes", async ({ page }) => {
  await offline(page);
  await page.goto(`${BASE}/`);
  const items = page.locator(".roadmap li.item");
  await expect(items).toHaveCount(2);
  await expect(items.first().locator("a.title")).toHaveText("Vibrance adjustment (Image › Adjustments › Vibrance)");
  await expect(items.first().locator("a.vote")).toHaveText("👍 3");
});

test("without GitHub the page still works and says so", async ({ page }) => {
  await page.route("https://api.github.com/**", (route) => route.abort());
  await page.goto(`${BASE}/`);
  await expect(page.locator(".roadmap")).toContainText("could not be loaded");
  await expect(page.locator(".badge [data-stat=release]")).toHaveText("v3.2.6");
});

test("install tabs switch, and Copy copies the commands without comments", async ({ page, context }) => {
  await offline(page);
  await page.goto(`${BASE}/`);
  await page.locator("#tab-source").click();
  await expect(page.locator("#panel-source")).toBeVisible();
  await expect(page.locator("#panel-bundle")).toBeHidden();
  await page.keyboard.press("ArrowLeft");
  await expect(page.locator("#panel-bundle")).toBeVisible();
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.locator("[data-copy]").click();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied).toContain("flatpak install --user GIMPhoto.flatpak");
  expect(copied).not.toContain("#");
  await expect(page.locator("[data-copy]")).toHaveText("Copied");
});

test("with no donation method set up yet, the section says donations open soon", async ({ page }) => {
  await offline(page);
  await page.goto(`${BASE}/`);
  await expect(page.locator("#donate [data-soon]")).toBeVisible();
  await expect(page.locator("#donate h2")).toContainText("Help the next Photoshop feature land.");
});

test("a catalogue card opens its feature: before and after, tests, more screenshots", async ({ page }) => {
  await offline(page);
  const errors = watchErrors(page);
  await page.goto(`${BASE}/`);
  await page.locator(".catalogue .card", { hasText: "Clipping masks" }).click();
  await expect(page).toHaveURL(`${BASE}/features/clipping-masks/`);
  await expect(page.locator("h1")).toHaveText("Clipping masks");
  await expect(page.locator(".compare figure")).toHaveCount(2);
  await expect(page.locator(".compare img").last()).toHaveAttribute("src", `${BASE}/images/clipping-masks.webp`);
  await expect(page.locator("[data-tests]")).toContainText("tests/smoke_clipping_mask.py");
  await expect(page.locator(".gallery figure").first()).toBeVisible();
  await expect(page.locator("a", { hasText: "Read the whole page on GitHub" })).toHaveAttribute("href", /docs\/features\/clipping-masks\.md$/);
  await imagesLoad(page);
  await noSideScroll(page);
  // in Portuguese: the page's labels, and a note that the details are in English
  await page.locator("a.lang").click();
  await expect(page).toHaveURL(`${BASE}/pt/features/clipping-masks/`);
  await expect(page.locator("h1")).toHaveText("Máscaras de recorte");
  await expect(page.locator("#tests-title")).toHaveText("Como é testado");
  await expect(page.locator(".note-en")).toBeVisible();
  expect(errors).toEqual([]);
});

test("every feature page in the sitemap is there, with its screenshots", async ({ page }) => {
  await offline(page);
  const sitemap = await (await page.request.get(`${BASE}/sitemap.xml`)).text();
  const urls = [...sitemap.matchAll(/<loc>https:\/\/diegochagas\.github\.io(\/gimphoto\/[^<]*)<\/loc>/g)].map((m) => m[1]);
  expect(urls.length).toBeGreaterThanOrEqual(42);
  for (const url of urls) {
    const response = await page.request.get(url);
    expect(response.status(), url).toBe(200);
    const html = await response.text();
    for (const src of [...html.matchAll(/src="(\/gimphoto\/images\/[^"]+)"/g)].map((m) => m[1])) {
      expect((await page.request.get(src)).status(), `${url}: ${src}`).toBe(200);
    }
  }
});

test("no serious accessibility problems on the home page and a feature page", async ({ page }) => {
  await offline(page);
  for (const path of [`${BASE}/`, `${BASE}/features/generative-fill/`]) {
    await page.goto(path);
    await expect(page.locator("h1")).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    const serious = results.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? ""));
    expect(serious.map((v) => `${path} ${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
  }
});

test("screenshots for review", async ({ page }, testInfo) => {
  mkdirSync(SHOTS, { recursive: true });
  await offline(page);
  const name = testInfo.project.name;
  for (const [path, file] of [
    [`${BASE}/`, "home-en"],
    [`${BASE}/pt/`, "home-pt"],
    [`${BASE}/features/clipping-masks/`, "feature-en"],
    [`${BASE}/pt/features/generative-fill/`, "feature-pt"],
  ]) {
    await page.goto(path);
    // through the whole page, so the lazy screenshots load, then back up
    await page.evaluate(async () => {
      for (let y = 0; y < document.body.scrollHeight; y += 600) {
        window.scrollTo(0, y);
        await new Promise((r) => setTimeout(r, 40));
      }
      window.scrollTo(0, 0);
    });
    await page.waitForLoadState("networkidle");
    await page.waitForFunction(() => [...document.images].every((i) => i.complete));
    await page.screenshot({ path: `${SHOTS}/${name}-${file}.png`, fullPage: true });
  }
});
