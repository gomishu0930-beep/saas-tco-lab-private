# P16 local acceptance tests

基準日: 2026-07-23

## 必須判定

- exact 8 gate、固定role、P18 singleton Gate 1、固定artifact component set、plan self-hashを変更できない。
- typed P18 bundle、consumer-owned P18 authority-root、plan pin、P18 pinsの三者一致に加え、packet外の
  consumer-owned P16 launch-handoff authority-rootがなければREADYにならない。
- 旧P11–P15 opaque componentと、別P18+別plan+全receipt再署名による一式差替えを拒否する。
- P16 trust、policy、plan、全8 receiptを別鍵で自己整合的に再署名した完全差替えも、元のP16 rootで拒否する。
- Gate 2–8はexact typed semantic packetとpacket外semantic rootを必須とし、hash-only、欠落、別scope、別expiry、
  semantic STOP、aggregate改ざんを拒否する。
- rights/affiliateの元行、P12 report+dossier、gold、P15 report+TCO attestation、P10 local assurance、
  P15原証拠へ結合したprobe署名deployment record、content/indexability/disclosure別のprobe署名publication recordを再実行し、receipt component/identity/subjectと完全一致させる。
- P12/P15/P10/P13を同一release/manifest/artifact/schema/provider target/pre/post/rollbackへ固定し、別dossier、target splice、任意readbackの再署名、`synthetic_contract`をSTOPにする。
- current blocked fixtureは8件全て`missing_receipt`でSTOP。
- complete synthetic packetとsynthetic 1件混入はSTOP。
- complete verified-record packetも`READY_FOR_FINAL_HUMAN_REVIEW`までで、外部authorityを内包しない。
- missing、exact duplicate、conflict、同一ID、wrong key/signature、scope/artifact spliceをSTOPにする。
- ordinal、predecessor chain、非減少時刻を検証し、sortでskip/reverseを修復しない。
- future、plan前、exact expiry、TTL+1、plan future/exact expiry/TTL超過をfail closedにする。
- bundle/reportはreverse、rotate、固定seed shuffle、duplicate順序で決定論的である。
- schemaはextra、URL、credential、secret、waiver、grant、token、authorization fieldを拒否する。
- CLIはlocal-onlyでSTOP=3、review-ready=0、invalid/duplicate JSON key=2である。
- schema exportとblocked fixture generationを2回実行し、checked-in byteと一致する。

## 実行command

```bash
uv run pytest -q tests/test_launch_handoff.py
uv run pytest -q

first=$(mktemp -d)
second=$(mktemp -d)
uv run python scripts/export_schemas.py --output-dir "$first"
uv run python scripts/export_schemas.py --output-dir "$second"
diff -rq "$first" "$second"

uv run python scripts/generate_p16_blocked_fixture.py
uv lock --check
python3 -m compileall -q src tests scripts
gitleaks dir . --redact --no-banner --no-color
```

P16 v3のcurrent検証数とschema総数はP18の最終verification artifactを正本とする。schema二重exportとchecked-in
set、blocked fixture二重生成、CLI STOP outputとexpected reportをbyte-identicalにする。

## release blocker

P16 local passは、参照artifactの真実性、実rights/Affiliate、実需要、30日shadow、実provider/KMS/anchor、
deploy/publication approvalを代替しない。current P11–P21 acceptanceはPENDINGであり、P16 candidateもHumanの
version付き受理前はworking-tree候補である。skip、xfail、waiver、synthetic、receipt件数だけでは受入にしない。
