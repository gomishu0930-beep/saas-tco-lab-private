export type PilotNumericField = {
  key: string;
  label: string;
  valueKind:
    | "price"
    | "quota"
    | "seat_count"
    | "tax_rate"
    | "exchange_rate"
    | "duration"
    | "usage"
    | "percentage"
    | "other";
  inputScope?: "vendor_plan" | "human_scenario";
};

export type PilotPage = {
  id: `P${string}`;
  slug: string;
  title: string;
  intent: string;
  pageType: string;
  question: string;
  readerOutcome: string;
  numericFields: readonly PilotNumericField[];
};

export type ServerArticleSlateEntry = {
  id: `SVR${string}`;
  slug: string;
  topic: string;
  sourceQuery: string;
  queryMatch: "exact";
  competitionStatus: "unobserved";
  selectionBasis: "transaction_intent_specificity_proxy";
  titleTemplate: string;
  readerQuestion: string;
  state: "candidate_only";
  layoutOrder: readonly ["disclosure", "calculator", "result", "cta_slot", "evidence"];
  reviewVoices: readonly ["analyst", "editor", "skeptical_buyer"];
  sections: readonly [
    { title: "結論"; focus: string },
    { title: "比較前提"; focus: string },
    { title: "料金と上限"; focus: string },
    { title: "12か月TCO"; focus: string },
    { title: "反証"; focus: string },
    { title: "選び方"; focus: string },
  ];
};

export type ServerBigWordHub = {
  sourceQuery: string;
  state: "deferred_internal_link_hub";
};

export type ServerPartnerCtaState = {
  partnerId: string;
  partnershipApproved: boolean;
  approvalCurrent: boolean;
  disclosureCompliant: boolean;
  destinationConfigured: boolean;
  ctaGo: boolean;
  confirmedCommissionSharePercent?: number | null;
};

export type ServerCtaPresentationPolicy = {
  eligiblePartnerIds: readonly string[];
  mode: "disabled" | "single" | "comparison";
  dependencyStatus: "not_measurable" | "structural_single_partner" | "observed" | "unobserved";
  dominantSharePercent: number | null;
  dependencyWarning: boolean;
  warningThresholdPercent: 80;
};

function validServerPartnerShare(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100;
}

