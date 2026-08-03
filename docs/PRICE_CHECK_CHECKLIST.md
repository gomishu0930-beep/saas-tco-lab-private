# 価格確認チェックリスト — P01–P12 × vendor

目的は、Humanが公式画面を開いて読み取り、`/operator`へ入力することだけである。これはURL一覧であり、
自動取得・保存・履歴化の許可ではない。ログイン限定値、個別見積、紹介parameter付きURL、税務・支払情報は
入力しない。不明値は推測せず、`unknown`と理由を明示する。unknownは証拠contractへ保持できるが、
TCO計算や記事承認には使えない。

## 使い方

1. 第1弾はP01、P02、P03の順に確認する。
2. 下の公式価格ページを新しいtabで開き、記事行のfieldだけを見る。
3. `/operator`で同じP-IDを選び、vendor識別子とplan識別子を入力する。比較対象を増やす場合は`vendor・plan行を追加`する。
4. 料金表の必要な行だけを貼り付けてlocal候補を抽出し、候補ごとにvendor・plan行と反映先fieldをHumanが選ぶ。
5. 事前入力後、値・単位／価格条件・出典URL・観測日・次回確認日に加え、billing toggleの位置と価格表示分類を公式画面と照合する。分類は`none`（割引・promo表示なし）、`annual_discount_permanent`（年払い・月払い差の恒常表示）、`time_limited_promo`（終了日・カウントダウン・クーポン・取消線priceのいずれかあり）、`unknown`の4値だけを使う。通貨が`$`だけならUSDと補完せず、通貨状態を`unknown`、画面表記を`$`とする。
6. 年払いplanは料金表の「月額換算」を一次値にしない。checkoutで支払直前に表示される年次請求総額を一次観測値として入力し、Operatorは`年次請求総額 ÷ 12`が最小通貨単位まで完全に割り切れる場合だけ月額派生値を表示する。割り切れない場合は総額を保持し、丸めず月額を非表示にする。checkout総額を安全に確認できなければ価格を`unknown`にする。account固有checkout URL、氏名、住所、メール、カード情報は入力せず、source URLには追跡parameterのない公式料金ページを使う。
7. seat数・利用量などHumanが決める条件はvendor行へ入れず、Humanシナリオ行へ入力する。再確認時は前回確定値との差分も見る。
8. 構造validation合格後に`Human確認して証拠contractを確定`を押した時だけJSONを保存する。unknownが残る場合はその値を使うTCO・順位claimをHOLDし、unknownを明示した記事本文はHuman reviewへ進める。

`time_limited_promo`と`unknown`は計算HOLD、`none`と`annual_discount_permanent`は価格表示分類だけでは
HOLDにしない。恒常割引率は、同一plan・同一通貨・同一税条件のHuman確認済み月払い価格と年次checkout総額が
両方そろう場合だけ、`1 - 年次総額 ÷ (月払い価格 × 12)`から「年払いは月払い比で約N%割安」と記事化する。
片方がunknown、条件不一致、または年次値がcheckout総額でない場合は割引率を出さない。

貼り付け原文と候補のsource lineはcontractや端末へ保存されない。抽出は数値と、同じ行に明記された通貨・
請求周期・税区分の事前入力を補助するだけで、単位、URL、日付、不明項目を推測しない。

## Vendor別の公式価格ページ

