import { articleDraft } from "./article-drafts.ts";
import type { PilotPage } from "./pilot-pages";

export type DerivativeTemplate = {
  articleId: PilotPage["id"];
  note: string;
  xThread: readonly string[];
};

type VerifiedDerivativeSpec = {
  title: string;
  summary: string;
  sections: readonly { title: string; body: string }[];
  xPoints: readonly [string, string, string, string, string, string];
  articleUrl: string;
  observedOn: string;
  nextReviewOn: string;
};

const disclosure = "[PR] 本稿にはアフィリエイトリンクが含まれます。比較・評価は広告条件から独立して行います。";

const verifiedDerivativeSpecs: Readonly<Partial<Record<PilotPage["id"], VerifiedDerivativeSpec>>> = {
  P01: {
    title: "Mangools Basicの12か月TCOは452.40 USD",
    summary: "2026年8月2日に購入直前画面で確認したMangools Basic年払いの請求総額は452.40 USDです。1人・月400ルックアップという利用条件では、確認できた契約料金を12か月TCOの基準にします。",
    sections: [
      { title: "年額を一次値にする", body: "37.70 USDは年次請求総額を12で割った比較用の月あたり金額です。毎月37.70 USDずつ請求される意味ではないため、支払判断では452.40 USDを先に見ます。" },
      { title: "月払いとの差", body: "同じBasicの月払い表示は61.00 USDでした。終了日、カウントダウン、クーポン、取消線価格はなく、年払いは月払い12回分より約38%低い計算です。" },
      { title: "利用上限", body: "確認済み上限は100 keyword research requests / 24hです。月400ルックアップとは時間単位が違うため、月間合計だけで上限内と断定しません。" },
      { title: "超過料金", body: "公式FAQには従量超過単価の表示がなく、上限が24時間ごとに更新される説明がありました。未提示の超過料金はTCOへ加えていません。" },
      { title: "税と対象外費用", body: "Japan選択時はVAT 0.00 USDで、SubtotalとTotalが同額でした。為替換算、カード会社の海外事務手数料、途中解約時の返金や残存支払は確認済み総額に含めていません。" },
      { title: "結論", body: "今回確認できた12か月TCOは452.40 USDです。利用人数、利用頻度、契約条件が変わる場合は、同じ結論を流用せず購入直前画面で再確認します。" },
    ],
    xPoints: [
      "一次の確認値は購入直前画面の年次総額452.40 USD。37.70 USD/月は比較用の月額換算で、月次請求額ではありません。(2/8)",
      "同条件の月払いは61.00 USD。期間限定表示はなく、年払いは月払い12回分より約38%低い計算です。(3/8)",
      "今回の利用条件は1人・月400ルックアップ。公式料金の仕様ではなく、試算の前提として分けています。(4/8)",
      "Basicの確認済み上限は100 keyword research requests / 24h。月400回とは時間単位が違うため直接比較しません。(5/8)",
      "FAQに従量超過単価の表示はありません。Japan選択時はVAT 0.00 USD、SubtotalとTotalが同額でした。(6/8)",
      "為替、カード会社手数料、途中解約・返金条件は未確認です。未確認費用を0円とせず、確認できた契約料金だけを示します。(7/8)",
    ],
    articleUrl: "https://saastcolab.jp/pilot/pricing-calculator",
    observedOn: "2026-08-02",
    nextReviewOn: "2026-08-31",
  },
  P02: {
    title: "Mangools 3プランの年払い総額と利用上限",
    summary: "2026年8月2日の購入直前画面では、年払い総額がBasic 452.40 USD、Premium 632.40 USD、Agency 1,172.40 USDでした。安い順だけで決めず、1日あたりの調査回数と利用人数も一緒に確認します。",
    sections: [
      { title: "3プランの年額", body: "一次値は月額換算ではなく、購入直前画面の12か月請求総額です。Basic 452.40 USD、Premium 632.40 USD、Agency 1,172.40 USDとして比較します。" },
      { title: "調査回数の上限", body: "確認済みのkeyword research requests / 24hは、Basic 100回、Premium 500回、Agency 1,200回です。月間回数や追跡キーワード数とは別の指標です。" },
      { title: "利用人数", body: "Basicは1ユーザーを確認済みです。PremiumとAgencyは追加できるseat数の表示はあるものの、最低seat数を確認できていないため、人数適合の順位は付けません。" },
      { title: "超過時の扱い", body: "公式FAQは上限が24時間ごとに更新されると説明し、従量超過課金を提示していません。追加単価を0 USDと推測するのではなく、従量課金の比較対象外としました。" },
      { title: "選び方", body: "必要な1日あたり調査回数を先に決め、上限を満たす最小プランを残します。PremiumとAgencyは最低seat数が未確認なので、チーム人数を理由に選ぶ場合は購入前の再確認が必要です。" },
      { title: "結論", body: "年額と調査回数だけなら3プランを並べられますが、全条件を満たす最安プランは一律には決まりません。用途に必要な上限と人数がそろった時だけ選択します。" },
    ],
    xPoints: [
      "年払いの一次値はBasic 452.40、Premium 632.40、Agency 1,172.40 USD。月額換算ではなく12か月請求総額です。(2/8)",
      "keyword research requests / 24hはBasic 100、Premium 500、Agency 1,200。追跡キーワード数とは別指標です。(3/8)",
      "Basicは1ユーザーを確認済み。PremiumとAgencyは追加seat表示だけで最低seat数を確認できず、人数適合の順位は保留です。(4/8)",
      "FAQは上限の24時間更新を説明していますが、従量超過単価は提示していません。未提示単価を0 USDとは扱いません。(5/8)",
      "選ぶ順序は、必要な1日あたり調査回数→人数条件→年額。価格だけの最安順位をそのまま推奨へ変えません。(6/8)",
      "3プランの年額は比較できますが、全条件を満たす最安プランは用途次第です。購入直前に人数と上限を再確認します。(7/8)",
    ],
    articleUrl: "https://saastcolab.jp/pilot/plan-comparison",
    observedOn: "2026-08-02",
    nextReviewOn: "2026-08-31",
  },
  P03: {
    title: "Mangools・SE Ranking・Semrushを価格順位なしで比較",
    summary: "12か月請求総額を確認できたのはMangools Basicの452.40 USDだけです。SE RankingとSemrushは利用上限を確認できても同条件の年額が未確認なので、3社の価格順位は出していません。",
    sections: [
      { title: "確認できた料金", body: "Mangools Basicは年払い452.40 USDを確認済みです。SE Ranking CoreとSemrush SEOは購入直前の12か月請求総額を確認していないため、以前の月額表示を年額へ換算していません。" },
      { title: "上限は同じ単位ではない", body: "Mangools Basicは200 keywords / unlimited domains、SE Ranking Coreは2,000 keywords tracked daily、Semrush SEOは500 keywords to track dailyです。対象機能と時間単位が異なるため、数だけを横並びにしません。" },
      { title: "追加機能", body: "今回の基本SEO用途では、3候補とも別売の必須addonは確認されませんでした。ただし上位機能や利用条件まで同等という意味ではありません。" },
      { title: "移行費用", body: "SE Rankingはannual subscription向けfree migrationを確認しました。MangoolsとSemrushは移行費用を確認できていないため、無料とは扱いません。" },
      { title: "候補の絞り方", body: "最初に必要な追跡対象、調査回数、domain数、移行支援を固定します。その後、同じ機能と請求条件で年額を確認できた候補だけを価格比較へ入れます。" },
      { title: "結論", body: "現時点で3社を最安順に並べる根拠はありません。確認済みの上限を用途適合の判断に使い、SE RankingとSemrushの年額が確定するまで横断価格順位を保留します。" },
    ],
    xPoints: [
      "12か月請求総額を確認できたのはMangools Basicの452.40 USDだけ。SE RankingとSemrushは年額未確認です。(2/8)",
      "Mangoolsは200 keywords / unlimited domains、SE Rankingは2,000 tracked daily、Semrushは500 tracked daily。単位が違います。(3/8)",
      "数が大きい順を性能順位にしません。対象機能、更新頻度、domain条件をそろえない比較は誤読を招きます。(4/8)",
      "基本SEO用途の別売必須addonは3候補とも確認されませんでしたが、上位機能まで同等という意味ではありません。(5/8)",
      "SE Rankingはannual subscription向けfree migrationを確認。MangoolsとSemrushの移行費用は未確認です。(6/8)",
      "同条件の年額がそろうまで価格順位は出しません。上限は用途適合、料金は請求総額として別々に判断します。(7/8)",
    ],
    articleUrl: "https://saastcolab.jp/pilot/alternatives",
    observedOn: "2026-08-02",
    nextReviewOn: "2026-08-29",
  },
  P04: {
    title: "1人運用で見るMangools Basicの固定費",
    summary: "Mangools Basicは最低1ユーザー、月払い61.00 USDを確認済みです。1人で始められる契約条件は確認できましたが、導入時間と毎月の運用時間はまだ実測していないため、人件費込み総額は出していません。",
    sections: [
      { title: "確認済み固定費", body: "2026年8月2日の購入直前画面で、Basicの月払い61.00 USDを確認しました。最低利用者数は1人なので、不要な追加seatを前提にする必要はありません。" },
      { title: "契約料金と人件費を分ける", body: "月払いの契約料金は確認できますが、初期設定に要した時間と月々の運用時間は未観測です。未観測時間を0時間として総額を小さく見せません。" },
      { title: "少人数でも残る作業", body: "キーワード候補の確認、除外判断、記事への反映、結果の見直しは利用者側の仕事です。ツール料金だけで運用負担までなくなるとは断定しません。" },
      { title: "向いている条件", body: "1人で開始し、まず月払いで利用量を確かめたい場合は条件を合わせやすい構成です。複数人で同時利用する場合は、上位プランの人数条件を改めて確認します。" },
      { title: "まだ分からないこと", body: "実運用時間がないため、1記事あたりの作業時間や時間単価を含む損益分岐は未確定です。運用開始後に同じ作業範囲で計測します。" },
      { title: "結論", body: "確認できたのは1人利用と月61.00 USDの契約料金です。少人数への適合は確認できますが、人件費込みTCOの結論は自データが取れるまで保留します。" },
    ],
    xPoints: [
      "Mangools Basicは最低1ユーザー、月払い61.00 USDを確認済み。1人で始める契約条件はそろっています。(2/8)",
      "ただし、導入時間と毎月の運用時間はまだ実測していません。未観測時間を0時間としてTCOを小さく見せません。(3/8)",
      "キーワード候補の確認、除外判断、記事反映、見直しは利用者側の作業です。契約料金だけで運用負担は分かりません。(4/8)",
      "1人で月払いから試す場合は条件を合わせやすい一方、複数人利用では上位プランの人数条件を再確認します。(5/8)",
      "現時点で確認できる固定費は月61.00 USD。人件費込み総額と損益分岐は、自分たちの運用時間を測ってからです。(6/8)",
      "少人数向けかどうかは価格だけでなく、実際の作業時間、利用量、複数人利用の必要性で判断します。(7/8)",
    ],
    articleUrl: "https://saastcolab.jp/pilot/small-team-fit",
    observedOn: "2026-08-02",
    nextReviewOn: "2026-08-31",
  },
  P06: {
    title: "Mangools Basicは年払いで279.60 USD低い",
    summary: "Mangools Basicは月払い61.00 USD、年払い総額452.40 USDでした。月払いを12回続ける732.00 USDと比べると、年払いは279.60 USD、約38%低くなります。ただし途中解約時の返金・残存支払は未確認です。",
    sections: [
      { title: "同じ12か月で比較", body: "月払い61.00 USDを12回続けると732.00 USDです。年払いの購入直前請求総額452.40 USDとの差は279.60 USDで、同じ通貨・税表示の比較です。" },
      { title: "年払いの条件", body: "年払いは12か月契約として確認しました。表示は恒常的な年払い差で、終了日、カウントダウン、クーポン、取消線価格はありませんでした。" },
      { title: "月払いの価値", body: "月払いは12か月続ければ高くなりますが、利用期間が短い場合の総支払は別です。何か月使うかを決めずに年額差だけで選びません。" },
      { title: "解約条件は未確認", body: "途中解約時の返金、残存支払、解約費用を同一条件で確認できていません。年払いを途中でやめる可能性がある場合、このunknownが判断を変えます。" },
      { title: "判断の分岐", body: "12か月使い切る前提なら年払いの確認済み総額が低くなります。利用継続が読めない場合は、279.60 USDの差と月払いの柔軟性を比べます。" },
      { title: "結論", body: "12か月利用では年払い452.40 USDが月払い12回分より279.60 USD低いことを確認できます。解約リスクまで含む最終判断は、契約直前の返金・終了条件を確認して行います。" },
    ],
    xPoints: [
      "月払い61.00 USDを12回続けると732.00 USD。年払いの購入直前請求総額は452.40 USDです。(2/8)",
      "差は279.60 USDで、年払いは約38%低い計算。同じBasic・USD・Japan選択時の表示で比べています。(3/8)",
      "年払いは12か月契約。終了日・カウントダウン・クーポン・取消線価格はなく、期間限定価格とは扱いません。(4/8)",
      "月払いは12か月続ければ高くなりますが、短期利用なら総支払が変わります。利用予定期間を先に決めます。(5/8)",
      "途中解約時の返金・残存支払・解約費用は未確認。この条件を0 USDとして差額へ混ぜません。(6/8)",
      "12か月使い切るなら年払い、継続が読めないなら279.60 USDの差と月払いの柔軟性を比較します。(7/8)",
    ],
    articleUrl: "https://saastcolab.jp/pilot/annual-vs-monthly",
    observedOn: "2026-08-02",
    nextReviewOn: "2026-08-31",
  },
  P07: {
    title: "Mangools Basicの上限は100リクエスト/24時間",
    summary: "Mangools Basicで確認できた上限は100 keyword research requests / 24hです。今回の利用想定は月400ルックアップですが、月間回数と24時間上限は同じ単位ではないため、超過費用を自動計算していません。",
    sections: [
      { title: "確認済みの上限", body: "公式FAQでBasicの上限を100 keyword research requests / 24hと確認しました。カレンダー日ごとではなく、24時間単位で説明されている点を残します。" },
      { title: "月400回との違い", body: "月400ルックアップは1人が月4〜5本の記事を書く想定です。平均すれば少なく見えても、短時間に100回を超える使い方なら上限へ当たる可能性があります。" },
      { title: "従量課金ではない", body: "公式FAQには超過単位と超過単価の提示がありません。上限が24時間ごとに更新される説明なので、従量課金の増分費用は比較対象外です。" },
      { title: "0 USDとは言わない", body: "従量課金が提示されていないことと、上限到達時の影響がないことは別です。利用停止、待ち時間、上位プランへの変更が必要になる可能性を残します。" },
      { title: "繁忙日の確認", body: "通常月と繁忙日を分け、最も集中する24時間のリクエスト数を確認します。月間総数だけでは上限到達を判定できません。" },
      { title: "結論", body: "超過単価を使った追加費用計算は不要ですが、100回/24hを超えない運用設計が必要です。実利用データが取れたら、集中日の回数で再評価します。" },
    ],
    xPoints: [
      "Basicの確認済み上限は100 keyword research requests / 24h。月間上限ではありません。(2/8)",
      "今回の利用想定は1人・月400ルックアップ。月間400回と24時間100回は同じ単位ではなく、直接比較しません。(3/8)",
      "平均回数が少なくても、短時間に100回を超える使い方なら上限へ当たる可能性があります。(4/8)",
      "FAQに超過単位・超過単価の表示はありません。従量課金の増分費用は比較対象外です。(5/8)",
      "超過料金が提示されないことと影響がないことは別。待ち時間や上位プラン変更の可能性を残します。(6/8)",
      "見るべき数字は月間合計だけでなく、最も集中する24時間の利用回数です。(7/8)",
    ],
    articleUrl: "https://saastcolab.jp/pilot/usage-overage",
    observedOn: "2026-08-01",
    nextReviewOn: "2026-08-29",
  },
  P08: {
    title: "Mangools Basicの基本SEO用途は年452.40 USD",
    summary: "Mangools Basicは年払い452.40 USD、必要利用者数は1人です。今回選んだ基本SEO用途では別売の必須addonが価格ページに示されていないため、確認済み総額は基本料金452.40 USDです。",
    sections: [
      { title: "基本料金", body: "2026年8月2日の購入直前画面で年払い総額452.40 USDを確認しました。月額換算ではなく、12か月分として実際に表示された請求総額を使います。" },
      { title: "今回必要な機能", body: "キーワード調査、順位確認など、選定した基本SEO機能はMangoolsのbundleに含まれています。今回の用途に必須となる別売addonは価格ページに示されていません。" },
      { title: "利用人数", body: "Basicは1ユーザーを確認済みです。複数人で利用する場合は同じ総額を流用せず、上位プランのseat条件を確認します。" },
      { title: "追加課金単位", body: "別売の必須addonが確認されていないため、addonの課金単位は未確認です。将来別機能を必須にした場合は、価格と課金単位を改めて総額へ加えます。" },
      { title: "含めていない費用", body: "任意機能、カード会社手数料、為替換算、公開画面にない追加サービスは452.40 USDへ含めていません。必要になった時だけ根拠を確認します。" },
      { title: "結論", body: "1人の基本SEO用途では、確認済みの必須契約料金は年452.40 USDです。別売機能が必要な用途へ広げる場合、この結論は再利用しません。" },
    ],
    xPoints: [
      "Mangools Basicの年払い総額は452.40 USD。必要利用者数は1人です。(2/8)",
      "今回の基本SEO用途では、キーワード調査などの必要機能はbundleに含まれています。(3/8)",
      "価格ページに別売の必須addonは示されていないため、確認済み総額は基本料金452.40 USDです。(4/8)",
      "別売addonがないことを全機能無料とは言い換えません。用途を広げる場合は必要機能を再確認します。(5/8)",
      "Basicは1ユーザー。複数人利用では同じ総額を使わず、上位プランのseat条件を確認します。(6/8)",
      "カード会社手数料、為替換算、公開画面にない追加サービスは確認済み総額へ含めていません。(7/8)",
    ],
    articleUrl: "https://saastcolab.jp/pilot/addon-cost",
    observedOn: "2026-08-02",
    nextReviewOn: "2026-08-31",
  },
  P10: {
    title: "Japan選択時のMangools年額と税表示",
    summary: "Mangools BasicはJapan選択時も年払い452.40 USDで、購入直前画面にはVAT 0.00 USD、SubtotalとTotalが同額と表示されました。これは画面表示の記録であり、日本の税率を0%と断定するものではありません。",
    sections: [
      { title: "表示価格と通貨", body: "購入直前画面の年払い総額は452.40 USDです。ドル記号だけでなくUSDとして確認し、円表示へ置き換えていません。" },
      { title: "Japan選択時の税表示", body: "CountryをJapanにした画面でVAT 0.00 USD、SubtotalとTotalが同額でした。税率そのものは表示されていないため、税率0%とは記録していません。" },
      { title: "円換算を出さない理由", body: "記事用の為替レートを確認していないため、452.40 USDを固定の円額へ換算していません。カード会社の適用レートや海外事務手数料も別条件です。" },
      { title: "表示と税務判断を分ける", body: "購入画面のVAT表示は支払時点の画面状態です。利用者の税務上の処理や将来の制度変更まで保証する情報ではありません。" },
      { title: "再確認する場所", body: "支払前にCountry、通貨、Subtotal、VAT、Totalを同じ画面で見ます。過去のスクリーン表示だけで、現在の請求総額を決めません。" },
      { title: "結論", body: "確認できた事実は452.40 USD、VAT 0.00 USD表示、SubtotalとTotalが同額という3点です。円額と税率は未確認のまま分離します。" },
    ],
    xPoints: [
      "Japan選択時のMangools Basic年払い総額は452.40 USD。通貨はUSDとして確認しました。(2/8)",
      "購入直前画面ではVAT 0.00 USD、SubtotalとTotalが同額でした。(3/8)",
      "これは画面表示の記録で、日本の税率が0%という意味ではありません。税率そのものは未確認です。(4/8)",
      "記事用の為替レートを確認していないため、固定の円額へ換算していません。(5/8)",
      "カード会社の適用レートや海外事務手数料も452.40 USDには含めていません。(6/8)",
      "支払前にCountry、通貨、Subtotal、VAT、Totalを同じ画面で再確認します。(7/8)",
    ],
    articleUrl: "https://saastcolab.jp/pilot/japan-tax",
    observedOn: "2026-08-02",
    nextReviewOn: "2026-08-31",
  },
  P12: {
    title: "SaaS料金記事の根拠を読者自身で確かめる方法",
    summary: "SaaS TCO Labでは、全数値へ同じ確認間隔を当てません。価格、税、利用上限、解約条件ごとに出典URL、観測日、次回確認日を記録し、期限切れや矛盾がある値は比較・計算から外します。",
    sections: [
      { title: "数値ごとに証拠を持つ", body: "料金表のページ名だけでなく、どの値をどの画面で確認したかをfield単位で記録します。同じページでも価格、税、上限、請求周期は別々の主張です。" },
      { title: "共通の確認日数を置かない", body: "価格と利用上限では変わる頻度が違い、キャンペーンには終了日があります。そのため全field共通の確認間隔は適用せず、観測ごとの次回確認日を使います。" },
      { title: "未確認と対象外を分ける", body: "調べ切れていない値は未確認です。一方、別売addonが存在しないなど、その比較条件に適用しない項目は対象外です。どちらも勝手に0へ置き換えません。" },
      { title: "一次値と派生値を分ける", body: "年払いでは購入直前画面の年次請求総額を一次値にし、月額換算は派生値として表示します。月額換算を毎月の請求額と誤読させません。" },
      { title: "期限切れと矛盾を止める", body: "次回確認日を過ぎた値、公式画面同士で食い違う値、通貨や税が曖昧な値は、再確認まで順位とTCO計算へ入りません。古い値を現在価格として自動更新しません。" },
      { title: "結論", body: "読者が確認すべきなのは、金額だけでなく出典、観測日、次回確認日、画面状態、未確認事項です。この5点を追えない数値は購入判断の根拠にしません。" },
    ],
    xPoints: [
      "料金表のページ名だけでなく、どの値をどの画面で確認したかを項目ごとに記録します。(2/8)",
      "価格・税・利用上限・キャンペーンで変化頻度が違うため、全項目共通の確認間隔は設けません。(3/8)",
      "調べ切れていない『未確認』と、その条件に適用しない『対象外』を分けます。どちらも勝手に0へしません。(4/8)",
      "年払いは年次請求総額が一次値。月額換算は比較用の派生値で、毎月の請求額ではありません。(5/8)",
      "期限切れ、公式表示の矛盾、通貨・税の曖昧さがあれば、再確認まで順位とTCO計算から外します。(6/8)",
      "金額・出典・観測日・次回確認日・画面状態を追えることが、料金比較の最低条件です。(7/8)",
    ],
    articleUrl: "https://saastcolab.jp/pilot/evidence-method",
    observedOn: "2026-08-09",
    nextReviewOn: "2026-09-07",
  },
};

