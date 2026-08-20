"use client";

import Link from "next/link";
import { useMemo, useState, type ReactNode } from "react";

import type { CalculatorPrefill } from "../lib/calculator-prefill";
import {
  calculateServerTco,
  calculateServerZeroInputTable,
  calculateTco,
  formatMinor,
  type BillingPeriod,
  type PriceBasis,
  type PricingQuote,
  type ServerUseCase,
  type ServerZeroInputContract,
  type TaxTreatment,
  type UsageScenario,
} from "../lib/tco";

type TcoCalculatorProps = {
  blockedReason?: string;
  embedded?: boolean;
  prefill?: CalculatorPrefill | null;
  sourceHref?: string;
};

function decimalPlaces(value: string): number {
  const match = /^\d+(?:\.(\d+))?$/.exec(value.trim());
  return Math.min(match?.[1]?.length ?? 0, 8);
}

function CalculatorSource({
  href,
  prefill,
}: {
  href: string;
  prefill?: CalculatorPrefill | null;
}) {
  if (prefill) {
    return (
      <p className="calculator-source" data-calculator-prefill-source="approved-evidence">
        <strong>{prefill.sourceLabel}の確認済み価格を初期表示</strong>
        <span>出典: {prefill.sourceUrl}</span>
        <span>確認日 {prefill.observedOn} / 次回確認日 {prefill.nextReviewOn}</span>
        <span>入力値は編集できます。変更内容は保存・送信されません。</span>
      </p>
    );
  }
  return (
    <p className="calculator-source">
      <a href={href} target="_top">計算仕様・根拠の確認</a>
      <span>入力値は保存・送信せず、出典確認済みの値だけを使用してください。</span>
    </p>
  );
}

