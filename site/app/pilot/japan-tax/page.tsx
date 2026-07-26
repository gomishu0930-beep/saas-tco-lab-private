import type { Metadata } from "next";
import { PilotArticle } from "../../components/PilotArticle";
import { pilotPage } from "../../lib/pilot-pages";
const page = pilotPage("japan-tax");
export const metadata: Metadata = { title: "合成pilot・日本向け税通貨", description: "日本向け税と通貨検証記事の合成noindex構造。" };
export default function Page() { return <PilotArticle page={page} />; }
