// Before `next dev` / `next build`: what the site serves from the repository,
// made into public/ (not stored twice in git). Every screenshot in
// docs/images as WebP, full size (at most 1600 px wide) and as a 640 px
// thumbnail; the icon, a favicon and the social preview (og.png, the
// splash screen on a 1200x630 card). Only files older than their source are
// remade.
import fs from "node:fs";
import path from "node:path";
import sharp from "sharp";

const ROOT = path.resolve(import.meta.dirname, "..", "..");
const IMAGES = path.join(ROOT, "docs", "images");
const PUBLIC = path.resolve(import.meta.dirname, "..", "public");

function stale(source, dest) {
  return !fs.existsSync(dest) || fs.statSync(dest).mtimeMs < fs.statSync(source).mtimeMs;
}

fs.mkdirSync(path.join(PUBLIC, "images", "thumbs"), { recursive: true });
let made = 0;
for (const name of fs.readdirSync(IMAGES).filter((f) => f.endsWith(".png"))) {
  const source = path.join(IMAGES, name);
  const stem = name.slice(0, -4);
  for (const [dest, width] of [
    [path.join(PUBLIC, "images", `${stem}.webp`), 1600],
    [path.join(PUBLIC, "images", "thumbs", `${stem}.webp`), 640],
  ]) {
    if (!stale(source, dest)) continue;
    await sharp(source).resize({ width, withoutEnlargement: true }).webp({ quality: 82 }).toFile(dest);
    made++;
  }
}

fs.copyFileSync(path.join(ROOT, "branding", "icon.svg"), path.join(PUBLIC, "icon.svg"));
await sharp(path.join(IMAGES, "gimphoto-icon.png")).resize(64, 64).png().toFile(path.join(PUBLIC, "favicon.png"));
const splash = await sharp(path.join(IMAGES, "splash-after.png")).resize({ width: 1000, height: 630, fit: "inside" }).toBuffer();
await sharp({ create: { width: 1200, height: 630, channels: 3, background: { r: 21, g: 17, b: 29 } } })
  .composite([{ input: splash, gravity: "center" }])
  .png()
  .toFile(path.join(PUBLIC, "og.png"));
console.log(`assets: ${made} screenshot file(s) made, icon, favicon and og.png written`);
