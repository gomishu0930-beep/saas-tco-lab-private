import type { Metadata } from "next";

import { PolicyPage } from "../components/PolicyPage";

export const metadata: Metadata = {
  title: "運営者情報",
  description: "SaaS TCO Labの運営主体、責任範囲、連絡方法に関する公開前情報。",
};

export default function OperatorInformationPage() {
  return <PolicyPage eyebrow="OPERATOR" title="運営者情報" lead="審査・公開前確認用の運営情報です。個人情報やcredentialをrepositoryへ保存しない境界を維持しています。" sections={[
    { title: "サイト名", paragraphs: ["SaaS TCO Lab"] },
    { title: "運営形態", paragraphs: ["日本の個人事業として運営し、公開上の表示名はomishuです。法令・契約上必要な本人情報は、公開release前のHuman確認で別管理します。"] },
    { title: "事業内容", paragraphs: ["SaaSの料金・利用条件・12か月TCOの編集記事、比較方法、計算ツールを提供します。"] },
    { title: "責任範囲", paragraphs: ["掲載内容は観測日時点の情報です。契約前には必ず提供事業者の最新ページと契約条件を確認してください。"] },
    { title: "連絡方法", paragraphs: ["お問い合わせrouteを用意しています。送信先は独自domain確定後、Humanが管理する事業用窓口として有効化します。"] },
    { title: "更新日", paragraphs: ["2026年7月28日"] },
  ]} />;
}
