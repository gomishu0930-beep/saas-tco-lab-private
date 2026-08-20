"use client";

import { useMemo, useState } from "react";

import {
  assessServerPromotionCandidate,
  emptyEditorialField,
  emptyEditorialRow,
  extractPriceTextCandidates,
  prefillExtractedCandidate,
  serverCategoryRowsFromCandidate,
  isoDay,
  validateSourceUrl,
  validateEditorialInput,
  type EditorialBillingToggleState,
  type EditorialFieldFormValue,
  type EditorialRowFormValue,
  type EditorialSaleBannerState,
  type ExtractedPriceCandidate,
  type PriceTextExtraction,
  type ServerCandidateArtifact,
  type ServerConditionStatus,
  type ServerObservationConditionRecord,
} from "../lib/editorial-input-contract";
import { serverObservationPage } from "../lib/pilot-pages";

type ServerCategoryContract = {
  schema_version: "1.0";
  category_id: "servers";
  template_kind: "pricing_tco";
  state: "candidate_only";
  numeric_fields: NonNullable<ReturnType<typeof validateEditorialInput>["contract"]>["numeric_fields"];
  server_conditions: ServerObservationConditionRecord[];
};

type ServerConditionForm = {
  campaignEndsOnStatus: ServerConditionStatus | "";
  campaignEndsOn: string;
  campaignEndsOnUnknownReason: string;
  minimumCommitmentMonthsStatus: ServerConditionStatus | "";
  minimumCommitmentMonths: string;
  minimumCommitmentUnknownReason: string;
  domainBenefitTermsStatus: ServerConditionStatus | "";
  domainBenefitTerms: string;
  domainBenefitTermsUnknownReason: string;
  sourceUrl: string;
  observedOn: string;
  nextReviewOn: string;
  acquisitionMethod: "manual_public_page" | "manual_checkout_review";
};

type ServerConditionAssessment = {
  errors: string[];
  record: ServerObservationConditionRecord | null;
};

function emptyServerCondition(): ServerConditionForm {
  return {
    campaignEndsOnStatus: "",
    campaignEndsOn: "",
    campaignEndsOnUnknownReason: "",
    minimumCommitmentMonthsStatus: "",
    minimumCommitmentMonths: "",
    minimumCommitmentUnknownReason: "",
    domainBenefitTermsStatus: "",
    domainBenefitTerms: "",
    domainBenefitTermsUnknownReason: "",
    sourceUrl: "",
    observedOn: "",
    nextReviewOn: "",
    acquisitionMethod: "manual_public_page",
  };
}

function normalizedText(value: string) {
  return value.trim().replace(/\s+/g, " ");
}

function conditionFormFromRecord(record: ServerObservationConditionRecord): ServerConditionForm {
  return {
    campaignEndsOnStatus: record.campaign_ends_on_status,
    campaignEndsOn: record.campaign_ends_on ?? "",
    campaignEndsOnUnknownReason: record.campaign_ends_on_unknown_reason ?? "",
    minimumCommitmentMonthsStatus: record.minimum_commitment_months_status,
    minimumCommitmentMonths: record.minimum_commitment_months?.toString() ?? "",
    minimumCommitmentUnknownReason: record.minimum_commitment_unknown_reason ?? "",
    domainBenefitTermsStatus: record.domain_benefit_terms_status,
    domainBenefitTerms: record.domain_benefit_terms ?? "",
    domainBenefitTermsUnknownReason: record.domain_benefit_terms_unknown_reason ?? "",
    sourceUrl: record.source_url,
    observedOn: record.observed_on,
    nextReviewOn: record.next_review_on,
    acquisitionMethod: record.acquisition_method,
  };
}

function conditionFormsFromCandidate(
  rows: readonly EditorialRowFormValue[],
  input: unknown,
): Record<string, ServerConditionForm> {
  const candidate = input as Partial<ServerCandidateArtifact> | null;
  const records = Array.isArray(candidate?.server_conditions) ? candidate.server_conditions : [];
  const byIdentity = new Map(records.map((record) => [
    `${record.vendor_id}\u0000${record.plan_id}`,
    record,
  ]));
  return Object.fromEntries(rows.map((row) => {
    const record = byIdentity.get(`${row.vendorId}\u0000${row.planId}`);
    return [row.rowId, record ? conditionFormFromRecord(record) : emptyServerCondition()];
  }));
}

