import type { Metadata } from "next";
import { PilotArticle } from "../../components/PilotArticle";
import { pilotPage } from "../../lib/pilot-pages";
const page = pilotPage("migration-cost");
export const metadata: Metadata = { title: "合成pilot・移行コスト", description: "移行コスト記事の合成noindex構造。" };
export default function Page() { return <PilotArticle page={page} />; }
