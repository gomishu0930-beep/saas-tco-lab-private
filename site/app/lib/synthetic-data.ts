export type SyntheticPlan = {
  id: string;
  vendor: string;
  plan: string;
  scenario: string;
  region: string;
  tax: string;
  currency: string;
  billing: string;
  commitment: string;
  tco: string;
  fit: "適合" | "非適合";
  fitReason: string;
  evidenceRetrievedAt: string;
  dataExpiresAt: string;
  rightsExpiresAt: string;
  affiliate: "無効";
};

export type SyntheticComparison = {
  label: string;
  generatedAt: string;
  methodology: string;
  plans: SyntheticPlan[];
};

// Values are precomputed synthetic fixtures. This UI performs no price or TCO arithmetic.
export const syntheticComparison: SyntheticComparison = {
  label: "合成データ / 非本番",
  generatedAt: "2026-07-21 21:00 JST",
  methodology:
    "1 seat・12か月の固定scenario。契約期間中の固定費をcanonical Python TCOから受領。",
  plans: [
    {
      id: "sample-a-basic",
      vendor: "Sample Vendor A",
      plan: "Basic",
      scenario: "1 seat / 12 months / usage 0",
      region: "JP",
      tax: "税込（合成条件）",
      currency: "JPY",
      billing: "月次請求",
      commitment: "12か月",
      tco: "JPY 13,200",
      fit: "適合",
      fitReason: "合成scenarioのseat数と契約期間を満たすため。",
      evidenceRetrievedAt: "2026-07-21 20:00 JST",
      dataExpiresAt: "2026-07-28 21:00 JST",
      rightsExpiresAt: "2026-08-20 21:00 JST",
      affiliate: "無効",
    },
    {
      id: "sample-b-starter",
      vendor: "Sample Vendor B",
      plan: "Starter",
      scenario: "1 seat / 12 months / usage 0",
      region: "JP",
      tax: "税込（合成条件）",
      currency: "JPY",
      billing: "年次請求",
      commitment: "12か月",
      tco: "JPY 18,000",
      fit: "非適合",
      fitReason: "合成scenarioで必要とする監査機能を含まないため。",
      evidenceRetrievedAt: "2026-07-21 20:00 JST",
      dataExpiresAt: "2026-07-28 21:00 JST",
      rightsExpiresAt: "2026-08-20 21:00 JST",
      affiliate: "無効",
    },
  ],
};