export function TcoCalculator({
  blockedReason,
  embedded = false,
  prefill = null,
  sourceHref = "/methodology/",
}: TcoCalculatorProps) {
  const [amount, setAmount] = useState(prefill?.amount ?? "1200");
  const [currency, setCurrency] = useState(prefill?.currency ?? "JPY");
  const [billingPeriod, setBillingPeriod] = useState<BillingPeriod>(prefill?.billingPeriod ?? "monthly");
  const [seats, setSeats] = useState(prefill?.seats ?? "3");
  const [basis, setBasis] = useState<PriceBasis>(prefill ? "flat" : "per_seat");
  const [taxTreatment, setTaxTreatment] = useState<TaxTreatment>(prefill?.taxTreatment ?? "included");
  const [taxRate, setTaxRate] = useState(prefill?.taxRate ?? "0.10");
  const [serverCostsEnabled, setServerCostsEnabled] = useState(false);
  const [initialFee, setInitialFee] = useState("0");
  const [renewalFee, setRenewalFee] = useState("0");
  const [renewalDueMonth, setRenewalDueMonth] = useState("13");
  const [campaignEnabled, setCampaignEnabled] = useState(false);
  const [campaignPrice, setCampaignPrice] = useState("");
  const [campaignPeriodMonths, setCampaignPeriodMonths] = useState("");
  const [domainBenefitEnabled, setDomainBenefitEnabled] = useState(false);
  const [domainPrice, setDomainPrice] = useState("");
  const [domainBillingPeriod, setDomainBillingPeriod] = useState<BillingPeriod>("annual");
  const [domainIncludedMonths, setDomainIncludedMonths] = useState("12");

  const outcome = useMemo(() => {
    try {
      const priceInputs = [amount];
      if (serverCostsEnabled) priceInputs.push(initialFee, renewalFee);
      if (serverCostsEnabled && campaignEnabled) priceInputs.push(campaignPrice);
      if (serverCostsEnabled && domainBenefitEnabled) priceInputs.push(domainPrice);
      const quote: PricingQuote = {
        currency,
        minorUnitDigits: Math.max(...priceInputs.map(decimalPlaces)),
        minimumCommitmentMonths: billingPeriod === "annual" ? 12 : 1,
        base: {
          name: prefill ? `${prefill.sourceLabel}の確認済み料金` : "入力した基本料金",
          amount,
          currency,
          billingPeriod,
          priceBasis: basis,
          minimumSeats: 1,
          includedSeats: 0,
          maximumSeats: null,
        },
        addons: [],
        usage: null,
        tax: {
          treatment: taxTreatment,
          rate: taxTreatment === "excluded" ? taxRate || null : null,
        },
      };
      const scenario: UsageScenario = {
        seats: Number(seats),
        monthlyUsage: Array.from({ length: 12 }, () => "0"),
        usageUnit: null,
      };
      const result = serverCostsEnabled
        ? calculateServerTco(quote, scenario, {
            initialFee,
            renewalFee,
            renewalDueMonth: Number(renewalDueMonth),
            campaignPrice: campaignEnabled ? campaignPrice : null,
            campaignPeriodMonths: campaignEnabled ? Number(campaignPeriodMonths) : null,
            domainPrice: domainBenefitEnabled ? domainPrice : null,
            domainBillingPeriod: domainBenefitEnabled ? domainBillingPeriod : null,
            domainIncludedMonths: domainBenefitEnabled ? Number(domainIncludedMonths) : null,
          })
        : calculateTco(quote, scenario);
      return { result, error: null };
    } catch (error) {
      return { result: null, error: error instanceof Error ? error.message : "入力を確認してください" };
    }
  }, [
    amount,
    basis,
    billingPeriod,
    campaignEnabled,
    campaignPeriodMonths,
    campaignPrice,
    currency,
    domainBenefitEnabled,
    domainBillingPeriod,
    domainIncludedMonths,
    domainPrice,
    initialFee,
    prefill,
    renewalDueMonth,
    renewalFee,
    seats,
    serverCostsEnabled,
    taxRate,
    taxTreatment,
  ]);

  if (blockedReason) {
    return (
      <section className={embedded ? "embed-calculator" : "shell page-section"} aria-labelledby="tco-calculator-title">
        <div className="calculator-card">
          <div>
            <p className="eyebrow">12か月費用を試算</p>
            <h2 id="tco-calculator-title">12か月TCO計算機</h2>
            <p>未確認の項目を0円や推測値へ置き換えないため、現在は計算を停止しています。</p>
          </div>
          <output className="calculator-result" aria-live="polite">
            <span>計算停止</span>
            <strong>未確認</strong>
            <small>{blockedReason}</small>
          </output>
          <CalculatorSource href={sourceHref} prefill={prefill} />
        </div>
      </section>
    );
  }

  return (
    <section className={embedded ? "embed-calculator" : "shell page-section"} aria-labelledby="tco-calculator-title">
      <div className="calculator-card">
        <div>
          <p className="eyebrow">12か月費用を試算</p>
          <h2 id="tco-calculator-title">12か月TCO計算機</h2>
          <p>
            {prefill
              ? "確認済みの年額・通貨・利用者数・税区分を初期表示しています。条件は自由に変更できます。"
              : "値は端末内で計算し、保存・送信しません。確認できた価格と税区分を入力してください。"}
          </p>
        </div>
        <div className="calculator-inputs">
          <label>料金<input inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} /></label>
          <label>通貨<input inputMode="text" value={currency} onChange={(event) => setCurrency(event.target.value.toUpperCase())} maxLength={3} /></label>
          <label>請求周期<select value={billingPeriod} onChange={(event) => setBillingPeriod(event.target.value as BillingPeriod)}><option value="monthly">月払い</option><option value="annual">年払い</option></select></label>
          <label>利用者数<input inputMode="numeric" value={seats} onChange={(event) => setSeats(event.target.value)} /></label>
          <label>料金の適用<select value={basis} onChange={(event) => setBasis(event.target.value as PriceBasis)}><option value="flat">表示された合計額</option><option value="per_seat">利用者ごとの料金</option></select></label>
          <label>税区分<select value={taxTreatment} onChange={(event) => setTaxTreatment(event.target.value as TaxTreatment)}><option value="included">税込</option><option value="excluded">税別</option><option value="not_applicable">対象外</option><option value="unknown">不明（計算停止）</option></select></label>
          {taxTreatment === "excluded" ? <label>税率<input inputMode="decimal" value={taxRate} onChange={(event) => setTaxRate(event.target.value)} /></label> : null}
          <label className="calculator-wide calculator-checkbox"><input type="checkbox" checked={serverCostsEnabled} onChange={(event) => setServerCostsEnabled(event.target.checked)} />サーバー固有費用を含める</label>
          {serverCostsEnabled ? <>
            <label>初期費用<input inputMode="decimal" value={initialFee} onChange={(event) => setInitialFee(event.target.value)} /></label>
            <label>更新料<input inputMode="decimal" value={renewalFee} onChange={(event) => setRenewalFee(event.target.value)} /></label>
            <label>更新料の支払月<input inputMode="numeric" value={renewalDueMonth} onChange={(event) => setRenewalDueMonth(event.target.value)} /></label>
            <label className="calculator-wide calculator-checkbox"><input type="checkbox" checked={campaignEnabled} onChange={(event) => setCampaignEnabled(event.target.checked)} />期間限定の月額料金を使う</label>
            {campaignEnabled ? <>
              <label>キャンペーン月額<input inputMode="decimal" value={campaignPrice} onChange={(event) => setCampaignPrice(event.target.value)} /></label>
              <label>適用月数<input inputMode="numeric" value={campaignPeriodMonths} onChange={(event) => setCampaignPeriodMonths(event.target.value)} /></label>
            </> : null}
            <label className="calculator-wide calculator-checkbox"><input type="checkbox" checked={domainBenefitEnabled} onChange={(event) => setDomainBenefitEnabled(event.target.checked)} />ドメイン込み特典を反映する</label>
            {domainBenefitEnabled ? <>
              <label>特典終了後のドメイン料金<input inputMode="decimal" value={domainPrice} onChange={(event) => setDomainPrice(event.target.value)} /></label>
              <label>ドメイン請求周期<select value={domainBillingPeriod} onChange={(event) => setDomainBillingPeriod(event.target.value as BillingPeriod)}><option value="monthly">月払い</option><option value="annual">年払い</option></select></label>
              <label>無料期間（月）<input inputMode="numeric" value={domainIncludedMonths} onChange={(event) => setDomainIncludedMonths(event.target.value)} /></label>
            </> : null}
          </> : null}
        </div>
        <output className="calculator-result" aria-live="polite">
          {outcome.result ? <><span>12か月総額</span><strong>{formatMinor(outcome.result.totalMinor, outcome.result.currency, outcome.result.minorUnitDigits)}</strong><small>入力条件を変更すると端末内で再計算します</small></> : <><span>計算停止</span><strong>未確認</strong><small>{outcome.error}</small></>}
        </output>
        {prefill ? <p className="calculator-note">初期値は確認時点の1プラン分の請求額です。利用者を増やした場合の追加料金は自動で推測しません。</p> : null}
        <CalculatorSource href={sourceHref} prefill={prefill} />
      </div>
    </section>
  );
}

