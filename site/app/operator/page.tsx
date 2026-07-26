import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "あなたの操作",
  description: "本人操作が必要な箇所だけを抜き出した手順表と、完了後の自動作業。",
};

const actions = [
  {
    id: "H1",
    timing: "今",
    title: "公開名義とURLを決める",
    minutes: "3分",
    status: "入力待ち",
    why: "外部への名義表示と許諾scopeは、Human Approverだけが確定できます。",
    steps: [
      "法的名義または事業者名を決める",
      "公開予定URLを決める。未公開なら『未公開』とする",
      "許諾判断を行う承認者名を決める",
    ],
    done: "返信テンプレートの3項目を返す",
    next: "5社の許諾メールへ反映し、同一scopeで送信準備を確定",
  },
  {
    id: "H2",
    timing: "完了",
    title: "5社への許諾照会を承認",
    minutes: "2分",
    status: "送信済み・回答待ち",
    why: "2026-07-23に5社へ送信済みです。送信済みは利用許諾の承認を意味しません。",
    steps: [
      "追加の送信操作は不要",
      "回答メールはGmail内に残す",
      "回答が届いた会社名だけを知らせる",
    ],
    done: "2026-07-23 送信済み",
    next: "回答を8項目へ分解し、Human最終判定へ回す",
  },
  {
    id: "H3",
    timing: "今",
    title: "Google Adsを課金画面前まで進める",
    minutes: "2分",
    status: "カード要求時は停止",
    why: "国・時刻・通貨はアカウント作成後に変更できません。",
    steps: [
      "国が日本であることを確認",
      "タイムゾーンがGMT+09:00 日本時間であることを確認",
      "通貨が日本円（JPY）であることを確認",
      "問題なければ google_ads: GO と返信",
      "カード・支払プロファイルを要求されたら確定せず停止",
    ],
    done: "google_ads: GO",
    next: "無料範囲ならKeyword Plannerへ進み、課金要求時は月末まで保留",
  },
  {
    id: "H4",
    timing: "完了",
    title: "Mangoolsアカウントを本人作成",
    minutes: "5–8分",
    status: "登録済み・Affiliate有効",
    why: "2026-07-26に無料アカウント、Affiliate section、紹介IDと素材の発行を確認しました。",
    steps: [
      "追加の登録操作は不要",
      "紹介IDは公開・repo保存しない",
      "rights回答と公開承認が揃うまで紹介リンクを使用しない",
    ],
    done: "2026-07-26 登録・Affiliate有効化確認済み",
    next: "rights回答をfield別に判定し、別途Affiliate decision recordを確定",
  },
  {
    id: "H5",
    timing: "完了",
    title: "SE Rankingへ個人publisher登録方法を照会",
    minutes: "2分",
    status: "送信済み・回答待ち",
    why: "登録画面はwork email必須です。カードや架空情報を使わず公式Affiliate窓口へ確認します。",
    steps: [
      "2026-07-23に公式Affiliate窓口へ送信済み",
      "公式回答が来るまでアカウント作成を再試行しない",
      "Google Workspaceとカード登録は月末まで保留",
    ],
    done: "2026-07-23 送信済み",
    next: "回答を登録可否、必要証拠、条件へ分解",
  },
  {
    id: "H6",
    timing: "今",
    title: "HubSpot Impact契約・申請",
    minutes: "10–15分",
    status: "契約同意直前",
    why: "契約checkbox、credential、本人・事業情報、申請送信は本人操作が必要です。",
    steps: [
      "保存済み契約PDFを読む",
      "同意する場合だけImpactのcheckboxとContinueを操作",
      "credential、2FA、site、集客方法を本人が入力",
      "申請内容を確認し本人が送信",
    ],
    done: "hubspot_application: submitted",
    next: "2–3営業日の審査を追跡し、結果と条件をhash-only記録へ変換",
  },
  {
    id: "H7",
    timing: "回答時",
    title: "許諾回答を最終判定",
    minutes: "1社5分",
    status: "回答待ち",
    why: "回答者の権限、条件、期限を承認記録にする判断はHuman Approver専用です。",
    steps: [
      "回答メールはGmail内に残す",
      "『○○社から回答あり』と知らせる",
      "Codexの8項目への分解案を確認",
      "approved / prohibited / unreviewedを最終承認",
    ],
    done: "会社別のapproveまたはreject",
    next: "field-level SourcePolicyを生成し、許可済みsourceだけadapterを実装",
  },
  {
    id: "H8",
    timing: "承認後",
    title: "受取・税務・本人確認",
    minutes: "1社10–20分",
    status: "後工程",
    why: "口座、税番号、本人確認情報は秘匿情報です。",
    steps: [
      "各サービス内で本人が入力",
      "値はチャットやrepoへ共有しない",
      "画面上の完了だけを知らせる",
    ],
    done: "対象サービスの設定完了通知",
    next: "支払方法、threshold、期限だけを非機密Evidenceへ反映",
  },
] as const;