function buildVerifiedDerivative(articleId: PilotPage["id"], spec: VerifiedDerivativeSpec): DerivativeTemplate {
  const sectionText = spec.sections.map((section) => `## ${section.title}\n\n${section.body}`).join("\n\n");
  const note = `${disclosure}\n\n# ${spec.title}\n\n${spec.summary}\n\n${sectionText}\n\n` +
    "## この数字の使い方\n\nここで示す結論は、本文に記録したプラン、請求周期、地域、利用人数、利用量にだけ有効です。" +
    "自分の条件が違う場合は、金額だけを流用せず、購入直前画面の請求総額と必要な利用上限を同じ順序で確認してください。" +
    "月額換算は比較の補助であり、実際の請求時期や契約期間を置き換えるものではありません。" +
    "確認できない税、追加料金、解約条件、社内作業時間は0として合計せず、判断を変え得る未確認事項として残します。\n\n" +
    "## 比較結果が変わるとき\n\n価格改定だけでなく、選択中の月払い・年払い、対象地域、税表示、利用上限の単位、必要機能が変われば結論も変わります。" +
    "期間限定価格は通常価格と分け、終了条件を確認できない割引は将来も続く前提にしません。" +
    "複数サービスを比べる場合は、同じ機能・期間・人数・利用量へそろえられた候補だけを順位へ入れます。" +
    "表示が食い違う場合や次回確認日を過ぎた場合は、古い値で結論を更新せず再確認まで保留します。" +
    "この記事だけで購入を決めず、最終的な請求額、解約条件、利用上限は必ず公式の購入画面で読み返してください。\n\n" +
    `## 出典と更新\n\n掲載値は公式公開画面を人が確認した記録です。観測日は${spec.observedOn}、次回確認日は${spec.nextReviewOn}です。` +
    `出典URL、画面状態、未確認事項は本文の根拠表で確認できます。\n${spec.articleUrl}`;
  const xThread = [
    `${disclosure}\n${spec.summary} (1/8)`,
    ...spec.xPoints,
    `出典・観測日・未確認事項はこちら。${spec.articleUrl} (8/8)`,
  ];
  return { articleId, note, xThread };
}