const serverUseCaseLabels: Record<ServerUseCase, string> = {
  small_site: "小規模サイト",
  corporate_site: "法人サイト",
  ecommerce: "ECサイト",
};

export function ServerZeroInputCalculator({
  contract,
  afterResults = null,
}: {
  contract: ServerZeroInputContract;
  afterResults?: ReactNode;
}) {
  const [months, setMonths] = useState<12 | 24 | 36>(12);
  const [useCase, setUseCase] = useState<ServerUseCase>("small_site");
  const confirmedUseCaseRequirements = contract.useCaseRequirements[useCase]
    .map((requirement) => requirement.trim())
    .filter(Boolean);
  const outcome = useMemo(() => {
    try {
      return { table: calculateServerZeroInputTable(contract, months, useCase), error: null };
    } catch (error) {
      return { table: null, error: error instanceof Error ? error.message : "計算条件を確認してください" };
    }
  }, [contract, months, useCase]);

  return (
    <div className="server-zero-input" data-server-zero-input="approved-contract-only">
      <div className="server-zero-input-heading">
        <div>
          <p className="eyebrow">料金比較</p>
          <h2>{months}か月の総額で比べる</h2>
          <p>初期費用と更新料を含めた実際の支払総額です。確認できていない費用は足しません。</p>
        </div>
        <div className="server-zero-input-controls">
          <fieldset>
            <legend>期間</legend>
            <div role="group" aria-label="比較期間">
              {([12, 24, 36] as const).map((value) => (
                <button
                  aria-pressed={months === value}
                  key={value}
                  onClick={() => setMonths(value)}
                  type="button"
                >
                  {value}か月
                </button>
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend>用途</legend>
            <div role="group" aria-label="用途区分">
              {(Object.keys(serverUseCaseLabels) as ServerUseCase[]).map((value) => (
                <button
                  aria-pressed={useCase === value}
                  key={value}
                  onClick={() => setUseCase(value)}
                  type="button"
                >
                  {serverUseCaseLabels[value]}
                </button>
              ))}
            </div>
          </fieldset>
        </div>
      </div>
      <p className="server-use-case-description" aria-live="polite">
        <strong>{serverUseCaseLabels[useCase]}の必要条件:</strong>{" "}
        {confirmedUseCaseRequirements.length
          ? `${confirmedUseCaseRequirements.join("・")}。この条件を公式情報で確認できたプランだけを順位対象にします。`
          : "確認済みの必要条件はまだありません。用途適合を推測せず、順位対象にしません。"}
      </p>

      {outcome.table ? (
        <div data-server-zero-input-results="precomputed">
          <p className="server-comparison-mode" data-comparison-mode={outcome.table.comparisonMode}>
            {outcome.table.comparisonMode === "ranked_comparison"
              ? `順位付き比較（確認済み${outcome.table.confirmedVendorCount}社）`
              : `確認済み一覧（${outcome.table.confirmedVendorCount}社・3社未満は順位を付けません）`}
          </p>
          <div className="table-scroll" tabIndex={0} aria-label={`${months}か月のサーバー総額表を横スクロール`}>
            <table className="server-zero-input-table">
              <thead><tr><th>順位</th><th>サービス・プラン</th><th>{months}か月総額</th><th>1位との差</th></tr></thead>
              <tbody>
                {outcome.table.rows.map((row) => (
                  <tr key={`${row.vendorId}-${row.planId}`} data-ranking-eligible={row.rank !== null ? "true" : "false"}>
                    <td>{row.rank ?? "—"}</td>
                    <th>
                      <span>{row.displayName}</span>
                      <details className="server-row-details">
                        <summary>確認内容</summary>
                        <dl>
                          <div><dt>状態</dt><dd>{row.status === "ranked" || row.status === "confirmed_unranked" ? "確認済み" : row.reason}</dd></div>
                          <div><dt>観測日</dt><dd>{row.observedOn ?? "未確認"}</dd></div>
                          <div><dt>次回確認日</dt><dd>{row.nextReviewOn ?? "未確認"}</dd></div>
                          {row.reason ? <div><dt>順位を付けない理由</dt><dd>{row.reason}</dd></div> : null}
                        </dl>
                      </details>
                    </th>
                    <td>
                      {row.totalMinor !== null && row.currency !== null && row.minorUnitDigits !== null
                        ? <strong>{formatMinor(row.totalMinor, row.currency, row.minorUnitDigits)}</strong>
                        : row.status === "unconfirmed" ? <strong>未確認</strong> : "対象外"}
                    </td>
                    <td>
                      {row.differenceFromLowestMinor !== null && row.currency !== null && row.minorUnitDigits !== null
                        ? <strong>{formatMinor(row.differenceFromLowestMinor, row.currency, row.minorUnitDigits)}</strong>
                        : row.status === "unconfirmed"
                          ? "未確認"
                          : row.status === "ineligible"
                            ? "対象外"
                            : "比較保留"}
                    </td>
                  </tr>
                ))}
                {outcome.table.rows.length === 0 ? (
                  <tr><td colSpan={4}>確認済みのサーバー料金はまだありません。</td></tr>
                ) : null}
              </tbody>
            </table>
          </div>
          {afterResults}
          <p className="server-zero-input-note">
            未確認の行は0円に置き換えず、順位と差額の計算から除外します。順位は同じ通貨で確認済みのvendorが3社以上ある場合だけ表示します。
          </p>
        </div>
      ) : (
        <p className="server-zero-input-error" role="alert">計算停止: {outcome.error}</p>
      )}
      <p className="server-zero-input-methodology">
        任意条件を試す場合は<Link href="/methodology#detailed-calculator">詳細計算モード</Link>を利用できます。
      </p>
    </div>
  );
}