function validateServerCondition(
  row: EditorialRowFormValue,
  form: ServerConditionForm,
): ServerConditionAssessment {
  const errors: string[] = [];
  const statuses = new Set<ServerConditionStatus>(["known", "unknown", "not_applicable"]);
  const campaignReason = normalizedText(form.campaignEndsOnUnknownReason);
  const minimumReason = normalizedText(form.minimumCommitmentUnknownReason);
  const domainTerms = normalizedText(form.domainBenefitTerms);
  const domainReason = normalizedText(form.domainBenefitTermsUnknownReason);

  function validateStatus(
    label: string,
    status: ServerConditionStatus | "",
    value: string,
    reason: string,
  ) {
    if (!statuses.has(status as ServerConditionStatus)) {
      errors.push(`${label}の確認状態を選択してください。`);
    } else if (status === "known") {
      if (!value) errors.push(`${label}の確認値を入力してください。`);
      if (reason) errors.push(`${label}が確認済みなら未確認理由を空にしてください。`);
    } else {
      if (value) errors.push(`${label}が未確認・該当なしなら確認値を空にしてください。`);
      if (!reason) errors.push(`${label}が未確認・該当なしの理由を入力してください。`);
    }
  }

  validateStatus("キャンペーン終了日", form.campaignEndsOnStatus, form.campaignEndsOn, campaignReason);
  validateStatus("最低契約期間", form.minimumCommitmentMonthsStatus, form.minimumCommitmentMonths, minimumReason);
  validateStatus("ドメイン特典条件", form.domainBenefitTermsStatus, domainTerms, domainReason);

  const campaignDay = form.campaignEndsOn ? isoDay(form.campaignEndsOn) : null;
  if (form.campaignEndsOnStatus === "known" && campaignDay === null) {
    errors.push("キャンペーン終了日をYYYY-MM-DD形式で入力してください。");
  }
  const minimumMonths = /^\d+$/.test(form.minimumCommitmentMonths)
    ? Number(form.minimumCommitmentMonths)
    : null;
  if (
    form.minimumCommitmentMonthsStatus === "known"
    && (minimumMonths === null || minimumMonths < 1 || minimumMonths > 120)
  ) errors.push("最低契約期間は1〜120の整数（月）で入力してください。");
  if (domainTerms.length > 500) errors.push("ドメイン特典条件は500文字以内にしてください。");
  if ([campaignReason, minimumReason, domainReason].some((value) => value.length > 300)) {
    errors.push("未確認・該当なしの理由は300文字以内にしてください。");
  }

  const sourceUrl = form.sourceUrl.trim();
  const sourceError = validateSourceUrl(sourceUrl);
  if (sourceError) errors.push(`条件出典: ${sourceError}`);
  const observedDay = isoDay(form.observedOn);
  const nextReviewDay = isoDay(form.nextReviewOn);
  if (observedDay === null) errors.push("条件の観測日をYYYY-MM-DD形式で入力してください。");
  if (nextReviewDay === null) errors.push("条件の次回確認日をYYYY-MM-DD形式で入力してください。");
  if (observedDay !== null && nextReviewDay !== null) {
    if (nextReviewDay <= observedDay) errors.push("条件の次回確認日は観測日より後にしてください。");
    if (nextReviewDay - observedDay > 180) errors.push("条件の次回確認日は観測日から180日以内にしてください。");
    if (campaignDay !== null && campaignDay < observedDay) errors.push("キャンペーン終了日は観測日以降にしてください。");
    if (campaignDay !== null && nextReviewDay > campaignDay) errors.push("次回確認日はキャンペーン終了日以前にしてください。");
  }
  if (errors.length) return { errors, record: null };

  return {
    errors: [],
    record: {
      schema_version: "1.0",
      vendor_id: row.vendorId.trim(),
      plan_id: row.planId.trim(),
      campaign_ends_on_status: form.campaignEndsOnStatus as ServerConditionStatus,
      campaign_ends_on: form.campaignEndsOnStatus === "known" ? form.campaignEndsOn : null,
      campaign_ends_on_unknown_reason: form.campaignEndsOnStatus === "known" ? null : campaignReason,
      minimum_commitment_months_status: form.minimumCommitmentMonthsStatus as ServerConditionStatus,
      minimum_commitment_months: form.minimumCommitmentMonthsStatus === "known" ? minimumMonths : null,
      minimum_commitment_unknown_reason: form.minimumCommitmentMonthsStatus === "known" ? null : minimumReason,
      domain_benefit_terms_status: form.domainBenefitTermsStatus as ServerConditionStatus,
      domain_benefit_terms: form.domainBenefitTermsStatus === "known" ? domainTerms : null,
      domain_benefit_terms_unknown_reason: form.domainBenefitTermsStatus === "known" ? null : domainReason,
      source_url: sourceUrl,
      observed_on: form.observedOn,
      next_review_on: form.nextReviewOn,
      entered_by: "human",
      acquisition_method: form.acquisitionMethod,
      rights_path: "human_editorial",
      review_status: "unreviewed",
    },
  };
}

const emptyExtraction: PriceTextExtraction = { error: null, candidates: [] };

type ServerCommonMetadata = {
  sourceUrl: string;
  observedOn: string;
  nextReviewOn: string;
  billingToggleState: EditorialBillingToggleState | "";
  saleBannerState: EditorialSaleBannerState | "";
};

