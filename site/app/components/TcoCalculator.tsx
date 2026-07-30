"use client";

import { useMemo, useState } from "react";

import { calculateTco, formatMinor, type PriceBasis, type TaxTreatment } from "../lib/tco";

type TcoCalculatorProps = {
  blockedReason?: string;
  embedded?: boolean;
  sourceHref?: string;
};

function CalculatorSource({ href }: { href: string }) {
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
  sourceHref = "/methodology/",
}: TcoCalculatorProps) {
  const [amount, setAmount] = useState("1200");
  const [seats, setSeats] = useState("3");
  const [basis, setBasis] = useState<PriceBasis>("per_seat");
  const [taxTreatment, setTaxTreatment] = useState<TaxTreatment>("included");
  const [taxRate, setTaxRate] = useState("0.10");

  const outcome = useMemo(() => {
    try {
      const result = calculateTco(
        {
          currency: "JPY",
          minorUnitDigits: 0,
          minimumCommitmentMonths: 1,
          base: {
            name: "Human入力の基本料金",
            amount,
            currency: "JPY",
            billingPeriod: "monthly",
            priceBasis: basis,
            minimumSeats: 1,
            includedSeats: 0,
            maximumSeats: null,
          },
          addons: [],
          usage: null,
          tax: {
            treatment: taxTreatment,
            rate: taxTreatment === "excluded" ? taxRate : null,
          },
        },
        {
          seats: Number(seats),
          monthlyUsage: Array.from({ length: 12 }, () => "0"),
          usageUnit: null,
        },
      );
      return { result, error: null };
    } catch (error) {
      return { result: null, error: error instanceof Error ? error.message : "入力を確認してください" };
    }
  }, [amount, basis, seats, taxRate, taxTreatment]);

  if (blockedReason) {
    return (
      <section className={embedded ? "embed-calculator" : "shell page-section"} aria-labelledby="tco-calculator-title">
        <div className="calculator-card">
          <div>
            <p className="eyebrow">INTERACTIVE TCO / FAIL CLOSED</p>
            <h2 id="tco-calculator-title">12か月TCO計算機</h2>
            <p>取込済みcontractの未確定fieldをゼロや推測値へ置き換えないため、入力と計算を停止しています。</p>
          </div>
          <output className="calculator-result" aria-live="polite">
            <span>計算停止</span>
            <strong>UNKNOWN</strong>
            <small>{blockedReason}</small>
          </output>
          <CalculatorSource href={sourceHref} />
        </div>
      </section>
    );
  }

  return (
    <section className={embedded ? "embed-calculator" : "shell page-section"} aria-labelledby="tco-calculator-title">
      <div className="calculator-card">
        <div>
          <p className="eyebrow">INTERACTIVE TCO / SYNTHETIC INPUT</p>
          <h2 id="tco-calculator-title">12か月TCO計算機</h2>
          <p>値は端末内で計算し、保存・送信しません。価格・税区分はHuman確認値だけを入力してください。</p>
        </div>
        <div className="calculator-inputs">
          <label>1回の料金<input inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} /></label>
          <label>seat数<input inputMode="numeric" value={seats} onChange={(event) => setSeats(event.target.value)} /></label>
          <label>課金単位<select value={basis} onChange={(event) => setBasis(event.target.value as PriceBasis)}><option value="flat">固定</option><option value="per_seat">seatごと</option></select></label>
          <label>税区分<select value={taxTreatment} onChange={(event) => setTaxTreatment(event.target.value as TaxTreatment)}><option value="included">税込</option><option value="excluded">税別</option><option value="not_applicable">対象外</option><option value="unknown">不明（計算停止）</option></select></label>
          {taxTreatment === "excluded" ? <label>税率<input inputMode="decimal" value={taxRate} onChange={(event) => setTaxRate(event.target.value)} /></label> : null}
        </div>
        <output className="calculator-result" aria-live="polite">
          {outcome.result ? <><span>12か月総額</span><strong>{formatMinor(outcome.result.totalMinor, outcome.result.currency, outcome.result.minorUnitDigits)}</strong><small>Python fixtureとのgolden一致を検査するTypeScript実装</small></> : <><span>計算停止</span><strong>UNKNOWN</strong><small>{outcome.error}</small></>}
        </output>
        <CalculatorSource href={sourceHref} />
      </div>
    </section>
  );
}
