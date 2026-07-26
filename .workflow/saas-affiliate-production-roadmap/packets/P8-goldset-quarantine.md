# P8 Offline gold set and quarantine

- Objective: Gate A/B後に受領する3社×6プランを、外部fetchなしでfield hash・scenario TCO・rights freshness・parser provenanceへ照合し、release候補かquarantineかを決定論的に判定できるようにする。
- Owner: Contract/Storage + TCO/QA。Integration/ReleaseがCLI/schema/docsを統合する。
- Ownership: `src/saas_preflight/goldset.py`、`tests/test_goldset.py`、CLI/schema、gold-set runbook、P8 result。
- Do: strict/frozen contract、UTC/Decimal、human label receipt SHA-256、minimum 3 vendor × 各6 plan coverage、vendorごと60–150 field label、current derive/publish/history/retention、policy-only rights manifest、source/parser hash、constant usage scenario、full TCO result hash、20% parser-failure stop、field/TCO mismatch quarantine、deterministic report。
- Do not: 実vendor値、実価格、外部source fetch、parserの自動生成、曖昧値補完、Human labelの捏造、raw本文、URL/credential、canonical DB write、release promote。
- Expected output: partial/full gold setを安全に受け入れるschema、candidate batch contract、hash-only quarantine report、read-only CLI、synthetic tests。
- Verification: missing/extra/duplicate、label/rights expiry、source hash mismatch、field mismatch、TCO mismatch、unsupported scenario、failure-rate 20% boundary、3×6/60–150 coverage、row permutation determinismを反証する。
