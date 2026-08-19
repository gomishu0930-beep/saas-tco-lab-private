# 拡張カテゴリslate（Q7 / X1–X2、準備のみ）

基準日: 2026-08-05（Asia/Tokyo）

authority: `candidate_only`

準備scope: `GO — scope_expand: GO (2026-08-05)`

公開・ASP申請・新vendor照会・価格取得・CTA: `HOLD — each requires a separate GO`

## 決定根拠と境界

W6のHuman export実測は150 query中known 34、no_data 116、rejected 0、known月間検索量合計9,610、
no_data率0.77333333だった。月20万円の既定逆算22,227 sessions/月に対し、known下限は43.24%である。
no_dataを0として扱えないため「総需要不足の確定」ではないが、現ニッチの追加測定と隣接カテゴリの準備を
前倒しする根拠にはなる。2026-08-05にHuman Approver `omishu`が準備scopeだけを承認した。

このGOはquery slate、ASP確認表、TCO適合判定、記事templateのlocal準備に限る。公開、index、ASP申請、
program提携、新vendor照会、価格観測、Affiliate CTA、KWFinder画面操作を代行する権限は含まない。
需要値が未観測のカテゴリを「需要あり」と記載しない。

## X1 — 現ニッチuniverse v2 extension

既存v1の150語は上書きせず、完全に別の追加60語として凍結する。カテゴリ語30、比較語30で、v1との
正規化query重複は0件である。

|slate_id|file|件数|intent|frozen SHA-256|
|---|---|---:|---|---|
|`seo_tools_v2_extension`|`examples/jp_ja_keyword_universe_v2_seo_extension.csv`|60|category 30 / comparison 30|`4e1930a108569222ff91afcc0d5aecc716765514d3ae3a769b0cfa86028a7b7d`|

この60語は追加測定用であり、v1の9,610へ測定前に加算しない。語句を変更する場合は同じファイルを
書き換えず、新versionとして凍結し直す。

## X2 — 5カテゴリの凍結query slate

各カテゴリ40語を、category / comparison / pricing / fit各10語で固定した。brand queryは新vendor選定を
先取りするため含めない。6 slate全体260語で相互重複0件である。

|category_id|file|件数|frozen SHA-256|
|---|---|---:|---|
|`servers`|`examples/jp_ja_keyword_slate_v2_servers.csv`|40|`a826707c61169a9efebc3bb4838cee624035d04f19b98b52d508a0c96f9e8ee1`|
|`accounting`|`examples/jp_ja_keyword_slate_v2_accounting.csv`|40|`9bc33b2c63c31f5d22a67cfa2f52bf7e1ef36e36b586bddfe4030c1102907c4e`|
|`crm`|`examples/jp_ja_keyword_slate_v2_crm.csv`|40|`b7bcc093aa85bda86d16a915dd83f5f1a50993afb6a429d71a2f28c0d98ceca3`|
|`forms`|`examples/jp_ja_keyword_slate_v2_forms.csv`|40|`2ea8dacda2813cbf1752b9886a1888e226acb50b763571a0976c436175b0f68d`|
|`email_marketing`|`examples/jp_ja_keyword_slate_v2_email_marketing.csv`|40|`1cd09f8281e0227b9e614f7da6b65a763c83920fcec434402f9bab6105539219`|

### Human export前のlocal検証

現ニッチextension:

```bash
uv run saas-preflight validate-keyword-universe \
  examples/jp_ja_keyword_universe_v2_seo_extension.csv \
  --minimum-keywords 50 --maximum-keywords 100
```

カテゴリslateは対象ファイルごとに次を実行する。

```bash
uv run saas-preflight validate-keyword-universe \
  examples/jp_ja_keyword_slate_v2_<category>.csv \
  --minimum-keywords 30 --maximum-keywords 50
```

HumanはKWFinder正規画面でlocation=`Japan`をread-backしてから、1 slateずつexportする。raw CSV、
query別volume、Mangools固有IDはrepositoryへ保存しない。v1.1の150語専用需要validatorへ40語・60語を
偽装して投入しない。2026-08-06のHuman指示によるexport開始後、複数CSVを1つの凍結slateとして完全一致
検証する`validate-mangools-slate-export`を追加した。1行でも欠落・重複・対象外queryがあればsafe-summaryを
出さず、完全一致時だけhashと集計値を保存する。

### 2026-08-06 実測進捗

