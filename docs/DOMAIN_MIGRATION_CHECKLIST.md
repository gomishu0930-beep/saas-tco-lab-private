# 7/31 domain day — 画面別実行手順書

authority token: `domain: GO <domain>`

この手順書は2026-07-31当日に上から順に実行する。合計目安はHuman操作約60–90分とDNS待機時間である。
購入、課金、DNS変更、GSC/GA4操作、Impact再verificationは、exact domainのGOを受領するまで行わない。
credential、支払情報、registrar名、verification値、measurement ID、partner ID、tracking IDはrepository、
chat、screenshot、logへ残さない。

## 開始カード — 5分

### 画面

候補domainの販売画面。購入buttonはまだ押さない。

### Human操作

- 綴り、初年度価格、更新価格、Whois privacy、移管条件、auto-renew設定を読む。
- 商標と既存brandの衝突がないと判断できる候補だけを残す。
- Codexへ次の一行だけ返す。

```text
domain: GO <取得するexact-domain> / HOLD
```

### Read-back

- [ ] GOの綴りと購入画面の綴りが完全一致する。
- [ ] credential、価格、カード情報を返信文へ含めていない。
- [ ] `index_go`とAffiliate CTAはHOLDのままである。

HOLDならここで終了する。

## Step 1 — Domain購入画面 — 10分

### 画面

Humanが選んだregistrarのcheckout。Codexへ画面共有する場合も、支払欄は表示しない。

### Human操作

1. exact domainをcartへ入れる。
2. 不要なmail、hosting、security addonを外す。必要性を推測して追加しない。
3. Whois privacy、更新価格、auto-renewをread-backする。
4. 支払情報をHumanだけで入力し、最終購入buttonを押す。

### Copy-paste

購入後、秘密情報を含まない次の一行だけ返す。

```text
domain_purchase: done <exact-domain>
```

### Read-back

- [ ] account内の登録domainがGOと一致する。
- [ ] receipt番号、支払方法、registrar account IDを返信していない。
- [ ] domain lockとprivacyの現在状態をHumanだけで確認した。

## Step 2 — SitesのCustom domain画面 — 10分

### 画面

Codexの対象site → Hosting／Domains → Add custom domain。表示名が異なる場合は似たbuttonを推測せずHOLDする。

### Human操作

1. exact domainを入力する。
2. Sitesが表示するDNS record名・type・valueを画面内で確認する。
3. A/CNAME/TXT値はコピーするが、chatやrepositoryへ貼らない。

### Copy-paste

```text
sites_domain_record: ready <exact-domain>
```

### Read-back

- [ ] 対象projectがSaaS TCO Labであり、FANZA projectではない。
- [ ] apexと`www`のどちらを正本にするか画面上で確定した。
- [ ] verification値を返信していない。

## Step 3 — Registrar DNS画面 — 10分＋伝播待ち

### 画面

registrar → DNS／Name Server／Zone editor。

### Human操作

1. Sitesが提示したexact recordだけを追加する。推測したIPやrecordを使わない。
2. 同じhost/typeの競合recordがある場合は削除せずHOLDする。
3. 保存後、Sites側のVerify／Check statusを押す。

### Copy-paste

```text
dns_saved: done <exact-domain>
```

### Read-back

- [ ] Sites画面がConnected／Active相当になった。
- [ ] browserで`https://<exact-domain>/healthz`が固定health応答を返す。
- [ ] TLS警告、mixed content、redirect loopがない。
- [ ] 不明な場合は`dns_saved: HOLD <exact-domain>`で停止する。

## Step 4 — 公開前route read-back — 10分

### 画面

新domainのhome、`/operator/`、`/pilot/`、`/about/`、`/privacy/`、`/contact/`。

### Human操作

各画面を一度開き、表示崩れ、誤domain、外部CTAがないかを見る。Developer Toolsでtokenを探す必要はない。

### Copy-paste

```text
domain_readback: done <exact-domain>
```

### Read-back

- [ ] 全画面でSaaS TCO Labと表示される。
- [ ] NOINDEX表示があり、CTAはDISABLEDである。
- [ ] 記事冒頭のPR表示がCTA位置より先にある。
- [ ] canonical、sitemap、index requestはまだ有効にしていない。

## Step 5 — Search Console画面 — 10分

### 画面

Search Console → property selector → Add property → DomainまたはURL-prefix。

### Human操作

1. 新domainを旧propertyへ付替えず、新しいpropertyとして追加する。
2. Googleが提示するverification方法を選ぶ。
3. verification tokenはDNS／runtime secretだけへ入力する。
4. Verifyを押し、ownership successを確認する。

