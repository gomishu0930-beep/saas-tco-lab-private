import { PilotArticle } from "../../components/PilotArticle";
import { TcoCalculator } from "../../components/TcoCalculator";
import { editorialMetadata } from "../../lib/editorial-metadata";
import { pilotPage } from "../../lib/pilot-pages";
const page = pilotPage("pricing-calculator");
export const metadata = editorialMetadata(page);
export default function Page() {
  return (
    <PilotArticle page={page}>
      <TcoCalculator blockedReason="通貨、税区分、超過単価がunknownです。確定後に同じPython仕様の計算を再開します。" />
    </PilotArticle>
  );
}
