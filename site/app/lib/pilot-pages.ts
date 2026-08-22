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

/** Shared catalog for Human-confirmed servers observations and batch restore. */
export const serverObservationPage = {
  id: "P01",
  slug: "server-observation-candidate",
  title: "servers価格観測候補",
  intent: "price_check",
  pageType: "pricing",
  question: "初期費用・通常料金・更新料・特典を分けて記録できるか",
  readerOutcome: "確認済みfieldだけをservers計算機候補へ渡せる",
  numericFields: [
    { key: "pricing.initial_fee", label: "初期費用", valueKind: "price" },
    { key: "pricing.base_price", label: "基本料金", valueKind: "price" },
    { key: "pricing.renewal_fee", label: "更新時請求額", valueKind: "price" },
    { key: "servers.campaign_price", label: "キャンペーン価格", valueKind: "price" },
    { key: "servers.campaign_period_months", label: "キャンペーン適用月数", valueKind: "duration" },
    { key: "servers.domain_benefit_amount", label: "ドメイン特典の確認額", valueKind: "price" },
    { key: "servers.domain_benefit_period_months", label: "ドメイン特典の適用月数", valueKind: "duration" },
    { key: "servers.compute_hours", label: "計算資源の時間上限", valueKind: "usage" },
    { key: "servers.storage_gb", label: "ストレージ容量", valueKind: "quota" },
    { key: "servers.data_transfer_gb", label: "データ転送量", valueKind: "quota" },
    { key: "servers.backup_price", label: "バックアップ料金", valueKind: "price" },
  ],
} as const satisfies PilotPage;

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

type ServerObservationFieldKey = (typeof serverObservationPage.numericFields)[number]["key"];