|category|取得行|safe-summary|known / no_data / rejected|known合計 / no_data率|判断|
|---|---:|---|---|---|---|
|servers|40 / 40|`artifacts/editorial-inputs/demand-safe-summaries/servers-2026-08-06.json`|14 / 26 / 0|28,220 / 0.65000000|必要22,227のknown下限は超えるが、拡張目安5万未満。候補維持|
|accounting|40 / 40|本表（P18固定scope維持のため新規artifactなし）|9 / 31 / 0|6,320 / 0.77500000|known下限は必要22,227を下回り、no_data率も高い。現時点では拡張しない|
|crm|40 / 40|本表（P18固定scope維持のため新規artifactなし）|8 / 32 / 0|5,530 / 0.80000000|known下限は必要22,227未満。no_data率80%のため不足確定ではないが、新規投資はHOLD|
|forms|40 / 40|本表（P18固定scope維持のため新規artifactなし）|4 / 36 / 0|490 / 0.90000000|known下限は必要22,227未満。no_data率90%のため不足確定ではないが、新規投資はHOLD|
|email_marketing|40 / 40|本表（P18固定scope維持のため新規artifactなし）|5 / 35 / 0|470 / 0.87500000|known下限は必要22,227未満。no_data率87.5%のため不足確定ではないが、新規投資はHOLD|
|seo_tools_v2_extension|60 / 60|本表（P18固定scope維持のため新規artifactなし）|1 / 59 / 0|10 / 0.98333333|既存SEOニッチへの追加known下限は小さい。no_data率98.33%のため不足確定ではないが、追加投資はHOLD|

serversの`volume_floor_met_not_proven`は、known行だけで月20万円逆算の必要sessionを超えたという下限判定で
あり、売上達成・総需要・カテゴリ採用の確定ではない。no_dataは0へ置換していない。残りslateはKWFinderの
検索回数カウンター回復後に再開し、部分CSVの集計値はrepositoryへ保存しない。

2026-08-11、未取得語を手入力せず正規画面へ渡せるよう、凍結slateのexact sliceをquery-only textへ
生成する`prepare-kwfinder-upload`を追加した。当初CRM残り10は`--start-index 30 --limit 10`、formsと
email marketingは`--start-index 0 --limit 40`、SEO追加は`--start-index 0 --limit 60`を使う。
出力は固定scope外の`outputs/`へ置き、元slateとの完全一致・重複0・範囲外拒否をtestで固定する。
これはHuman export用の入力補助であり、需要値、query別volume、取得済み判定、外部取得権限を含まない。
KWFinderのProcessとCSV exportは引き続きHumanが正規画面で行い、完全なcategory CSVだけを行単位validatorへ渡す。

2026-08-12、Downloads内のCRM既存CSVを凍結slateへ再照合したところ、完全一致要件を満たさなかった。
取得済み30語という進捗を撤回し、`--start-index 0 --limit 40`で`outputs/kwfinder_crm_40.txt`を再生成した。
残るHuman exportはCRM 40、forms 40、email marketing 40、SEO追加60の計180語である。これはquery集合の
整合性監査であり、部分volumeやquery別値を需要判断へ採用しない。

4件のexport後は`validate-mangools-expansion-set`で一括受入する。各slateの既存validatorを順に通し、
4件すべてが完全な場合だけ`MangoolsExpansionSetSafeSummary`を構築する。envelopeは4つのsafe-summary、
合計180行のknown / no_data / rejected件数、known合計、hash、観測窓だけを含む。rawとquery値は保存せず、
途中失敗時はenvelope自体を出さない。

## 2026-08-06 category primary decision

Human Approver `omishu`の`category_primary: GO servers`により、新規投資の第一カテゴリをserversへ固定する。
公開可能な需要証拠はknown 28,220/月、14/40 known、no_data率65%である。A8.net管理画面で確認された
XServerビジネスの成果報酬・確定率と、それらから逆算できる成約数・sessionsは
`restricted_dashboard_only`であり、値をrepositoryへ保存しない。選定はHuman decisionとして有効だが、
売上達成、Affiliate承認、個別queryの需要順位を意味しない。

|姿勢|実施案|Hard gate|停止条件|
|---|---|---|---|
|conservative|6記事slateとHuman価格確認checklistだけを準備|価格未観測・提携未承認のため公開とCTA不可|公式料金fieldを同一条件で観測できない|
|balanced|Y1–Y3をlocal candidateとして実装し、価格観測後に記事ごとHuman review|公開・index・XServer CTA・提携申請は別GO|golden不一致、unknownの0補完、需要または提携の否定証拠|
|aggressive|価格観測前に6記事公開しXServer CTAを有効化|証拠・提携・公開gate未成立で`ineligible`|現時点で開始しない|

