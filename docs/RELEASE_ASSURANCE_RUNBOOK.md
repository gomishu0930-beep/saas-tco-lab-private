# 公開前Release Assurance runbook

## 1. 判定の意味

P10は、技術的なローカル検証と公開許可を分離します。

|判定|意味|外部操作権限|
|---|---|---|
|`local ready`|同じrelease/manifest/artifact/policyへ結合した13検査が、現在有効な証拠として全件合格|なし|
|`public GO`|local readyに加え、TCO/QA署名、実BusinessDossierの`GO`、manifestとの全data binding、同じdossierを含むHuman署名が全て有効|別途承認されたdeploy/publication scopeに限る|
|`STOP`|1項目でも欠落、失敗、future、expiry、hash・scope・key・署名・data binding不一致|なし|

ローカル検証の合格は、rights、提携、需要、EPC、30日運用、Human判断を作りません。現在は
rights 0/3、Affiliate 0/3、実JP需要・confirmed EPC・30日shadow run・Human公開署名がないため、
public判定は`STOP`です。

`examples/local-assurance.synthetic-ready.json`は型とhash境界だけを示す合成例です。
`examples/release-assurance.current-stop.json`は、その合成local passを現在の実不足を表す
`business-dossier.current-blocked.json`と突き合わせても公開はSTOPになることを示します。どちらも
実test receipt、実価格、実rights、実Affiliate提携、公開承認ではありません。

## 2. 信頼境界

`ReleaseAssuranceAuthority`は、次をtrusted bootstrapとして一度だけ固定します。

- `AssurancePolicy`: policy ID、必須13検査、各検査のfacts種別・tool/version・command/subject hash、最大evidence TTL、最大attestation TTL。
- `ControlTrustStore`: controller、TCO/QA、Humanのrole分離Ed25519公開鍵。
- trust-store全体のSHA-256とcontroller・TCO/QA・Human key ID。

evaluatorへpolicyとTrustStoreを個別注入できません。秘密鍵はmodel、schema、fixture、report、repoへ
保存せず、署名関数へ実行時だけ渡します。別Authority、別key、別issuer、改変copy、自己再hashは
正規Authorityでの公開判定を通りません。

最終consumerは`ReleaseAssuranceRuntime`へcontroller公開鍵、assurance policy hash、最大authorization
TTLを独立に固定し、評価時の現在時刻でcontroller署名を再検証します。report内の自己申告keyや
Authorityを信頼根として使いません。exact expiry以後のreplay、別policy・別controllerが作った
自己完結report、署名なしの`GO`は拒否します。

## 3. 13のlocal check

`AssuranceEvidenceBundle`は次の完全な集合だけをcanonical順で受け入れます。重複、欠落、追加は
validation errorです。

1. `python_tests`
2. `web_local_tests`
3. `web_production_tests`
4. `schema_determinism`
5. `lock_integrity`
6. `sbom_current`
7. `secret_scan`
8. `dependency_audit`
9. `threat_model_review`
10. `accessibility`
11. `mobile_reflow`
12. `seo_policy`
13. `rollback_faults`

各checkの`AssuranceRequirement`はfacts種別、tool名・version、command SHA-256、検査対象
subject SHA-256をpolicyへ固定します。各evidenceはそのrequirement、release ID、
manifest/artifact/policy SHA-256、観測時刻、失効時刻、controller-role runner identity、自身の
canonical hashとEd25519署名へ結合します。

合否はcheck別の型付きfactsからevaluatorが導出します。testは全collected件の
passed/failed/skipped分類とexit code、determinismは2回生成物とcommitted artifactの3 hash、
integrityはinvalid/drift、scanはfindings/unresolved、reviewはrequirements/blockers、Web assuranceは
5 routeのcoverage/violationsを検証します。callerが汎用`passed=true`や任意の合計件数だけを渡す
入口はありません。

runner署名は、policyで承認されたcontroller keyがこのfactsを発行したことを証明する境界であり、
物理的なコマンド実行そのものを数学的に証明するものではありません。実運用adapterは固定commandを
実行してexit/outputからfactsを生成し、秘密鍵を持たないTCO/QAがlog hash・対象hash・反証を独立に
確認してからlocal reportへ署名します。

半開区間`observed_at <= evaluated_at < expires_at`を使います。exact expiryは失効です。evidenceの
TTLがpolicy上限を超えた場合もSTOPです。

## 4. 検証コマンド

repository rootで実行します。

```bash
uv run pytest -q
uv lock --check
uv run python scripts/export_schemas.py
uv run python scripts/export_sbom.py --output artifacts/release-assurance/sbom.cdx.json --check
uv run python -m compileall -q src tests scripts

cd site
npm ci
npm test
npm run lint
npm audit --audit-level=low
```

Gitleaksはversionを固定した実行物でrepository全体を検査します。schemaとSBOMは一時directoryへ
再生成し、既存artifactとbyte比較します。成功log本文やsecret scan結果そのものはreportへ埋めず、
最小hash receiptだけをevidenceへ渡します。

