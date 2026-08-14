"use client";

import { useEffect, useMemo, useState } from "react";

import {
  annualDiscountPercent,
  annualMonthlyEquivalent,
  buildP09OwnedDataPrefill,
  buildP11OwnedDataPrefill,
  confirmOwnedObservation,
  emptyEditorialField,
  emptyEditorialRow,
  extractPriceTextCandidates,
  observationMonthTotals,
  parseConfirmedOwnedObservations,
  prefillExtractedCandidate,
  secondsToDecimalHours,
  summedObservationHours,
  validateEditorialInput,
  valuesFromContract,
  reusableEditorialEvidence,
  type EditorialContract,
  type EditorialFieldFormValue,
  type EditorialRowFormValue,
  type ExtractedPriceCandidate,
  type ConfirmedOwnedObservation,
  type OwnedDataPrefill,
  type OwnedObservationArticleId,
  type OwnedObservationKind,
  type P09OwnedDataInput,
  type P11OwnedDataInput,
  type PriceTextExtraction,
} from "../lib/editorial-input-contract";
import { editorialContract } from "../lib/editorial-contracts";
import { pilotFieldScope, pilotPages, type PilotNumericField, type PilotPage } from "../lib/pilot-pages";

function initialRows(page: PilotPage): EditorialRowFormValue[] {
  const scopes = new Set(page.numericFields.map(pilotFieldScope));
  return [
    ...(scopes.has("vendor_plan") ? [emptyEditorialRow(page, "vendor_plan", "vendor-1")] : []),
    ...(scopes.has("human_scenario") ? [emptyEditorialRow(page, "human_scenario", "scenario-1")] : []),
  ];
}

function errorMessages(
  errors: Readonly<Record<string, readonly string[]>>,
  key: string,
  show: boolean,
) {
  const messages = errors[key];
  if (!show || !messages?.length) return null;
  return <ul className="operator-field-errors">{messages.map((message) => <li key={message}>{message}</li>)}</ul>;
}

function parseStoredContract(page: PilotPage, raw: string | null): EditorialContract | null {
  if (!raw) return null;
  try {
    const candidate = JSON.parse(raw) as EditorialContract;
    const rows = valuesFromContract(page, candidate);
    if (!rows) return null;
    return validateEditorialInput(page, rows).contract;
  } catch {
    return null;
  }
}

function storageKey(articleId: string) {
  return `saas-tco-lab:confirmed-editorial-v2-2:${articleId}`;
}

function rowIdentity(row: EditorialRowFormValue) {
  return row.scopeKind === "vendor_plan"
    ? `${row.vendorId || "vendor未入力"} / ${row.planId || "plan未入力"}`
    : "Human scenario";
}

function fieldSummary(value: EditorialFieldFormValue | undefined, row?: EditorialRowFormValue) {
  if (!value) return "未入力";
  const parts = [
    `状態 ${value.valueStatus}`,
    value.value && `${value.value} ${value.unit}`.trim(),
    value.unknownReason,
    value.currencyStatus !== "not_applicable" && `通貨 ${value.currencyStatus}`,
    value.currency,
    value.currencyDisplay,
    value.billingPeriod,
    value.taxTreatment,
    value.observedPriceBasis,
    value.monthlyReferenceValue && `月払い比較 ${value.monthlyReferenceValue} / mo`,
    row?.scopeKind === "vendor_plan" && `toggle ${value.billingToggleState || row.billingToggleState}`,
    row?.scopeKind === "vendor_plan" && `sale ${value.saleBannerState || row.saleBannerState}`,
    value.billingPeriod === "annual" && value.value && (
      annualMonthlyEquivalent(value.value, value.currencyStatus === "known" ? value.currency : "") === null
        ? "月額派生 最小通貨単位で割り切れないため非表示"
        : `月額派生 ${annualMonthlyEquivalent(value.value, value.currency)} / mo`
    ),
    value.sourceUrl,
    value.observedOn && `観測 ${value.observedOn}`,
    value.nextReviewOn && `次回 ${value.nextReviewOn}`,
  ].filter(Boolean);
  return parts.length ? parts.join(" / ") : "未入力";
}

function candidateMetadata(candidate: ExtractedPriceCandidate) {
  const parts = [candidate.currency ?? candidate.currencyDisplay, candidate.billingPeriod, candidate.taxTreatment].filter(Boolean);
  return parts.length ? parts.join(" / ") : "補助項目なし";
}

function rowFields(page: PilotPage, row: EditorialRowFormValue) {
  return page.numericFields.filter((field) => pilotFieldScope(field) === row.scopeKind);
}

function targetValue(rowId: string, fieldKey: string) {
  return `${rowId}::${fieldKey}`;
}

function splitTarget(value: string) {
  const separator = value.indexOf("::");
  return separator < 0 ? ["", ""] as const : [value.slice(0, separator), value.slice(separator + 2)] as const;
}

function contractRowsByIdentity(page: PilotPage, contract: EditorialContract | null) {
  if (!contract) return new Map<string, EditorialRowFormValue>();
  const rows = valuesFromContract(page, contract) ?? [];
  return new Map(rows.map((row) => [rowIdentity(row), row]));
}

function rowsHaveInput(rows: readonly EditorialRowFormValue[]) {
  return rows.some((row) => row.vendorId || row.planId || row.billingToggleState || row.saleBannerState || Object.values(row.values).some((field) => (
    field.billingToggleState || field.saleBannerState || field.value || field.unit || field.unknownReason || field.monthlyReferenceValue || field.sourceUrl || field.observedOn || field.nextReviewOn
  )));
}

const emptyP09OwnedData: P09OwnedDataInput = {
  overlapMonths: "",
  workHours: "",
  hourlyCost: "",
  trainingHours: "",
  currency: "JPY",
  observedOn: "",
  nextReviewOn: "",
};

const emptyP11OwnedData: P11OwnedDataInput = {
  baselineMonth: "",
  comparisonMonth: "",
  baselineHours: "",
  comparisonHours: "",
  hourlyCost: "",
  implementationCost: "",
  monthlyTco: "",
  currency: "JPY",
  observedOn: "",
  nextReviewOn: "",
};

const emptyOwnedDataResult: OwnedDataPrefill = {
  errors: {},
  warnings: [],
  scenarioBasis: "",
  values: {},
};

const emptyExtraction: PriceTextExtraction = { error: null, candidates: [] };