function ServerCommonMetadataForm({ onApply }: { onApply: (metadata: ServerCommonMetadata) => void }) {
  return (
    <form className="operator-common-metadata" aria-label="全field共通の観測情報" onSubmit={(event) => {
      event.preventDefault();
      const data = new FormData(event.currentTarget);
      onApply({
        sourceUrl: String(data.get("sourceUrl") ?? ""),
        observedOn: String(data.get("observedOn") ?? ""),
        nextReviewOn: String(data.get("nextReviewOn") ?? ""),
        billingToggleState: String(data.get("billingToggleState") ?? "") as ServerCommonMetadata["billingToggleState"],
        saleBannerState: String(data.get("saleBannerState") ?? "") as ServerCommonMetadata["saleBannerState"],
      });
    }}>
      <p className="eyebrow">COMMON OBSERVATION</p>
      <h4>共通の画面情報を11 fieldと条件記録へ一括適用</h4>
      <p>公式URL・日付はfieldと条件記録へ、画面状態は11 fieldへ複製します。値、通貨、税、請求周期、確認状態は変更しません。</p>
      <div className="operator-identity-grid">
        <label className="operator-wide-field">共通の公式出典URL<input name="sourceUrl" type="url" autoCapitalize="none" spellCheck={false} placeholder="公式料金ページのURL" required /></label>
        <label>共通の観測日<input name="observedOn" type="date" required /></label>
        <label>共通の次回確認日<input name="nextReviewOn" type="date" required /></label>
        <label>共通の支払周期表示<select name="billingToggleState" defaultValue="not_present" required>
          <option value="">選択</option><option value="annual_selected">年払い選択</option><option value="monthly_selected">月払い選択</option><option value="not_present">切替なし</option><option value="unknown">不明</option>
        </select></label>
        <label>共通の価格表示分類<select name="saleBannerState" defaultValue="time_limited_promo" required>
          <option value="">選択</option><option value="none">割引表示なし</option><option value="annual_discount_permanent">恒常年払い差</option><option value="time_limited_promo">期間限定</option><option value="unknown">不明</option>
        </select></label>
      </div>
      <button type="submit">共通情報をfield・条件へ適用</button>
    </form>
  );
}

function freshRow(index: number): EditorialRowFormValue {
  return emptyEditorialRow(serverObservationPage, "vendor_plan", `server-vendor-${index}`);
}

function nextRowNumber(rows: readonly EditorialRowFormValue[]) {
  return Math.max(0, ...rows.map((row) => Number(row.rowId.match(/(\d+)$/)?.[1] ?? 0))) + 1;
}

function candidateTarget(rowId: string, fieldKey: string) {
  return `${rowId}|${fieldKey}`;
}

function splitCandidateTarget(value: string) {
  const separator = value.indexOf("|");
  return separator === -1 ? ["", ""] : [value.slice(0, separator), value.slice(separator + 1)];
}

function setField(
  rows: EditorialRowFormValue[],
  rowId: string,
  fieldKey: string,
  key: keyof EditorialFieldFormValue,
  value: string,
) {
  return rows.map((row) => {
    if (row.rowId !== rowId) return row;
    const next = { ...row.values[fieldKey], [key]: value } as EditorialFieldFormValue;
    if (key === "valueStatus" && value === "unknown") {
      next.value = "";
      next.observedPriceBasis = next.currencyStatus === "not_applicable" ? "" : "unknown";
      next.monthlyReferenceValue = "";
    }
    if (key === "valueStatus" && value === "not_applicable") {
      next.value = "";
      next.currencyStatus = "not_applicable";
      next.currency = "";
      next.currencyDisplay = "";
      next.currencyUnknownReason = "";
      next.billingPeriod = next.observedPriceBasis ? "not_applicable" : "";
      next.taxTreatment = next.observedPriceBasis ? "not_applicable" : "";
      next.observedPriceBasis = next.observedPriceBasis ? "not_applicable" : "";
      next.monthlyReferenceValue = "";
    }
    if (key === "currencyStatus" && value === "known") {
      next.currencyDisplay = "";
      next.currencyUnknownReason = "";
    }
    if (key === "currencyStatus" && value === "unknown") next.currency = "";
    return { ...row, values: { ...row.values, [fieldKey]: next } };
  });
}

