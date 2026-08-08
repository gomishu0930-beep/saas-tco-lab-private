import { articleDraft } from "./article-drafts.ts";
import type { PilotPage } from "./pilot-pages";

export type DerivativeTemplate = {
  articleId: PilotPage["id"];
  note: string;
  xThread: readonly string[];
};

const disclosure = "[PR] 本稿には、承認後にアフィリエイトリンクを含む場合があります。比較・評価は広告条件から独立して行います。";

const p01ArticleUrl = "https://saastcolab.jp/pilot/pricing-calculator";

function buildP01VerifiedDerivative(): DerivativeTemplate {
  const note = `${disclosure}

# Mangools Basicの12か月TCOは452.40 USD

SaaSの料金表には「月額」が大きく表示されていても、実際の請求が月払いとは限りません。そこでMangools Basicについて、1人で月400ルックアップを使う条件を置き、公式の料金画面と購入直前画面で12か月の支払額を確認しました。

結論から言うと、2026年8月2日に確認した年払いの請求総額は452.40 USDです。画面では年払いが選ばれ、終了日・カウントダウン・クーポン・取消線価格はありませんでした。月払い61.00 USDと同じプラン・通貨・税条件で比べると、年払いは月払い12回分より約38%低い計算です。

37.70 USDは一次の確認値ではありません。購入直前画面の年次総額452.40 USDを12で割った、比較用の月あたり金額です。毎月37.70 USDずつ請求されるという意味ではないため、支払判断では年次請求総額を先に見ます。

利用条件も価格と分けました。今回の条件は1ユーザー、月400ルックアップです。公式FAQで確認したBasicの上限は100 keyword research requests / 24hでした。「月400回」と「24時間あたり100回」は時間単位が違うため、同じ指標として直接比べられません。月間合計が400回でも、特定日に100回を超える使い方なら上限へ当たる可能性があります。

上限超過について、確認した公式FAQには従量超過単価の表示がなく、上限が24時間ごとに更新される説明がありました。未提示の超過料金は推測せず、12か月TCOへ加えていません。

税は、CountryをJapanにした購入直前画面でVAT 0.00 USD、SubtotalとTotalが同額でした。これは2026年8月2日の画面状態で、将来の税務条件やカード会社の海外事務手数料を保証するものではありません。

今回確認できた12か月TCOは契約料金452.40 USDです。為替換算、カード会社の手数料、公開画面にない追加費用は含めていません。途中解約・返金・残存支払条件も未確認なので、契約の柔軟性は結論を保留しています。

料金比較では、まず購入直前画面の請求総額を見て、次に選択中の月払い・年払い、税・通貨・契約期間、自分の利用量と公式上限の単位を確認します。料金表の月額表示だけを先に見ると、年次一括請求と月次請求を取り違えやすいためです。

同じ452.40 USDでも、誰にでも同じ結論になるわけではありません。1人・月400ルックアップという条件が変われば、必要なプランや上限到達の可能性も変わります。価格と自分の利用条件を分離し、条件を変えた時は結論も再確認します。

掲載値はリアルタイム連携や価格の自動取得ではなく、正規画面を人が確認した時点の記録です。料金改定や表示条件の変化を見つけた場合は、次回確認日前でも再確認し、古い値を新しい価格として扱いません。

価格の次回確認日は2026年8月31日です。詳しい計算条件、出典、観測日はこちらで確認できます。
${p01ArticleUrl}`;

  const xThread = [
    `${disclosure}\nMangools Basicの12か月TCOを公式画面で確認しました。年払いの請求総額は452.40 USDです。(1/8)`,
    "一次の確認値は購入直前画面の年次総額452.40 USD。37.70 USD/月は年額を12で割った比較用の金額で、月次請求額ではありません。(2/8)",
    "同条件の月払いは61.00 USD。終了日・カウントダウン・クーポン・取消線価格はなく、年払いは月払い12回分より約38%低い計算です。(3/8)",
    "今回の利用条件は1ユーザー、月400ルックアップ。これは料金表の公式仕様ではなく、自分の利用条件として分けています。(4/8)",
    "Basicの確認済み上限は100 keyword research requests / 24h。月400回とは時間単位が違うので、直接同じ指標として比べません。(5/8)",
    "公式FAQに従量超過単価の表示はありませんでした。購入直前画面はJapan選択時にVAT 0.00 USD、SubtotalとTotalは同額でした。(6/8)",
    "為替、カード会社の手数料、途中解約・返金・残存支払条件は含めていません。未確認費用を0円にせず、確認できた契約料金だけを示します。(7/8)",
    `出典・観測日・次回確認日と計算条件はこちら。${p01ArticleUrl} (8/8)`,
  ];

  return { articleId: "P01", note, xThread };
}