export default function OperatorPage() {
  return (
    <main id="main-content" className="page-main">
      <header className="shell page-header">
        <p className="eyebrow">HUMAN-ONLY ACTIONS</p>
        <h1>あなたの操作だけ。<br />ここに残す。</h1>
        <p>
          credential、CAPTCHA、契約、税務、最終承認以外はCodexが担当します。
          秘密情報を共有せず、完了の合図だけを返せる形にしています。
        </p>
        <p>
          現在はカード不要モードです。カード登録、有料trial、課金開始は月末まで停止します。
        </p>
      </header>

      <section className="shell operator-summary" aria-labelledby="operator-summary-title">
        <div>
          <p className="eyebrow">CURRENT HANDOFF</p>
          <h2 id="operator-summary-title">カード不要の作業だけ先行</h2>
        </div>
        <dl>
          <div><dt>許諾メール</dt><dd>5件送信済み・回答待ち</dd></div>
          <div><dt>Google Ads</dt><dd>カード要求時は停止</dd></div>
          <div><dt>Affiliate</dt><dd>無料登録・照会だけ</dd></div>
        </dl>
      </section>

      <section className="shell operator-table-card" aria-labelledby="operator-table-title">
        <div className="operator-section-heading">
          <div>
            <p className="eyebrow">ACTION TABLE</p>
            <h2 id="operator-table-title">操作一覧</h2>
          </div>
          <p>申請中は承認済みに数えず、規約同意とcredentialは本人操作のまま残します。</p>
        </div>
        <div className="table-scroll" tabIndex={0} aria-label="人間操作一覧を横スクロール">
          <table className="operator-table">
            <caption>Human Approver本人が行う操作、完了条件、完了後の自動作業</caption>
            <thead>
              <tr>
                <th scope="col">ID</th>
                <th scope="col">時期 / 操作</th>
                <th scope="col">現在地</th>
                <th scope="col">所要</th>
                <th scope="col">完了の合図</th>
                <th scope="col">次の自動作業</th>
              </tr>
            </thead>
            <tbody>
              {actions.map((action) => (
                <tr key={action.id}>
                  <th scope="row"><span className="action-id">{action.id}</span></th>
                  <td><strong>{action.title}</strong><small>{action.timing}</small></td>
                  <td><span className="action-status">{action.status}</span></td>
                  <td>{action.minutes}</td>
                  <td><code>{action.done}</code></td>
                  <td>{action.next}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="shell operator-manual" aria-labelledby="operator-manual-title">
        <div className="operator-section-heading">
          <div>
            <p className="eyebrow">STEP-BY-STEP</p>
            <h2 id="operator-manual-title">画面別マニュアル</h2>
          </div>
          <p>各項目を開くと、操作順と停止理由を確認できます。</p>
        </div>
        <div className="manual-list">
          {actions.map((action) => (
            <details key={action.id} open={action.id === "H1" || action.id === "H3"}>
              <summary>
                <span>{action.id}</span>
                <strong>{action.title}</strong>
                <small>{action.status}</small>
              </summary>
              <div className="manual-body">
                <p>{action.why}</p>
                <ol>{action.steps.map((step) => <li key={step}>{step}</li>)}</ol>
                <p><b>完了後:</b> {action.next}</p>
              </div>
            </details>
          ))}
        </div>
      </section>

      <section className="shell operator-reply" aria-labelledby="reply-title">
        <div>
          <p className="eyebrow">COPY &amp; REPLY</p>
          <h2 id="reply-title">最初に返す内容</h2>
          <p>未公開ならsite URLは「未公開」で構いません。パスワードや2FAは書かないでください。</p>
        </div>
        <pre>{`legal_name_or_entity:
site_url:
human_approver_name:

google_ads: GO / STOP

mangools_terms: GO / STOP
hubspot_impact_contract: GO / STOP`}</pre>
      </section>
    </main>
  );
}