function FieldInput({
  row,
  field,
  update,
}: {
  row: EditorialRowFormValue;
  field: (typeof serverObservationPage.numericFields)[number];
  update: (key: keyof EditorialFieldFormValue, value: string) => void;
}) {
  const value = row.values[field.key];
  const isPrice = field.valueKind === "price";
  return (
    <fieldset className="operator-field-card">
      <legend>{field.label} <small><code>{field.key}</code></small></legend>
      <div className="operator-field-grid">
        <label>確認状態<select value={value.valueStatus} onChange={(event) => update("valueStatus", event.target.value)}>
          <option value="known">確認済み</option><option value="unknown">未確認</option><option value="not_applicable">該当なし</option>
        </select></label>
        <label>値<input inputMode="decimal" value={value.value} disabled={value.valueStatus !== "known"} onChange={(event) => update("value", event.target.value)} /></label>
        <label>単位<input value={value.unit} placeholder={isPrice ? "/ mo または / yr" : "GB、か月など"} onChange={(event) => update("unit", event.target.value)} /></label>
        <label className="operator-wide-field">未確認・該当なしの理由<input value={value.unknownReason} disabled={value.valueStatus === "known"} onChange={(event) => update("unknownReason", event.target.value)} /></label>
        {isPrice ? <>
          <label>通貨状態<select value={value.currencyStatus} onChange={(event) => update("currencyStatus", event.target.value)}>
            <option value="">選択</option><option value="known">ISO通貨確認済み</option><option value="unknown">記号のみ・不明</option><option value="not_applicable">該当なし</option>
          </select></label>
          <label>ISO通貨<input value={value.currency} placeholder="JPY" disabled={value.currencyStatus !== "known"} onChange={(event) => update("currency", event.target.value.toUpperCase())} /></label>
          <label>画面の通貨表記<input value={value.currencyDisplay} placeholder="¥ / $" disabled={value.currencyStatus !== "unknown"} onChange={(event) => update("currencyDisplay", event.target.value)} /></label>
          <label>通貨不明の理由<input value={value.currencyUnknownReason} disabled={value.currencyStatus !== "unknown"} onChange={(event) => update("currencyUnknownReason", event.target.value)} /></label>
          <label>請求周期<select value={value.billingPeriod} onChange={(event) => update("billingPeriod", event.target.value)}>
            <option value="">選択</option><option value="monthly">月次</option><option value="annual">年次</option><option value="one_time">一回</option><option value="per_usage">従量</option><option value="not_applicable">該当なし</option><option value="unknown">不明</option>
          </select></label>
          <label>税区分<select value={value.taxTreatment} onChange={(event) => update("taxTreatment", event.target.value)}>
            <option value="">選択</option><option value="included">税込</option><option value="excluded">税別</option><option value="not_applicable">該当なし</option><option value="unknown">不明</option>
          </select></label>
          <label>一次観測<select value={value.observedPriceBasis} onChange={(event) => update("observedPriceBasis", event.target.value)}>
            <option value="">選択</option><option value="displayed_price">料金ページ表示</option><option value="checkout_billed_total">checkout請求総額</option><option value="not_applicable">該当なし</option><option value="unknown">不明</option>
          </select></label>
          <label>月払い比較値<input inputMode="decimal" value={value.monthlyReferenceValue} onChange={(event) => update("monthlyReferenceValue", event.target.value)} /></label>
        </> : null}
        <label>画面の支払周期<select value={value.billingToggleState} onChange={(event) => update("billingToggleState", event.target.value)}>
          <option value="">選択</option><option value="annual_selected">年払い選択</option><option value="monthly_selected">月払い選択</option><option value="not_present">切替なし</option><option value="unknown">不明</option>
        </select></label>
        <label>価格表示分類<select value={value.saleBannerState} onChange={(event) => update("saleBannerState", event.target.value)}>
          <option value="">選択</option><option value="none">割引表示なし</option><option value="annual_discount_permanent">恒常年払い差</option><option value="time_limited_promo">期間限定</option><option value="unknown">不明</option>
        </select></label>
        <label className="operator-wide-field">公式出典URL<input inputMode="url" autoCapitalize="none" spellCheck={false} value={value.sourceUrl} placeholder="公式HTTPS URL（tracking parameterなし）" onInput={(event) => update("sourceUrl", event.currentTarget.value)} /></label>
        <label>観測日<input type="date" value={value.observedOn} onInput={(event) => update("observedOn", event.currentTarget.value)} /></label>
        <label>次回確認日<input type="date" value={value.nextReviewOn} onInput={(event) => update("nextReviewOn", event.currentTarget.value)} /></label>
      </div>
    </fieldset>
  );
}

