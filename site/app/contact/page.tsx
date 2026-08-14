import type { Metadata } from "next";

import { PolicyPage } from "../components/PolicyPage";

export const metadata: Metadata = {
  title: "お問い合わせ",
  description: "SaaS TCO Labへの掲載内容、訂正、広告、権利に関する問い合わせ案内。",
};

export default function ContactPage() {
  return <PolicyPage eyebrow="CONTACT" title="お問い合わせ" lead="掲載内容の訂正、権利、広告、その他のご連絡に関する受付方針です。" sections={[
    { title: "現在の受付状態", paragraphs: ["このページには入力フォームを設置していません。公開用の事業窓口を追加するまでは、個人情報や非公開情報を送信しないでください。"] },
    { title: "訂正依頼", paragraphs: ["対象記事、対象field、正しい情報を確認できる公開URL、確認日をお知らせください。価格や契約条件は公式情報を優先します。"] },
    { title: "権利・広告", paragraphs: ["掲載範囲、商標、広告表示、Affiliate条件に関する連絡はHuman Approverが確認します。自動返信を承認回答として扱いません。"] },
    { title: "送らない情報", paragraphs: ["パスワード、API key、支払情報、本人確認書類、個人の健康・金融情報は送信しないでください。"] },
  ]} />;
}