export function OperatorInputForm() {
  const [articleId, setArticleId] = useState(pilotPages[0].id);
  const [rowsByArticle, setRowsByArticle] = useState<Record<string, EditorialRowFormValue[]>>(() => ({
    [pilotPages[0].id]: initialRows(pilotPages[0]),
  }));
  const [copyState, setCopyState] = useState("未コピー");
  const [confirmedContract, setConfirmedContract] = useState<EditorialContract | null>(null);
  const [previousContract, setPreviousContract] = useState<EditorialContract | null>(null);
  const [previousLookupState, setPreviousLookupState] = useState("未確認");
  const [confirmationState, setConfirmationState] = useState("Human確認前");
  const [pastedText, setPastedText] = useState("");
  const [extraction, setExtraction] = useState<PriceTextExtraction>(emptyExtraction);
  const [candidateTargets, setCandidateTargets] = useState<Record<string, string>>({});
  const [p09OwnedData, setP09OwnedData] = useState<P09OwnedDataInput>(emptyP09OwnedData);
  const [p11OwnedData, setP11OwnedData] = useState<P11OwnedDataInput>(emptyP11OwnedData);
  const [ownedDataResult, setOwnedDataResult] = useState<OwnedDataPrefill>(emptyOwnedDataResult);
  const [ownedDataState, setOwnedDataState] = useState("未反映");
  const [sessionStartedAt, setSessionStartedAt] = useState<number | null>(null);
  const [clockNow, setClockNow] = useState<number | null>(null);
  const page = pilotPages.find((candidate) => candidate.id === articleId) ?? pilotPages[0];
  const rows = rowsByArticle[page.id] ?? initialRows(page);
  const validation = useMemo(() => validateEditorialInput(page, rows), [page, rows]);
  const sourceContracts = useMemo(() => pilotPages
    .map((candidate) => editorialContract(candidate))
    .filter((candidate): candidate is EditorialContract => candidate !== null), []);
  const reusableEvidence = useMemo(
    () => reusableEditorialEvidence(page, sourceContracts),
    [page, sourceContracts],
  );
  const json = confirmedContract ? `${JSON.stringify(confirmedContract, null, 2)}\n` : "";
  const hasStarted = rowsHaveInput(rows);
  const errorCount = Object.values(validation.errors).reduce((total, messages) => total + messages.length, 0);
  const previousRows = contractRowsByIdentity(page, previousContract);
  const candidateOptions = rows.flatMap((row) => rowFields(page, row).map((field) => ({ row, field })));
  const elapsedMinutes = sessionStartedAt === null || clockNow === null
    ? 0
    : Math.max(0, Math.floor((clockNow - sessionStartedAt) / 60_000));
  const workflowPhase = sessionStartedAt === null
    ? "未開始"
    : elapsedMinutes < 20
      ? "価格確認"
      : elapsedMinutes < 40
        ? "Operator入力"
        : elapsedMinutes < 60
          ? "表示・根拠確認"
          : "60分到達・公開/HOLD判断";

  useEffect(() => {
    if (sessionStartedAt === null) return undefined;
    const timer = window.setInterval(() => setClockNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, [sessionStartedAt]);

  function resetConfirmation() {
    setConfirmedContract(null);
    setConfirmationState("Human確認前");
    setCopyState("未コピー");
  }

  function setCurrentRows(update: (current: EditorialRowFormValue[]) => EditorialRowFormValue[]) {
    setRowsByArticle((current) => ({
      ...current,
      [page.id]: update(current[page.id] ?? initialRows(page)),
    }));
    resetConfirmation();
  }

  function selectArticle(nextArticleId: string) {
    const nextPage = pilotPages.find((candidate) => candidate.id === nextArticleId) ?? pilotPages[0];
    const stored = parseStoredContract(nextPage, window.localStorage.getItem(storageKey(nextPage.id)))
      ?? editorialContract(nextPage);
    setRowsByArticle((current) => current[nextPage.id] ? current : { ...current, [nextPage.id]: initialRows(nextPage) });
    setArticleId(nextPage.id);
    setPreviousContract(stored);
    setPreviousLookupState(stored ? "読込済み" : "前回値なし");
    setPastedText("");
    setExtraction(emptyExtraction);
    setCandidateTargets({});
    setOwnedDataResult(emptyOwnedDataResult);
    setOwnedDataState("未反映");
    resetConfirmation();
  }

  function updateRow(rowId: string, key: "vendorId" | "planId" | "scenarioBasis" | "billingToggleState" | "saleBannerState", value: string) {
    setCurrentRows((current) => current.map((row) => row.rowId === rowId ? { ...row, [key]: value } : row));
  }

  function updateField(rowId: string, fieldKey: string, key: keyof EditorialFieldFormValue, value: string) {
    setCurrentRows((current) => current.map((row) => {
      if (row.rowId !== rowId) return row;
      const next = { ...(row.values[fieldKey] ?? emptyEditorialField()), [key]: value } as EditorialFieldFormValue;
      if (key === "valueStatus" && value === "not_applicable") {
        next.value = "";
        next.currencyStatus = "not_applicable";
        next.currency = "";
        next.currencyDisplay = "";
        next.currencyUnknownReason = "";
        next.billingPeriod = "not_applicable";
        next.taxTreatment = "not_applicable";
        next.observedPriceBasis = "not_applicable";
        next.monthlyReferenceValue = "";
      }
      if (key === "valueStatus" && value === "unknown") {
        next.value = "";
        next.observedPriceBasis = "unknown";
        next.monthlyReferenceValue = "";
      }
      if (key === "currencyStatus" && value === "known") {
        next.currencyDisplay = "";
        next.currencyUnknownReason = "";
      }
      if (key === "currencyStatus" && value === "unknown") next.currency = "";
      return { ...row, values: { ...row.values, [fieldKey]: next } };
    }));
  }

  function addVendorRow() {
    const existing = rows.filter((row) => row.scopeKind === "vendor_plan").length;
    setCurrentRows((current) => [...current, emptyEditorialRow(page, "vendor_plan", `vendor-${Date.now()}-${existing + 1}`)]);
  }

  function removeVendorRow(rowId: string) {
    setCurrentRows((current) => current.filter((row) => row.rowId !== rowId));
  }

  function copyFirstEvidenceAcrossRow(rowId: string) {
    setCurrentRows((current) => current.map((row) => {
      if (row.rowId !== rowId) return row;
      const fields = rowFields(page, row);
      const first = row.values[fields[0]?.key];
      if (!first) return row;
      return {
        ...row,
        values: Object.fromEntries(fields.map((field) => [field.key, {
          ...(row.values[field.key] ?? emptyEditorialField()),
          sourceUrl: first.sourceUrl,
          observedOn: first.observedOn,
          nextReviewOn: first.nextReviewOn,
        }])),
      };
    }));
  }

  function analyzePaste() {
    const result = extractPriceTextCandidates(pastedText);
    setExtraction(result);
    const defaultTarget = candidateOptions[0] ? targetValue(candidateOptions[0].row.rowId, candidateOptions[0].field.key) : "";
    setCandidateTargets(Object.fromEntries(result.candidates.map((candidate) => [candidate.id, defaultTarget])));
  }

  function clearPaste() {
    setPastedText("");
    setExtraction(emptyExtraction);
    setCandidateTargets({});
  }

  function applyCandidate(candidate: ExtractedPriceCandidate) {
    const fallback = candidateOptions[0] ? targetValue(candidateOptions[0].row.rowId, candidateOptions[0].field.key) : "";
    const [rowId, fieldKey] = splitTarget(candidateTargets[candidate.id] ?? fallback);
    const field = page.numericFields.find((item) => item.key === fieldKey);
    if (!rowId || !field) return;
    setCurrentRows((current) => current.map((row) => row.rowId === rowId ? {
      ...row,
      values: {
        ...row.values,
        [field.key]: prefillExtractedCandidate(field, row.values[field.key] ?? emptyEditorialField(), candidate),
      },
    } : row));
  }

  function restorePrevious() {
    if (!previousContract) return;
    const restored = valuesFromContract(page, previousContract);
    if (!restored) return;
    setRowsByArticle((current) => ({ ...current, [page.id]: restored }));
    resetConfirmation();
  }

  function applyReusableEvidence() {
    if (!reusableEvidence || hasStarted) return;
    setRowsByArticle((current) => ({ ...current, [page.id]: [...reusableEvidence.rows] }));
    resetConfirmation();
  }

  function applyOwnedDataCandidate() {
    const result = page.id === "P09"
      ? buildP09OwnedDataPrefill(p09OwnedData)
      : page.id === "P11"
        ? buildP11OwnedDataPrefill(p11OwnedData)
        : emptyOwnedDataResult;
    setOwnedDataResult(result);
    if (Object.keys(result.errors).length) {
      setOwnedDataState("修正が必要です");
      return;
    }
    setCurrentRows((current) => {
      const seed = reusableEvidence && !rowsHaveInput(current)
        ? reusableEvidence.rows.map((row) => ({ ...row, values: { ...row.values } }))
        : current;
      let scenarioFound = false;
      const merged = seed.map((row) => {
        if (row.scopeKind !== "human_scenario") return row;
        scenarioFound = true;
        return {
          ...row,
          scenarioBasis: result.scenarioBasis,
          values: { ...row.values, ...result.values },
        };
      });
      if (!scenarioFound) {
        const scenario = emptyEditorialRow(page, "human_scenario", "scenario-1");
        merged.push({ ...scenario, scenarioBasis: result.scenarioBasis, values: { ...scenario.values, ...result.values } });
      }
      return merged;
    });
    setOwnedDataState("候補を一般入力欄へ反映済み・Human確認前");
  }

  function loadPrevious() {
    const stored = parseStoredContract(page, window.localStorage.getItem(storageKey(page.id)))
      ?? editorialContract(page);
    setPreviousContract(stored);
    setPreviousLookupState(stored ? "読込済み" : "前回値なし");
  }

  function confirmContract() {
    if (!validation.contract) return;
    const contract = validation.contract;
    setConfirmedContract(contract);
    setPreviousContract(contract);
    setPreviousLookupState("読込済み");
    try {
      window.localStorage.setItem(storageKey(page.id), JSON.stringify(contract));
      setConfirmationState("Human確認済み・前回値を端末内へ保存");
    } catch {
      setConfirmationState("Human確認済み・前回値の端末保存は利用不可");
    }
  }

  async function copyJson() {
    if (!json) return;
    try {
      await navigator.clipboard.writeText(json);
      setCopyState("コピー済み");
    } catch {
      setCopyState("コピーできませんでした。下のJSONを選択してください");
    }
  }

  function downloadJson() {
    if (!json) return;
    const blob = new Blob([json], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${page.id}-editorial-input.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="operator-input-card" aria-labelledby="operator-input-title">
      <div className="operator-section-heading">
        <div><p className="eyebrow">EDITORIAL INPUT 2.3</p><h2 id="operator-input-title">記事の実値を入力</h2></div>
        <p>vendor・planごとに行を分け、Humanシナリオも別管理します。年払いはcheckout請求総額を一次観測値とし、月額換算は12で最小通貨単位まで完全に割り切れる場合だけ派生表示します。価格表示は4区分で記録し、期間限定promoと不明だけを計算HOLDにします。Human確認前の候補を保存・送信しません。</p>
      </div>

      <section className="operator-timebox" aria-labelledby="operator-timebox-title">
        <div>
          <p className="eyebrow">60 MINUTE TIMEBOX</p>
          <h3 id="operator-timebox-title">価格確認20分 → 入力20分 → 確認20分</h3>
          <p>80点で公開候補へ進め、改善は後日に回します。ただし、推測・開示・出典・承認・index/CTA gateは省略しません。</p>
        </div>
        <dl aria-live="polite">
          <div><dt>経過時間</dt><dd>{sessionStartedAt === null ? "未開始" : `${elapsedMinutes}分`}</dd></div>
          <div><dt>現在の工程</dt><dd>{workflowPhase}</dd></div>
        </dl>
        <div className="operator-timebox-actions">
          <button type="button" onClick={() => {
            const now = Date.now();
            setSessionStartedAt(now);
            setClockNow(now);
          }}>60分セッション開始</button>
          <button type="button" onClick={() => {
            setSessionStartedAt(null);
            setClockNow(null);
          }}>タイマーをリセット</button>
        </div>
      </section>

      <div className="operator-article-picker">
        <label htmlFor="operator-article">記事を選ぶ</label>
        <select id="operator-article" value={articleId} onChange={(event) => selectArticle(event.target.value)}>
          {pilotPages.map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.id} — {candidate.title}{Number(candidate.id.slice(1)) <= 3 ? "（第1弾）" : ""}</option>)}
        </select>
        <p>{page.question}</p>
      </div>

      {reusableEvidence ? <section className="operator-reuse" aria-labelledby="operator-reuse-title">
        <div>
          <p className="eyebrow">APPROVED EVIDENCE REUSE</p>
          <h3 id="operator-reuse-title">承認済み証拠を再入力せず候補化</h3>
          <p>{reusableEvidence.appliedFields.length} fieldを同じvendor・planの承認済み観測から再利用し、{reusableEvidence.explicitUnknownFields.length} fieldを数値なしのunknown候補として事前入力できます。unknown候補はHuman確認前に確定せず、対象記事は必ずunreviewedへ戻ります。</p>
        </div>
        <button type="button" onClick={applyReusableEvidence} disabled={hasStarted}>
          {hasStarted ? "入力開始後は再利用できません" : "承認済み証拠を候補へ反映"}
        </button>
      </section> : null}

      <form onSubmit={(event) => event.preventDefault()} noValidate>
        {page.id === "P09" || page.id === "P11" ? <section className="operator-owned-data" aria-labelledby="operator-owned-data-title">
          <div className="operator-paste-heading">
            <div><p className="eyebrow">OWNED DATA / LOCAL ONLY</p><h3 id="operator-owned-data-title">{page.id}の自データを実測値から候補化</h3></div>
            <p>一般相場やvendor資料から補完せず、SaaS TCO Lab自身の記録だけを入力します。候補はこの画面のmemory内だけで処理し、下のHuman確定操作まではcontract・端末・外部へ保存しません。</p>
          </div>

          {page.id === "P09" ? <>
            <p className="operator-owned-data-note">実際に完了した移行1回について、重複契約・作業・教育を直接記録します。時間単価はHumanの評価条件であり、公式料金と混ぜません。</p>
            <OwnedObservationRecorder
              key="P09-owned-recorder"
              articleId="P09"
              applyP09Totals={(workHours, trainingHours) => {
                setP09OwnedData((current) => ({ ...current, workHours, trainingHours }));
                setOwnedDataState("Human確認済み台帳の時間合計を自データ欄へ反映済み・contract未反映");
              }}
            />
            <div className="operator-owned-data-grid">
              <label>重複契約月数<input type="number" min="0" step="0.01" value={p09OwnedData.overlapMonths} onChange={(event) => setP09OwnedData((current) => ({ ...current, overlapMonths: event.target.value }))} placeholder="例: 1" /></label>
              <label>移行作業時間<input type="number" min="0" step="0.01" value={p09OwnedData.workHours} onChange={(event) => setP09OwnedData((current) => ({ ...current, workHours: event.target.value }))} placeholder="hours" /></label>
              <label>教育時間<input type="number" min="0" step="0.01" value={p09OwnedData.trainingHours} onChange={(event) => setP09OwnedData((current) => ({ ...current, trainingHours: event.target.value }))} placeholder="hours" /></label>
              <label>時間単価<input type="number" min="0" step="0.01" value={p09OwnedData.hourlyCost} onChange={(event) => setP09OwnedData((current) => ({ ...current, hourlyCost: event.target.value }))} placeholder="数値のみ" /></label>
              <label>ISO通貨<input value={p09OwnedData.currency} onChange={(event) => setP09OwnedData((current) => ({ ...current, currency: event.target.value.toUpperCase() }))} maxLength={3} autoComplete="off" /></label>
              <label>観測日<input type="date" value={p09OwnedData.observedOn} onChange={(event) => setP09OwnedData((current) => ({ ...current, observedOn: event.target.value }))} /></label>
              <label>次回確認日<input type="date" value={p09OwnedData.nextReviewOn} onChange={(event) => setP09OwnedData((current) => ({ ...current, nextReviewOn: event.target.value }))} /></label>
            </div>
          </> : <>
            <p className="operator-owned-data-note">導入前後の完全な暦月を1か月ずつ比較します。月途中の値を30日換算せず、削減時間は「基準月 − 比較月」で決定論的に計算します。</p>
            <OwnedObservationRecorder
              key="P11-owned-recorder"
              articleId="P11"
              baselineMonth={p11OwnedData.baselineMonth}
              comparisonMonth={p11OwnedData.comparisonMonth}
              applyP11Totals={(baselineMonth, comparisonMonth, baselineHours, comparisonHours) => {
                setP11OwnedData((current) => ({
                  ...current,
                  baselineMonth,
                  comparisonMonth,
                  baselineHours,
                  comparisonHours,
                }));
                setOwnedDataState("Human確認済み台帳の完全暦月合計を自データ欄へ反映済み・contract未反映");
              }}
            />
            <div className="operator-owned-data-grid">
              <label>導入前の基準月<input type="month" value={p11OwnedData.baselineMonth} onChange={(event) => setP11OwnedData((current) => ({ ...current, baselineMonth: event.target.value }))} /></label>
              <label>導入後の比較月<input type="month" value={p11OwnedData.comparisonMonth} onChange={(event) => setP11OwnedData((current) => ({ ...current, comparisonMonth: event.target.value }))} /></label>
              <label>基準月の作業時間<input type="number" min="0" step="0.01" value={p11OwnedData.baselineHours} onChange={(event) => setP11OwnedData((current) => ({ ...current, baselineHours: event.target.value }))} placeholder="hours" /></label>
              <label>比較月の作業時間<input type="number" min="0" step="0.01" value={p11OwnedData.comparisonHours} onChange={(event) => setP11OwnedData((current) => ({ ...current, comparisonHours: event.target.value }))} placeholder="hours" /></label>
              <label>時間単価<input type="number" min="0" step="0.01" value={p11OwnedData.hourlyCost} onChange={(event) => setP11OwnedData((current) => ({ ...current, hourlyCost: event.target.value }))} placeholder="数値のみ" /></label>
              <label>導入費<input type="number" min="0" step="0.01" value={p11OwnedData.implementationCost} onChange={(event) => setP11OwnedData((current) => ({ ...current, implementationCost: event.target.value }))} placeholder="数値のみ" /></label>
              <label>月額TCO<input type="number" min="0" step="0.01" value={p11OwnedData.monthlyTco} onChange={(event) => setP11OwnedData((current) => ({ ...current, monthlyTco: event.target.value }))} placeholder="数値のみ" /></label>
              <label>ISO通貨<input value={p11OwnedData.currency} onChange={(event) => setP11OwnedData((current) => ({ ...current, currency: event.target.value.toUpperCase() }))} maxLength={3} autoComplete="off" /></label>
              <label>観測日<input type="date" value={p11OwnedData.observedOn} onChange={(event) => setP11OwnedData((current) => ({ ...current, observedOn: event.target.value }))} /></label>
              <label>次回確認日<input type="date" value={p11OwnedData.nextReviewOn} onChange={(event) => setP11OwnedData((current) => ({ ...current, nextReviewOn: event.target.value }))} /></label>
            </div>
          </>}

          {Object.keys(ownedDataResult.errors).length ? <ul className="operator-field-errors" role="alert">
            {Object.entries(ownedDataResult.errors).flatMap(([key, messages]) => messages.map((message) => <li key={`${key}-${message}`}>{message}</li>))}
          </ul> : null}
          {ownedDataResult.warnings.length ? <ul className="operator-owned-data-warnings">
            {ownedDataResult.warnings.map((warning) => <li key={warning}>{warning}</li>)}
          </ul> : null}
          <div className="operator-paste-actions">
            <button type="button" onClick={applyOwnedDataCandidate}>実測値を未承認候補へ反映</button>
            <span aria-live="polite">{ownedDataState}</span>
          </div>
        </section> : null}

        <section className="operator-paste-parser" aria-labelledby="operator-paste-title">
          <div className="operator-paste-heading">
            <div><p className="eyebrow">LOCAL PASTE ANALYSIS</p><h3 id="operator-paste-title">価格ページのコピーテキストを解析</h3></div>
            <p>公開価格ページの必要範囲だけを貼り付けます。account画面、氏名、メール、credential、tracking URLは貼り付けないでください。</p>
          </div>
          <label htmlFor="operator-price-paste">コピーテキスト</label>
          <textarea id="operator-price-paste" value={pastedText} onChange={(event) => setPastedText(event.target.value)} maxLength={100_000} rows={7} autoComplete="off" placeholder="料金表の必要な行だけを貼り付け" />
          <div className="operator-paste-actions">
            <button type="button" onClick={analyzePaste}>ローカルで候補を抽出</button>
            <button type="button" onClick={clearPaste}>貼り付け原文を消去</button>
            <span>原文はcontract・端末保存・外部通信へ含めません。</span>
          </div>
          {extraction.error ? <p className="operator-extraction-error" role="status">{extraction.error}</p> : null}
          {extraction.candidates.length ? <div className="operator-candidate-list" aria-label="抽出した数値候補">
            {extraction.candidates.map((candidate) => <article key={candidate.id} className="operator-candidate">
              <div><strong>{candidate.value}</strong><small>行 {candidate.lineNumber} / {candidateMetadata(candidate)}</small></div>
              <blockquote>{candidate.sourceLine}</blockquote>
              {candidate.warnings.length ? <ul>{candidate.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : null}
              <label>反映先<select value={candidateTargets[candidate.id] ?? ""} onChange={(event) => setCandidateTargets((current) => ({ ...current, [candidate.id]: event.target.value }))}>
                {candidateOptions.map(({ row, field }) => <option key={targetValue(row.rowId, field.key)} value={targetValue(row.rowId, field.key)}>{rowIdentity(row)} — {field.label}</option>)}
              </select></label>
              <button type="button" onClick={() => applyCandidate(candidate)}>この候補を事前入力</button>
            </article>)}
          </div> : null}
        </section>

        <section className="operator-previous" aria-labelledby="operator-previous-title">
          <div className="operator-previous-heading">
            <div><p className="eyebrow">RECONFIRMATION</p><h3 id="operator-previous-title">前回確定値とのside-by-side差分</h3></div>
            {previousContract ? <button type="button" onClick={restorePrevious}>前回値を現在欄へ戻す</button> : <button type="button" onClick={loadPrevious}>端末内の前回値を読み込む</button>}
          </div>
          {previousContract && hasStarted ? <div className="table-scroll" tabIndex={0} aria-label="前回値と現在値の差分を横スクロール">
            <table className="operator-diff-table"><thead><tr><th>行 / field</th><th>前回確定値</th><th>現在値</th><th>差分</th></tr></thead><tbody>
              {rows.flatMap((row) => rowFields(page, row).map((field) => {
                const previousRow = previousRows.get(rowIdentity(row));
                const before = fieldSummary(previousRow?.values[field.key], previousRow);
                const current = fieldSummary(row.values[field.key], row);
                return <tr key={`${row.rowId}-${field.key}`}><th>{rowIdentity(row)} / {field.label}</th><td>{before}</td><td>{current}</td><td><span className={before === current ? "diff-same" : "diff-changed"}>{before === current ? "同じ" : "変更あり"}</span></td></tr>;
              }))}
            </tbody></table>
          </div> : <p>{previousLookupState === "前回値なし" ? "この記事の前回確定値はありません。" : "前回確定値がある場合は端末内から読み込み、vendor・plan行単位で比較できます。"}</p>}
        </section>

        {errorMessages(validation.errors, "_rows", hasStarted)}
        <div className="operator-row-stack">
          {rows.map((row, rowIndex) => <section key={row.rowId} className={`operator-entry-row ${row.scopeKind === "human_scenario" ? "is-scenario" : ""}`}>
            <header className="operator-row-header">
              <div><p className="eyebrow">{row.scopeKind === "vendor_plan" ? `VENDOR / PLAN ${rows.slice(0, rowIndex + 1).filter((candidate) => candidate.scopeKind === "vendor_plan").length}` : "HUMAN SCENARIO"}</p><h3>{rowIdentity(row)}</h3></div>
              <div className="operator-row-actions">
                <button type="button" onClick={() => copyFirstEvidenceAcrossRow(row.rowId)}>先頭fieldの出典・日付を全fieldへ反映</button>
                {row.scopeKind === "vendor_plan" ? <button type="button" onClick={() => removeVendorRow(row.rowId)}>この行を削除</button> : null}
              </div>
            </header>

            {row.scopeKind === "vendor_plan" ? <div className="operator-identity-grid">
              <label>vendor識別子<input value={row.vendorId} onChange={(event) => updateRow(row.rowId, "vendorId", event.target.value)} placeholder="mangools" autoComplete="off" /></label>
              <label>plan識別子<input value={row.planId} onChange={(event) => updateRow(row.rowId, "planId", event.target.value)} placeholder="basic" autoComplete="off" /></label>
              {errorMessages(validation.errors, `${row.rowId}.vendorId`, hasStarted)}
              {errorMessages(validation.errors, `${row.rowId}.planId`, hasStarted)}
              {errorMessages(validation.errors, `${row.rowId}.identity`, hasStarted)}
              <p>billing toggle位置と価格表示の分類は、同じplanでもfieldごとに確認画面が異なるため各field内で記録します。</p>
            </div> : <div className="operator-identity-grid one-column">
              <label>Humanシナリオ根拠<input value={row.scenarioBasis} onChange={(event) => updateRow(row.rowId, "scenarioBasis", event.target.value)} maxLength={300} /></label>
              <p>seat数・利用量は公式料金から補完せず、この記事で試す条件としてHumanが入力します。</p>
              {errorMessages(validation.errors, `${row.rowId}.scenarioBasis`, hasStarted)}
            </div>}

            <div className="operator-field-stack">
              {rowFields(page, row).map((field, index) => <EditorialFieldset key={field.key} page={page} row={row} field={field} index={index} validationErrors={validation.errors} showErrors={hasStarted} updateField={updateField} />)}
            </div>
          </section>)}
        </div>

        {page.numericFields.some((field) => pilotFieldScope(field) === "vendor_plan") ? <button className="operator-add-row" type="button" onClick={addVendorRow}>vendor・plan行を追加</button> : null}

        <div className={`operator-validation-summary ${confirmedContract ? "is-valid" : "is-waiting"}`} aria-live="polite">
          <strong>{confirmedContract ? "入力contract確定" : validation.contract ? "構造は合格・Human確認待ち" : hasStarted ? `修正が必要です（${errorCount}件）` : "入力待ち"}</strong>
          <p>{validation.contract && validation.calculationBlockers.length
            ? `unknownを${validation.calculationBlockers.length}件保持しています。証拠contractは確定できますが、TCO計算・記事承認はHOLDのままです。`
            : confirmedContract ? `${confirmationState}。記事承認はまだunreviewedです。`
              : validation.contract ? "公式画面と差分表を確認し、下のボタンで証拠contractを確定してください。" : "構造errorを直すまでcontractを出力しません。"}</p>
          <button type="button" disabled={!validation.contract || Boolean(confirmedContract)} onClick={confirmContract}>Human確認して証拠contractを確定</button>
        </div>

        {confirmedContract ? <div className="operator-json-output">
          <div className="operator-json-actions"><button type="button" onClick={copyJson}>JSONをコピー</button><button type="button" onClick={downloadJson}>JSONを保存</button><span>{copyState}</span></div>
          <pre aria-label={`${page.id} editorial input contract JSON`}>{json}</pre>
        </div> : null}
      </form>
    </section>
  );
}

const ownedLedgerStorageKey = "saas-tco-lab:human-confirmed-owned-observations-v1";

const ownedKindLabels: Readonly<Record<OwnedObservationKind, string>> = {
  p09_migration_work: "P09 移行作業",
  p09_training: "P09 教育",
  p11_baseline_work: "P11 導入前作業",
  p11_comparison_work: "P11 導入後作業",
};

const ownedArticleKinds: Readonly<Record<OwnedObservationArticleId, readonly OwnedObservationKind[]>> = {
  P09: ["p09_migration_work", "p09_training"],
  P11: ["p11_baseline_work", "p11_comparison_work"],
};

function localDay(date = new Date()): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function elapsedLabel(seconds: number): string {
  const hours = Math.floor(seconds / 3_600);
  const minutes = Math.floor((seconds % 3_600) / 60);
  const remainder = seconds % 60;
  return [hours, minutes, remainder].map((value) => String(value).padStart(2, "0")).join(":");
}

function OwnedObservationRecorder({
  articleId,
  baselineMonth,
  comparisonMonth,
  applyP09Totals,
  applyP11Totals,
}: {
  articleId: OwnedObservationArticleId;
  baselineMonth?: string;
  comparisonMonth?: string;
  applyP09Totals?: (workHours: string, trainingHours: string) => void;
  applyP11Totals?: (
    baselineMonth: string,
    comparisonMonth: string,
    baselineHours: string,
    comparisonHours: string,
  ) => void;
}) {
  const [kind, setKind] = useState<OwnedObservationKind>(ownedArticleKinds[articleId][0]);
  const [calendarMonth, setCalendarMonth] = useState("");
  const [confirmedOn, setConfirmedOn] = useState("");
  const [observations, setObservations] = useState<readonly ConfirmedOwnedObservation[]>([]);
  const [ledgerState, setLedgerState] = useState("確認済み台帳を読込中");
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [measurementClockNow, setMeasurementClockNow] = useState<number | null>(null);
  const [candidateSeconds, setCandidateSeconds] = useState<string | null>(null);
  const [candidateId, setCandidateId] = useState("");
  const [candidateErrors, setCandidateErrors] = useState<readonly string[]>([]);

  useEffect(() => {
    const task = window.setTimeout(() => {
      const today = localDay();
      setCalendarMonth(today.slice(0, 7));
      setConfirmedOn(today);
      const parsed = parseConfirmedOwnedObservations(window.localStorage.getItem(ownedLedgerStorageKey));
      setObservations(parsed.observations);
      setLedgerState(parsed.error ?? (parsed.observations.length ? `${parsed.observations.length}件読込済み` : "確認済み観測なし"));
    }, 0);
    return () => window.clearTimeout(task);
  }, []);

  useEffect(() => {
    if (startedAt === null) return undefined;
    const timer = window.setInterval(() => setMeasurementClockNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, [startedAt]);

  const elapsedSeconds = startedAt === null || measurementClockNow === null
    ? 0
    : Math.max(0, Math.floor((measurementClockNow - startedAt) / 1_000));
  const totals = useMemo(
    () => observationMonthTotals(observations, articleId),
    [articleId, observations],
  );

  function startMeasurement() {
    const now = Date.now();
    setStartedAt(now);
    setMeasurementClockNow(now);
    setCandidateSeconds(null);
    setCandidateId("");
    setCandidateErrors([]);
    setLedgerState("計測中・未保存");
  }

  function stopMeasurement() {
    if (startedAt === null) return;
    const seconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1_000));
    setStartedAt(null);
    setMeasurementClockNow(null);
    setCandidateSeconds(String(seconds));
    setCandidateId(`${articleId}:${kind}:${Date.now()}`);
    setCandidateErrors([]);
    setLedgerState("計測停止・Human確認前・未保存");
  }

  function discardCandidate() {
    setCandidateSeconds(null);
    setCandidateId("");
    setCandidateErrors([]);
    setLedgerState(observations.length ? `${observations.length}件確認済み` : "確認済み観測なし");
  }

  function confirmCandidate() {
    if (candidateSeconds === null) return;
    const result = confirmOwnedObservation({
      articleId,
      kind,
      calendarMonth,
      elapsedSeconds: candidateSeconds,
      confirmedOn,
      observationId: candidateId,
    });
    if (!result.observation) {
      setCandidateErrors(result.errors);
      setLedgerState("修正が必要です・未保存");
      return;
    }
    const current = parseConfirmedOwnedObservations(window.localStorage.getItem(ownedLedgerStorageKey));
    if (current.error) {
      setCandidateErrors([current.error]);
      setLedgerState("台帳error・未保存");
      return;
    }
    const next = [...current.observations, result.observation];
    try {
      window.localStorage.setItem(ownedLedgerStorageKey, JSON.stringify(next));
    } catch {
      setCandidateErrors(["端末内へ保存できませんでした。候補は確定せず、外部送信もしていません。"]);
      setLedgerState("端末保存error・未保存");
      return;
    }
    setObservations(next);
    setCandidateSeconds(null);
    setCandidateId("");
    setCandidateErrors([]);
    setLedgerState(`${next.length}件確認済み・端末内append-only保存`);
  }

  function applyTotals() {
    if (articleId === "P09" && applyP09Totals) {
      const work = summedObservationHours(observations, "P09", "p09_migration_work");
      const training = summedObservationHours(observations, "P09", "p09_training");
      if (!work || !training) {
        setCandidateErrors(["移行作業と教育の両方にHuman確認済み観測が必要です。未観測値は補完しません。"]);
        return;
      }
      applyP09Totals(work, training);
      setCandidateErrors([]);
      setLedgerState("P09確認済み合計を未承認入力候補へ反映済み");
      return;
    }
    if (articleId === "P11" && applyP11Totals) {
      if (!baselineMonth || !comparisonMonth) {
        setCandidateErrors(["上の入力欄で導入前の基準月と導入後の比較月を選んでください。"]);
        return;
      }
      const baseline = summedObservationHours(observations, "P11", "p11_baseline_work", baselineMonth);
      const comparison = summedObservationHours(observations, "P11", "p11_comparison_work", comparisonMonth);
      if (!baseline || !comparison) {
        setCandidateErrors(["選択した完全暦月の導入前・導入後観測が両方必要です。月途中や未観測値は補完しません。"]);
        return;
      }
      applyP11Totals(baselineMonth, comparisonMonth, baseline, comparison);
      setCandidateErrors([]);
      setLedgerState("P11確認済み月合計を未承認入力候補へ反映済み");
    }
  }

  return <section className="operator-measurement-recorder" aria-labelledby={`owned-recorder-${articleId}`}>
    <div className="operator-paste-heading">
      <div>
        <p className="eyebrow">CONFIRMED OBSERVATION LEDGER</p>
        <h4 id={`owned-recorder-${articleId}`}>実作業をその場で計測</h4>
      </div>
      <p>計測停止まではmemoryだけです。秒数を確認して明示的に確定したsessionだけ、PIIなしで端末内台帳へ追記します。既存行は上書き・削除しません。</p>
    </div>
    <div className="operator-owned-data-grid">
      <label>作業区分<select value={kind} disabled={startedAt !== null || candidateSeconds !== null} onChange={(event) => setKind(event.target.value as OwnedObservationKind)}>
        {ownedArticleKinds[articleId].map((candidate) => <option value={candidate} key={candidate}>{ownedKindLabels[candidate]}</option>)}
      </select></label>
      <label>計測対象月<input type="month" value={calendarMonth} disabled={startedAt !== null || candidateSeconds !== null} onChange={(event) => setCalendarMonth(event.target.value)} /></label>
      <label>Human確認日<input type="date" value={confirmedOn} disabled={startedAt !== null} onChange={(event) => setConfirmedOn(event.target.value)} /></label>
    </div>
    <div className="operator-measurement-clock" aria-live="polite">
      <strong>{elapsedLabel(elapsedSeconds)}</strong>
      <span>{startedAt === null ? "停止中" : "計測中・未保存"}</span>
    </div>
    <div className="operator-paste-actions">
      <button type="button" onClick={startMeasurement} disabled={startedAt !== null || candidateSeconds !== null}>計測開始</button>
      <button type="button" onClick={stopMeasurement} disabled={startedAt === null}>計測停止</button>
      {candidateSeconds !== null ? <>
        <button type="button" onClick={confirmCandidate}>この{candidateSeconds}秒をHuman確認して追記</button>
        <button type="button" onClick={discardCandidate}>候補を破棄</button>
      </> : null}
      <span>{ledgerState}</span>
    </div>
    {candidateSeconds !== null ? <p>
      未保存候補: {candidateSeconds}秒 = {secondsToDecimalHours(candidateSeconds) ?? "1秒以上の計測が必要"}時間
    </p> : null}
    {candidateErrors.length ? <ul className="operator-field-errors" role="alert">
      {candidateErrors.map((error) => <li key={error}>{error}</li>)}
    </ul> : null}
    {totals.length ? <div className="table-scroll" tabIndex={0} aria-label={`${articleId}の確認済み実測合計`}>
      <table className="operator-diff-table">
        <caption>Human確認済みsessionだけの月別合計</caption>
        <thead><tr><th>月</th><th>区分</th><th>session数</th><th>合計時間</th></tr></thead>
        <tbody>{totals.map((total) => <tr key={`${total.calendarMonth}-${total.kind}`}>
          <td>{total.calendarMonth}</td><td>{ownedKindLabels[total.kind]}</td><td>{total.sessions}</td><td>{total.hours}時間</td>
        </tr>)}</tbody>
      </table>
    </div> : <p>Human確認済みsessionはまだありません。</p>}
    <button type="button" onClick={applyTotals} disabled={!totals.length}>確認済み合計を上の自データ欄へ反映</button>
    <p><small>台帳合計を反映しても記事・fieldはunreviewedです。P11は完全に終了した暦月だけが後段validationを通ります。</small></p>
  </section>;
}

function EditorialFieldset({
  page,
  row,
  field,
  index,
  validationErrors,
  showErrors,
  updateField,
}: {
  page: PilotPage;
  row: EditorialRowFormValue;
  field: PilotNumericField;
  index: number;
  validationErrors: Readonly<Record<string, readonly string[]>>;
  showErrors: boolean;
  updateField: (rowId: string, fieldKey: string, key: keyof EditorialFieldFormValue, value: string) => void;
}) {
  const current = row.values[field.key] ?? emptyEditorialField();
  const effectiveSaleBannerState = current.saleBannerState || row.saleBannerState;
  const monthlyEquivalent = annualMonthlyEquivalent(
    current.value,
    current.currencyStatus === "known" ? current.currency : "",
  );
  const inputId = `${page.id}-${row.rowId}-${field.key.replaceAll(".", "-")}`;
  const prefix = `${row.rowId}.${field.key}`;
  const known = current.valueStatus === "known";
  return <fieldset>
    <legend><span>{String(index + 1).padStart(2, "0")}</span>{field.label}</legend>
    <p className="operator-contract-key">contract: {field.key} / {field.valueKind} / {row.scopeKind}</p>
    <div className="operator-status-row">
      <label>値状態<select value={current.valueStatus} onChange={(event) => updateField(row.rowId, field.key, "valueStatus", event.target.value)}><option value="known">確認済み</option><option value="unknown">不明</option><option value="not_applicable">該当なし</option></select></label>
      {!known ? <label>理由<input value={current.unknownReason} onChange={(event) => updateField(row.rowId, field.key, "unknownReason", event.target.value)} placeholder="公式ページに記載なし、など" maxLength={300} /></label> : null}
    </div>
    {errorMessages(validationErrors, `${prefix}.unknownReason`, showErrors)}
    {row.scopeKind === "vendor_plan" ? <div className="operator-identity-grid">
      <label>このfieldのbilling toggle位置<select value={current.billingToggleState} onChange={(event) => updateField(row.rowId, field.key, "billingToggleState", event.target.value)}><option value="">選択</option><option value="annual_selected">年払い選択</option><option value="monthly_selected">月払い選択</option><option value="not_present">toggleなし</option><option value="unknown">不明</option></select></label>
      <label>このfieldの価格表示分類<select value={current.saleBannerState} onChange={(event) => updateField(row.rowId, field.key, "saleBannerState", event.target.value)}><option value="">選択</option><option value="none">なし</option><option value="annual_discount_permanent">年払い恒常割引</option><option value="time_limited_promo">期間限定promo</option><option value="unknown">不明</option></select></label>
      {errorMessages(validationErrors, `${prefix}.billingToggleState`, showErrors)}
      {errorMessages(validationErrors, `${prefix}.saleBannerState`, showErrors)}
    </div> : null}
    <div className="operator-form-grid">
      <div className="operator-input-group">
        <label htmlFor={`${inputId}-value`}>{field.valueKind === "price" && current.billingPeriod === "annual" ? "一次観測値（checkout請求総額）" : "値"}</label>
        <div className="operator-value-row">
          <input id={`${inputId}-value`} inputMode="decimal" value={current.value} disabled={!known} onChange={(event) => updateField(row.rowId, field.key, "value", event.target.value)} placeholder={known ? "数値だけ" : "不明は空欄"} />
          <input id={`${inputId}-unit`} value={current.unit} onChange={(event) => updateField(row.rowId, field.key, "unit", event.target.value)} placeholder={known ? "画面表記の単位" : "判明時のみ単位"} aria-label={`${field.label}の単位`} />
        </div>
        {errorMessages(validationErrors, `${prefix}.value`, showErrors)}
        {errorMessages(validationErrors, `${prefix}.unit`, showErrors)}
        {field.valueKind === "price" ? <div className="operator-price-options expanded">
          <label>通貨状態<select value={current.currencyStatus} onChange={(event) => updateField(row.rowId, field.key, "currencyStatus", event.target.value)}><option value="">選択</option><option value="known">確認済み</option><option value="unknown">不明</option><option value="not_applicable">該当なし</option></select></label>
          {current.currencyStatus === "known" ? <label>ISO通貨code<input value={current.currency} onChange={(event) => updateField(row.rowId, field.key, "currency", event.target.value)} placeholder="JPY" maxLength={3} /></label> : null}
          {current.currencyStatus === "unknown" ? <><label>画面の通貨表記{current.valueStatus === "known" ? "（必須）" : "（表示がある場合）"}<input value={current.currencyDisplay} onChange={(event) => updateField(row.rowId, field.key, "currencyDisplay", event.target.value)} placeholder={current.valueStatus === "known" ? "$" : "未掲載なら空欄"} maxLength={20} /></label><label>通貨不明の理由<input value={current.currencyUnknownReason} onChange={(event) => updateField(row.rowId, field.key, "currencyUnknownReason", event.target.value)} maxLength={300} /></label></> : null}
          <label>請求周期<select value={current.billingPeriod} onChange={(event) => updateField(row.rowId, field.key, "billingPeriod", event.target.value)}><option value="">選択</option><option value="monthly">月次</option><option value="annual">年次</option><option value="one_time">一回</option><option value="per_usage">従量</option><option value="not_applicable">該当なし</option><option value="unknown">不明</option></select></label>
          <label>税区分<select value={current.taxTreatment} onChange={(event) => updateField(row.rowId, field.key, "taxTreatment", event.target.value)}><option value="">選択</option><option value="included">税込</option><option value="excluded">税別</option><option value="not_applicable">該当なし</option><option value="unknown">不明</option></select></label>
          {row.scopeKind === "vendor_plan" ? <label>価格の一次観測<select value={current.observedPriceBasis} onChange={(event) => updateField(row.rowId, field.key, "observedPriceBasis", event.target.value)}><option value="">選択</option><option value="checkout_billed_total">checkout請求総額</option><option value="displayed_price">公式画面の表示価格</option><option value="unknown">不明</option><option value="not_applicable">該当なし</option></select></label> : null}
          {current.billingPeriod === "annual" && known ? <div className="operator-derived-value"><span>月額換算（派生値）</span><strong>{monthlyEquivalent === null ? "最小通貨単位で割り切れないため非表示" : `${monthlyEquivalent} / mo`}</strong><small>checkout請求総額 ÷ 12（最小通貨単位で完全に割り切れる場合のみ表示）</small></div> : null}
          {current.billingPeriod === "annual" && known && effectiveSaleBannerState === "annual_discount_permanent" ? <>
            <label>同じplanの月払い比較値<input inputMode="decimal" value={current.monthlyReferenceValue} onChange={(event) => updateField(row.rowId, field.key, "monthlyReferenceValue", event.target.value)} placeholder="通貨記号なし（例: 61.00）" /><small>同じ通貨・税条件の月払い表示をHuman確認し、数値だけを入力します。単位は / mo 固定です。</small></label>
            <div className="operator-derived-value"><span>年払い割引率（派生値）</span><strong>{annualDiscountPercent(current.value, current.monthlyReferenceValue) === null ? "月払い比較値の確認待ち" : `約${annualDiscountPercent(current.value, current.monthlyReferenceValue)}%`}</strong><small>1 − 年次checkout総額 ÷（月払い価格 × 12）、整数%へ四捨五入</small></div>
          </> : null}
        </div> : null}
        {errorMessages(validationErrors, `${prefix}.currencyStatus`, showErrors)}
        {errorMessages(validationErrors, `${prefix}.currency`, showErrors)}
        {errorMessages(validationErrors, `${prefix}.currencyDisplay`, showErrors)}
        {errorMessages(validationErrors, `${prefix}.currencyUnknownReason`, showErrors)}
        {errorMessages(validationErrors, `${prefix}.billingPeriod`, showErrors)}
        {errorMessages(validationErrors, `${prefix}.taxTreatment`, showErrors)}
        {errorMessages(validationErrors, `${prefix}.observedPriceBasis`, showErrors)}
        {errorMessages(validationErrors, `${prefix}.monthlyReferenceValue`, showErrors)}
      </div>

      <div className="operator-input-group">
        {row.scopeKind === "vendor_plan" ? <><label htmlFor={`${inputId}-source`}>公式出典URL</label><input id={`${inputId}-source`} type="url" inputMode="url" autoComplete="off" value={current.sourceUrl} onChange={(event) => updateField(row.rowId, field.key, "sourceUrl", event.target.value)} placeholder="公式価格ページの完全URL" />{errorMessages(validationErrors, `${prefix}.sourceUrl`, showErrors)}</> : <><label>入力経路</label><p className="operator-scenario-note">公式価格ではなくHumanシナリオ。vendor出典URLは保存しません。</p></>}
      </div>
      <div className="operator-input-group"><label htmlFor={`${inputId}-observed`}>観測日</label><input id={`${inputId}-observed`} type="text" inputMode="numeric" autoComplete="off" placeholder="YYYY-MM-DD" maxLength={10} value={current.observedOn} onChange={(event) => updateField(row.rowId, field.key, "observedOn", event.target.value)} />{errorMessages(validationErrors, `${prefix}.observedOn`, showErrors)}</div>
      <div className="operator-input-group"><label htmlFor={`${inputId}-review`}>次回確認日</label><input id={`${inputId}-review`} type="text" inputMode="numeric" autoComplete="off" placeholder="YYYY-MM-DD" maxLength={10} value={current.nextReviewOn} onChange={(event) => updateField(row.rowId, field.key, "nextReviewOn", event.target.value)} />{errorMessages(validationErrors, `${prefix}.nextReviewOn`, showErrors)}</div>
    </div>
  </fieldset>;
}