function ServerConditionInput({
  value,
  update,
}: {
  value: ServerConditionForm;
  update: (key: keyof ServerConditionForm, next: string) => void;
}) {
  return (
    <fieldset className="operator-field-card operator-server-conditions">
      <legend>契約・キャンペーン・ドメイン特典条件 <small><code>server_conditions</code></small></legend>
      <p>価格とは別に公式画面で確認します。不明は推測せず「未確認」と理由を残してください。</p>
      <div className="operator-field-grid">
        <label>キャンペーン期限の状態<select value={value.campaignEndsOnStatus} onChange={(event) => update("campaignEndsOnStatus", event.target.value)}>
          <option value="">選択</option><option value="known">確認済み</option><option value="unknown">未確認</option><option value="not_applicable">期間限定施策なし</option>
        </select></label>
        <label>キャンペーン終了日<input type="date" value={value.campaignEndsOn} disabled={value.campaignEndsOnStatus !== "known"} onChange={(event) => update("campaignEndsOn", event.target.value)} /></label>
        <label className="operator-wide-field">期限の未確認・該当なし理由<input value={value.campaignEndsOnUnknownReason} disabled={value.campaignEndsOnStatus === "known"} onChange={(event) => update("campaignEndsOnUnknownReason", event.target.value)} /></label>

        <label>最低契約期間の状態<select value={value.minimumCommitmentMonthsStatus} onChange={(event) => update("minimumCommitmentMonthsStatus", event.target.value)}>
          <option value="">選択</option><option value="known">確認済み</option><option value="unknown">未確認</option><option value="not_applicable">最低期間なし</option>
        </select></label>
        <label>最低契約期間（月）<input inputMode="numeric" value={value.minimumCommitmentMonths} disabled={value.minimumCommitmentMonthsStatus !== "known"} onChange={(event) => update("minimumCommitmentMonths", event.target.value)} /></label>
        <label className="operator-wide-field">期間の未確認・該当なし理由<input value={value.minimumCommitmentUnknownReason} disabled={value.minimumCommitmentMonthsStatus === "known"} onChange={(event) => update("minimumCommitmentUnknownReason", event.target.value)} /></label>

        <label>ドメイン特典条件の状態<select value={value.domainBenefitTermsStatus} onChange={(event) => update("domainBenefitTermsStatus", event.target.value)}>
          <option value="">選択</option><option value="known">確認済み</option><option value="unknown">未確認</option><option value="not_applicable">特典なし</option>
        </select></label>
        <label className="operator-wide-field">ドメイン特典の適用条件<input value={value.domainBenefitTerms} disabled={value.domainBenefitTermsStatus !== "known"} placeholder="更新・対象TLD・契約継続など、公式表示の必要最小限" onChange={(event) => update("domainBenefitTerms", event.target.value)} /></label>
        <label className="operator-wide-field">特典の未確認・該当なし理由<input value={value.domainBenefitTermsUnknownReason} disabled={value.domainBenefitTermsStatus === "known"} onChange={(event) => update("domainBenefitTermsUnknownReason", event.target.value)} /></label>

        <label className="operator-wide-field">条件の公式出典URL<input type="url" autoCapitalize="none" spellCheck={false} value={value.sourceUrl} onChange={(event) => update("sourceUrl", event.target.value)} /></label>
        <label>条件の観測日<input type="date" value={value.observedOn} onChange={(event) => update("observedOn", event.target.value)} /></label>
        <label>条件の次回確認日<input type="date" value={value.nextReviewOn} onChange={(event) => update("nextReviewOn", event.target.value)} /></label>
        <label>確認経路<select value={value.acquisitionMethod} onChange={(event) => update("acquisitionMethod", event.target.value)}>
          <option value="manual_public_page">公開公式ページ</option><option value="manual_checkout_review">checkout直前画面</option>
        </select></label>
      </div>
    </fieldset>
  );
}

