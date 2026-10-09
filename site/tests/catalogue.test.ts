import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { IMAGES, catalogue, cover, pngSize, readmeRows, testsOf } from "@/lib/catalogue";

const features = catalogue();

describe("the feature catalogue (README + docs/features)", () => {
  it("has every README feature, each with its own page", () => {
    expect(features.length).toBe(readmeRows().length);
    expect(features.length).toBeGreaterThanOrEqual(20);
    expect(new Set(features.map((f) => f.slug)).size).toBe(features.length);
  });

  it("points only at screenshots that exist", () => {
    for (const feature of features) {
      for (const shot of [feature.before, feature.after, ...feature.gallery]) {
        if (shot) expect(fs.existsSync(path.join(IMAGES, shot.file)), `${feature.slug}: ${shot.file}`).toBe(true);
      }
    }
  });

  it("finds the before and after pair of the pages that have one", () => {
    const clipping = features.find((f) => f.slug === "clipping-masks");
    expect(clipping?.before?.file).toBe("clipping-masks-before.png");
    expect(clipping?.after?.file).toBe("clipping-masks.png");
    expect(clipping?.after?.caption).toMatch(/clipped/);
    // the pair is not repeated in the gallery
    expect(clipping?.gallery.map((s) => s.file)).not.toContain("clipping-masks.png");
  });

  it("reads how each feature is tested, in its page's own words", () => {
    expect(features.find((f) => f.slug === "fill-layers")?.tests).toMatch(/^\*\*Smoke test\*\*/);
    expect(features.find((f) => f.slug === "merge-layers")?.tests).toMatch(/smoke_merge_layers/);
    expect(features.find((f) => f.slug === "layer-style-fx-button")?.tests).toMatch(/scripts\/smoke/);
    // most pages say how they are tested
    expect(features.filter((f) => f.tests).length).toBeGreaterThan(features.length / 2);
  });

  it("reads a list item that says how the feature is tested", () => {
    expect(features.find((f) => f.slug === "psd-editable-text")?.tests).toMatch(/smoke_psd_text/);
    expect(features.find((f) => f.slug === "smart-objects")?.tests).toMatch(/^\*\*Tests:\*\* `tests\/smoke_smart_objects\.py`/);
    const md = "- **Use:** x\n- **Tests:** unit tests;\n  smoke too:\n  - a\n  - b\n- **Limits:** y\n";
    expect(testsOf(md)).toBe("**Tests:** unit tests;\nsmoke too:\n- a\n- b");
  });

  it("keeps a test paragraph's list and stops at the next paragraph", () => {
    const md = "## What changed\n\n**Tests:**\n- one\n- two\n  more\n\nNext paragraph.\n";
    expect(testsOf(md)).toBe("**Tests:**\n- one\n- two\n  more");
  });

  it("starts each summary after the name and its (AI) note", () => {
    const fill = features.find((f) => f.slug === "generative-fill");
    expect(fill?.summary).toMatch(/^a prompt fills the selection/);
    for (const feature of features) expect(feature.summary, feature.slug).not.toMatch(/^[(:,]/);
  });

  it("marks the AI features", () => {
    expect(features.find((f) => f.slug === "remove-tool")?.ai).toBe(true);
    expect(features.find((f) => f.slug === "clipping-masks")?.ai).toBe(false);
  });

  it("covers each card with a window-sized screenshot, not a menu blown up", () => {
    expect(cover(features.find((f) => f.slug === "clipping-masks")!)?.file).toBe("clipping-masks.png");
    const fx = cover(features.find((f) => f.slug === "layer-style-fx-button")!);
    expect(fx && pngSize(fx.file).width).toBeGreaterThanOrEqual(900);
    expect(cover(features.find((f) => f.slug === "comfyui-with-gimphoto")!)).toBeNull();
  });
});
