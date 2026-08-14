import type { Metadata } from "next";

import { PolicyPage } from "../components/PolicyPage";

export const metadata: Metadata = {
  title: "プライバシーポリシー",
  description: "SaaS TCO Labのアクセス解析、保存情報、外部送信、問い合わせ情報の取扱方針。",
};

export default function PrivacyPage() {
  return <PolicyPage eyebrow="PRIVACY" title="プライバシーポリシー" lead="必要最小限の計測だけを、訪問者の同意後に行います。query文字列、個人情報、Affiliate識別子は解析eventへ入れません。" sections={[
    { title: "アクセス解析", paragraphs: ["同意後にpage view、30秒到達、比較操作、外部送客clickの種類を計測する場合があります。同意前または拒否後はGoogle Analyticsへの通信を開始しません。"] },
    { title: "端末内の保存", paragraphs: ["解析への同意状態を端末内へ保存します。広告目的の個人プロファイル作成には利用しません。"] },
    { title: "問い合わせ", paragraphs: ["お問い合わせで提供された情報は回答と必要な記録のためだけに使います。credential、支払情報、本人確認書類の送信は求めません。"] },
    { title: "Affiliate", paragraphs: ["有効な広告リンクの遷移先事業者がcookie等を使用する場合があります。リンクより前に広告であることを表示し、未承認partnerのリンクは有効化しません。"] },
    { title: "保存と削除", paragraphs: ["保有目的がなくなった情報は削除または匿名化します。法令・契約で保存期間が定められる場合はその範囲に従います。"] },
    { title: "改定", paragraphs: ["重要な変更はこのページで公表し、更新日を明示します。最終更新日は2026年7月28日です。"] },
  ]} />;
}
