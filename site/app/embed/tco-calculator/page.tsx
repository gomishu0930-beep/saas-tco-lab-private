import type { Metadata } from "next";

import { AdvertisingDisclosure } from "../../components/AdvertisingDisclosure";
import { TcoCalculator } from "../../components/TcoCalculator";

export const metadata: Metadata = {
  title: "埋め込み用12か月TCO計算機",
  description: "Human確認値を端末内だけで計算する埋め込み用12か月TCO計算機。",
  robots: {
    index: false,
    follow: false,
    noarchive: true,
    nosnippet: true,
  },
};

export default function EmbeddedTcoCalculatorPage() {
  return (
    <main id="main-content" className="embed-page">
      <AdvertisingDisclosure />
      <h1>埋め込み用12か月TCO計算機</h1>
      <TcoCalculator embedded sourceHref="/methodology/" />
    </main>
  );
}
