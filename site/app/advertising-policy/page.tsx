import type { Metadata } from "next";

import { PolicyPage } from "../components/PolicyPage";

export const metadata: Metadata = {
  title: "広告掲載ポリシー",
  description: "SaaS TCO LabのPR表示、Affiliate CTA、比較独立性、報酬の取扱方針。",
};

export default function AdvertisingPolicyPage() {
  return <PolicyPage eyebrow="ADVERTISING POLICY" title="広告掲載ポリシー" lead="広告収益と比較判断を分離し、読者が広告であることをCTAより先に認識できるようにします。" sections={[
    { title: "PR表示", paragraphs: ["Affiliate広告を含む記事は冒頭にPR・広告表示を固定し、広告リンクより先に表示します。"] },
    { title: "生成AIの補助利用", paragraphs: ["記事制作に生成AIを補助的に使用する場合があります。公開前に人が公式の一次情報、数値、計算結果を確認し、未確認値は推測しません。"] },
    { title: "CTAの条件", paragraphs: ["対象site、region、表示方法についてAffiliate承認済みのpartnerだけを有効化します。申請中、期限切れ、遷移先不一致は無効です。"] },
    { title: "比較の独立性", paragraphs: ["報酬額や提携の有無を、TCO計算、長所・短所、順位の根拠として使いません。提携がないサービスも同じ検証基準で扱います。"] },
    { title: "成果の記録", paragraphs: ["収益はconfirmed commissionsだけを月次KPIへ算入します。pending、rejected、refundを確定収益として表示しません。"] },
    { title: "停止", paragraphs: ["開示がCTAより後、partner未承認、リンク切れ、条件期限切れの場合はCTAを自動的に無効とするrelease gateを適用します。"] },
  ]} />;
}
