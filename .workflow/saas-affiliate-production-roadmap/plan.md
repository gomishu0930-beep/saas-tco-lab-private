# SaaS affiliate production roadmap and implementation

## Goal

SEO・マーケティングSaaSの料金・利用上限・12か月TCO比較を、権利と収益性を先に検証し、公開MVP、80%自動運用、最大180日のTraction test、月20万円の拡大判定まで到達できる一つの実装路線へ固定する。外部承認を要しない部分は順次実装し、Human専有gateでは必要入力と再開条件を機械判定できる形で残す。

## Success Criteria

- Phase 0–1の既存contract/TCO/storageを壊さず、権利・提携・需要・EPC・品質・人手のGO/STOP evaluatorを追加する。
- immutable release、read-time expiry、affiliate CTA gate、idempotent run、例外queue、人手budgetをlocalで再現する。
- 3社×6プランgold setを受け入れられるtemplate、import validation、fault injectionを用意する。
- 代表条件のnoindex previewを、canonical Python TCO結果から生成できる。
- 外部source取得、affiliate申請、cloud、domain、公開、analyticsは、必要なHuman入力・approval・credentialを明示して分離する。
- 全工程をPhase、owner、入口、出口、停止条件、検証コマンド付きのロードマップとして保存する。

## Current Context

- Phase 0–1 local coreは完了。57 tests、Pydantic contract、append-only SQLite、TCO、CLI、Gitleaks、pinned CIがある。
- 第一候補はSaaS比較。第二候補の高額商品横断比較は不採用。
- 本番GOに必要な実データは未取得: field-level rights、実利用可能affiliate 3社、日本語qualified demand、確定EPC。
- workspaceはgit初期化済みだが未commit・未push。外部account/credential/cloud/publicationは未承認。

## Constraints

- source rightsをHumanが承認するまでnetwork fetch、履歴保存、比較表示に採用しない。
- affiliate申請、メール送信、OAuth、API key、課金、cloud、push、deploy、公開は別gate。
- raw全文、credential、PII、非公開報酬をrepo・prompt・logへ入れない。
- Python/Pydantic/TCOをschema/計算の正本とし、UIで料金計算を再実装しない。
- FANZA運用とbrand、domain、repo、credential、analyticsを分離する。

## Risks

- 実装を先行してもrights/affiliate/demand/EPC gateが不成立なら事業はSTOPになる。
- 汎用fetcherはSSRF、redirect、rate-limit、利用規約違反を生むため、approved host/method単位でしか有効化しない。
- static UIが期限切れデータを残すため、release manifestとread-time/serve-time gateを必須にする。
- 収益KPIをpending成果で過大評価しない。confirmed cohortだけでEPCを判定する。

## Approval Required

今回の承認範囲はroadmap、local code/tests/docs、read-only公式調査、既存承認済みlocal依存の利用。外部申請・送信・account・credential・課金・source fetch・push・deploy・公開はHuman Approverの個別承認まで実行しない。

## Work Packets

Current status: P1–P21 credential-free technical candidate、P19のlocal contract/consumer slices、P20のlocal
hardeningとP21 typed semantic enforcementは実装済み。独立Contract/Storage・TCO/QA・security監査で
既知P0/P1を修正した。実immutable runner/CAS、別OS identityの
provider broker/KMS、production clock/current-root/anchor、P11–P21の形式的repo acceptance、実producer/export、
実30日測定、外部操作権限、事業・公開判定は`STOP`のまま。

- P1 Evidence/Policy: 候補5社の公式rights/affiliate一次資料、未確認点、照会票。docsのみ。
- P2 Release/Operations: immutable release、TTL、affiliate gate、run idempotency、exception/budget。新規module/tests。
- P3 Economics/QA: demand、qualified session、click/cohort EPC、20万円逆算、GO/STOP判定。新規module/tests。
- P4 Integration(root): 完成ロードマップ、preflight dossier contract、CLI、preview、fault injection、統合検証。
- P5 Provenance/Intake(root): Plan policy、Affiliate decision、需要/cohort/operations evidenceからdossierを自動組立し、自己申告bool/件数をproduction pathから排除。
- P6 Phase 3 Measurement: deduplicated demand、confirmed cohort、shadow operationsのtyped raw summaryをEvidenceへ決定論変換し、外部認証後すぐ測定開始できる状態にする。
- P7 Local MVP: Sites-compatible local UIとPython release runtimeを接続し、noindex・serve-time expiry・CTA redaction・methodology/disclosure/health/rollbackをsynthetic dataで完成する。
- P8 Gold set/Quarantine: 3社×6プランのHuman label、material field hash、scenario TCO、parser provenance、current rightsを照合し、release候補とquarantineを外部fetchなしで判定する。
- P9 Autonomous control cycle: dossier、gold-set report、release、heartbeat、例外、人手budgetを一つのpure fail-closed判定へ結合し、短命dead-man leaseを発行する。promotion、publish、network、永続化は行わない。
- P10 Release assurance: threat model、lockfile由来SBOM、accessibility/mobile/SEOのsynthetic検証、typed public-release gateを外部接続なしで統合する。local assurance合格とpublic GOを分離する。
- P11 External-free execution handoff: L1–L11とPhase 3–6を要件単位で監査し、Humanの外部操作前後を結ぶ署名付きaction request/receipt、Gate A–D run specification、production consumer adapterのうち、認証情報なしで先行可能な最優先sliceを実装する。
- P12 Measurement integrity: producer署名、固定run/分母、transaction status/payout/funnel照合、必須8 fault identityをlocal契約へ固定し、Gate C/Dの集計水増しを拒否する。
- P13 Production consumer: P10 public authorizationとP9 serving leaseを実edgeで二段検証し、P11 provider adapter、shared store/fencing、global STOP、postcondition probeをHuman承認済み環境へ接続する。
- P14 Crash-safe evidence and conformance: provider結果をP11/P13 terminal commit前に認証storeへimmutable記録し、
  crash/restart時もfactual receiptを保持して`UNKNOWN + STOP`へ回収する。multi-process fencing、schema tamper、
  P9/P10 artifact swap、fork ownership、adapter artifact mutationをcredential-free fixtureで反証する。