`npm test`は13件の成功表示だけでなく、command自体のexit 0とproduction Wrangler process groupの
消滅までを合格条件にします。production actual-HTTP testは独立process groupで起動し、終了時に
SIGTERM、bounded wait、必要時SIGKILLを行い、残留processがあればtestを失敗させます。

SBOMの生成、`--check`、lockfile source制約は`docs/SBOM_RUNBOOK.md`、脅威・production残課題・
kill switchは`docs/THREAT_MODEL.md`を正本とします。

## 5. accessibility・mobile・SEO境界

synthetic-local buildの5 routeで、次を検査します。

- `lang=ja`、viewport、route固有title/description、robots noindex/noarchive/nosnippet。
- main 1件、route固有h1 1件、label付きheader/footer nav、skip linkと存在するtarget。
- 内部linkだけ、外部origin・active CTA・`rel=sponsored`なし。
- comparison tableのcaption、row/column scope、keyboard focus可能な横scroll領域。
- 無効CTAと隣接する広告説明の`aria-describedby` binding。
- 900px/620px reflow、page全体の固定min-width禁止、visible focus、reduced motion。
- canonicalとJSON-LDは意図的に不在。

実domainと実source-backed内容がHuman承認されるまで、canonical、structured data、sitemap、公開originを
合成値で先行実装しません。production buildはWorker-firstで静的assetを含む保護routeを503にし、
health/robotsだけ200です。

## 6. 署名handoff

### TCO/QA acceptance

`evaluate_local_assurance`が生成した`LocalAssuranceReport`をTCO/QAが独立再検証します。合格時だけ、
TCO/QA専用keyで次を署名します。

- local report hashとevidence bundle hash
- release ID、manifest hash、artifact hash
- assurance policy hash
- issuer、role、scope、key ID、issued/expiry

TCO/QA署名は検査を代行しません。秘密鍵所持だけで証拠の真実性を作れるため、署名前にコマンド、
hash、検査対象、反証を人または独立役割が確認します。

### Human public approval

Human Approverは、同じlocal report bindingに加え、exact `BusinessDossier`全体のcanonical SHA-256、
manifest内の全data snapshotを重複なしcanonical順で明示した完全list、
`GO | STOP | CONDITIONAL`、decision record hash、issued/expiryをHuman専用keyで署名します。
別dossierや未審査snapshotを追加したmanifestへの署名使い回しは失敗します。`STOP`と
`CONDITIONAL`はpublic GOになりません。

Human approval後もevaluatorは次を再計算します。

- BusinessDossierが評価時刻でfreshかつeconomics `GO`。
- dossierのrights/Affiliate bundleがmanifestと一致。
- demand/cohort/operations source hashが全てmanifest data snapshotsに存在。
- manifestとlocal reportのrelease/manifest/artifactが一致。
- CTAがapproved、manifest・local report・両署名がcurrent。
- TCO/QAとHumanがAuthorityの別role keyで署名。

全条件を満たした場合だけAuthorityのcontrollerが、report core、policy、local report、dossier、
release/manifest/artifact、issued/expiryへ結合した最終authorizationへ署名します。public reportは
上記の最短expiryまでだけ有効で、consumerは`ReleaseAssuranceRuntime`で現在時刻に再検証します。
署名があってもexternal account、cloud、domain、credential、deploy、publicationの操作権限は
別のHuman-approved execution scopeが必要です。

## 7. faultと停止手順

次を最低反証します。

- 1検査のfail/skip、missing/duplicate/extra check。
- future、exact expiry/replay、過長TTL、check別factsのcoverage・分類不一致。
- evidence/bundle/local/public reportのcopy改変と自己hash差替え。
- policy/TrustStore/Authority同時・個別差替え、同一role key、attacker署名、consumer pin不一致。
- tool/version/command/subject、release/manifest/artifact、rights/Affiliate/data snapshot、dossierのcross-binding。
- required 3 snapshotを含みつつ未審査snapshotを追加したmanifest。
- Human署名の別dossier再利用、Human STOP/CONDITIONAL、署名欠落。
- expired manifest、unapproved CTA、production asset-first bypass。

失敗時はpromotion、deploy、publicationを実行せず、production接続後であればleaseを失効させ、
protected routeを固定503へ閉じます。検査をwaive、時刻を巻き戻す、TTLを延長する、合成証拠を
production evidenceへ読み替えることは禁止です。

## 8. 現在の再開条件

公開へ進むには、少なくとも次のversion付き入力が必要です。

1. 3社以上のfield-level source rightsと3社以上の実Affiliate承認。
2. 3社×6プランの実gold set、quarantine 0、重大誤表示0。
3. 重複除去済みJP/ja需要、mature confirmed cohort、30日shadow operations。
4. production provider/domain/account/credential/retention/privacy/redirect/analytics設計。
5. deploy済み環境でのWorker/asset、security、accessibility、mobile、SEO、rollback probe。
6. exact release/dossier/local reportへ結合したTCO/QA署名とHuman signed GO。

不足中はlocal implementationを改善できますが、public URL、実Affiliate CTA、source fetch、production
write、deploy、publicationは開始しません。
