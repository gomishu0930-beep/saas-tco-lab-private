# P11–P18 local candidate acceptance — PENDING

基準日: 2026-07-22

## 状態

P18はP11–P18のexact repository scopeと検証・署名・current-head契約を実装するが、本書はHuman署名票ではない。現在のdecisionは`PENDING/STOP`であり、local integration、source利用、Affiliate、外部write、公開、production、spend、scaleを承認しない。

過去の`P11_P15_LOCAL_ACCEPTANCE_PENDING.md`、`P11_P16_LOCAL_ACCEPTANCE_PENDING.md`、`P11_P17_LOCAL_ACCEPTANCE_PENDING.md`は履歴として変更しない。

## 機械可読な現在値

scope外の次の3 artifactを`generate_p18_pending_fixture.py`で再生成する。

- `artifacts/local-acceptance/p18-current-stop/verification-evidence.synthetic.json`
- `artifacts/local-acceptance/p18-current-stop/candidate-manifest.pending.json`
- `artifacts/local-acceptance/p18-current-stop/expected-stop-report.json`

これらは合成検証と署名欠落を明示して`STOP / local_verification`になる。生成後のtree/manifest/report hashはartifact内を正本とし、本書へ転記して自己参照を作らない。

## Human受理前の必須入力

1. current treeへ対する14件の非synthetic verification facts。
2. Integration Evidence Runnerと独立TCO/QAの署名・固定hash PASS。
3. Human、Integration、TCO/QAの別trust keysとpolicy。
4. consumerがpacket外で保持するauthority-pins hash。
5. current revision/predecessorへ署名したHuman `GO | CONDITIONAL | STOP`。

`GO`でもP18が許可するのはlocal integrationだけで、次gateはrights evidenceである。実rights、Affiliate 3社、JP/ja需要、gold source、production証拠、公開承認、連続30日観測、settlement、EPC/20万円は別gateのままである。
