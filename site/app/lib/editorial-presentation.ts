import type { EditorialContract } from "./editorial-input-contract";
import type { PilotPage } from "./pilot-pages";

type ImportedField = EditorialContract["numeric_fields"][number];

const vendorDisplayNames: Readonly<Record<string, string>> = {
  mangools: "Mangools",
  "se-ranking": "SE Ranking",
  semrush: "Semrush",
};

const planDisplayNames: Readonly<Record<string, string>> = {
  "mangools/basic": "Basic",
  "mangools/premium": "Premium",
  "mangools/agency": "Agency",
  "se-ranking/core": "Core",
  "semrush/seo": "SEO",
};

const pageConclusions: Readonly<Record<PilotPage["id"], string>> = {
  P01: "この金額を基準に、利用人数と利用量を変えた初年度費用を検討できます。",
  P02: "料金だけでなく利用上限もそろえて選ぶ必要があります。",
  P03: "確認できていない他社の年額を含めた価格順位はまだ確定できません。",
  P04: "最低利用人数と運用時間がそろうまで、小規模チームの総費用は確定できません。",
  P05: "管理・監査・導入支援の追加費用がそろうまで、組織利用の総費用は確定できません。",
  P06: "年払いと月払いは、同じ通貨・税条件で確認できた支払額だけを比べます。",
  P07: "上限超過時の扱いが確認できるまで、追加料金を0円とも有料とも決めません。",
  P08: "必要な追加機能の料金がそろうまで、実際の総費用は確定できません。",
  P09: "重複契約・作業・教育・支援の費用がそろうまで、移行初年度の総費用は確定できません。",
  P10: "表示通貨と税の扱いが確認できない金額は、円換算や総額計算から外します。",
  P11: "実際に削減できた時間が確認できるまで、導入効果を確定値として扱いません。",
  P12: "出典と確認期限を追えない数値は、比較や計算に使いません。",
};

export function vendorDisplayName(vendorId: string | null): string {
  if (!vendorId) return "SaaS";
  return vendorDisplayNames[vendorId] ?? vendorId;
}

export function planDisplayName(vendorId: string | null, planId: string | null): string {
  if (!planId) return "料金プラン";
  return planDisplayNames[`${vendorId}/${planId}`] ?? planId;
}

export function billingPeriodLabel(period: ImportedField["billing_period"]): string {
  switch (period) {
    case "annual": return "年次請求";
    case "monthly": return "月次請求";
    case "one_time": return "一回払い";
    case "per_usage": return "従量課金";
    case "not_applicable": return "課金なし";
    default: return "請求周期未確認";
  }
}

export function confirmedPriceFields(contract: EditorialContract | null): readonly ImportedField[] {
  if (!contract) return [];
  return contract.numeric_fields.filter((field) => (
    field.scope_kind === "vendor_plan"
    && field.value_kind === "price"
    && field.review_status === "approved"
    && field.value_status === "known"
    && field.currency_status === "known"
    && field.value !== null
    && field.currency !== null
    && field.vendor_id !== null
    && field.plan_id !== null
  ));
}

export function primaryConfirmedPrice(contract: EditorialContract | null): ImportedField | null {
  const fields = confirmedPriceFields(contract);
  return fields.find((field) => (
    field.billing_period === "annual"
    && field.observed_price_basis === "checkout_billed_total"
  )) ?? fields[0] ?? null;
}

function observedMonth(observedOn: string): string {
  const match = /^(\d{4})-(\d{2})-\d{2}$/.exec(observedOn);
  if (!match) return "確認月不明";
  return `${match[1]}年${Number(match[2])}月`;
}

function confirmedAmount(field: ImportedField): string {
  return `${field.currency} ${field.value}`;
}

export type EditorialPresentation = {
  title: string;
  description: string;
  lead: string;
  observedMonth: string | null;
  vendorName: string;
};

export function editorialPresentation(
  page: PilotPage,
  contract: EditorialContract | null,
): EditorialPresentation {
  const price = primaryConfirmedPrice(contract);
  const firstVendorId = contract?.numeric_fields.find((field) => field.vendor_id)?.vendor_id ?? null;
  const vendorName = vendorDisplayName(price?.vendor_id ?? firstVendorId);
  const conclusion = pageConclusions[page.id];

  if (!price) {
    const title = `${vendorName}料金: 確認済み実額なし・12か月TCOは確認中｜${page.title}`;
    return {
      title,
      description: `${page.question}について、確認できた値と未確認項目を分けて説明します。実額が確認できるまで総額は確定しません。`,
      lead: `確認済みの実額はまだなく、${conclusion}`,
      observedMonth: null,
      vendorName,
    };
  }

  const month = observedMonth(price.observed_on);
  const amount = confirmedAmount(price);
  const planName = planDisplayName(price.vendor_id, price.plan_id);
  return {
    title: `${vendorName}料金(${month}確認): ${amount}と12か月TCO｜${page.title}`,
    description: `${vendorName} ${planName}の${amount}を公式画面で確認。${page.question}を、出典・確認日・次回確認日付きで説明します。`,
    lead: `${vendorName} ${planName}の確認済み実額は${amount}（${billingPeriodLabel(price.billing_period)}）で、${conclusion}`,
    observedMonth: month,
    vendorName,
  };
}