採用は`balanced`である。これはlocal準備の実行方針であり、外部申請、価格取得、記事承認、公開、index、
Affiliate CTAの権限を付与しない。confirmed EPCがないため収益予測は作らず、最小の情報獲得単位を
「1 vendor・1 planのHuman価格観測」とする。

### Y1 — servers旧6記事案（政策v2で置換済み）

query別volumeは保存していないため、下表の順序はHumanが指定した取引意図の編集優先順であり、検索量順ではない。
下表は2026-08-06の旧案を残す履歴であり、現在の実装正本ではない。現在の正本は後述する政策v2の20記事である。

|ID|テーマ|凍結40語との対応|記事の問い|状態|
|---|---|---|---|---|
|SVR01|料金|`レンタルサーバー 料金` exact|初期費用と基本料金を含む初年度総額はいくらか|candidate only|
|SVR02|プラン比較|`法人向け サーバー 料金` exact|同一vendor内で必要条件を満たす最小planはどれか|candidate only|
|SVR03|他社比較|`国内 サーバー 比較` exact|複数vendorを同一条件で比較するとどれが残るか|candidate only|
|SVR04|初期費用込み総額|`サーバー 初期費用` exact|契約時支払と12か月継続費の合計はいくらか|candidate only|
|SVR05|更新料|`サーバー 年払い 割引` thematic|初回特典終了後の更新時支払はいくらか|candidate only|
|SVR06|移行|`サーバー 移行 費用` exact|重複契約・支援・Human作業を含めるといくらか|candidate only|

旧案のSVR05は凍結queryに「更新料」の完全一致語がないためthematic対応としていた。政策v2では
`サーバー 年払い 割引`をexact source queryとし、「2年目料金」は記事角度に限定する。

## 2026-08-06 政策v2 — 失敗経路の潰し込み

本節は上の6記事案を置き換える実行方針である。観測済み事実はservers slate全体のknown需要だけで、
query別volumeと競合性はrepositoryへ保存していない。このため「競合が薄い」は観測事実として断定せず、
語の具体性と購入直前性をproxyに選び、全記事を`competition_status=unobserved`で開始する。

|姿勢|案|cost / signal / reversibility|Hard gate・kill条件|EVI|
|---|---|---|---|---|
|conservative|既存6記事だけをHuman観測へ進める|Human 360分 / 初回6記事 / 高|主要queryが抽象的なまま、または公式価格を確認不能なら停止|confirmed EPC未観測のためunknown|
|balanced|下記20ロングテール候補を60分/本で処理し、計算機first・partner冗長化を適用|Human最大1,200分 / 記事単位 / 高|推測、主要claimのunknown、開示・承認・CTA gate不成立で当該記事HOLD|最小単位は1記事のHuman観測と公開後signal|
|aggressive|ビッグワードを先行公開し、未承認partnerも比較CTAへ含める|高 / 不明 / 低|rights・Affiliate・公開hard gate不成立で`ineligible`|算定しない|

Humanが採用したのは`balanced`である。表は実行優先順位の助言であり、記事承認、公開、index、CTA、
提携申請を自動許可しない。

### Z1 — 第1弾ロングテール20記事

全件が凍結40語とのexact対応を持つ。タイトル角度の「2年目料金」と「二重支払い」は、年払い・移行費用の
記事内で検証する論点であり、未観測query volumeを追加したものではない。

|ID|凍結query|記事角度|
|---|---|---|
|SVR01|法人向け サーバー 料金|年次表示額・初期費用と未確認条件|
|SVR02|中小企業 サーバー|小規模運用の最小構成|
|SVR03|ECサイト サーバー 費用|backup・転送込みEC費用|
|SVR04|サーバー 初期費用|初期費用込み総額|
|SVR05|サーバー 年払い 割引|2年目料金・更新額|
|SVR06|サーバー 移行 費用|乗り換え時の二重支払い|
|SVR07|法人向け レンタルサーバー|法人契約前の総費用|
|SVR08|ECサイト サーバー|EC用途の性能・復旧条件|
|SVR09|メールサーバー 法人|account・保全込み費用|
|SVR10|マネージド サーバー|運用代行範囲込み費用|
|SVR11|法人向け レンタルサーバー 比較|法人要件をそろえた比較|
|SVR12|中小企業 サーバー 比較|過剰契約を避ける比較|
|SVR13|ECサイト サーバー 比較|EC必須条件による比較|
|SVR14|メールサーバー 法人 比較|mail移行・保全込み比較|
|SVR15|マネージド サーバー 比較|運用範囲をそろえた比較|
|SVR16|WordPress サーバー 費用|backup・更新込み費用|
|SVR17|サーバー データ転送 料金|転送上限と超過条件|
|SVR18|サーバー バックアップ 料金|保存・復元込み費用|
|SVR19|サーバー 法人 小規模|小規模法人の最小構成|
|SVR20|サーバー 解約 条件|解約期限・返金・data移行|

