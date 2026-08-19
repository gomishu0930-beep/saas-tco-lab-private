import savedM3ServerCandidates from "../../../artifacts/category-expansion-inputs/M3-servers-3vendor-candidate-2026-08-18.json";
import savedSvr01Candidate from "../../../artifacts/category-expansion-inputs/SVR01-servers-category-expansion-input-v3-2026-08-14.json";

import {
  reviewedServerCandidateEvidence,
  reviewedServerCandidateEvidenceBatch,
  type ServerCandidateEvidenceSource,
} from "./editorial-input-contract";
import type { ServerZeroInputContract } from "./tco";

export const serverUseCaseRequirements = {
  small_site: ["storage 100GB以上", "転送量無制限", "backup利用可", "無料SSL"],
  corporate_site: ["small_site条件", "複数人管理またはmanaged運用"],
  ecommerce: ["small_site条件", "EC用途またはECアプリ対応"],
} as const satisfies ServerZeroInputContract["useCaseRequirements"];

export const m3ServerSources = [
  {
    vendorId: "conoha-wing",
    planId: "wing-pack-standard-12m",
    displayName: "ConoHa WING Standard（WINGパック12か月）",
    expectedSourceHost: "www.conoha.jp",
    eligibleUseCases: ["small_site"],
  },
  {
    vendorId: "sakura-rental-server",
    planId: "business-12m",
    displayName: "さくらのレンタルサーバ Business（12か月）",
    expectedSourceHost: "rs.sakura.ad.jp",
    eligibleUseCases: ["small_site", "corporate_site"],
  },
  {
    vendorId: "kagoya",
    planId: "light-1c4g-12m",
    displayName: "KAGOYA Light（1コア/4GB・12か月）",
    expectedSourceHost: "www.kagoya.jp",
    eligibleUseCases: ["small_site", "corporate_site"],
  },
] as const satisfies readonly ServerCandidateEvidenceSource[];

export const m3ServerEvidence = reviewedServerCandidateEvidenceBatch(
  savedM3ServerCandidates,
  m3ServerSources,
) ?? [];

export const xserverSmallSiteEvidence = reviewedServerCandidateEvidence(
  savedSvr01Candidate,
  "XServerビジネス 共有スタンダード（12か月）",
  "business.xserver.ne.jp",
  ["small_site"],
);

export const serverFirstYearComparisonEvidence = [
  ...(xserverSmallSiteEvidence ? [xserverSmallSiteEvidence] : []),
  ...m3ServerEvidence,
];

export const m3ConfirmedFirstYearEvidence = m3ServerEvidence.filter(
  (evidence) => evidence.initialPayment !== null,
);
