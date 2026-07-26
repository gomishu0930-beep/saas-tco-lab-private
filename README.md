# SaaS Comparison Preflight

SEO・マーケティングSaaSの料金、利用上限、12か月TCO比較を検証するためのローカル決定論コア、公開前noindex MVP、署名付き自律制御境界です。

3社×6プラン程度のgold setを、field単位の利用根拠、短い原文証拠、再計算可能なTCOとともに作り、市場・提携・権利・自動化可能性を検証します。`site/`は合成データだけのローカル表示見本で、公開・deployはしていません。

## 安全境界

- `approved`でないsourceから取得・公開しません。
- raw HTML/PDF全文は既定で保存しません。
- AIや外部サービスに価格DBの確定・公開権限を与えません。
- 通貨、税、課金周期、契約期間、seat、usage単位が曖昧な場合は計算を停止します。
- 外部AI、MCP、Cloud、remote DB、SentryはPreflight Phase 0–1の対象外です。
- synthetic local MVPは全route noindex、CTA無効、robots全拒否です。
- production buildは署名検証adapterが承認・接続されるまで、静的assetを含む保護routeを503で閉じ、`/healthz`と`/robots.txt`だけを返します。
- TCO/QA、Human Approver、controllerは別のEd25519鍵に分離し、秘密鍵・credentialはfixtureやrepoへ保存しません。
- 13項目の型付き・runner署名済みlocal assuranceが合格しても、実BusinessDossierとTCO/QA・Human署名が揃わなければpublic releaseはSTOPです。
- 最終GOはcontroller署名authorizationを伴い、consumerが別途固定したcontroller公開鍵・policy hash・現在時刻で再検証できなければ拒否します。
- rights問い合わせ、Affiliate申請、公開activate/disableは、exact Human GO、controller grant、固定runtime、固定store ID・外部monotonic pin・認証anchor・HMAC・schema fingerprint付きSQLite CASによるlocal one-shot claim、guard時刻のexecutor receiptまでを実装しています。connector・credential・外部callはなく、このローカルSQLiteを分散production正本へ無検証で転用できません。
- P12計測は開始前Human freeze、需要/cohort/operations別producer署名、funnel各段coverage root、current transaction/payout、logical job、exact 8 fault、事後index、consumer固定hash、TCO/QA署名reportを同時検証します。実source/export署名は未接続です。
- P13はP9 lease、P10 public GO、P11 durable Human-approved claim、P12 bound dossierを同じreleaseへ結合し、default STOP、Human reset、epoch/fence、外部anchor付きSQLite、固定digestのlocal subprocess、provider署名receipt、別鍵probeを合成状態で検証します。実provider・credential・deploy・公開は接続していません。
- P14は検証済みprovider receiptをprobe/terminalより前に追記専用journalへ保存し、owner crash後も事実を保持した`UNKNOWN + STOP`へ1回だけ回収します。same-host 4-process owner競合は検証済みですが、remote exactly-once、multi-host consensus、KMS、実readbackは未接続です。
- P15–P16 v3は実環境11証拠とlaunch前8 gateを署名・期限・固定順序へ結合します。P21の型付き意味packetはrights、Affiliate、P12需要・運用、gold set、P15、P10、deployment/publicationを公開鍵だけで再計算し、P12 fault target、P15 plan、P10 manifest、P13 requestを同一release/manifest/artifact/schema/target/pre/post/rollbackへ固定します。Gate 8はP11 disable policyとP15 independent-readback/rollback evidenceのexact hash、直前deployment、consumer-owned legal/disclosure期待値、個別観測の鮮度・順序へ実環境readbackを固定し、opaque hashや自己申告record、別scopeの再署名を拒否します。結果は最終Human review入力までで公開権限を発行しません。
- P17はP12完全packetを30日ごとに再実行し、TIME_AUDITOR署名時刻と外部anchor付きglobal ledgerへ観測・settlement・評価・post-anchor finalizationを保存して、累積EPCと最新売上・CTR・partner集中・運用品質を判定します。一時失敗は唯一のpending tailだけを回復し、期限超過はactive evidenceでなく署名付きtombstoneにします。clock workerはhost-global root lockとfork-safe one-shot FD leaseで重複実行をfail-closedにします。`READY_FOR_SCALE_REVIEW`も投資・公開権限ではなく、現在のempty fixtureとbare CLIはSTOPです。
- P18はP11–P21の全対象fileとversion付きexact path-setをMerkle manifestへ固定し、argv/cwd/environment/network/interpreter/import closureを含む14検証、Integration/TCO/Humanの別署名、Human前のverification-authority root、current receipt headと省略不能な全revision chainを照合します。P16 v3はP18、handoff、typed semanticsの三つのconsumer-owned authority rootを要求します。P13 childは`-I -S`隔離とhash済みimport allowlistで`PYTHONPATH/sitecustomize`や未pin runtime moduleをloadしません。本番bootstrapはread-only immutable runtimeが必須です。現在のP18 fixtureは合成・未署名なので`STOP / local_verification`です。
- 14検証のlocal diagnostic runnerに加え、immutable runnerが将来発行するV2 challenge/image/advisory/spec/result/clock契約、packet外root検証、store固定・durable freeze・Storage Auditor署名receipt付きone-shot consumerを実装しています。receiptはP18→P16→P13へ署名連鎖します。P17はcredential-blind broker、P13は署名時刻/current-root再取得、provider後時刻、P18/P16完全再検証を持ちます。旧`verified_local_run`は署名済みでも永久STOPです。現在は実quote verifier、artifact CAS read-back、production clock/anchor/current-root serviceがないためP19は`IN_PROGRESS / STOP`です。
- 30日運用はtask schedule、execution receipt、匿名化human activity、resource usageから再計算し、P17観測が全行を保持します。月20万円はsettled売上ではなく、人件費・resource費控除後のnet operating profitで判定します。

