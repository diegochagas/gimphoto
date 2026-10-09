import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import donate from "../content/donate.json";
import showcase from "../content/features.json";
import { IMAGES, readmeRows } from "@/lib/catalogue";
import { textKeys } from "@/lib/i18n";

describe("the site's own content", () => {
  it("has every interface text in English and Portuguese", () => {
    const keys = textKeys();
    expect(keys.pt).toEqual(keys.en);
  });

  it("shows only screenshots that exist and features that have a page", () => {
    const slugs = new Set(readmeRows().map((r) => r.slug));
    for (const item of showcase.showcase) {
      expect(fs.existsSync(path.join(IMAGES, item.image)), item.image).toBe(true);
      expect(slugs.has(item.docs), item.docs).toBe(true);
      expect(item.title.pt && item.text.pt, item.id).toBeTruthy();
    }
    for (const slug of Object.keys(showcase.titles)) expect(slugs.has(slug), slug).toBe(true);
  });

  it("has a valid donation config: https links, a complete PIX or none", () => {
    for (const [id, url] of Object.entries(donate.links)) {
      expect(url === "" || url.startsWith("https://"), id).toBe(true);
    }
    const { key, name, city } = donate.pix;
    expect([key, name, city].every(Boolean) || [key, name, city].every((v) => !v)).toBe(true);
    expect(donate.goal.monthly).toBeGreaterThanOrEqual(0);
  });
});