export function buildDerivativeTemplate(page: PilotPage): DerivativeTemplate {
  if (page.id === "P01") return buildP01VerifiedDerivative();
  const draft = articleDraft(page);
  const fieldChecklist = page.numericFields
    .map((field) => `- ${field.label}: 【Human確認値またはunknown】／【出典】／【観測日】／【次回確認日】`)
    .join("\n");
  const sections = draft.sections.map((section, index) => (
    `## ${index + 1}. ${section.title}\n\n${section.body}\n\n` +
    "公式画面の事実とHuman scenarioを分け、未確認条件はunknownのまま残します。"
  )).join("\n\n");
  const note = `${disclosure}\n\n# ${page.title}: ${page.question}\n\n` +
    `この記事で目指すのは、${page.readerOutcome}状態です。料金の安さだけで決めず、同じ利用条件、契約期間、税・通貨、追加費用、運用負担を一つずつ確認します。` +
    "本文中の数値はHumanが公式公開画面で確認したfieldだけを使い、未確認値はunknownのまま残します。自動取得した価格DBや推測値は使いません。\n\n" +
    `${sections}\n\n## 証拠チェック\n\n${fieldChecklist}\n\n` +
    "数値の横に出典URL、観測日、次回確認日がない場合、その値は比較・順位・TCO計算へ入れません。" +
    "価格改定、条件変更、契約終了を見つけた場合は、次回確認日前でも再確認します。\n\n" +
    "## まとめ\n\n結論は、確認済みの入力条件にだけ有効です。自分のseat数・利用量・移行条件へ置き換え、unknownが残る場合は計算を止めてください。" +
    "最終判断の前には、購入直前の公式画面で請求総額と税表示をもう一度確認し、この記事の観測日以後に条件が変わっていないか確かめてください。" +
    "記事URL: 【Humanが公開時に入力】";

  const xThread = [
    `${disclosure}\n${page.id}「${page.title}」を、${page.question}という観点で整理します。投稿時点で未承認の数値・リンクは掲載しません。(1/8)`,
    `先に揃えるのは、同じ利用条件です。seat数、利用量、契約期間を混ぜたまま価格だけ比べると、判断がずれます。(2/8)`,
    `確認対象: ${page.numericFields.map((field) => field.label).join("／")}。値・出典・観測日・次回確認日をfield単位で記録します。(3/8)`,
    "通貨記号だけ、税表示なし、課金周期不明などはunknownです。推測でISO通貨、税込・税別、月額・年額を補いません。(4/8)",
    `今回の読者成果は「${page.readerOutcome}」こと。確認できない条件が結論を左右する場合は、比較やTCO計算を止めます。(5/8)`,
    "公式表示とHuman scenarioは別の証拠です。利用人数や社内時間単価を、vendorの公式仕様として扱わないように分離します。(6/8)",
    "出典期限を過ぎた値、未承認field、Affiliate承認前のCTAは使いません。PR表示はリンクより前に置きます。(7/8)",
    "詳しい入力条件と根拠は記事で確認できます。記事URL: 【Humanが公開時に入力】 (8/8)",
  ];

  return { articleId: page.id, note, xThread };
}
