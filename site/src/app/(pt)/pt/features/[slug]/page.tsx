import type { Metadata } from "next";
import { pageMetadata } from "@/components/Document";
import FeaturePage, { findFeature } from "@/components/FeaturePage";
import { featureTitle } from "@/components/Home";
import { catalogue } from "@/lib/catalogue";

type Params = { params: Promise<{ slug: string }> };

export const dynamicParams = false;

export function generateStaticParams() {
  return catalogue().map((feature) => ({ slug: feature.slug }));
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  const { feature } = findFeature(slug);
  return pageMetadata("pt", `/features/${slug}/`, featureTitle("pt", feature), feature.summary.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1").replace(/[*`]/g, ""));
}

export default async function Page({ params }: Params) {
  const { slug } = await params;
  return <FeaturePage lang="pt" slug={slug} />;
}