|Code|Vendor|Humanが開く公式価格ページ|入力前の確認|
|---|---|---|---|
|M|Mangools|[Plans & Pricing](https://mangools.com/plans-and-pricing)|region、通貨、月／年表示、税表示を画面どおり記録|
|H|HubSpot|[Customer Platform Pricing](https://www.hubspot.com/pricing/suite)|選択中product、seat／credit、commitment、通貨を確認|
|SE|SE Ranking|[Plans & Pricing](https://seranking.com/subscription.html)|地域、月／年、seat、keyword／project上限を確認|
|SM|Semrush|[SEO・AI Search Pricing](https://www.semrush.com/pricing/seo-ai-search/)|選択中product、月／年、limit、addonを確認|
|SR|Serpstat|[Pricing Plans](https://serpstat.com/page/pricing-plans/)|月／年、query／project／API上限、retentionを確認|

この五つのURLは既存の一次調査台帳に記録済みの公式URLである。redirect、404、地域差、login要求が出た場合は
別URLを推測せず`HOLD`とし、Codexへ画面名だけを伝える。

## 記事×vendorの確認表

各行をM・H・SE・SM・SRについて独立に実施する。すなわち一つの行に五つの確認単位がある。
記事の目的に合わないvendor／fieldはゼロで埋めず「対象外」として採用しない。

|優先|記事|対象vendor|公式画面で確認するfield|Operatorで必ず記録する項目|
|---:|---|---|---|---|
|第1弾|P01 料金計算|M / H / SE / SM / SR|vendor行: 基本料金、超過単価、税率。Human scenario行: seat数、月間利用量|vendor行にはvendor・plan識別子、billing toggle位置、価格表示の4区分、数値またはunknown、単位、価格なら一次観測区分・通貨状態・請求周期・税区分、出典URL、観測日、次回確認日。年払いはcheckout年次請求総額だけを一次値とする。scenario行にはHuman入力根拠と日付|
|第1弾|P02 プラン比較|M / H / SE / SM / SR|各plan料金、最低seat数、利用上限、超過単価、契約月数|同上。planごとに条件を変えず、同じscenarioで記録|
|第1弾|P03 代替候補|M / H / SE / SM / SR|各候補料金、利用上限、必須addon料金、公開されている移行費用|同上。移行費用が非公開なら未入力|
|通常|P04 小規模チーム適合|M / H / SE / SM / SR|最低seat数、月額料金、公開されている運用／導入時間|同上。vendorが示さない時間を体験談で補完しない|
|通常|P05 組織利用適合|M / H / SE / SM / SR|最低seat数、管理機能料金、監査addon料金、導入支援費|同上。見積依頼だけならunknown|
|通常|P06 年契約と月契約|M / H / SE / SM / SR|月契約料金、年契約料金、最低契約月数、公開解約費用|同上。割引と請求周期を分離|
|通常|P07 従量超過|M / H / SE / SM / SR|含有利用量、超過単位、超過単価、Human scenarioの月間利用量|公式値とHuman scenarioを別fieldとして記録|
|通常|P08 追加機能費用|M / H / SE / SM / SR|基本料金、addon料金、addon課金単位、必要seat数|同上。内包機能と別売addonを分離|
|通常|P09 移行コスト|M / H / SE / SM / SR|重複契約月数、作業時間、時間単価、教育時間、移行支援費|公式価格とHuman見積を混ぜず、根拠がないfieldは未入力|
|通常|P10 日本向け税・通貨|M / H / SE / SM / SR|表示価格、税率、換算レート|表示地域、通貨、税区分、換算観測日を同時確認|
|通常|P11 損益分岐|M / H / SE / SM / SR|月間削減時間、時間単価、導入費、月額TCO|vendor価格と自社観測を別sourceとして記録|
|通常|P12 根拠の検証|M / H / SE / SM / SR|確認間隔日数|全fieldのURL・観測日・次回確認日がそろっているか監査|

## その場でSTOPする条件

- URLに`utm_`、`ref`、affiliate ID等が入っている。
- login後だけ見える個別価格、営業見積、非公開報酬しかない。
- vendorまたはplanを識別できない、あるいは不明理由を記録できない。
- 同じ画面内で表示が矛盾する、regionを変えると条件が変わる、または価格表示を4区分へ分類できない。
- 年払いなのにcheckoutの年次請求総額を確認できず、料金表の月額換算値しかない。
- CAPTCHA、403、地域制限、規約回避が必要である。

通貨、税、請求周期、seat、quotaを画面から確定できない場合は、空欄やゼロへせずunknownと理由を記録する。
証拠contractは作成できるが、そのfieldを使う計算と記事承認は`HOLD`とする。STOP時のHuman作業は値を作ることではない。
