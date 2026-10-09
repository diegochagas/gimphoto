import type { MetadataRoute } from "next";
import { catalogue } from "@/lib/catalogue";
import { LANGS, localePath } from "@/lib/i18n";
import { SITE_URL } from "@/lib/site";

export const dynamic = "force-static";

export default function sitemap(): MetadataRoute.Sitemap {
  const paths = ["/", ...catalogue().map((f) => `/features/${f.slug}/`)];
  return paths.flatMap((path) => LANGS.map((lang) => ({ url: `${SITE_URL}${localePath(lang, path)}` })));
}