- P15 Production integration readiness: real provider接続前にprovider idempotency/readback、KMS、external anchor、
  trusted clock、shared store/fencing、egress、backup/restore、rollback/disableを型付き・期限付き証拠で全件検証する。
  credential、URL、account、network、deployは扱わず、不足・競合・期限切れは常にSTOPにする。
- P16 Launch handoff sequencer: P11–P15 candidate acceptanceからrights、affiliate、需要、shadow、gold set、
  production integration、deployment/publication readinessまでを、一つのscope・固定順序・署名・期限へ結合する。
  完全なpacketでも最終Human review入力に留め、外部操作やpublic GOを発行しない。
- P17 Traction/scale control: verified P12 monthly observationを改変不能な順序へ結合し、1,000 click/180日、
  confirmed EPC、月20万円capacity、merchant集中、人手・自動化・品質を継続判定する。出力は投資・公開権限で
  なくHuman scale reviewへの勧告に限定する。
- P18 Local acceptance/restart contract: P11–P17候補のexact file scope、hash、検証receipt、除外事項を
  authorityなしのmanifestへ固定し、別Human署名acceptanceだけをlocal integration受理へ変換する。公開・外部write・
  production・scale権限は発行せず、受理後の次gateと必要入力を機械判定する。
- P19 Verified runner and operational binding: immutable runnerが発行すべきtermination/output/advisory/image契約を
  typed result v2へ固定し、P17実測ledgerのcredential-free運用CLIと、P18/P16を最終publication/production直前に
  packet外rootで再検証する下流bindingを実装する。実image、KMS鍵、advisory署名、provider、公開権限は扱わない。
- P20 Completion gap audit: 原目標の権利・提携・需要・EPC・公開MVP・80%自動運用・収益検証を要件単位で
  authoritative evidenceへ対応付け、未充足を外部入力とローカル実装可能項目へ分離する。後者があれば
  credential-free範囲で実装・反証し、前者だけなら再開入力と機械的STOP証拠を固定する。local scopeは完了、
  business/public/production/scaleは外部証拠待ちの`STOP`。
- P21 Typed launch semantics: P16 Gates 2–8へgate固有のtyped payloadを必須化し、component hash、署名、順序だけで
  READYへ到達できないようにする。consumer-owned plan/policy/trustへthreshold・scopeを固定し、rights、Affiliate、
  需要、30日運用、gold/source、P15、本番前deployment/publication factsを現在時刻で再評価する。

## Integration Policy

既存`models.py`、`storage.py`、`tco.py`は正本として維持する。P2/P3は相互にimportしない新規moduleを所有し、rootだけがCLIとroadmapへ統合する。外部事実が競合した場合は最新版の公式規約・公式affiliate条件を優先し、法的結論ではなく実装gateとして記録する。

## Verification

- Narrow unit/property tests then full `uv run pytest`。
- schema export reproducibility、`uv lock --check`、compileall、Gitleaks。
- release expiry、CTA disable、duplicate run、rollback、budget freezeのfault tests。
- EPCのpending除外、1,000 confirmed-click gate、必要session逆算のtests。
- workflow verifierとroadmap completeness audit。

## Reusable Artifacts

- `docs/PRODUCTION_ROADMAP.md`
- `docs/CANDIDATE_RIGHTS_RESEARCH.md`
- `src/saas_preflight/release.py`
- `src/saas_preflight/operations.py`
- `src/saas_preflight/economics.py`
- `src/saas_preflight/preflight.py`
- `.workflow/recipes/saas-affiliate-production.md`
- `docs/THREAT_MODEL.md`
- `docs/RELEASE_ASSURANCE_RUNBOOK.md`
- `artifacts/release-assurance/sbom.cdx.json`
