import type { Metadata } from "next";
import { PilotArticle } from "../../components/PilotArticle";
import { pilotPage } from "../../lib/pilot-pages";
const page = pilotPage("annual-vs-monthly");
export const metadata: Metadata = { title: "合成pilot・年契約と月契約", description: "年契約と月契約比較記事の合成noindex構造。" };
export default function Page() { return <PilotArticle page={page} />; }
