export function AdvertisingDisclosure() {
  return (
    <aside
      className="shell article-pr-disclosure"
      id="article-pr-disclosure"
      aria-label="広告・アフィリエイトに関する表示"
    >
      <strong>PR・広告に関する表示</strong>
      <p>
        当サイトはアフィリエイト広告を利用する場合があります。報酬の有無で比較条件や
        算定結果を変えません。<span data-affiliate-disclosure-status="disabled">現在、この記事の送客リンクは無効です。</span>
      </p>
      <p>
        記事制作に生成AIを補助的に使用する場合があります。公開前に人が一次情報、数値、
        計算結果を確認しています。
      </p>
    </aside>
  );
}
