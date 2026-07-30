import type { Metadata } from "next";

import { PolicyPage } from "../components/PolicyPage";

export const metadata: Metadata = {
  title: "SaaS TCO Labについて",
  description: "Human確認値と12か月TCOでSaaS選定を支援するSaaS TCO Labの目的と編集方針。",
};

export default function AboutPage() {
  return <PolicyPage eyebrow="ABOUT" title="SaaS TCO Labについて" lead="料金表の安さだけではなく、利用条件をそろえた12か月総額と、選ばない条件まで示す比較メディアです。" sections={[
    { title: "目的", paragraphs: ["SaaSの料金、seat、利用上限、超過、必須addonを同じscenarioで整理し、導入後に想定外の費用が出るリスクを減らします。"] },
    { title: "情報の作り方", paragraphs: ["数値はHumanが公開ページで確認し、出典URL、観測日、次回確認日を付けます。自動取得や価格履歴DBへ無断転用しません。", "税、通貨、課金周期が不明な場合は推測せずunknownとします。"] },
    { title: "比較の独立性", paragraphs: ["提携報酬の有無で計算式や比較条件を変えません。広告リンクがある場合は記事冒頭でPR表示し、提携承認済みのpartnerだけを案内します。"] },
    { title: "現在地", paragraphs: ["現在は公開前のnoindex運用です。実記事、indexing、送客CTAはそれぞれHuman reviewと個別GOを通過してから有効化します。"] },
  ]} />;
}
