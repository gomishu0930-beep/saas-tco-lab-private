import type { Metadata } from "next";

import { editorialContract } from "./editorial-contracts";
import { editorialPresentation } from "./editorial-presentation";
import type { PilotPage } from "./pilot-pages";

export function editorialMetadata(page: PilotPage): Metadata {
  const contract = editorialContract(page);
  const presentation = editorialPresentation(page, contract);
  const url = `https://saastcolab.jp/pilot/${page.slug}`;
  return {
    title: presentation.title,
    description: presentation.description,
    openGraph: {
      title: presentation.title,
      description: presentation.description,
      type: "article",
      url,
      siteName: "SaaS TCO Lab",
    },
    twitter: {
      card: "summary",
      title: presentation.title,
      description: presentation.description,
    },
  };
}