## 開発

```bash
uv sync --group dev
uv run pytest
uv run python scripts/export_schemas.py
uv run python scripts/generate_p18_pending_fixture.py
uv run saas-preflight --help

cd site
npm ci
npm test
npm run dev
```

## ローカル運用

```bash
uv run saas-preflight validate-plan plan.json
uv run saas-preflight validate-keyword-universe examples/jp_ja_keyword_universe_v1.csv
uv run saas-preflight init-db --db data/cohort-2026-07.sqlite
uv run saas-preflight store-plan plan.json --db data/cohort-2026-07.sqlite
uv run saas-preflight calculate-tco plan.json --seats 10 --months 12
uv run saas-preflight aggregate-demand demand-summary.json --output demand-evidence.json # diagnostic only
uv run saas-preflight aggregate-cohort cohort-summary.json --output cohort-evidence.json
uv run saas-preflight aggregate-operations operations-summary.json --output operations-evidence.json
uv run saas-preflight assemble-readiness \
  --plan vendor-a.json --plan vendor-b.json --plan vendor-c.json \
  --affiliate-decisions affiliate-decisions.json \
  --demand-evidence demand-evidence.json \
  --cohort-evidence cohort-evidence.json \
  --operations-evidence operations-evidence.json \
  --property-domain comparison.example \
  --output dossier.json
uv run saas-preflight evaluate-readiness examples/business-dossier.current-blocked.json
uv run saas-preflight render-preview examples/preview-page.synthetic.json --output /tmp/saas-preview.html
uv run saas-preflight evaluate-gold-set \
  --gold-set gold-set.json \
  --candidates candidate-batch.json
uv run saas-preflight evaluate-editorial-package editorial-package.json --at 2026-07-23T03:00:00Z
uv run saas-preflight rank-growth-initiatives initiative-portfolio.json
uv run saas-preflight build-growth-scorecard feedback.json \
  --operations operations-kpi.json --at 2026-07-23T03:00:00Z --output scorecard.json
uv run saas-preflight evaluate-cta-health cta-health.json --at 2026-07-23T03:00:00Z
uv run saas-preflight evaluate-growth-activation \
  examples/conditional-activation.current-stop.json --at 2026-07-23T03:00:00Z
uv run saas-preflight evaluate-model-route examples/model-routing-request.synthetic.json \
  --policy examples/model-router-policy.current-stop.json --at 2026-07-23T03:00:00Z
uv run saas-preflight evaluate-initial-learning-quality bundle.json \
  --policy strict-policy.json --trust-store public-trust-store.json \
  --expected-authority-sha256 <consumer-owned-sha256> --at 2026-07-23T03:00:00Z
uv run saas-preflight evaluate-traction \
  examples/p17/blocked/evidence-bundle.json \
  --plan examples/p17/blocked/plan.json \
  --policy examples/p17/blocked/policy.json \
  --trust-store examples/p17/blocked/trust-store.json \
  --authority-pins examples/p17/blocked/authority-pins.json \
  --settlement-policy examples/p17/blocked/settlement-policy.json \
  --settlement-trust-store examples/p17/blocked/settlement-trust-store.json \
  --at 2026-07-31T15:00:00Z
```

