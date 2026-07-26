# Local noindex MVP

基準日: 2026-07-22

## 実装範囲

P7は公開前UIと配信境界をlocalで完成させる。外部source、実価格、実Affiliate URL、
credential、analytics、公開domain、Sites deployは対象外であり、Human GOまで追加しない。

### Web UI

`site/`はSites/vinext互換のresponsive UIで、次のrouteを持つ。

- `/`: 目的、現在のSTOP状態、合成比較の要約。
- `/comparison`: region、tax、currency、billing、commitment、scenario、事前計算TCO、適合理由、根拠時刻、data/rights期限、広告状態。
- `/methodology`: canonical Python TCO、field policy、配信時TTLの説明。
- `/disclosure`: 広告表示、`rel=sponsored`、編集独立性、CTA失効方針。
- `/readiness`: Gate A–Dと月20万円の目標式。実績値として表示しない。
- `/robots.txt`: 全crawlerへ`Disallow: /`。

全routeのmetadataは`noindex, nofollow, noarchive, nosnippet`である。UIは
`app/lib/synthetic-data.ts`の事前計算済みfixtureを表示するだけで、価格・TCO計算式を持たない。

### Python delivery boundary

`saas_preflight.mvp`がproduction adapterへ渡すpureな正本である。

1. `build_mvp_artifact(page, at=UTC)`はdata/rightsと有効CTAをbuild時に検査する。
2. route本文をcanonical JSON化し、release用`artifact_sha256`を生成する。
3. CTA destinationはURL本体ではなく、sorted bundle SHA-256でmanifestと照合する。
4. disclosure本文もSHA-256で照合し、片方でも不一致ならCTAだけをredactする。
5. `LocalPreviewRuntime.handle()`はlocal test専用としてrequestごとにcurrent releaseと3 expiryを再検査する。
6. releaseなし、artifact不一致、data/rights/affiliate期限到達時は比較本文・金額・CTAを含まない503へfail-closedする。
7. GET/HEADだけを許可し、CSP、no-store、no-referrer、nosniff、DENY、X-Robots-Tagを全responseへ付ける。
8. `/healthz`は状態や数値を漏らさず`ok`だけを返す。

これはsocket serverではない。production entry pointは`ControlledMvpRuntime`で署名済みleaseを必須にする。
Sites workerは承認済み署名検証adapterが実装されるまでhealth/robots以外を常時503にする。
production hostingへ接続するHTTP adapter、永続release state、secret resolutionは個別承認後に実装する。

## Local verification

```bash
uv run pytest -q
uv run python scripts/export_schemas.py --output-dir schemas
uv lock --check
python3 -m compileall -q src tests scripts
gitleaks dir . --redact --no-banner --no-color

cd site
npm ci
npm test
npm run lint
npm audit --json
npm run dev
```

ローカル画面は`http://localhost:3000/`。`npm audit`は0 vulnerabilityを必須とする。

## Fault acceptance

- expiry直前は表示、exact expiryで503。
- CTA destination/disclosure hash不一致は金額を残してCTAだけredact。
- artifact hash不一致は全candidate本文を停止。
- release rollback後は再選択されたartifactだけを表示。
- query付き比較もnoindex。
- unknown routeは404、POSTは405、HEADは空body。
- inactive CTA fixtureから追跡URLや`sponsored` linkを出さない。

## 外部再開条件

公開へは次をすべて満たした別Human GOが必要。

1. Gate A: 公開予定fieldの権利が3社でcurrent。
2. Gate B: 対象propertyで実利用可能なAffiliateが3社。
3. Gate C: JP/ja qualified demandの保守ケースが成立。
4. Gate D: 30日shadowで重大誤表示0、job 99%以上、例外24以下、人手720分以下、rollback合格。
5. domain、legal/privacy/disclosure、account、billing、credential、deploy先、rollback ownerの承認。

条件未達の現在判定は`STOP`であり、local実装完了を事業GOへ読み替えない。