### Copy-paste

```text
gsc_property: done <exact-domain>
```

### Read-back

- [x] 2026-08-03、property selectorに`sc-domain:saastcolab.jp`が表示された。
- [x] sitemap送信、URL inspectionのindex requestは実行していない。
- [x] token、property IDをrepo・報告へ保存していない。DNS TXTは所有権維持のため残す。

## Step 6 — GA4 Web stream画面 — 10分

### 画面

GA4 → Admin → Data collection and modification → Data streams → Web。

### Human操作

1. 新origin専用のWeb streamを作成または選択する。旧originと混ぜない。
2. Stream URLへ`https://<exact-domain>`を入力する。
3. data sharing OFF、event retention 14か月、enhanced measurement OFFを確認する。
4. measurement IDはruntime secretへだけ設定する。

### Copy-paste

```text
ga4_stream: done <exact-domain>
```

### Read-back

- [x] 2026-08-03、既存専用Web streamのoriginを`https://saastcolab.jp`へ更新した。
- [x] 公開HTMLを外部read-backし、同意前はGoogle tagを静的読込せず、同意bootstrapのdefault denyを維持した。
- [x] 拡張計測OFF、event／user retention 14か月、任意data sharing全OFFを画面で確認した。
- [x] internal traffic filterは`test`のままで`active`へ変更していない。
- [ ] 同意後だけ`page_view`、表示継続後に`qualified_session`をRealtimeで確認する。S6の公開24時間後read-backで実施する。
- [ ] query、PII、Affiliate識別子がevent parameterにないことをS6の受信標本で再確認する。

## Step 7 — Redirect画面 — 5分

### 画面

Sites本番Worker。2026-08-03にHumanのexact mapping承認を受け、旧origin hostだけを新originへ301する
限定versionを反映した。

### Human操作

旧routeから同じ新routeへの一対一mappingを確認する。queryやAffiliate parameterを付加しない。

### Copy-paste

```text
redirect_map: approve <exact-domain> / HOLD
```

### Read-back

- [x] 旧originから新originへのredirectは1段で、chainとloopがない。
- [x] 旧originの301 responseと新originの200 responseがNOINDEXを維持する。
- [x] pathと既存queryは保持し、Affiliate parameterを新規付加しない。
- [x] 旧originはrollback用に削除していない。

## Step 8 — Impact／Affiliate media property画面 — 10分

### 画面

Impact → Media Properties／Websites → AddまたはEdit Website。Programごとの対象site画面も確認する。

### Human操作

1. 新domainをmedia propertyへ追加する。
2. verification値は画面とruntime secret間だけで扱う。
3. 対象site変更がprogram側で承認済みになるまでCTAを有効にしない。

### Copy-paste

```text
impact_domain_verification: done <exact-domain> / HOLD
```

### Read-back

- [x] 2026-08-03、`saastcolab.jp`がImpactのMy Channelsで`Connected`になった。
- [x] 申請中をAffiliate承認済みとして数えていない。
- [x] partner ID、tracking ID、報酬画面を返信していない。

## Step 9 — 終了判定 — 5分

すべて成功した場合だけ次を返す。

```text
domain_day: done <exact-domain>
index_go: HOLD
affiliate_cta: HOLD Mangools
```

2026-08-03追記: 後続の個別GOで`index_go: GO P01,P02,P03`、
`affiliate_cta: GO Mangools P01,P02,P03`へ移行した。domain day当日のHOLD記録は入口状態として保持する。

### Read-back

- [x] domain、TLS、route、GSC、GA4、Impactの結果を確認した。
- [x] domain day終了時点ではindex／CTAをHOLDした。後続GO後も未承認記事はNOINDEX・CTA無効である。
- [x] credentialや識別子をrepositoryへ保存していない。

## Rollback

TLS、route、NOINDEX、計測、verificationのどれかが失敗したら次を返す。

```text
domain_day: HOLD <exact-domain>
rollback: GO prelaunch-origin
```

Codexは新domainの公開候補を停止し、旧origin、NOINDEX、CTA無効を維持する。DNS recordをHuman判断だけで
削除せず、Sitesが示すrollback手順とread-backがそろってから変更する。

## Index解除は別日・別GO

domain day完了はindexing authorityではない。P01–P12のHuman実値入力、記事別承認、PR表示順序、
公開前testがそろった後、`index_go: GO`を別に受領する。Affiliate CTAもpartner別の別GOを必要とする。
