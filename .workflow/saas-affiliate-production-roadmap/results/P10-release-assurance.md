# P10 Result: Pre-publication release assurance

## Accepted

- 24件のmaterial threatを予防、検知、停止、復旧、残余リスク、owner、Human gateへ分解し、local controlとproduction launch blocker L1–L11を分離した。
- `uv.lock`と`site/package-lock.json`だけからnetworkなしで決定論的なCycloneDX 1.6 SBOMを生成する。649 components、649 dependency nodes、lockfile hash、purl、利用可能なdistribution hashとlicenseを保持する。
- 13のlocal checkをcheck別のtyped factsへ分け、tool/version、command/subject SHA-256を`AssurancePolicy`へ固定した。controller-role runnerのEd25519署名、future/expiry/TTL、coverage、exit code、finding、determinismを再計算する。
- local readyとpublic GOを分離した。public GOはcurrent BusinessDossier、rights/Affiliate/data binding、TCO/QA署名、Human GOとmanifest全snapshot完全listを要求する。
- 全条件GOのときだけcontrollerが最終authorizationへ署名する。consumerは別途固定したcontroller公開鍵、policy SHA-256、最大TTLと現在時刻を持つ`ReleaseAssuranceRuntime`で再検証する。
- synthetic-local 5 routeのmetadata、landmark、skip link、内部link、table、広告説明、無効CTA、900/620px reflow、focus、reduced motion、canonical/JSON-LD/public origin不在を検査した。
- production起動は常にproduction buildを先行し、worker-firstでpages/assetsを503へ閉じる。actual-HTTP testはprocess groupを回収し、成功表示後のhangや孤児Wranglerも失敗にする。

## Counterexamples closed

- 旧aggregate-only API、未署名/攻撃者署名facts、正規runnerによるunpinned subject。
- 別policy、別TrustStore、攻撃者Authorityの自己完結GO、report copyと自己再hash。
- future、exact expiry、期限後replay、最大TTL超過、issuer/role/scope不一致。
- dossierや署名のrelease間再利用、rights/Affiliate/data binding不一致、Human STOP/CONDITIONAL。
- required dataを含みながら未審査snapshotを追加するmanifestとHuman承認listの省略・改変。
- `build:local → start`によるsynthetic公開と、test終了後のWrangler/workerd残留。

## Verification

- Python full: 287 passed。Release assurance focused: 20 passed。
- JSON Schema: 38件を再生成しrepositoryとbyte一致。全schemaはunknown propertyを拒否する。
- SBOM: 649 components / 649 dependency nodes、SHA-256 `138757ba3f5eed42ab48276fff6b1533e447d60559529676637d5ab06cd7ac1f`、`--check`合格。
- Web: local 9、startup boundary 1、production actual-HTTP 3。`npm test`はexit 0、終了後のproduction test/Wrangler残留0。
- `uv lock --check`、compileall、ESLint、npm audit 0 vulnerabilities、Gitleaks 4.71 MB leak 0、workflow verifier合格。
- Contract/Storage、Governance、TCO/QAの独立read-only adversarial reviewはいずれもrelease blockerなし。

## External boundary

現在のbusiness/public判定は`STOP`である。rights 0/3、Affiliate 0/3、実JP/ja需要、mature confirmed cohort、30日shadow operation、Human public GO、production key store/runner/provider/domain/credential/deployがない。P10成果物は外部操作・公開権限を作らず、Gate A–Dと別のHuman-approved production scopeを代替しない。
