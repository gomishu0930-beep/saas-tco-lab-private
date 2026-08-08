import type { PilotPage } from "./pilot-pages";

export type ArticleDraftSection = {
  title: string;
  body: string;
};

export type ArticleDraft = {
  priority: "first" | "standard";
  sections: readonly ArticleDraftSection[];
  reviewVoices: readonly ["analyst", "editor", "skeptical_buyer"];
};

const sourceBlock =
  "掲載した数値には、公式ページ、確認日、次回確認日を付ける。確認できない費用は「未確認」として計算から外し、0円とは扱わない。";

const drafts: Readonly<Record<PilotPage["id"], ArticleDraft>> = {
  P01: {
    priority: "first",
    reviewVoices: ["analyst", "editor", "skeptical_buyer"],
    sections: [
      { title: "判断の要点", body: "確認済みの年額を初年度費用の基準にする。月額換算は比較用に分け、確認できない追加費用は合計へ入れない。" },
      { title: "今回の利用条件", body: "利用者{{contract:scenario.seat_count.value}}、月間利用量{{contract:scenario.monthly_usage.value}}を今回の試算条件にする。人数や利用量が異なる場合は計算機で変更できるが、公式画面で確認した元の金額は変えない。" },
      { title: "料金と利用上限", body: "年払いでは実際に請求される12か月分の総額を使う。料金表にある月あたりの表示は、年額そのものとして扱わない。" },
      { title: "12か月の支払額", body: "12か月分の請求総額をそのまま示し、12で正確に割れる場合だけ月あたりの参考額を表示する。年払いの割引率は、同じ条件の月払い価格と比較できる場合だけ示す。" },
      { title: "購入前の注意", body: "税、上限超過時の扱い、最低契約期間、必須の追加機能を確認する。確認できない項目がある場合は、その分を含む総額を断定しない。" },
      { title: "出典と更新", body: sourceBlock },
    ],
  },
  P02: {
    priority: "first",
    reviewVoices: ["analyst", "editor", "skeptical_buyer"],
    sections: [
      { title: "判断の要点", body: "安いプランを選ぶ前に、必要な利用者数とキーワード調査回数を満たすか確認する。条件を満たさないプランは価格比較から外す。" },
      { title: "比較条件", body: "利用地域、通貨、税、契約期間、必要な利用者数、利用量を全プランでそろえる。条件をそろえられない金額は、単純な差額にしない。" },
      { title: "料金と利用上限", body: "各プランの料金、最低利用者数、キーワード調査回数、上限超過時の扱いを並べる。年払いは12か月分の請求総額と、月あたりの参考額を分けて示す。" },
      { title: "12か月で比べる", body: "年払いの請求総額、月あたりの参考額、同条件の月払い価格、年払いによる差額を分けて確認する。最低利用者数が未確認のプランには適合順位を付けない。" },
      { title: "比較を誤らせる条件", body: "初回限定価格、期間限定キャンペーン、最低利用者数、上限超過時の課金が順位を変えないか確認する。終了日がある価格は通常価格として扱わない。" },
      { title: "出典と更新", body: sourceBlock },
    ],
  },
  P03: {
    priority: "first",
    reviewVoices: ["analyst", "editor", "skeptical_buyer"],
    sections: [
      { title: "判断の要点", body: "代替サービスは安さだけで選ばず、必要機能、利用上限、追加機能、移行負担を満たすものへ絞る。年額が未確認の候補には価格順位を付けない。" },
      { title: "置き換え条件", body: "現在必要な機能、利用量、担当者、移行期限を先に整理する。候補ごとに条件を変えず、満たせない要件を価格より先に確認する。" },
      { title: "料金と利用上限", body: "候補ごとの料金、追跡できるキーワード数、対象サイト数、必須の追加料金を分けて見る。名称が似た機能でも、上限や課金単位が同じとは限らない。" },
      { title: "12か月で比べる", body: "Mangools Basicは確認済みの年額を示す。SE RankingとSemrushは12か月分の請求総額が未確認のため、横断的な価格順位から外す。移行や教育の未確認費用を0円として加えない。" },
      { title: "乗り換え前の注意", body: "移行できないデータ、権限の違い、サポート条件、解約制約を確認する。公式説明が曖昧な機能は、同等だと断定しない。" },
      { title: "出典と更新", body: sourceBlock },
    ],
  },
  P04: {
    priority: "standard",
    reviewVoices: ["analyst", "editor", "skeptical_buyer"],
    sections: [
      { title: "判断の要点", body: "小規模チームでは最低利用者数と運用時間が固定費を左右する。{{contract:team.minimum_seats.value}}が実人数を超える場合は、使わない人数分も含めて判断する。" },
      { title: "今回の利用条件", body: "担当人数、利用頻度、導入時と日常運用の役割を分ける。兼任作業も無料とはみなさず、確認できた時間だけを試算に使う。" },
      { title: "料金と利用上限", body: "{{contract:team.monthly_price.value}}と最低利用者数を一緒に確認する。無料枠や初回限定価格は通常月の費用へ混ぜない。" },
      { title: "12か月で考える", body: "契約費用とは別に、毎月の運用時間{{contract:team.monthly_operation_hours.value}}と導入時間{{contract:team.onboarding_hours.value}}を示す。時間単価がなければ金額へ換算しない。" },
      { title: "少人数でも残る負担", body: "管理、請求、権限設定の作業が少人数でも残る可能性を確認する。公式情報にない導入時間を体験談だけで補わない。" },
      { title: "出典と更新", body: sourceBlock },
    ],
  },
  P05: {
    priority: "standard",
    reviewVoices: ["analyst", "editor", "skeptical_buyer"],
    sections: [
      { title: "判断の要点", body: "組織利用では管理・監査・移行支援を基本料金と分けて確認する。必要な機能が個別見積もりなら、公開価格だけで総額を決めない。" },
      { title: "組織の条件", body: "利用人数、権限の階層、監査要件、移行支援の必要性を整理する。セキュリティ要件は金額とは別の必須条件として確認する。" },
      { title: "料金と利用上限", body: "含まれる管理者数{{contract:enterprise.included_manager_seats.value}}、Agency Pack料金{{contract:enterprise.agency_pack_price.value}}、毎月の監査ページ上限{{contract:enterprise.audit_pages_per_month.value}}を個別に確認する。" },
      { title: "12か月で考える", body: "契約費用とは別に移行支援費{{contract:enterprise.migration_support_price.value}}を加える。個別見積もりの項目は、金額が分かるまで未確認のまま残す。" },
      { title: "契約前の注意", body: "最低契約額、導入支援の必須条件、監査機能を使えるプラン、追加利用者の条件を確認する。営業資料だけを料金の根拠にしない。" },
      { title: "出典と更新", body: sourceBlock },
    ],
  },
  P06: {
    priority: "standard",
    reviewVoices: ["analyst", "editor", "skeptical_buyer"],
    sections: [
      { title: "判断の要点", body: "年払いの割引と、途中で利用をやめても残る負担を分けて判断する。請求単位が違う金額は、そのまま差し引かない。" },
      { title: "利用期間を決める", body: "利用開始日、使う予定の期間、支払周期、途中解約の可能性を整理する。継続期間が読めない場合は、月払いの柔軟性も判断材料にする。" },
      { title: "月払いと年払い", body: "月払い{{contract:billing.monthly_contract_price.value}}と年払い{{contract:billing.annual_contract_price.value}}を、通貨と税条件をそろえて比べる。終了日のない年払い割引であることを確認できた場合だけ、月払い12回との差を表示する。" },
      { title: "12か月で比べる", body: "最低契約期間{{contract:billing.minimum_commitment_months.value}}と解約時の費用{{contract:billing.termination_cost.value}}を確認し、利用停止後にも残る支払いがあれば含める。" },
      { title: "契約前の注意", body: "自動更新、返金の可否、割引終了、契約途中の利用人数変更を確認する。公式説明にない解約費用は加えない。" },
      { title: "出典と更新", body: sourceBlock },
    ],
  },
  P07: {
    priority: "standard",
    reviewVoices: ["analyst", "editor", "skeptical_buyer"],
    sections: [
      { title: "判断の要点", body: "上限超過時の追加費用は、含まれる利用量、追加単位、単価、実際の利用量がそろった時だけ計算する。未確認項目を0円とはみなさない。" },
      { title: "利用量を分ける", body: "通常月と繁忙月の利用量を分け、同じ単位で比べる。未使用分の繰越やチーム内共有がある場合は、公式条件を確認する。" },
      { title: "上限と追加料金", body: "含まれる利用量{{contract:usage.included_quota.value}}、追加課金の単位{{contract:usage.overage_unit_size.value}}、追加単価{{contract:usage.overage_price.value}}を並べる。" },
      { title: "利用量から試算する", body: "月間利用量{{contract:usage.monthly_volume.value}}が上限を超える期間だけ追加費用を計算する。丸め方と最低課金単位は、公式記載がある場合だけ適用する。" },
      { title: "上限到達時の注意", body: "上限を超えた時に自動課金されるのか、利用が止まるのか、通知や自動アップグレードがあるのかを確認する。不明な動作は計算から外す。" },
      { title: "出典と更新", body: sourceBlock },
    ],
  },
  P08: {
    priority: "standard",
    reviewVoices: ["analyst", "editor", "skeptical_buyer"],
    sections: [
      { title: "判断の要点", body: "業務に必要な追加機能を外し、基本料金だけで比較しない。必須機能は最初から総費用へ含める。" },
      { title: "必要機能を分ける", body: "必要な機能、対象となる利用者数、課金単位、利用期間を整理し、任意機能と必須機能を分ける。" },
      { title: "基本料金と追加料金", body: "基本料金{{contract:addon.base_price.value}}、追加機能の料金{{contract:addon.price.value}}、課金単位{{contract:addon.billing_unit_size.value}}を別々に確認する。" },
      { title: "12か月で考える", body: "必要な利用者数{{contract:addon.required_seats.value}}へ適用される追加機能だけを合計する。組織一括か利用者ごとか不明なら総額を出さない。" },
      { title: "重複課金の注意", body: "上位プランに同じ機能が含まれていないか、最低購入数や途中追加の請求条件がないか確認する。機能一覧だけから価格を補わない。" },
      { title: "出典と更新", body: sourceBlock },
    ],
  },
  P09: {
    priority: "standard",
    reviewVoices: ["analyst", "editor", "skeptical_buyer"],
    sections: [
      { title: "判断の要点", body: "移行費用は契約料金と分け、重複契約、作業、教育、外部支援を確認できた分だけ積み上げる。" },
      { title: "移行範囲を決める", body: "移すデータ、担当者、並行稼働の期間、教育範囲を整理する。社内作業時間は公式料金と混ぜず、自社の試算として分ける。" },
      { title: "移行に必要な時間", body: "重複契約{{contract:migration.overlap_months.value}}、移行作業{{contract:migration.work_hours.value}}、教育{{contract:migration.training_hours.value}}を個別に示す。" },
      { title: "初年度費用へ加える", body: "作業費には時間単価{{contract:migration.hourly_cost.value}}、外部支援には支援費{{contract:migration.support_price.value}}を使う。未確認項目は0円に置き換えない。" },
      { title: "移行前の注意", body: "データ出力の制限、再設定、停止時間、旧契約の解約条件を確認する。経験則だけの作業時間を確定費用として扱わない。" },
      { title: "出典と更新", body: sourceBlock },
    ],
  },
  P10: {
    priority: "standard",
    reviewVoices: ["analyst", "editor", "skeptical_buyer"],
    sections: [
      { title: "判断の要点", body: "表示通貨、税込・税別、換算日を分けて確認する。未確認の税や通貨を補って総額を作らない。" },
      { title: "日本から見た条件", body: "請求先の地域、画面の表示通貨、税の扱いを確認する。地域を変えると価格が変わる場合は、確認した状態と日付を残す。" },
      { title: "表示価格と税", body: "画面の価格{{contract:localization.displayed_price.value}}と税率{{contract:localization.tax_rate.value}}を別々に確認する。税込か税別か不明な金額は合計に使わない。" },
      { title: "円換算するとき", body: "換算が必要な場合だけ、換算レート{{contract:localization.exchange_rate.value}}と確認日を使う。将来のレートや税率を予測して入れない。" },
      { title: "決済時の注意", body: "カード会社の手数料、海外取引、税登録状態など公開価格に含まれない条件は、根拠がなければ計算外と明記する。" },
      { title: "出典と更新", body: sourceBlock },
    ],
  },
  P11: {
    priority: "standard",
    reviewVoices: ["analyst", "editor", "skeptical_buyer"],
    sections: [
      { title: "判断の要点", body: "削減できる時間を自動的な利益とはみなさず、実際に確認した時間と費用だけで損益分岐を示す。" },
      { title: "対象業務を決める", body: "対象業務、現在の作業時間、導入後の作業時間、担当者の時間単価を整理する。未観測の削減時間は期待値として表示しない。" },
      { title: "時間の価値", body: "月間削減時間{{contract:break_even.monthly_hours_saved.value}}と時間単価{{contract:break_even.hourly_cost.value}}を別の根拠として確認する。" },
      { title: "費用と便益を比べる", body: "導入費{{contract:break_even.implementation_cost.value}}と月額総費用{{contract:break_even.monthly_tco.value}}を費用側へ置き、便益が上回る条件を計算機で示す。" },
      { title: "効果を過大評価しない", body: "削減時間を別業務へ使えない場合、定着に時間がかかる場合、利用量が増える場合も確認する。販売資料の効果を自社実績へ置き換えない。" },
      { title: "出典と更新", body: sourceBlock },
    ],
  },
  P12: {
    priority: "standard",
    reviewVoices: ["analyst", "editor", "skeptical_buyer"],
    sections: [
      { title: "判断の要点", body: "読者が各数値の出典と新しさを確認できるようにする。根拠がない数値は比較や計算から外す。" },
      { title: "確認時に残すもの", body: "正規の公開画面で値を確認し、公式ページ、確認日、次回確認日を同時に記録する。画面にない情報は補わない。" },
      { title: "数値の読み方", body: "単位、通貨、請求周期、税込・税別を明示する。複数の公式情報が食い違う場合は、解消するまで未確認として扱う。" },
      { title: "計算とのつながり", body: "計算機には確認済みの値だけを入れ、入力値と計算結果を分けて表示する。本文に別の手計算結果を置かない。" },
      { title: "更新のタイミング", body: "確認間隔{{contract:evidence.review_interval_days.value}}以内でも、価格や条件が変わった場合は期限前に再確認する。期限を過ぎた数値は再確認まで計算から外す。" },
      { title: "出典と更新", body: sourceBlock },
    ],
  },
};

export function articleDraft(page: PilotPage): ArticleDraft {
  return drafts[page.id];
}
