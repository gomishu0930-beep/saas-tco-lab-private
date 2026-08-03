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
  "各fieldはvendor・plan、値、toggle位置、価格表示分類、出典URL、観測日、次回日を同じ行に表示する。Human scenarioはvendor行と分離する。期限切れ、未入力、未承認、計算不能なunknownを推測で補わない。";

const drafts: Readonly<Record<PilotPage["id"], ArticleDraft>> = {
  P01: {
    priority: "first",
    reviewVoices: ["analyst", "editor", "skeptical_buyer"],
    sections: [
      { title: "結論", body: "年次checkout総額を12か月TCOの一次値とし、Basic 1ユーザー・月400 lookupに当てはめる。月額換算と年払い差は派生値、未確認費用は計算外とする。" },
      { title: "前提scenario", body: "利用地域、通貨、請求周期、税区分はvendor・plan行、seatと利用量はHuman scenario行から読み込む。読者の条件が異なる場合は計算機で差し替え、元の観測値を上書きしない。" },
      { title: "料金と上限", body: "基本料金と超過単価は、vendor・plan、billing toggle位置、価格表示分類、表示単位、通貨状態、課金周期を隣接表示する。年払いplanはcheckout請求総額を一次観測値とし、料金表の月額表示を一次値へ置き換えない。" },
      { title: "対象期間TCO", body: "TCO表は年次checkout総額を一次値にする。月額換算は最小通貨単位で12分割できる時だけ、年払い差は同じplan・通貨・税条件の月払い価格×12と比較できる時だけ表示する。" },
      { title: "反証と注意点", body: "税区分、超過条件、最低契約、必須addonのどれかが未確認なら総額を確定しない。公式画面の地域・請求周期が読者条件と違う場合も比較対象外とする。" },
      { title: "出典と更新", body: sourceBlock },
    ],
  },
  P02: {
    priority: "first",
    reviewVoices: ["analyst", "editor", "skeptical_buyer"],
    sections: [
      { title: "結論", body: "プラン名だけでなく、下表の料金、最低seat数、利用上限をvendor・plan行ごとに同じscenarioへ置いて選ぶ。必要条件を満たさないプランは価格が低くても候補から外す。" },
      { title: "前提scenario", body: "地域、通貨、税、契約期間、必要seat、利用量を先に固定する。各プランへ同じ入力を適用できない場合は横並びの差額を出さない。" },
      { title: "料金と上限", body: "各plan料金、最低seat、利用上限、超過単価をcontract参照で並べる。billing toggle位置と価格表示分類を併記し、年払いはcheckout請求総額を一次観測値、12分の1を月額派生値として分離する。" },
      { title: "対象期間TCO", body: "3プランの年次checkout請求総額、請求上の月額換算、同条件の月払い比較値、年払い差を同じ表へ分離する。最低seat数がunknownのplanには適合順位を付けないが、確認済み支払総額は表示する。" },
      { title: "反証と注意点", body: "年払い表示、初回割引、最低seat、超過課金が比較結果を逆転させないか確認する。期間限定表示は恒常価格として扱わない。" },
      { title: "出典と更新", body: sourceBlock },
    ],
  },
  P03: {
    priority: "first",
    reviewVoices: ["analyst", "editor", "skeptical_buyer"],
    sections: [
      { title: "結論", body: "代替候補は安さではなく、必要機能、利用上限、addon、移行負担を満たすものだけ残す。下表で料金または通貨がunknownのvendor・plan行には価格順位を付けない。" },
      { title: "前提scenario", body: "置き換え前の必須機能、利用量、運用担当、移行期限を言語化する。候補ごとに条件を変えず、満たせない要件を先に表示する。" },
      { title: "料金と上限", body: "候補料金、追跡keyword数、domain上限、必須addon料金をvendor・plan行ごとに並べる。年払いはcheckout請求総額を一次観測値、12分の1を月額派生値として表示し、billing toggle位置、価格表示分類、税区分を隣接させる。機能名が似ていても上限や課金単位を同一と推測しない。" },
      { title: "対象期間TCO", body: "Mangools Basicの確認済み年次checkout総額だけを表示し、SE RankingとSemrushはcheckout総額がunknownのため横断価格順位から外す。移行費用、重複契約、教育のunknownはゼロとして混ぜず計算外へ分離する。" },
      { title: "反証と注意点", body: "移行できないデータ、権限差、サポート条件、解約制約が候補を失格にしないか確認する。公式説明が曖昧なら同等機能と断定しない。" },
      { title: "出典と更新", body: sourceBlock },
    ],
  },
  P04: {
    priority: "standard",
    reviewVoices: ["analyst", "editor", "skeptical_buyer"],
    sections: [
      { title: "結論", body: "小規模チームでは最低seatと運用時間が固定費を左右する。{{contract:team.minimum_seats.value}}が実人数を超える場合は、未使用seatを含む総額で判断する。" },
      { title: "前提scenario", body: "担当人数、利用頻度、導入と定常運用の役割を分ける。兼任作業は無償とせず、時間はcontract値がある場合だけ計算へ入れる。" },
      { title: "料金と上限", body: "{{contract:team.monthly_price.value}}と最低seatを同時に表示し、無料枠や初回割引を恒常費用へ混ぜない。" },
      { title: "対象期間TCO", body: "契約費用へ{{contract:team.monthly_operation_hours.value}}と{{contract:team.onboarding_hours.value}}を別項目で加える。時間単価がない場合は金額換算せず時間のまま示す。" },
      { title: "反証と注意点", body: "少人数でも管理、請求、権限設定が減らない可能性を確認する。導入時間が公式に示されない場合は体験談から補完しない。" },
      { title: "出典と更新", body: sourceBlock },
    ],
  },
  P05: {
    priority: "standard",
    reviewVoices: ["analyst", "editor", "skeptical_buyer"],
    sections: [
      { title: "結論", body: "組織利用では管理・監査・導入支援を基本プランと分けて確認する。必要機能が見積依頼のみなら、公開価格だけで総額を確定しない。" },
      { title: "前提scenario", body: "組織人数、権限階層、監査要件、導入支援の必要性を固定する。セキュリティ要件は価格fieldと別の適合条件として扱う。" },
      { title: "料金と上限", body: "{{contract:enterprise.minimum_seats.value}}、{{contract:enterprise.admin_feature_price.value}}、{{contract:enterprise.audit_addon_price.value}}を個別に表示する。bundle込みと別料金を推測で統合しない。" },
      { title: "対象期間TCO", body: "契約費用へ{{contract:enterprise.onboarding_support_price.value}}を加え、見積値がない項目はunknownとして残す。非公開見積を記事へ転記しない。" },
      { title: "反証と注意点", body: "契約最低額、導入支援必須、監査機能の対象plan、追加seat条件を確認する。営業資料だけの主張は公開料金の根拠にしない。" },
      { title: "出典と更新", body: sourceBlock },
    ],
  },
  P06: {
    priority: "standard",
    reviewVoices: ["analyst", "editor", "skeptical_buyer"],
    sections: [
      { title: "結論", body: "年契約の表示上の割引と、途中解約できない負担を分けて判断する。月契約と年契約の請求単位が一致しない場合は単純差額を出さない。" },
      { title: "前提scenario", body: "利用開始日、想定利用期間、支払周期、解約可能性を固定する。期間が不確実なら短い契約を選ぶ価値も金額外の条件として示す。" },
      { title: "料金と上限", body: "{{contract:billing.monthly_contract_price.value}}と{{contract:billing.annual_contract_price.value}}を請求周期・税区分付きで表示する。annual_discount_permanentかつ同一通貨・同一税条件のHuman確認済み月払い価格と年次checkout総額がそろう場合だけ、1−年次総額÷（月払い価格×12）を「年払いは月払い比で約N%割安」と記載する。" },
      { title: "対象期間TCO", body: "{{contract:billing.minimum_commitment_months.value}}と{{contract:billing.termination_cost.value}}を使い、利用停止後も残る支払いを対象期間へ含める。" },
      { title: "反証と注意点", body: "自動更新、返金不可、割引終了、契約途中のseat変更条件を確認する。規約にない解約費用を推測しない。" },
      { title: "出典と更新", body: sourceBlock },
    ],
  },
  P07: {
    priority: "standard",
    reviewVoices: ["analyst", "editor", "skeptical_buyer"],
    sections: [
      { title: "結論", body: "従量超過は含有量、超過単位、単価、実利用量がそろった時だけ計算する。どれかがunknownなら超過なしと仮定しない。" },
      { title: "前提scenario", body: "通常月と繁忙時の利用量を分け、同じ測定単位へそろえる。繰越や共有枠がある場合は公式条件を別fieldで確認する。" },
      { title: "料金と上限", body: "{{contract:usage.included_quota.value}}、{{contract:usage.overage_unit_size.value}}、{{contract:usage.overage_price.value}}を隣接表示する。" },
      { title: "対象期間TCO", body: "{{contract:usage.monthly_volume.value}}が含有量を超える期間だけ増分を計算する。丸め単位と最低課金単位は公式記載がある場合だけ適用する。" },
      { title: "反証と注意点", body: "超過時に自動課金か利用停止か、通知があるか、上位planへ自動変更されるかを確認する。動作不明は価格計算から除外する。" },
      { title: "出典と更新", body: sourceBlock },
    ],
  },
  P08: {
    priority: "standard",
    reviewVoices: ["analyst", "editor", "skeptical_buyer"],
    sections: [
      { title: "結論", body: "必要なaddonを外した基本料金だけで比較しない。業務要件に必須の機能は最初から実効総額へ含める。" },
      { title: "前提scenario", body: "必要機能、対象seat、課金単位、利用期間を固定し、任意addonと必須addonを分ける。" },
      { title: "料金と上限", body: "{{contract:addon.base_price.value}}、{{contract:addon.price.value}}、{{contract:addon.billing_unit_size.value}}をcontractから表示する。" },
      { title: "対象期間TCO", body: "{{contract:addon.required_seats.value}}へ適用されるaddonだけを加算する。組織一括課金かseat課金か不明なら合計しない。" },
      { title: "反証と注意点", body: "上位planに内包される場合、重複購入、最低数量、途中追加の請求条件を確認する。機能一覧だけから価格を推測しない。" },
      { title: "出典と更新", body: sourceBlock },
    ],
  },
  P09: {
    priority: "standard",
    reviewVoices: ["analyst", "editor", "skeptical_buyer"],
    sections: [
      { title: "結論", body: "移行費用は契約料金と分け、重複契約、作業、教育、支援を確認済みfieldだけで積み上げる。" },
      { title: "前提scenario", body: "移行対象、担当者、並行稼働、教育範囲を固定する。社内時間は観測またはHuman見積として区別し、vendor価格と混ぜない。" },
      { title: "料金と上限", body: "{{contract:migration.overlap_months.value}}、{{contract:migration.work_hours.value}}、{{contract:migration.training_hours.value}}を個別表示する。" },
      { title: "対象期間TCO", body: "作業費は{{contract:migration.hourly_cost.value}}、外部支援は{{contract:migration.support_price.value}}を使い、未確認項目をゼロに置換しない。" },
      { title: "反証と注意点", body: "データexport制限、再設定、停止時間、旧契約の解約条件が追加負担にならないか確認する。経験則だけの工数は公式価格として扱わない。" },
      { title: "出典と更新", body: sourceBlock },
    ],
  },
  P10: {
    priority: "standard",
    reviewVoices: ["analyst", "editor", "skeptical_buyer"],
    sections: [
      { title: "結論", body: "表示通貨、税の内外、換算時点を分けて確認し、unknownの税や通貨を総額へ補完しない。" },
      { title: "前提scenario", body: "対象地域、請求先、表示通貨、税区分を固定する。地域選択前後で画面表示が変わる場合は観測条件を出典と一緒に残す。" },
      { title: "料金と上限", body: "{{contract:localization.displayed_price.value}}と{{contract:localization.tax_rate.value}}を公式表示どおり別fieldで記録する。" },
      { title: "対象期間TCO", body: "換算が必要な場合だけ{{contract:localization.exchange_rate.value}}と観測日を使う。将来の換算レートや税率を推測しない。" },
      { title: "反証と注意点", body: "カード会社手数料、海外取引、税登録状態など公開価格外の条件は、根拠がなければ計算外と明示する。" },
      { title: "出典と更新", body: sourceBlock },
    ],
  },
  P11: {
    priority: "standard",
    reviewVoices: ["analyst", "editor", "skeptical_buyer"],
    sections: [
      { title: "結論", body: "損益分岐は削減時間を便益として自動確定せず、Human確認した時間と費用だけで条件式を示す。" },
      { title: "前提scenario", body: "対象業務、現在工数、導入後工数、担当者の時間単価を固定する。削減時間が未観測なら期待値と表示しない。" },
      { title: "料金と上限", body: "{{contract:break_even.monthly_hours_saved.value}}と{{contract:break_even.hourly_cost.value}}を別の根拠として記録する。" },
      { title: "対象期間TCO", body: "{{contract:break_even.implementation_cost.value}}と{{contract:break_even.monthly_tco.value}}を費用側へ置き、便益が費用を上回る入力条件を計算機で示す。" },
      { title: "反証と注意点", body: "削減時間が他業務へ転用されない、定着に時間がかかる、利用量が増える可能性を確認する。販売資料の効果を自社実績へ置換しない。" },
      { title: "出典と更新", body: sourceBlock },
    ],
  },
  P12: {
    priority: "standard",
    reviewVoices: ["analyst", "editor", "skeptical_buyer"],
    sections: [
      { title: "結論", body: "読者が各数値の出典と鮮度を追えることを、比較結果より先に保証する。根拠がないfieldは記事から外す。" },
      { title: "前提scenario", body: "Humanが正規の公開画面を確認し、値、URL、観測日、次回確認日を同時に記録する。自動取得権とは別のeditorial pathとして扱う。" },
      { title: "料金と上限", body: "数値の単位、通貨、請求周期、税区分を明示し、画面にない情報を補完しない。複数sourceが矛盾する場合は解消までunknownとする。" },
      { title: "対象期間TCO", body: "計算機は承認済みcontract値だけを受け取り、入力値と計算結果を区別する。本文に手計算の別結果を置かない。" },
      { title: "反証と注意点", body: "{{contract:evidence.review_interval_days.value}}以内でも、価格改定や条件変更を検知した場合は期限前に再確認する。期限切れは自動的に非表示候補とする。" },
      { title: "出典と更新", body: sourceBlock },
    ],
  },
};

export function articleDraft(page: PilotPage): ArticleDraft {
  return drafts[page.id];
}
