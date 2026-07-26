import type { Metadata } from "next";
import { PilotArticle } from "../../components/PilotArticle";
import { pilotPage } from "../../lib/pilot-pages";
const page = pilotPage("evidence-method");
export const metadata: Metadata = { title: "合成pilot・根拠検証", description: "field単位の根拠検証記事の合成noindex構造。" };
export default function Page() { return <PilotArticle page={page} />; }