export function buildDerivativeTemplate(page: PilotPage): DerivativeTemplate {
  const verified = verifiedDerivativeSpecs[page.id];
  if (verified) return buildVerifiedDerivative(page.id, verified);

  const draft = articleDraft(page);
  const fieldChecklist = page.numericFields
    .map((field) => `- ${field.label}: 【確認待ち】／【出典】／【観測日】／【次回確認日】`)
    .join("\n");
  const sections = draft.sections.map((section, index) => (
    `## ${index + 1}. ${section.title}\n\n${section.body}\n\n` +
    "公式画面の事実と利用者側の試算を分け、未確認条件は確認待ちのまま残します。"
  )).join("\n\n");
  const note = `${disclosure}\n\n# ${page.title}: ${page.question}\n\n` +
    `この記事で目指すのは、${page.readerOutcome}状態です。数値の確認が終わるまで投稿しません。\n\n` +
    `${sections}\n\n## 証拠チェック\n\n${fieldChecklist}\n\n` +
    "確認済みの値・出典・観測日・次回確認日がそろった後に、本文と配信素材を再生成します。";

  const xThread = [
    `${disclosure}\n${page.id}「${page.title}」は証拠確認中です。未確認の数値・リンクを含むため投稿しません。(1/1)`,
  ];

  return { articleId: page.id, note, xThread };
}
