import type { SyntheticComparison } from "../lib/synthetic-data";

export function ComparisonTable({
  data,
  compact = false,
}: {
  data: SyntheticComparison;
  compact?: boolean;
}) {
  return (
    <div className="comparison-card">
      <div className="comparison-toolbar">
        <div>
          <span className="fixture-label">{data.label}</span>
          <p>{data.methodology}</p>
        </div>
        <dl>
          <div>
            <dt>生成時刻</dt>
            <dd>{data.generatedAt}</dd>
          </div>
          <div>
            <dt>広告リンク</dt>
            <dd>0件</dd>
          </div>
        </dl>
      </div>
      <p
        className="comparison-disclosure"
        id="comparison-ad-disclosure"
        role="note"
      >
        <strong>広告表示:</strong> 合成fixtureのためアフィリエイトリンクはなく、
        すべての送客CTAは無効です。
      </p>
      <div className="table-scroll" tabIndex={0} aria-label="比較表、横スクロール可能">
        <table>
          <caption className="sr-only">合成データによるSaaSプラン比較</caption>
          <thead>
            <tr>
              <th scope="col">サービス / プラン</th>
              <th scope="col">比較条件</th>
              <th scope="col">12か月TCO</th>
              <th scope="col">適合判定</th>
              {!compact && <th scope="col">根拠と期限</th>}
              <th scope="col">広告</th>
            </tr>
          </thead>
          <tbody>
            {data.plans.map((plan) => (
              <tr key={plan.id}>
                <th scope="row">
                  <strong>{plan.vendor}</strong>
                  <span>{plan.plan}</span>
                </th>
                <td>
                  <span>{plan.region} / {plan.currency} / {plan.tax}</span>
                  <small>{plan.billing}・契約 {plan.commitment}</small>
                  {!compact && <small>{plan.scenario}</small>}
                </td>
                <td className="tco-cell">
                  <strong>{plan.tco}</strong>
                  <small>Python算定済み</small>
                </td>
                <td>
                  <span className={`fit-badge ${plan.fit === "適合" ? "fit" : "not-fit"}`}>
                    {plan.fit}
                  </span>
                  <small>{plan.fitReason}</small>
                </td>
                {!compact && (
                  <td className="evidence-cell">
                    <strong>合成根拠（外部リンクなし）</strong>
                    <small>取得 {plan.evidenceRetrievedAt}</small>
                    <small>data期限 {plan.dataExpiresAt}</small>
                    <small>rights期限 {plan.rightsExpiresAt}</small>
                  </td>
                )}
                <td>
                  <span
                    className="cta-disabled"
                    aria-label="広告リンク無効"
                    aria-describedby="comparison-ad-disclosure"
                  >
                    {plan.affiliate}
                  </span>
                  <small>実提携なし</small>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
