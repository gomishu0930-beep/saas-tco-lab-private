import { articleDraft } from "./article-drafts.ts";
import type { PilotPage } from "./pilot-pages";

export type DerivativeTemplate = {
  articleId: PilotPage["id"];
  note: string;
  xThread: readonly string[];
};

const disclosure = "[PR] 本稿には、承認後にアフィリエイトリンクを含む場合があります。比較・評価は広告条件から独立して行います。";

export function buildDerivativeTemplate(page: PilotPage): DerivativeTemplate {
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
