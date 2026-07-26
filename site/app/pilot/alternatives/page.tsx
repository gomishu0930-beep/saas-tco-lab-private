import type { Metadata } from "next";
import { PilotArticle } from "../../components/PilotArticle";
import { pilotPage } from "../../lib/pilot-pages";
const page = pilotPage("alternatives");
export const metadata: Metadata = { title: "合成pilot・代替候補", description: "代替候補記事の合成noindex構造。" };
export default function Page() { return <PilotArticle page={page} />; }
