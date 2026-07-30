import { PilotArticle } from "../../components/PilotArticle";
import { editorialMetadata } from "../../lib/editorial-metadata";
import { pilotPage } from "../../lib/pilot-pages";
const page = pilotPage("annual-vs-monthly");
export const metadata = editorialMetadata(page);
export default function Page() { return <PilotArticle page={page} />; }
