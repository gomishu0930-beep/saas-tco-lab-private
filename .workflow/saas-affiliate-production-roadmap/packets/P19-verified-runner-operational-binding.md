# P19 — Verified runner result contract and operational binding

## Objective

外部認証情報なしで、P18の将来のverified runnerが満たすresult contract v2、P17実測ledgerの運用入口、
P18/P16をpublication/production直前に再検証するfail-closed bindingを実装する。

## Ownership

- Integration/Release: code、CLI、schema、統合。
- Contract/Storage: result contract、署名・root・replay・output/termination反証。
- TCO/QA: P17運用入口、automation/TCO、下流GO誤昇格反証。

## Do

- image/advisory/runner/check/resultをbyte-level hashと期限へ固定するtyped v2 contractを作る。
- diagnostic runnerからverified authorityを発行しない既存境界を維持する。
- credential-free fixtureでv2 verifierを正例・改変・欠落・期限切れ・rollbackへ反証する。
- P17 append/evaluateに必要な入力をCLI化し、raw eventやcredentialを保存しない。
- P18/P16 packetとconsumer-owned rootをpublication/production consumer入口で毎回再検証する。

## Do not

- OCI/VMを実在したことにする、advisory鮮度を合成する、秘密鍵を生成・保存する。
- source fetch、affiliate申請、provider call、deploy、公開、課金を行う。
- synthetic/local diagnosticを`verified_local_run`へ昇格する。

## Verification

- touched-module focused tests、schema double export、fixture determinism。
- attacker-controlled root、self-consistent packet replacement、timeout/output truncation、signal/expiry/replay反証。
- full Python、Web、lock、compileall、Gitleaks、workflow verifier。
