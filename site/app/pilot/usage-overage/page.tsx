import type { Metadata } from "next";
import { PilotArticle } from "../../components/PilotArticle";
import { pilotPage } from "../../lib/pilot-pages";
const page = pilotPage("usage-overage");
export const metadata: Metadata = { title: "合成pilot・従量超過", description: "従量超過費用記事の合成noindex構造。" };
export default function Page() { return <PilotArticle page={page} />; }
