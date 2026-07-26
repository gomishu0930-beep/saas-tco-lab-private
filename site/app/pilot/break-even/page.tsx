import type { Metadata } from "next";
import { PilotArticle } from "../../components/PilotArticle";
import { pilotPage } from "../../lib/pilot-pages";
const page = pilotPage("break-even");
export const metadata: Metadata = { title: "合成pilot・損益分岐", description: "損益分岐検証記事の合成noindex構造。" };
export default function Page() { return <PilotArticle page={page} />; }
