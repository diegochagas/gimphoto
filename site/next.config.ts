import type { NextConfig } from "next";

// Static files for GitHub Pages: the site lives under /gimphoto there
// (SITE_BASE_PATH=/gimphoto in the workflow), at / locally.
const basePath = process.env.SITE_BASE_PATH ?? "";

const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  basePath,
  images: { unoptimized: true },
  env: { NEXT_PUBLIC_BASE_PATH: basePath },
  // the docs and screenshots it reads at build time are one level up
  outputFileTracingRoot: process.cwd(),
};

export default nextConfig;
