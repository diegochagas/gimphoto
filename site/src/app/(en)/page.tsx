import Home from "@/components/Home";
import { pageMetadata } from "@/components/Document";

export const metadata = pageMetadata("en", "/");

export default function Page() {
  return <Home lang="en" />;
}
