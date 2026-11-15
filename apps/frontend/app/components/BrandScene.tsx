"use client";

import dynamic from "next/dynamic";
import { usePathname } from "next/navigation";

const BlobScene = dynamic(() => import("./blob-scene"), { ssr: false });

export default function BrandScene() {
  const pathname = usePathname();
  return pathname?.startsWith("/login") ? <BlobScene /> : null;
}
