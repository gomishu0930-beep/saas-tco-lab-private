# 月次15分ルーチン — 5 KPIとMangools確認

毎月の作業は、指定画面を見る、同じ対象月の値をdashboard転記フォームへ入力する、tokenを返す、の三つだけである。
credential、property ID、tracking ID、query文字列、個人情報、transaction ID、非公開の明細行は記録しない。
時刻はAsia/Tokyo、対象期間は前月の初日から末日へ統一する。

## 開始前 — 1分

1. ローカルの`status-dashboard.html`をbrowserで開く。
2. 「月次KPI転記フォーム」で対象月を選ぶ。
3. 別tabでGSC、GA4、Impact、Mangoolsを開く。loginはHumanが行う。

期間が一つでも違う場合は合計せず、`monthly_kpi_csv: pending`で止める。

## KPI 1 — 公開記事数 — 自動・0分

取得場所: repositoryの有効なeditorial input contract、記事承認state、index GO。

Humanは入力しない。dashboard更新scriptが承認済みcontract数とindex状態から再生成する。

## KPI 2 — インデックス数 — Search Console・2分

### 画面

Search Console → 対象domain property → Indexing → Pages。画面名が変わった場合は、indexed pagesの合計が
表示される公式reportだけを使う。

### 転記

- 前月末時点の「Indexed」相当の件数を`indexed_articles`へ入力する。
- 未承認route、query/filter page、旧domainを含めない。分離できなければpendingにする。

## KPI 3 — GSC clicks — Search Console・2分

### 画面

Search Console → Performance → Search results → Date → Custom → 前月初日〜末日。

### 転記

- Search typeはWeb、filter追加なしでTotal clicksを`gsc_clicks`へ入力する。
- query/pageの明細はCSVへ入れない。

## KPI 4 — Outbound clicks — GA4・2分

### 画面

GA4 → Reports → Engagement → Events → `outbound_click`。日付を前月初日〜末日にする。

### 転記

- Event countを`outbound_clicks`へ入力する。
- 同じ期間の`page_view`ではなく、event名が完全一致する行だけを使う。
- funnel確認用に`Sessions`、`qualified_session`のEvent countもフォームへ入力する。
- link domain、URL、query、Affiliate識別子は転記しない。

## KPI 5 — Confirmed commissions — Impact／Mangools・3分

### Impact画面

Impact → ReportsまたはPerformance → date rangeを前月へ設定 → action／commission statusをConfirmedまたは
Approved相当へ限定する。画面名が違う場合は確定状態と通貨をHumanが確認できる集計だけを使う。

### Mangools画面

Mangools account → Affiliate → commissions／conversionsの集計画面 → 対象月。Approved／Confirmed相当だけを使う。

### 転記

- 確定額だけをJPYへそろえたsafe totalとして`confirmed_commissions_yen`へ入力する。
- pending額は任意の`pending_commissions_yen`へ分ける。
- rejected、refund、未確定conversionを確定額へ足さない。
- 通貨換算根拠がない場合は合算せずpendingにする。
- transaction ID、紹介ID、顧客情報、明細行は保存しない。

## Mangools定例確認 — 2分

### 毎月4日

Mangools → Affiliate → tier／commission rate。直近期間のtier表示が変わったかだけを見る。

### 毎月15日

Mangools → Affiliate → conversions／payment eligibility。前月conversionの承認状態とexport可否だけを見る。

変更がある場合も紹介IDや明細を貼らず、次のどちらかだけ返す。

```text
mangools_monthly: unchanged
mangools_monthly: changed review_needed
```

## CSV保存とdashboard更新 — 3分

1. `status-dashboard.html`の「月次KPI転記フォーム」で「CSVを保存」を押す。
2. 保存された`monthly-kpi-YYYY-MM.csv`を加工せずローカルdropとして渡す。
3. 次のtokenを返す。

```text
monthly_kpi_csv: done
```

Codexは次を実行し、raw CSVをrepositoryへ保存せずdashboardのsafe totalだけを更新する。

```text
uv run python scripts/update_status_dashboard.py --kpi-csv <local-csv-path>
```

対話入力を使う場合は`--kpi-csv`を省略する。自動処理では`--no-prompt`を指定し、前回外部値を保持する。

## 15分以内に終わらない時

- 画面の数字が合わない、期間がそろわない、通貨が混在する場合は推測しない。
- report exportや明細照合へ広げず、その月をpendingにする。
- 次の一行だけ返す。

```text
monthly_kpi_csv: pending <GSC|GA4|Impact|Mangools>
```
