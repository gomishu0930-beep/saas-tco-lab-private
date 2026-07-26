import type { Metadata } from "next";
import { PilotArticle } from "../../components/PilotArticle";
import { pilotPage } from "../../lib/pilot-pages";
const page = pilotPage("addon-cost");
export const metadata: Metadata = { title: "合成pilot・追加機能費用", description: "追加機能費用記事の合成noindex構造。" };
export default function Page() { return <PilotArticle page={page} />; }
