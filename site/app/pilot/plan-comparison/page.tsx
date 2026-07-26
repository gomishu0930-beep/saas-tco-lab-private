import type { Metadata } from "next";
import { PilotArticle } from "../../components/PilotArticle";
import { pilotPage } from "../../lib/pilot-pages";
const page = pilotPage("plan-comparison");
export const metadata: Metadata = { title: "合成pilot・プラン比較", description: "プラン比較記事の合成noindex構造。" };
export default function Page() { return <PilotArticle page={page} />; }