`レンタルサーバー 比較`、`クラウドサーバー 比較`、`VPS サーバー 比較`、`WordPress サーバー 比較`、
`国内 サーバー 比較`等は第1弾から除外し、20記事から受ける内部link hub候補としてだけ保持する。

### I7 — 20本到達までのservers実行キュー

公開済み12本から固定20本ラインへ進む次の8本は、取引意図と2026-08-17のHuman入力tokenを踏まえ、
`SVR05 → SVR04 → SVR06 → SVR07 → SVR02 → SVR03 → SVR09 → SVR08`の順とする。
更新・2年目料金、初期費用込み総額、乗り換え時の二重支払い、法人契約を先に扱う。解約期限・返金・
data移行はSVR05/SVR06の必須確認fieldに含め、専用のSVR20はこの8本の後続候補として維持する。
SEOツールの新規記事へは投資しない。`server_price_input: done SVR02,...,SVR09`はHuman操作完了tokenとして
受領済みだが、repositoryにSVR02–SVR09のcandidate JSONが存在しない限り、値入力・記事承認・index・CTAへ
昇格させない。各記事は「公式価格確認 → contract検証 → 記事標本 → Human承認」の順で進める。

### Z2–Z7 — 共通運用

- 記事templateは`開示 → 計算機 → 結果 → CTA枠 → 根拠表`の順で固定する。
- servers CTAは有効なpartnerが0社なら無効、1社なら単独、2社以上なら比較表示とする。各partnerは従来の
  承認・開示・destination・`cta_go`を個別に満たす。1社だけなら構造上の依存率100%として80%警告を出す。
  2社以上でconfirmed commission shareが未観測なら依存率を推測しない。
- 1記事60分の標準workflowは`docs/PRICE_CHECK_CHECKLIST.md`のZ4節を正本とする。
- 2026-12-31の固定撤退ラインは、公開20本、GSC clicks 300/月、confirmed 1件をすべて満たすこととし、
  事後に緩和しない。未達時はembed配布、note有料、受託を転換候補としてHuman判断へ送る。
- servers記事の計算機はzero-inputとする。記事表示時点でHuman承認済みcontractだけから選択期間の総額表を
  計算済みで表示し、読者が選べるのは12/24/36か月と、小規模サイト・法人サイト・ECサイトの用途区分だけとする。
  金額、seat、価格基準、税区分の入力欄は記事に置かない。価格または記事が未承認の行は`未確認`、用途の
  Human分類外は`対象外`と表示し、いずれも順位から除外する。通貨が混在する場合も換算せず順位を付けない。
- 任意入力式の従来計算機は`/methodology/#detailed-calculator`へ移し、記事からは1リンクで参照する。
  zero-input表と詳細計算モードは同じPython正本を使い、TypeScriptは12/24/36か月のgolden一致を必須とする。
  初期実装時は承認済みservers価格contractが0件だったため、実価格をseedせず空状態をfail-closedで表示した。
  以後もHuman承認済みcontractだけを採用し、現在の承認・公開状態は`docs/CURRENT_ADOPTION_ACTIONS.md`を正本とする。

## 国内ASP案件の有無checklist

未確認のcategory×ASPセルだけを`unknown`とする。ASPログイン後のHuman検索結果だけで更新し、検索結果が
0件でも「将来も案件なし」とは断定しない。serversの確認済み状態は下表へ反映済みである。非公開報酬、
program ID、tracking URLはrepoへ保存しない。

|category|A8.net検索語|もしも検索語|バリューコマース検索語|現在状態|
|---|---|---|---|---|
|servers|レンタルサーバー / VPS / ホスティング|レンタルサーバー / VPS|レンタルサーバー / ホスティング|`A8: XServerビジネス承認済み / もしも: ロリポップ承認済み / ValueCommerce: ABLENET承認済み`|
|accounting|会計ソフト / クラウド会計|会計ソフト / 確定申告|会計ソフト / クラウド会計|`unknown / Human確認待ち`|
|crm|CRM / 顧客管理 / SFA|CRM / 顧客管理|CRM / SFA / 顧客管理|`unknown / Human確認待ち`|
|forms|フォーム / アンケート / 予約|フォーム / アンケート|フォーム / 予約 / 決済|`unknown / Human確認待ち`|
|email_marketing|メール配信 / メルマガ|メール配信 / メルマガ|メール配信 / メールマーケティング|`unknown / Human確認待ち`|

