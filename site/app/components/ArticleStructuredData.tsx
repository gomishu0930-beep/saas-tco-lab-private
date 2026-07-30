import type { EditorialContract } from "../lib/editorial-input-contract";
import type { PilotPage } from "../lib/pilot-pages";
import { articleStructuredData, serializeStructuredData } from "../lib/structured-data";

export function ArticleStructuredData({
  page,
  contract,
}: {
  page: PilotPage;
  contract: EditorialContract | null;
}) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: serializeStructuredData(articleStructuredData(page, contract)) }}
    />
  );
}