export function ServerObservationForm({ savedCandidate }: { savedCandidate?: unknown }) {
  const [rows, setRows] = useState<EditorialRowFormValue[]>([freshRow(1)]);
  const [conditions, setConditions] = useState<Record<string, ServerConditionForm>>({
    "server-vendor-1": emptyServerCondition(),
  });
  const [confirmed, setConfirmed] = useState<ServerCategoryContract | null>(null);
  const [candidateImportState, setCandidateImportState] = useState("未読込");
  const [pastedText, setPastedText] = useState("");
  const [extraction, setExtraction] = useState<PriceTextExtraction>(emptyExtraction);
  const [candidateTargets, setCandidateTargets] = useState<Record<string, string>>({});
  const validation = useMemo(() => validateEditorialInput(serverObservationPage, rows), [rows]);
  const promotionAssessment = useMemo(
    () => validation.contract ? assessServerPromotionCandidate(validation.contract.numeric_fields) : null,
    [validation.contract],
  );
  const conditionAssessments = useMemo(() => rows.map((row) => (
    validateServerCondition(row, conditions[row.rowId] ?? emptyServerCondition())
  )), [conditions, rows]);
  const conditionErrors = conditionAssessments.flatMap((item) => item.errors);
  const conditionRecords = conditionAssessments
    .map((item) => item.record)
    .filter((item): item is ServerObservationConditionRecord => item !== null);
  const conditionsReady = conditionErrors.length === 0 && conditionRecords.length === rows.length;
  const errors = [...Object.values(validation.errors).flat(), ...conditionErrors];
  const priceTargets = useMemo(() => rows.flatMap((row) => serverObservationPage.numericFields
    .filter((field) => field.valueKind === "price")
    .map((field) => ({ row, field }))), [rows]);

  function updateRow(rowId: string, key: "vendorId" | "planId", value: string) {
    setRows((current) => current.map((row) => row.rowId === rowId ? { ...row, [key]: value } : row));
    setConfirmed(null);
  }

  function updateField(rowId: string, fieldKey: string, key: keyof EditorialFieldFormValue, value: string) {
    setRows((current) => setField(current, rowId, fieldKey, key, value));
    setConfirmed(null);
  }

  function updateCondition(rowId: string, key: keyof ServerConditionForm, value: string) {
    setConditions((current) => {
      const next = { ...(current[rowId] ?? emptyServerCondition()), [key]: value } as ServerConditionForm;
      if (key.endsWith("Status")) {
        const status = value as ServerConditionStatus;
        if (key === "campaignEndsOnStatus") {
          if (status === "known") next.campaignEndsOnUnknownReason = "";
          else next.campaignEndsOn = "";
        } else if (key === "minimumCommitmentMonthsStatus") {
          if (status === "known") next.minimumCommitmentUnknownReason = "";
          else next.minimumCommitmentMonths = "";
        } else if (key === "domainBenefitTermsStatus") {
          if (status === "known") next.domainBenefitTermsUnknownReason = "";
          else next.domainBenefitTerms = "";
        }
      }
      return { ...current, [rowId]: next };
    });
    setConfirmed(null);
  }

  function addRow() {
    const next = freshRow(nextRowNumber(rows));
    setRows((current) => [...current, next]);
    setConditions((current) => ({ ...current, [next.rowId]: emptyServerCondition() }));
    setConfirmed(null);
  }

  function applyCommonMetadata(rowId: string, metadata: ServerCommonMetadata) {
    setRows((current) => current.map((row) => {
      if (row.rowId !== rowId) return row;
      return {
        ...row,
        billingToggleState: metadata.billingToggleState,
        saleBannerState: metadata.saleBannerState,
        values: Object.fromEntries(Object.entries(row.values).map(([fieldKey, value]) => [fieldKey, {
          ...value,
          sourceUrl: metadata.sourceUrl,
          observedOn: metadata.observedOn,
          nextReviewOn: metadata.nextReviewOn,
          billingToggleState: metadata.billingToggleState,
          saleBannerState: metadata.saleBannerState,
        }])),
      };
    }));
    setConditions((current) => ({
      ...current,
      [rowId]: {
        ...(current[rowId] ?? emptyServerCondition()),
        sourceUrl: metadata.sourceUrl,
        observedOn: metadata.observedOn,
        nextReviewOn: metadata.nextReviewOn,
      },
    }));
    setConfirmed(null);
  }

  function confirm() {
    if (!validation.contract || !conditionsReady) return;
    setConfirmed({
      schema_version: "1.0",
      category_id: "servers",
      template_kind: "pricing_tco",
      state: "candidate_only",
      numeric_fields: validation.contract.numeric_fields,
      server_conditions: conditionRecords,
    });
  }

  async function restoreSavedCandidate(file: File | undefined) {
    if (!file) return;
    if (file.size > 1_000_000) {
      setCandidateImportState("読込失敗: JSONは1MB以内にしてください");
      return;
    }
    try {
      const parsed = JSON.parse(await file.text()) as ServerCategoryContract;
      const restored = serverCategoryRowsFromCandidate(serverObservationPage, parsed);
      if (!restored) throw new Error("invalid candidate");
      setRows(restored);
      setConditions(conditionFormsFromCandidate(restored, parsed));
      setConfirmed(null);
      const conditionCount = Array.isArray(parsed.server_conditions) ? parsed.server_conditions.length : 0;
      setCandidateImportState(`読込済み: ${restored.length} vendor・${restored.length * serverObservationPage.numericFields.length} field・条件記録${conditionCount}件を現在欄へ復元`);
    } catch {
      setCandidateImportState("読込失敗: servers candidate-only JSONを選んでください");
    }
  }

  function restoreBundledCandidate() {
    const restored = serverCategoryRowsFromCandidate(serverObservationPage, savedCandidate);
    if (!restored) {
      setCandidateImportState("読込失敗: repositoryのSVR01候補を再生成してください");
      return;
    }
    setRows(restored);
    setConditions(conditionFormsFromCandidate(restored, savedCandidate));
    setConfirmed(null);
    const candidate = savedCandidate as Partial<ServerCandidateArtifact> | undefined;
    const conditionCount = Array.isArray(candidate?.server_conditions) ? candidate.server_conditions.length : 0;
    setCandidateImportState(`読込済み: repositoryのSVR01候補${restored.length * serverObservationPage.numericFields.length} field・条件記録${conditionCount}件を現在欄へ復元`);
  }

  function analyzePaste() {
    const result = extractPriceTextCandidates(pastedText);
    setExtraction(result);
    const firstTarget = priceTargets[0]
      ? candidateTarget(priceTargets[0].row.rowId, priceTargets[0].field.key)
      : "";
    setCandidateTargets(Object.fromEntries(result.candidates.map((candidate) => [candidate.id, firstTarget])));
  }

  function applyCandidate(candidate: ExtractedPriceCandidate) {
    const firstTarget = priceTargets[0]
      ? candidateTarget(priceTargets[0].row.rowId, priceTargets[0].field.key)
      : "";
    const [rowId, fieldKey] = splitCandidateTarget(candidateTargets[candidate.id] ?? firstTarget);
    const field = serverObservationPage.numericFields.find((item) => item.key === fieldKey);
    if (!rowId || !field || field.valueKind !== "price") return;
    setRows((current) => current.map((row) => row.rowId === rowId ? {
      ...row,
      values: {
        ...row.values,
        [field.key]: prefillExtractedCandidate(
          field,
          row.values[field.key] ?? emptyEditorialField(),
          candidate,
        ),
      },
    } : row));
    setConfirmed(null);
  }

  function download() {
    if (!confirmed) return;
    const url = URL.createObjectURL(new Blob([`${JSON.stringify(confirmed, null, 2)}\n`], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "servers-category-expansion-input.json";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="operator-input-card" aria-labelledby="server-observation-title">
      <div className="operator-section-heading">
        <div><p className="eyebrow">SERVERS / CANDIDATE ONLY</p><h2 id="server-observation-title">サーバー価格をfield単位で確認</h2></div>
        <p>最初はXServerビジネスの共有サーバー1プランだけを入力します。公開、提携申請、index、CTAはこの画面から実行されません。</p>
      </div>
      <p className="operator-extraction-error">年払いはcheckout請求総額だけを一次値にし、キャンペーン期限・更新額・ドメイン特典を通常料金へ混ぜないでください。</p>
      <section className="operator-previous" aria-labelledby="server-previous-title">
        <div className="operator-previous-heading">
          <div><p className="eyebrow">RECONFIRMATION</p><h3 id="server-previous-title">保存済みSVR01候補から再開</h3></div>
          <div className="operator-paste-actions">
            <button type="button" onClick={restoreBundledCandidate} disabled={!savedCandidate}>repositoryのSVR01候補を読込</button>
            <label>別の候補JSONをローカル読込<input type="file" accept="application/json,.json" onChange={(event) => { void restoreSavedCandidate(event.target.files?.[0]); event.currentTarget.value = ""; }} /></label>
          </div>
        </div>
        <p>保存済みcandidate-only JSONはHuman選択後だけブラウザメモリへ読みます。repository候補もHumanがボタンを押した後だけブラウザメモリへ読み、外部送信・端末保存を行いません。追加観測は該当fieldだけ更新し、再度Human確認するまでcontractへ確定しません。</p>
        <p aria-live="polite">{candidateImportState}</p>
      </section>
      <section className="operator-paste-parser" aria-labelledby="server-paste-title">
        <div className="operator-paste-heading">
          <div><p className="eyebrow">LOCAL PASTE ANALYSIS</p><h3 id="server-paste-title">公式価格ページの必要行だけを解析</h3></div>
          <p>公開ページの必要範囲だけを貼り付けます。account画面、氏名、メール、credential、tracking URLは貼り付けないでください。</p>
        </div>
        <label htmlFor="server-price-paste">コピーテキスト</label>
        <textarea id="server-price-paste" value={pastedText} onChange={(event) => setPastedText(event.target.value)} maxLength={100_000} rows={6} autoComplete="off" placeholder="料金と税・請求周期が同じ行で分かる必要範囲だけを貼り付け" />
        <div className="operator-paste-actions">
          <button type="button" onClick={analyzePaste}>ローカルで候補を抽出</button>
          <button type="button" onClick={() => { setPastedText(""); setExtraction(emptyExtraction); setCandidateTargets({}); }}>貼り付け原文を消去</button>
          <span>抽出値は事前入力だけです。原文はcontract・端末保存・外部通信へ含めません。</span>
        </div>
        {extraction.error ? <p className="operator-extraction-error" role="status">{extraction.error}</p> : null}
        {extraction.candidates.length ? <div className="operator-candidate-list" aria-label="serversの抽出候補">
          {extraction.candidates.map((candidate) => <article key={candidate.id} className="operator-candidate">
            <div><strong>{candidate.value}</strong><small>行 {candidate.lineNumber}</small></div>
            <blockquote>{candidate.sourceLine}</blockquote>
            {candidate.warnings.length ? <ul>{candidate.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : null}
            <label>反映先<select value={candidateTargets[candidate.id] ?? ""} onChange={(event) => setCandidateTargets((current) => ({ ...current, [candidate.id]: event.target.value }))}>
              {priceTargets.map(({ row, field }) => <option key={candidateTarget(row.rowId, field.key)} value={candidateTarget(row.rowId, field.key)}>{row.vendorId || "vendor未入力"} / {row.planId || "plan未入力"} — {field.label}</option>)}
            </select></label>
            <button type="button" onClick={() => applyCandidate(candidate)}>この候補を事前入力</button>
          </article>)}
        </div> : null}
      </section>
      <div className="operator-row-stack">
        {rows.map((row, rowIndex) => <section className="operator-entry-row" key={row.rowId}>
          <header className="operator-row-header"><div><p className="eyebrow">VENDOR / PLAN {rowIndex + 1}</p><h3>{row.vendorId || "vendor未入力"} / {row.planId || "plan未入力"}</h3></div></header>
          <div className="operator-identity-grid">
            <label>vendor識別子<input value={row.vendorId} placeholder="xserver-business" onChange={(event) => updateRow(row.rowId, "vendorId", event.target.value)} /></label>
            <label>plan識別子<input value={row.planId} placeholder="shared-standard" onChange={(event) => updateRow(row.rowId, "planId", event.target.value)} /></label>
          </div>
          <ServerCommonMetadataForm onApply={(metadata) => applyCommonMetadata(row.rowId, metadata)} />
          <div className="operator-field-stack">
            {serverObservationPage.numericFields.map((field) => <FieldInput key={field.key} row={row} field={field} update={(key, value) => updateField(row.rowId, field.key, key, value)} />)}
            <ServerConditionInput value={conditions[row.rowId] ?? emptyServerCondition()} update={(key, value) => updateCondition(row.rowId, key, value)} />
          </div>
          {rows.length > 1 ? <button type="button" onClick={() => {
            setRows((current) => current.filter((item) => item.rowId !== row.rowId));
            setConditions((current) => Object.fromEntries(Object.entries(current).filter(([key]) => key !== row.rowId)));
            setConfirmed(null);
          }}>この行を削除</button> : null}
        </section>)}
      </div>
      <button className="operator-add-row" type="button" onClick={addRow}>vendor・plan行を追加</button>
      <div className={`operator-validation-summary ${confirmed ? "is-valid" : "is-waiting"}`} aria-live="polite">
        <strong>{confirmed ? "候補contract確定" : validation.contract && conditionsReady ? "構造は合格・Human確認待ち" : `修正が必要です（${errors.length}件）`}</strong>
        <p>{validation.calculationBlockers.length ? `未確認fieldを${validation.calculationBlockers.length}件保持します。該当計算と順位はHOLDです。` : "入力はcandidate_onlyです。記事承認と計算機採用は別に行います。"}</p>
        <p><strong>契約・特典条件: {conditionsReady ? "READY" : "HOLD"}</strong>{conditionsReady ? ` — ${conditionRecords.length} vendor・plan分を構造化済み` : ` — 修正待ち${conditionErrors.length}件`}</p>
        {promotionAssessment ? <div aria-label="servers候補の昇格準備判定">
          <p><strong>TCO: {promotionAssessment.tcoReady ? "READY" : "HOLD"}</strong>{promotionAssessment.tcoBlockers.length ? ` — ${promotionAssessment.tcoBlockers.slice(0, 3).join(" / ")}${promotionAssessment.tcoBlockers.length > 3 ? ` / ほか${promotionAssessment.tcoBlockers.length - 3}件` : ""}` : " — TCO fieldは明示済み"}</p>
          <p><strong>用途判定: {promotionAssessment.suitabilityReady ? "READY" : "HOLD"}</strong>{promotionAssessment.suitabilityBlockers.length ? ` — ${promotionAssessment.suitabilityBlockers.slice(0, 3).join(" / ")}${promotionAssessment.suitabilityBlockers.length > 3 ? ` / ほか${promotionAssessment.suitabilityBlockers.length - 3}件` : ""}` : " — 用途fieldは明示済み"}</p>
          <p><strong>contract昇格: {promotionAssessment.contractPromotionReady ? "READY" : "HOLD"}</strong>{promotionAssessment.reviewBlockers.length ? ` — Human field確認待ち ${promotionAssessment.reviewBlockers.length}件` : " — field確認済み"}</p>
          <p>READYでも記事承認・index・CTAは別のHuman gateです。HOLDのfieldは公式画面で確認し、該当しない場合は理由付き「該当なし」にしてください。</p>
        </div> : <div aria-label="servers候補の昇格準備判定">
          <p><strong>TCO: HOLD</strong> — 入力構造の修正待ち</p>
          <p><strong>用途判定: HOLD</strong> — 入力構造の修正待ち</p>
          <p><strong>contract昇格: HOLD</strong> — validation合格とHuman field確認待ち</p>
          <p>READYでも記事承認・index・CTAは別のHuman gateです。HOLDのfieldは公式画面で確認し、該当しない場合は理由付き「該当なし」にしてください。</p>
        </div>}
        {errors.length && rows.some((row) => row.vendorId || row.planId) ? <ul className="operator-field-errors">{[...new Set(errors)].slice(0, 12).map((error) => <li key={error}>{error}</li>)}</ul> : null}
        <button type="button" disabled={!validation.contract || !conditionsReady || Boolean(confirmed)} onClick={confirm}>Human確認してservers候補contractを確定</button>
      </div>
      {confirmed ? <div className="operator-json-output"><button type="button" onClick={download}>候補JSONを保存</button><pre>{`${JSON.stringify(confirmed, null, 2)}\n`}</pre></div> : null}
    </section>
  );
}
