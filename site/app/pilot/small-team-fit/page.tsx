import type { Metadata } from "next";
import { PilotArticle } from "../../components/PilotArticle";
import { pilotPage } from "../../lib/pilot-pages";
const page = pilotPage("small-team-fit");
export const metadata: Metadata = { title: "合成pilot・小規模チーム", description: "小規模チーム適合記事の合成noindex構造。" };
export default function Page() { return <PilotArticle page={page} />; }
