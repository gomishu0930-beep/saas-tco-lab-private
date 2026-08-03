# 拡張カテゴリslate（準備のみ）

基準日: 2026-07-31（Asia/Tokyo）
authority: `candidate_only`
公開・申請・外部取得: `HOLD until scope_expand: GO`

これはW6のJP/ja実需要が月20万円の逆算経路へ届かない場合に備えた入力準備であり、需要が確認済みという
主張ではない。カテゴリ選定、公開、ASP申請、価格取得、CTAは開始しない。既存のrights model v2、
Human確認値・画面状態・出典URL・観測日・次回確認日、unknown保持をそのまま使う。年払いはcheckout請求総額を一次観測値、12分の1を月額派生値とするv2.2 contractに従う。

## 候補と記事構造

全カテゴリで共通する6章は、`結論 → 前提scenario → 料金と上限 → 12か月TCO → 反証 → 選び方`とする。

|category_id|対象|取引意図template|固有の比較軸|
|---|---|---|---|
|`accounting`|会計SaaS|料金・法人/事業数・取引量別TCO|法人/事業数、月間取引数、seat|
|`crm`|CRM|seat・contact・automation込みTCO|contact上限、automation addon、seat|
|`forms`|フォーム|response・storage・決済手数料込みTCO|月間response、storage、決済率|
|`email_marketing`|メール配信|contact・配信通数・超過込みTCO|登録contact、月間send、超過単価|
|`servers`|server/cloud|compute・storage・transfer・backup込みTCO|compute時間、容量、転送、backup|

## 入力contract

Pydantic正本は`CategoryExpansionInput`、生成schemaは`schemas/category-expansion-input.schema.json`。
状態は常に`candidate_only`で、scope拡大authorityを持たない。各vendor・plan行は次のfieldをexactに揃える。

### accounting

- `pricing.base_price`（price）
- `pricing.minimum_seats`（seat_count）
- `accounting.entity_count`（quota）
- `accounting.monthly_transactions`（quota）

### crm

- `pricing.base_price`（price）
- `pricing.minimum_seats`（seat_count）
- `crm.contact_count`（quota）
- `crm.automation_addon_price`（price）

### forms

- `pricing.base_price`（price）
- `forms.monthly_responses`（quota）
- `forms.storage_quota`（quota）
- `forms.payment_fee`（percentage）

### email_marketing

- `pricing.base_price`（price）
- `email.contact_count`（quota）
- `email.monthly_sends`（quota）
- `email.overage_price`（price）

### servers

- `pricing.base_price`（price）
- `servers.compute_hours`（usage）
- `servers.storage_gb`（quota）
- `servers.data_transfer_gb`（quota）
- `servers.backup_price`（price）

## Human scenario

vendor観測とは別に、既存P01/P07/P09/P11のHuman scenario contractで人数、月間利用量、移行時間、
社内時間単価を入力する。公式価格から補完しない。カテゴリinputへHuman scenarioを混ぜず、TCO計算時に
明示的に結合する。

## 再開条件

1. 2026-10-31の90日判定で拡張条件を満たす、または需要不足に対するHuman判断を行う。
2. `scope_expand: GO`を受領する。
3. 対象カテゴリ、記事本数、ASP/partner、Human予算を既存launch lane内で確定する。

GO前はschema・templateのlocal検証だけを許可する。