/** Presentation-only policy. It grants no partner, CTA, publication, or external-action authority. */
export function serverCtaPresentationPolicy(
  partners: readonly ServerPartnerCtaState[],
): ServerCtaPresentationPolicy {
  const ids = partners.map((partner) => partner.partnerId.trim());
  if (ids.some((id) => !/^[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?$/.test(id))) {
    throw new Error("server CTA partner ID is invalid");
  }
  if (new Set(ids).size !== ids.length) throw new Error("server CTA partner IDs must be unique");
  const eligible = partners
    .filter((partner) => (
      partner.partnershipApproved
      && partner.approvalCurrent
      && partner.disclosureCompliant
      && partner.destinationConfigured
      && partner.ctaGo
    ))
    .sort((left, right) => left.partnerId.localeCompare(right.partnerId));
  const eligiblePartnerIds = eligible.map((partner) => partner.partnerId);
  if (eligible.length === 0) {
    return { eligiblePartnerIds, mode: "disabled", dependencyStatus: "not_measurable", dominantSharePercent: null, dependencyWarning: false, warningThresholdPercent: 80 };
  }
  if (eligible.length === 1) {
    return { eligiblePartnerIds, mode: "single", dependencyStatus: "structural_single_partner", dominantSharePercent: 100, dependencyWarning: true, warningThresholdPercent: 80 };
  }
  const shares = eligible.map((partner) => partner.confirmedCommissionSharePercent);
  if (!shares.every(validServerPartnerShare)) {
    return { eligiblePartnerIds, mode: "comparison", dependencyStatus: "unobserved", dominantSharePercent: null, dependencyWarning: false, warningThresholdPercent: 80 };
  }
  const observedShares = shares as number[];
  if (Math.abs(observedShares.reduce((sum, value) => sum + value, 0) - 100) > 0.01) {
    throw new Error("observed server partner shares must total 100 percent");
  }
  const dominantSharePercent = Math.max(...observedShares);
  return { eligiblePartnerIds, mode: "comparison", dependencyStatus: "observed", dominantSharePercent, dependencyWarning: dominantSharePercent > 80, warningThresholdPercent: 80 };
}

export const pilotPages: readonly PilotPage[] = [
  { id: "P01", slug: "pricing-calculator", title: "料金計算", intent: "price_check", pageType: "pricing", question: "利用者数と利用量をそろえると12か月総額はいくらか", readerOutcome: "自分の利用者数と利用量で、初年度の支払総額を再計算できる", numericFields: [
    { key: "pricing.base_price", label: "基本料金", valueKind: "price" }, { key: "scenario.seat_count", label: "利用者数", valueKind: "seat_count", inputScope: "human_scenario" }, { key: "scenario.monthly_usage", label: "月間利用量", valueKind: "usage", inputScope: "human_scenario" }, { key: "pricing.overage_price", label: "超過単価", valueKind: "price" }, { key: "pricing.tax_rate", label: "税率", valueKind: "tax_rate" },
  ] },
  { id: "P02", slug: "plan-comparison", title: "プラン比較", intent: "compare", pageType: "comparison", question: "同じ利用条件で複数の料金プランをどう比較するか", readerOutcome: "同じ利用条件で価格差と上限差を比較できる", numericFields: [
    { key: "plan.price", label: "各プランの料金", valueKind: "price" }, { key: "plan.minimum_seats", label: "最低利用者数", valueKind: "seat_count" }, { key: "plan.usage_quota", label: "キーワード検索回数 / 24時間", valueKind: "quota" }, { key: "plan.overage_price", label: "超過単価", valueKind: "price" }, { key: "plan.commitment_months", label: "契約月数", valueKind: "duration" },
  ] },
  { id: "P03", slug: "alternatives", title: "代替候補", intent: "replace", pageType: "alternatives", question: "置き換え候補をTCOと適合条件でどう絞るか", readerOutcome: "必要条件を落とさず候補を3社以内へ絞れる", numericFields: [
    { key: "alternative.price", label: "各候補の料金", valueKind: "price" }, { key: "alternative.usage_quota", label: "追跡キーワード数（候補別単位）", valueKind: "quota" }, { key: "alternative.required_addon_price", label: "必須の追加機能料金", valueKind: "price" }, { key: "alternative.migration_cost", label: "移行費用", valueKind: "price" },
  ] },
  { id: "P04", slug: "small-team-fit", title: "小規模チーム適合", intent: "fit_check", pageType: "use_case_fit", question: "少人数運用で固定費と人手を抑えられるか", readerOutcome: "少人数で使う場合の固定費と運用時間を見積もれる", numericFields: [
    { key: "team.minimum_seats", label: "最低利用者数", valueKind: "seat_count" }, { key: "team.monthly_price", label: "月額料金", valueKind: "price" }, { key: "team.monthly_operation_hours", label: "月間運用時間", valueKind: "duration", inputScope: "human_scenario" }, { key: "team.onboarding_hours", label: "導入時間", valueKind: "duration", inputScope: "human_scenario" },
  ] },
  { id: "P05", slug: "enterprise-fit", title: "組織利用適合", intent: "fit_check", pageType: "use_case_fit", question: "権限・監査・運用費を含めて組織要件に合うか", readerOutcome: "組織向け必須条件と追加費用を切り分けられる", numericFields: [
    { key: "enterprise.agency_extra_seats_available", label: "Agencyで追加可能なseat数", valueKind: "seat_count" }, { key: "enterprise.agency_annual_checkout_total", label: "Agency年次checkout総額", valueKind: "price" }, { key: "enterprise.site_analysis_requests_per_24h", label: "Site analysis回数 / 24時間", valueKind: "quota" }, { key: "enterprise.migration_support_price", label: "移行支援費", valueKind: "price" },
  ] },
  { id: "P06", slug: "annual-vs-monthly", title: "年契約と月契約", intent: "compare", pageType: "comparison", question: "契約期間と解約リスクを含む総額差はいくらか", readerOutcome: "契約期間と解約リスクを含む差額を判断できる", numericFields: [
    { key: "billing.monthly_contract_price", label: "月契約料金", valueKind: "price" }, { key: "billing.annual_contract_price", label: "年契約料金", valueKind: "price" }, { key: "billing.minimum_commitment_months", label: "最低契約月数", valueKind: "duration" }, { key: "billing.termination_cost", label: "解約費用", valueKind: "price" },
  ] },
  { id: "P07", slug: "usage-overage", title: "従量超過", intent: "price_check", pageType: "pricing", question: "利用量が基準を超えた時の増分費用はいくらか", readerOutcome: "通常・繁忙期の超過費用を別々に計算できる", numericFields: [
    { key: "usage.included_quota", label: "含有利用量", valueKind: "quota" }, { key: "usage.overage_unit_size", label: "超過単位", valueKind: "usage" }, { key: "usage.overage_price", label: "超過単価", valueKind: "price" }, { key: "usage.monthly_volume", label: "月間利用量", valueKind: "usage", inputScope: "human_scenario" },
  ] },
  { id: "P08", slug: "addon-cost", title: "追加機能費用", intent: "price_check", pageType: "pricing", question: "必須の追加機能を含めた実効総額はいくらか", readerOutcome: "必須・任意の追加機能を分けて実効総額を確認できる", numericFields: [
    { key: "addon.base_price", label: "基本料金", valueKind: "price" }, { key: "addon.price", label: "追加機能の料金", valueKind: "price" }, { key: "addon.billing_unit_size", label: "追加機能の課金単位", valueKind: "usage" }, { key: "addon.required_seats", label: "必要利用者数", valueKind: "seat_count" },
  ] },
  { id: "P09", slug: "migration-cost", title: "移行コスト", intent: "migrate", pageType: "migration", question: "移行作業・重複契約・教育を含む初年度費用はいくらか", readerOutcome: "見落としやすい移行費用を初年度TCOへ足せる", numericFields: [
    { key: "migration.overlap_months", label: "重複契約月数", valueKind: "duration", inputScope: "human_scenario" }, { key: "migration.work_hours", label: "作業時間", valueKind: "duration", inputScope: "human_scenario" }, { key: "migration.hourly_cost", label: "時間単価", valueKind: "price", inputScope: "human_scenario" }, { key: "migration.training_hours", label: "教育時間", valueKind: "duration", inputScope: "human_scenario" }, { key: "migration.support_price", label: "移行支援費", valueKind: "price" },
  ] },
  { id: "P10", slug: "japan-tax", title: "日本向け税・通貨", intent: "verify_method", pageType: "methodology", question: "円換算と日本向け税表示をどう検証するか", readerOutcome: "税・通貨が未確認の値を計算から除外できる", numericFields: [
    { key: "localization.displayed_price", label: "表示価格", valueKind: "price" }, { key: "localization.tax_rate", label: "税率", valueKind: "tax_rate" }, { key: "localization.exchange_rate", label: "換算レート", valueKind: "exchange_rate" },
  ] },
  { id: "P11", slug: "break-even", title: "損益分岐", intent: "fit_check", pageType: "use_case_fit", question: "削減時間と運用費から導入の損益分岐をどう求めるか", readerOutcome: "削減時間が費用を上回る条件を試算できる", numericFields: [
    { key: "break_even.monthly_hours_saved", label: "月間削減時間", valueKind: "duration", inputScope: "human_scenario" }, { key: "break_even.hourly_cost", label: "時間単価", valueKind: "price", inputScope: "human_scenario" }, { key: "break_even.implementation_cost", label: "導入費", valueKind: "price", inputScope: "human_scenario" }, { key: "break_even.monthly_tco", label: "月額TCO", valueKind: "price", inputScope: "human_scenario" },
  ] },
  { id: "P12", slug: "evidence-method", title: "根拠の検証", intent: "verify_method", pageType: "methodology", question: "数値ごとの根拠・権利・期限をどう監査するか", readerOutcome: "数値ごとの出典と鮮度を読者自身が確認できる", numericFields: [
    { key: "evidence.review_interval_days", label: "確認間隔日数", valueKind: "duration", inputScope: "human_scenario" },
  ] },
] as const;

export const firstReleasePilotIds = ["P01", "P02", "P03"] as const;

const serverReviewVoices = ["analyst", "editor", "skeptical_buyer"] as const;

/**
 * Human-selected transaction-intent slate for the servers launch lane.
 * Query-level volume was not retained, so ordering is editorial priority and
 * must never be represented as a per-query demand ranking.
 */
const serverArticleSeeds = [
  {
    id: "SVR01", slug: "business-server-pricing", topic: "法人向け料金", sourceQuery: "法人向け サーバー 料金", queryMatch: "exact",
    titleTemplate: "法人向けサーバー料金: XServerビジネスの年次表示額・初期費用と未確認条件",
    readerQuestion: "新規12か月契約の表示額と、総額計算前に残る未確認条件は何か",
    state: "candidate_only", reviewVoices: serverReviewVoices,
    sections: [
      { title: "結論", focus: "確認済みの年次表示額・初期費用と計算停止理由" },
      { title: "比較前提", focus: "用途・契約期間・必要容量・転送量" },
      { title: "料金と上限", focus: "初期費用・基本料金・容量・転送・backup" },
      { title: "12か月の表示額", focus: "通常料金と期間限定表示を分離し、未承認の合算を行わない" },
      { title: "反証", focus: "税・更新・特典条件・超過費用の未確認項目" },
      { title: "選び方", focus: "最安ではなく用途条件を満たす候補" },
    ],
  },
  {
    id: "SVR02", slug: "small-business-server", topic: "中小企業向け", sourceQuery: "中小企業 サーバー", queryMatch: "exact",
    titleTemplate: "中小企業向けサーバー料金: 小規模運用の12か月TCO",
    readerQuestion: "中小企業の用途条件を満たす最小構成はいくらか",
    state: "candidate_only", reviewVoices: serverReviewVoices,
    sections: [
      { title: "結論", focus: "条件を満たす最小planと上位planが必要な境界" },
      { title: "比較前提", focus: "サイト数・容量・転送量・管理要件" },
      { title: "料金と上限", focus: "plan別の基本料金・上限・初期費用" },
      { title: "12か月TCO", focus: "同じ契約期間でそろえたplan別総額" },
      { title: "反証", focus: "上限表記の単位差・専用機能・見積価格" },
      { title: "選び方", focus: "将来余力を含むupgrade条件" },
    ],
  },
  {
    id: "SVR03", slug: "ec-server-cost", topic: "ECサイト費用", sourceQuery: "ECサイト サーバー 費用", queryMatch: "exact",
    titleTemplate: "ECサイト用サーバー費用: backup・転送込み12か月TCO",
    readerQuestion: "ECサイト運用に必要な容量・転送・backup込み総額はいくらか",
    state: "candidate_only", reviewVoices: serverReviewVoices,
    sections: [
      { title: "結論", focus: "用途別に残る候補と除外条件" },
      { title: "比較前提", focus: "共有・VPS・managedを混同しない比較単位" },
      { title: "料金と上限", focus: "vendor別の料金・容量・転送・backup" },
      { title: "12か月TCO", focus: "初期費用・通常料金・特典を分離した総額" },
      { title: "反証", focus: "service種別・support・SLA・regionの非同等性" },
      { title: "選び方", focus: "価格以外の必須条件で候補を絞る手順" },
    ],
  },
  {
    id: "SVR04", slug: "server-first-year-total", topic: "初期費用込み総額", sourceQuery: "サーバー 初期費用", queryMatch: "exact",
    titleTemplate: "サーバー初期費用込み総額: 契約初年度に払う金額",
    readerQuestion: "契約時支払と12か月の継続費を合わせるといくらか",
    state: "candidate_only", reviewVoices: serverReviewVoices,
    sections: [
      { title: "結論", focus: "初期費用を含む確認済み初年度総額" },
      { title: "比較前提", focus: "契約開始月・請求周期・税区分" },
      { title: "料金と上限", focus: "初期費用・初回請求・通常料金" },
      { title: "12か月TCO", focus: "初回と継続請求を二重計上しない合計" },
      { title: "反証", focus: "初月無料・返金条件・setup作業費" },
      { title: "選び方", focus: "初年度資金と継続費を分けた判断" },
    ],
  },
  {
    id: "SVR05", slug: "server-renewal-cost", topic: "更新料", sourceQuery: "サーバー 年払い 割引", queryMatch: "exact",
    titleTemplate: "サーバー2年目料金: 初回割引終了後の更新総額",
    readerQuestion: "初回特典が終わった後の更新時支払はいくらか",
    state: "candidate_only", reviewVoices: serverReviewVoices,
    sections: [
      { title: "結論", focus: "確認済み更新額と初回価格との差" },
      { title: "比較前提", focus: "初回契約期間・更新周期・自動更新時期" },
      { title: "料金と上限", focus: "通常料金・更新料・domain更新条件" },
      { title: "12か月TCO", focus: "更新が対象期間内に到来する場合だけ加算" },
      { title: "反証", focus: "初回限定・期間限定・永久無料の適用条件" },
      { title: "選び方", focus: "初回価格ではなく更新後負担を含む判断" },
    ],
  },
  {
    id: "SVR06", slug: "server-migration-cost", topic: "移行", sourceQuery: "サーバー 移行 費用", queryMatch: "exact",
    titleTemplate: "サーバー乗り換え費用: 二重支払いと作業を含む初年度TCO",
    readerQuestion: "移行支援・重複契約・Human作業を含めるといくらか",
    state: "candidate_only", reviewVoices: serverReviewVoices,
    sections: [
      { title: "結論", focus: "公式移行費とHuman scenarioを分離した総額" },
      { title: "比較前提", focus: "移行対象・停止許容時間・重複期間" },
      { title: "料金と上限", focus: "公式移行支援・対象外作業・容量制限" },
      { title: "12か月TCO", focus: "新旧契約と移行費を含む初年度合計" },
      { title: "反証", focus: "DNS・mail・database・rollbackの追加作業" },
      { title: "選び方", focus: "安さより停止リスクを抑える移行経路" },
    ],
  },
] as const;

const additionalServerArticleSeeds = [
  { id: "SVR07", slug: "business-rental-server", topic: "法人向け契約", sourceQuery: "法人向け レンタルサーバー", titleTemplate: "法人向けレンタルサーバー: 契約前に確認する総費用", readerQuestion: "法人契約で見落としやすい費用と条件は何か" },
  { id: "SVR08", slug: "ec-server-requirements", topic: "EC用途", sourceQuery: "ECサイト サーバー", titleTemplate: "ECサイト向けサーバー: 売上機会を止めない費用条件", readerQuestion: "ECサイトで必要な性能・backup・復旧条件はいくらか" },
  { id: "SVR09", slug: "business-mail-server", topic: "法人メール", sourceQuery: "メールサーバー 法人", titleTemplate: "法人メールサーバー料金: account・保全込み12か月TCO", readerQuestion: "法人メール運用に必要なaccount数と保全費用はいくらか" },
  { id: "SVR10", slug: "managed-server-cost", topic: "managed", sourceQuery: "マネージド サーバー", titleTemplate: "マネージドサーバー費用: 運用代行範囲込み12か月TCO", readerQuestion: "運用代行に含まれる作業と追加費用は何か" },
  { id: "SVR11", slug: "business-rental-server-comparison", topic: "法人比較", sourceQuery: "法人向け レンタルサーバー 比較", titleTemplate: "法人向けレンタルサーバー比較: 契約条件込み12か月TCO", readerQuestion: "法人要件を同じにするとどの候補が残るか" },
  { id: "SVR12", slug: "small-business-server-comparison", topic: "中小企業比較", sourceQuery: "中小企業 サーバー 比較", titleTemplate: "中小企業向けサーバー比較: 必要十分なプランの総額", readerQuestion: "小規模運用で過剰契約を避ける最小planはどれか" },
  { id: "SVR13", slug: "ec-server-comparison", topic: "EC比較", sourceQuery: "ECサイト サーバー 比較", titleTemplate: "ECサイト向けサーバー比較: 転送・backup込み総額", readerQuestion: "EC用途の必須条件を満たす候補はどれか" },
  { id: "SVR14", slug: "business-mail-server-comparison", topic: "法人メール比較", sourceQuery: "メールサーバー 法人 比較", titleTemplate: "法人メールサーバー比較: account・保全・移行込み総額", readerQuestion: "mail移行と保全要件まで含めるとどの候補が残るか" },
  { id: "SVR15", slug: "managed-server-comparison", topic: "managed比較", sourceQuery: "マネージド サーバー 比較", titleTemplate: "マネージドサーバー比較: 運用範囲と12か月TCO", readerQuestion: "運用代行範囲をそろえると総額はいくらか" },
  { id: "SVR16", slug: "wordpress-server-cost", topic: "WordPress費用", sourceQuery: "WordPress サーバー 費用", titleTemplate: "WordPressサーバー費用: backup・更新込み12か月TCO", readerQuestion: "WordPress運用の必須機能を含む総額はいくらか" },
  { id: "SVR17", slug: "server-transfer-cost", topic: "転送料金", sourceQuery: "サーバー データ転送 料金", titleTemplate: "サーバー転送料金: 上限超過を含む総額の確認方法", readerQuestion: "想定転送量で追加料金または制限が発生するか" },
  { id: "SVR18", slug: "server-backup-cost", topic: "backup料金", sourceQuery: "サーバー バックアップ 料金", titleTemplate: "サーバーbackup料金: 保存・復元込み12か月TCO", readerQuestion: "backup保存だけでなく復元まで含む費用はいくらか" },
  { id: "SVR19", slug: "small-corporate-server", topic: "小規模法人", sourceQuery: "サーバー 法人 小規模", titleTemplate: "小規模法人向けサーバー: 最小構成の12か月TCO", readerQuestion: "小規模法人に必要十分な容量と管理機能はいくらか" },
  { id: "SVR20", slug: "server-cancellation-terms", topic: "解約条件", sourceQuery: "サーバー 解約 条件", titleTemplate: "サーバー解約条件: 更新前に確認する費用と期限", readerQuestion: "解約期限・返金・data移行を含めた終了費用はいくらか" },
] as const;

const serverLayoutOrder = ["disclosure", "calculator", "result", "cta_slot", "evidence"] as const;

function standardServerSections(readerQuestion: string): ServerArticleSlateEntry["sections"] {
  return [
    { title: "結論", focus: `確認済み数値だけで「${readerQuestion}」へ答える` },
    { title: "比較前提", focus: "用途・契約期間・容量・転送・backup条件を固定する" },
    { title: "料金と上限", focus: "初期費用・基本料金・更新料・campaign・domain特典を分離する" },
    { title: "12か月TCO", focus: "計算機の入力値・結果・請求時期を明示する" },
    { title: "反証", focus: "未確認項目、対象外、期間限定条件、解約・移行条件を確認する" },
    { title: "選び方", focus: "安さだけでなく必須条件と乗り換え余地で絞る" },
  ];
}

export const serverArticleSlate: readonly ServerArticleSlateEntry[] = [
  ...serverArticleSeeds,
  ...additionalServerArticleSeeds.map((article) => ({
    ...article,
    sections: standardServerSections(article.readerQuestion),
  })),
].map((article) => ({
  ...article,
  queryMatch: "exact" as const,
  competitionStatus: "unobserved" as const,
  selectionBasis: "transaction_intent_specificity_proxy" as const,
  state: "candidate_only" as const,
  layoutOrder: serverLayoutOrder,
  reviewVoices: serverReviewVoices,
}));

export const serverBigWordHubs: readonly ServerBigWordHub[] = [
  "レンタルサーバー",
  "クラウドサーバー",
  "VPS サーバー",
  "WordPress サーバー",
  "レンタルサーバー 比較",
  "クラウドサーバー 比較",
  "VPS サーバー 比較",
  "WordPress サーバー 比較",
  "国内 サーバー 比較",
].map((sourceQuery) => ({ sourceQuery, state: "deferred_internal_link_hub" as const }));

/**
 * Launch-quarter drafting order. Transaction-intent pages are completed first,
 * while the first public review batch remains P01-P03.
 */
export const launchDraftPriority = [
  "P01",
  "P06",
  "P07",
  "P08",
  "P09",
  "P02",
  "P03",
  "P04",
  "P05",
  "P11",
  "P10",
  "P12",
] as const satisfies readonly PilotPage["id"][];

export function launchPriorityPages(): readonly PilotPage[] {
  const byId = new Map(pilotPages.map((page) => [page.id, page]));
  return launchDraftPriority.map((id) => {
    const page = byId.get(id);
    if (!page) throw new Error(`Unknown launch-priority article: ${id}`);
    return page;
  });
}

export function pilotPage(slug: string): PilotPage {
  const page = pilotPages.find((candidate) => candidate.slug === slug);
  if (!page) throw new Error(`Unknown editorial template slug: ${slug}`);
  return page;
}

export function pilotFieldScope(field: PilotNumericField): "vendor_plan" | "human_scenario" {
  return field.inputScope ?? "vendor_plan";
}
