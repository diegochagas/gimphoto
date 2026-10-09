import Home from "@/components/Home";
import { pageMetadata } from "@/components/Document";

export const metadata = pageMetadata("pt", "/");

export default function Page() {
  return <Home lang="pt" />;
}