Human確認時はカテゴリ×ASPごとに次だけを記録する。

- `checked_on`、検索語、`listed / not_found / login_blocked / unknown`
- 個別提携審査の有無、登録siteへの掲載可否、deep link可否、SNS掲載可否
- 公開可能なprogram名だけ。非公開報酬・識別子・規約本文は記録しない
- ASP account成立と個別program提携承認を別状態にする

## TCO計算機の適用可否

Pydantic正本は`CategoryExpansionInput`、生成schemaは
`schemas/category-expansion-input.schema.json`である。状態は常に`candidate_only`で、scope、公開、価格入力の
authorityを持たない。数値は将来のHuman観測値だけを受け入れ、未観測値はunknownのままにする。

|category|適用判定|必須入力|HOLD条件|
|---|---|---|---|
|accounting|適用可|base price、minimum seats、法人/事業数、月間取引数|取引数tier、税、法人追加料金がunknown|
|crm|適用可|base price、minimum seats、contact数、automation addon|contact tierまたはaddon条件がunknown|
|forms|条件付き適用|base price、月間response、storage、決済手数料率|決済額scenarioまたは手数料の課税基準がunknown|
|email_marketing|適用可|base price、contact数、月間send、超過単価|contact/sendの課金軸または超過処理がunknown|
|servers|条件付き適用|initial fee、base price（月額/年額metadata）、renewal fee、campaign price/期間、domain benefit額/期間、compute時間、storage、transfer、backup|いずれかの金額・通貨・税・請求周期・campaign終了条件・domain更新条件がunknown|

## カテゴリ別記事構造template

全カテゴリ共通の6章は、`結論 → 前提scenario → 料金と上限 → 12か月TCO → 反証 → 選び方`とする。
各記事は冒頭PR表示、Human確認値、出典URL、観測日、次回確認日、unknown表示を既存記事と同じ順序で持つ。

|category|取引意図title template|scenarioで固定する項目|反証で必ず確認する項目|
|---|---|---|---|
|servers|`<用途>向けサーバー料金比較: 容量・転送・backup込み12か月TCO`|稼働時間、storage、月間transfer、backup世代|初期費用、転送超過、region差、復元費用、移行停止時間|
|accounting|`<事業規模>向け会計SaaS料金比較: seat・取引量込み12か月TCO`|法人/事業数、利用者数、月間取引数|税申告機能、追加法人、法改正対応、データ移行・解約export|
|crm|`<チーム規模>向けCRM料金比較: seat・contact・自動化込み12か月TCO`|利用者数、contact数、automation回数|必須addon、最低seat、実装支援、contact超過、メール費用|
|forms|`<月間回答数>向けフォーム料金比較: storage・決済手数料込み12か月TCO`|response数、添付容量、月間決済額|決済率、ファイル保存、回答超過、個人情報機能、外部連携|
|email_marketing|`<登録者数>向けメール配信料金比較: 配信通数・超過込み12か月TCO`|contact数、月間send数、配信頻度|contact重複、超過、到達率機能、専用IP、automation addon|

## 実測後も維持する境界

1. 6 slateのHuman exportは完了済み。rawをrepo外に置き、完全一致したsafe-summaryだけを判断へ使う。
2. query count可変のsafe-summary intakeは、欠落・重複・対象外queryが1行でもあればbatch全体をfail-closedにする。
3. serversはHuman選定済みのため、`docs/PRICE_CHECK_CHECKLIST.md`に沿って1 vendor・1 planずつ価格を観測する。
4. serversはXServerビジネス、ロリポップ、ABLENET、シンレンタルサーバー、ConoHa WING、
   お名前.com レンタルサーバーの6programが提携承認済みである。ただし、記事承認、公開、index、
   runtime destination、partner別CTA gateはそれぞれ独立して満たす。
5. accounting / crm / forms / email_marketingは40/40実測済みだが、known下限はいずれも必要22,227を下回り、
   no_data率も高い。総需要不足とは断定せず、新規投資はHOLDする。

R1–R6、P06–P09、既存ASP申請準備の優先順位は変更しない。
