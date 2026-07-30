import type { Metadata } from "next";

import { PolicyPage } from "../components/PolicyPage";

export const metadata: Metadata = {
  title: "お問い合わせ",
  description: "SaaS TCO Labへの掲載内容、訂正、広告、権利に関する問い合わせ窓口の公開前案内。",
};

export default function ContactPage() {
  return <PolicyPage eyebrow="CONTACT" title="お問い合わせ" lead="掲載内容の訂正、権利、広告、その他のご連絡を受け付けるための準備中routeです。" sections={[
    { title: "現在の受付状態", paragraphs: ["事業用窓口は独自domain確定後に有効化します。現在このページから外部送信は行いません。"] },
    { title: "訂正依頼", paragraphs: ["対象記事、対象field、正しい情報を確認できる公開URL、確認日をお知らせください。価格や契約条件は公式情報を優先します。"] },
    { title: "権利・広告", paragraphs: ["掲載範囲、商標、広告表示、Affiliate条件に関する連絡はHuman Approverが確認します。自動返信を承認回答として扱いません。"] },
    { title: "送らない情報", paragraphs: ["パスワード、API key、支払情報、本人確認書類、個人の健康・金融情報は送信しないでください。"] },
  ]} />;
}