export type ServerLaunchArticleBrief = {
  articleId: ServerArticleSlateEntry["id"];
  decisionRule: string;
  readerSections: ServerArticleSlateEntry["sections"];
  reusableObservationFields: readonly ServerObservationFieldKey[];
  additionalHumanChecks: readonly string[];
  approvalQuestion: string;
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

/** Eight server articles that take the site from 12 to the fixed 20-article line. */
export const serverLaunchPriorityIds = [
  "SVR05", // renewal / second-year charge
  "SVR04", // initial-fee-inclusive total
  "SVR06", // migration and overlap
  "SVR07", // corporate contract total
  "SVR02", // small-business minimum configuration
  "SVR03", // EC cost
  "SVR09", // corporate mail cost
  "SVR08", // EC recovery requirements
] as const satisfies readonly ServerArticleSlateEntry["id"][];

export type ServerInternalRevenueFunnel = {
  destination: "/servers/business-server-pricing";
  label: string;
  context: string;
};

export type ServerRevenueCell = {
  id: "cell-a-comparison" | "cell-b-single";
  version: "v2";
  ctaType: "affiliate_comparison" | "affiliate_single";
  state: "human_selected" | "hold_vendor_selection";
  primaryPartnerId: "a8net-xserver-business" | null;
  alternativePartnerId: "moshimo-conoha-wing" | null;
};

/**
 * Revenue-cell assignment is presentation metadata, not activation authority.
 * Runtime destination, article/channel GO, use-case fit, and current evidence
 * remain separate fail-closed gates in the edge worker and evidence matrix.
 */
const serverRevenueCells = {
  SVR01: {
    id: "cell-a-comparison",
    version: "v2",
    ctaType: "affiliate_comparison",
    state: "human_selected",
    primaryPartnerId: "a8net-xserver-business",
    alternativePartnerId: "moshimo-conoha-wing",
  },
  SVR04: {
    id: "cell-b-single",
    version: "v2",
    ctaType: "affiliate_single",
    state: "human_selected",
    primaryPartnerId: "a8net-xserver-business",
    alternativePartnerId: null,
  },
} as const satisfies Partial<Record<ServerArticleSlateEntry["id"], ServerRevenueCell>>;

export function serverRevenueCellFor(
  articleId: ServerArticleSlateEntry["id"],
): ServerRevenueCell | null {
  return serverRevenueCells[articleId as keyof typeof serverRevenueCells] ?? null;
}

const serverInternalRevenueFunnels = {
  SVR02: {
    destination: "/servers/business-server-pricing",
    label: "小規模サイト向けの12か月請求額を比較する",
    context: "最低条件を満たす候補について、確認済みの12か月請求額と未確認条件を同じ画面で確認できます。",
  },
  SVR03: {
    destination: "/servers/business-server-pricing",
    label: "EC用途の候補と12か月請求額を確認する",
    context: "EC適合を推測せず、用途条件が確認済みの候補と契約時請求額を分けて確認できます。",
  },
  SVR04: {
    destination: "/servers/business-server-pricing",
    label: "初期費用込みの12か月請求額を比較する",
    context: "月額表示ではなく、初期費用を含む確認済みの契約時請求額で候補を見比べます。",
  },
  SVR05: {
    destination: "/servers/business-server-pricing",
    label: "初年度の確認済み請求額を比較する",
    context: "更新額が未確認の候補は長期総額へ延長せず、まず確認済みの初年度負担だけを比較します。",
  },
  SVR06: {
    destination: "/servers/business-server-pricing",
    label: "移行先候補の12か月請求額を比較する",
    context: "移行費用とは別に、移行先で最初に必要となる確認済みの契約料金を比較します。",
  },
  SVR07: {
    destination: "/servers/business-server-pricing",
    label: "法人用途候補の12か月請求額を比較する",
    context: "法人向けという名称だけで推奨せず、確認済みの用途条件と初年度負担を分けて確認します。",
  },
  SVR08: {
    destination: "/servers/business-server-pricing",
    label: "EC運用候補の確認済み条件を比較する",
    context: "復旧条件が未確認の候補は推奨せず、比較できる料金と用途条件だけを確認します。",
  },
  SVR09: {
    destination: "/servers/business-server-pricing",
    label: "法人メール候補の初年度料金を比較する",
    context: "メール固有条件とサーバー料金を混同せず、確認済みの初年度負担を比較画面で確認します。",
  },
} as const satisfies Record<(typeof serverLaunchPriorityIds)[number], ServerInternalRevenueFunnel>;

export function serverInternalRevenueFunnelFor(
  articleId: ServerArticleSlateEntry["id"],
): ServerInternalRevenueFunnel | null {
  return serverInternalRevenueFunnels[articleId as keyof typeof serverInternalRevenueFunnels] ?? null;
}

/**
 * Article-specific evidence routing for the eight August launch drafts.
 * It reuses only exact fields from the common server observation and keeps
 * non-numeric or scenario-specific facts as explicit Human checks.
 */
export const serverLaunchArticleBriefs: readonly ServerLaunchArticleBrief[] = [
  {
    articleId: "SVR05",
    decisionRule: "初回の支払額と更新時の支払額を分け、同じ契約期間で2年目までの負担を判断する。",
    readerSections: [
      { title: "結論", focus: "更新時請求額を確認できたサービスだけで2年目の負担を示し、未確認のサービスには順位を付けません" },
      { title: "比較前提", focus: "初回価格、更新時請求額、契約期間、自動更新の時期を別々に確認します" },
      { title: "料金と上限", focus: "初期費用、初回12か月の請求総額、更新時請求額、ドメイン特典を分けて示します" },
      { title: "12か月TCO", focus: "初年度は確認済みの請求総額を使い、更新額が未確認なら2年目へ延長しません" },
      { title: "反証", focus: "初回限定の割引を更新時にも続くものとして扱わず、解約期限も未確認のまま明示します" },
      { title: "選び方", focus: "初年度の安さだけでなく、確認できた更新額と契約終了条件を見て判断します" },
    ],
    reusableObservationFields: [
      "pricing.base_price", "pricing.renewal_fee", "servers.campaign_price",
      "servers.campaign_period_months", "servers.domain_benefit_amount",
      "servers.domain_benefit_period_months",
    ],
    additionalHumanChecks: ["自動更新日と解約期限", "初回限定条件と更新後の適用条件"],
    approvalQuestion: "初回特典を更新時料金へ流用せず、2年目に実際に支払う範囲を説明できているか。",
  },
  {
    articleId: "SVR04",
    decisionRule: "初期費用と契約期間中の請求を重複させず、初年度の資金負担を判断する。",
    readerSections: [
      { title: "結論", focus: "初期費用と12か月の請求総額を同じ基準でそろえ、契約時に必要な金額を示します" },
      { title: "比較前提", focus: "12か月契約、円表示、税区分が確認できた行だけを同じ表で扱います" },
      { title: "料金と上限", focus: "初期費用、年次請求総額、容量、転送量、バックアップ料金を分けて確認します" },
      { title: "12か月TCO", focus: "年次請求総額に初期費用が含まれるかを確認し、同じ費用を二重に足しません" },
      { title: "反証", focus: "無料期間、返金条件、期間限定価格は通常の初年度総額へ推測で混ぜません" },
      { title: "選び方", focus: "最小の表示額ではなく、用途条件を満たしたうえで契約時の資金負担を比べます" },
    ],
    reusableObservationFields: [
      "pricing.initial_fee", "pricing.base_price", "pricing.renewal_fee",
      "servers.campaign_price", "servers.campaign_period_months",
    ],
    additionalHumanChecks: ["初回請求日と請求対象期間", "無料期間・返金条件・税込／税別表示"],
    approvalQuestion: "初回請求と継続請求を二重計上せず、契約時に必要な金額を説明できているか。",
  },
  {
    articleId: "SVR06",
    decisionRule: "新旧契約の重複期間、公式移行支援、Human作業を分離して乗り換え費用を判断する。",
    readerSections: [
      { title: "結論", focus: "新しい契約の料金と、旧契約の重複期間、移行支援、作業時間を別項目として示します" },
      { title: "比較前提", focus: "移行対象、停止できる時間、旧契約を残す月数を決めてから総額を計算します" },
      { title: "料金と上限", focus: "新サーバーの確認済み料金だけを先に示し、移行支援の対象外作業は別に残します" },
      { title: "12か月TCO", focus: "旧契約額や重複月数が未確認なら、その部分を0円にせず合計を停止します" },
      { title: "反証", focus: "WebサイトだけでなくDNS、メール、データベース、切り戻し作業が残る可能性を確認します" },
      { title: "選び方", focus: "料金差よりも停止リスクと移行範囲を優先し、必要な確認が少ない候補へ絞ります" },
    ],
    reusableObservationFields: ["pricing.base_price", "pricing.renewal_fee"],
    additionalHumanChecks: ["旧契約の月額と重複月数", "公式移行支援の料金・対象・対象外", "DNS・mail・databaseの作業時間"],
    approvalQuestion: "公式料金とHuman作業を混ぜず、二重支払いが発生する条件を説明できているか。",
  },
  {
    articleId: "SVR07",
    decisionRule: "法人契約に必要な条件を満たす候補だけで、契約時と更新時の負担を判断する。",
    readerSections: [
      { title: "結論", focus: "小規模サイトの条件に加え、複数人管理または運用代行を確認できた候補だけを法人向けとして扱います" },
      { title: "比較前提", focus: "容量、転送量、バックアップ、無料SSL、管理方法を同じ必要条件にそろえます" },
      { title: "料金と上限", focus: "確認済みの初年度料金と、未確認の更新額・請求方法を分けて示します" },
      { title: "12か月TCO", focus: "初年度の請求総額は比較し、更新額が未確認の候補は24か月以降へ延長しません" },
      { title: "反証", focus: "法人向けという名称だけで請求書払い、SLA、権限管理が使えるとは判断しません" },
      { title: "選び方", focus: "管理体制の必要条件を先に満たし、その後で初年度の資金負担を比べます" },
    ],
    reusableObservationFields: [
      "pricing.initial_fee", "pricing.base_price", "pricing.renewal_fee",
      "servers.domain_benefit_amount", "servers.domain_benefit_period_months",
    ],
    additionalHumanChecks: ["最低契約期間", "請求書払い・SLA・法人名義の対応", "解約期限と返金条件"],
    approvalQuestion: "価格だけで法人向けと断定せず、必要条件と未確認条件を分けているか。",
  },
  {
    articleId: "SVR02",
    decisionRule: "小規模運用の必要条件を満たす最小構成と、上位プランへ移る境界を判断する。",
    readerSections: [
      { title: "結論", focus: "100GB以上、転送量無制限、バックアップ利用可、無料SSLを確認できた候補だけを残します" },
      { title: "比較前提", focus: "小規模という言葉から利用量を推測せず、確認済みの4条件を最低ラインにします" },
      { title: "料金と上限", focus: "初年度料金、容量、転送量、バックアップ料金を同じ行で確認します" },
      { title: "12か月TCO", focus: "確認済みの年次請求総額だけを表示し、期間限定価格は通常価格の順位へ入れません" },
      { title: "反証", focus: "サイト数、管理者数、サポート範囲が未確認なら上位プランが不要とは断定しません" },
      { title: "選び方", focus: "最低条件を満たす候補から、将来必要になる管理機能を追加確認して選びます" },
    ],
    reusableObservationFields: [
      "pricing.initial_fee", "pricing.base_price", "pricing.renewal_fee",
      "servers.storage_gb", "servers.data_transfer_gb", "servers.backup_price",
    ],
    additionalHumanChecks: ["最低契約期間", "サイト数・管理者数・サポート範囲", "上位プランへの変更条件"],
    approvalQuestion: "小規模という語から必要量を推測せず、Human確認した用途条件だけで候補を絞っているか。",
  },
  {
    articleId: "SVR03",
    decisionRule: "EC用途の容量・転送・backup条件を満たす候補だけで、12か月の負担を判断する。",
    readerSections: [
      { title: "結論", focus: "小規模サイトの4条件に加えてEC用途またはECアプリ対応を確認できた候補だけを比較対象にします" },
      { title: "比較前提", focus: "共有サーバー、VPS、運用代行付きサービスを同じ性能として混ぜません" },
      { title: "料金と上限", focus: "初年度料金、容量、転送量、バックアップ料金とEC対応状況を分けて確認します" },
      { title: "12か月TCO", focus: "EC適合が未確認の行は、価格が確認済みでも順位と差額から除外します" },
      { title: "反証", focus: "復元料金、保存世代、復旧時間、SLAが未確認なら安全性を断定しません" },
      { title: "選び方", focus: "価格より先にEC対応と復旧条件を確認し、条件を満たす候補だけで総額を比べます" },
    ],
    reusableObservationFields: [
      "pricing.initial_fee", "pricing.base_price", "pricing.renewal_fee",
      "servers.storage_gb", "servers.data_transfer_gb", "servers.backup_price",
    ],
    additionalHumanChecks: ["復元料金・保存世代・復旧時間", "SLA・サポート時間・停止時の責任範囲", "EC機能の対応条件"],
    approvalQuestion: "共有・VPS・managedを混同せず、EC用途の必須条件を確認済み事実だけで示しているか。",
  },
  {
    articleId: "SVR09",
    decisionRule: "必要なmail account数、保存・backup・移行条件を分けて法人メールの負担を判断する。",
    readerSections: [
      { title: "結論", focus: "Web容量をメール容量へ読み替えず、アカウント数、保存容量、保全、移行条件を確認して判断します" },
      { title: "比較前提", focus: "必要なメールアカウント数と1アカウント当たり容量を決め、Web用途の条件と分離します" },
      { title: "料金と上限", focus: "サーバー料金は確認済み値を使い、メール固有の追加料金と上限は未確認のまま示します" },
      { title: "12か月TCO", focus: "メール固有の費用が未確認なら、サーバー料金だけを法人メールの総額とは呼びません" },
      { title: "反証", focus: "迷惑メール対策、アーカイブ、移行停止時間がプランに含まれるとは推測しません" },
      { title: "選び方", focus: "アカウント数と保全要件を満たした候補だけを残し、その後で初年度料金を比較します" },
    ],
    reusableObservationFields: ["pricing.initial_fee", "pricing.base_price", "pricing.renewal_fee", "servers.backup_price"],
    additionalHumanChecks: ["mail account数と1accountあたり容量", "迷惑mail・保全・archive条件", "mail移行の対象・費用・停止時間"],
    approvalQuestion: "web hostingの容量をmail容量へ流用せず、mail固有の上限と移行条件を確認しているか。",
  },
  {
    articleId: "SVR08",
    decisionRule: "ECサイトの継続運用に必要な性能・backup・復旧条件を満たす候補を判断する。",
    readerSections: [
      { title: "結論", focus: "EC対応とバックアップ利用可だけでなく、復元方法と障害時対応を確認できるまで推奨を確定しません" },
      { title: "比較前提", focus: "容量、転送量、無料SSL、バックアップ、EC対応を最低条件として確認します" },
      { title: "料金と上限", focus: "確認済みの初年度料金とバックアップ料金を示し、復元料金と復旧時間は別に扱います" },
      { title: "12か月TCO", focus: "価格が確認済みでもEC用途が未確認なら、計算結果から順位と差額を外します" },
      { title: "反証", focus: "高負荷対応、SLA、決済や個人情報への対応をプラン名から推測しません" },
      { title: "選び方", focus: "売上停止時の復旧条件を先に確認し、同じ条件を満たした候補だけで費用を比べます" },
    ],
    reusableObservationFields: [
      "pricing.base_price", "pricing.renewal_fee", "servers.compute_hours",
      "servers.storage_gb", "servers.data_transfer_gb", "servers.backup_price",
    ],
    additionalHumanChecks: ["backupの保存期間・復元料金・復旧時間", "障害時のSLAとサポート範囲", "決済・個人情報を扱う場合の公式対応条件"],
    approvalQuestion: "性能や安全性をプラン名から推測せず、未確認の復旧・運用条件を明示しているか。",
  },
];

export function serverLaunchBriefFor(
  articleId: ServerArticleSlateEntry["id"],
): ServerLaunchArticleBrief | null {
  return serverLaunchArticleBriefs.find((brief) => brief.articleId === articleId) ?? null;
}

export function serverLaunchPriorityArticles(): readonly ServerArticleSlateEntry[] {
  const byId = new Map(serverArticleSlate.map((article) => [article.id, article]));
  return serverLaunchPriorityIds.map((id) => {
    const article = byId.get(id);
    if (!article) throw new Error(`server launch priority article is missing: ${id}`);
    return article;
  });
}

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