CLIにはfetch、外部送信、公開、本番write、affiliate操作を実装していません。TCOは全fieldの`derive`承認が現在有効な場合だけ計算します。3つの`aggregate-*`、`assemble-readiness`、`evaluate-readiness`は互換性を残した**unsigned diagnostic**であり、production authorityではありません。P12のauthority経路は`assemble-signed-readiness` / `evaluate-signed-readiness`で、consumerが別管理するpolicy、trust root、run、exact bundle-index hashを毎回再検証します。出力先は既存ファイルを上書きしません。

SQLiteはappend-onlyのため、異なる保持期限を1ファイルへ混在させません。1つの権利・保持期限cohortを1 DBにまとめ、表示される最短期限までにHuman Approverの承認を受けてDB全体をrotateし、削除またはcrypto-eraseします。行単位削除でappend-only監査証跡を破壊しません。

自データの初回受入条件と本人作業は`docs/INITIAL_LEARNING_QUALITY_GATE.md`を正本とする。`READY_FOR_HUMAN_REVIEW`は学習・公開権限ではない。

`business-dossier.current-blocked.json`は現在の不足を正直に表すSTOP fixtureです。ゼロhashはproduction evidence未取得を示すplaceholderであり、実績や市場値ではありません。`preview-page.synthetic.json`も実在価格・実Affiliate linkを含まず、noindex表示境界だけを確認します。`external-action-request.synthetic-unapproved.json`は署名も実行権限もない合成requestです。production入力の定義は `docs/READINESS_INPUTS.md`、raw exportからsafe summaryを作る人間側手順は`docs/PHASE3_EVIDENCE_RUNBOOK.md`、gold set受入は`docs/GOLD_SET_RUNBOOK.md`、Webと配信境界は`docs/LOCAL_MVP.md`、署名付きcontrol cycleは`docs/CONTROL_CYCLE_RUNBOOK.md`、外部action境界は`docs/EXTERNAL_ACTION_RUNBOOK.md`、P13のlocal production consumerは`docs/P13_PRODUCTION_CONSUMER.md`、P14のcrash-safe境界は`docs/P14_CRASH_SAFE_EVIDENCE.md`、P17のtraction/scale境界は`docs/P17_TRACTION_SCALE_CONTROL.md`、P18のrepo受入は`docs/P18_REPOSITORY_ACCEPTANCE.md`、脅威・SBOM・公開前判定は`docs/THREAT_MODEL.md`、`docs/SBOM_RUNBOOK.md`、`docs/RELEASE_ASSURANCE_RUNBOOK.md`にあります。

本人操作が必要な箇所だけを抜き出した表と画面別手順は`docs/HUMAN_ACTION_MANUAL.md`を正本とし、local UIの`/operator/`にも表示します。

完成までのPhase、外部承認gate、停止条件は `docs/PRODUCTION_ROADMAP.md` を正本とし、次にHumanから受け取る
入力と受領後の実行順は `docs/NEXT_IMPLEMENTATION_HANDOFF.md` に固定しています。

現時点で導入可能なrepository、plugin、data connector、生成AI、custom skill、計測、運用の全計画は
`docs/CURRENT_ADOPTION_MASTER_PLAN.md`、機械可読台帳は`docs/CURRENT_ADOPTION_REGISTRY.json`、
非Human実装の37件監査は`docs/CURRENT_ADOPTION_IMPLEMENTATION_STATUS.json`、本人操作だけの表は
`docs/CURRENT_ADOPTION_ACTIONS.md`を参照してください。

役割分担と承認境界は `docs/OPERATING_MODEL.md`、agent実行規律は `AGENTS.md` を参照してください。
