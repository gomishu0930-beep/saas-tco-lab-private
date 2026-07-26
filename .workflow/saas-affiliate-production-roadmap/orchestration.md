# Orchestration: SaaS affiliate production roadmap and implementation

## Execution Rules

- Keep the original objective intact.
- Ask for approval before risky, expensive, external, or destructive actions.
- Keep immediate blocking work local.
- Delegate only bounded, disjoint, materially useful packets.
- Integrate packet results before final verification.

## Branching Rules

1. rightsの7 actionまたはaffiliate stateが未承認なら候補を保存/計算/CTA/public releaseへ進めない。
2. 3 affiliate、保守qualified demand、重大誤表示0、人手≤720分/月のいずれかが欠ければproduction gateはSTOP。
3. 実source adapterはHuman-approved host/methodが得られたsourceだけ別packetで実装する。
4. cloud/UI/analyticsはPreflight GO後にカテゴリごと1製品だけ選ぶ。
5. pending/rejected commissionをEPC numeratorへ含めない。
6. 外部操作のgateではlocal simulationとexact handoff artifactまで進め、勝手に代替値を置かない。

## Packet Prompts

- P1は公式一次情報だけを引用し、申請・ログイン・問い合わせ送信をしない。unknownを明示する。
- P2は既存正本を変更せず、新規release/operations moduleとtestsだけを所有する。
- P3は新規economics moduleとtests/measurement docだけを所有する。
- P4はworkflow/roadmap/preflight/CLI/previewを所有し、全interface conflictを解く。
- P5はproduction Dossierをplan policyとversion付きhash-only evidenceから組み立て、自己申告bool・件数・率を受け取らない。
- P6はL2 safe summaryから需要/cohort/operations Evidenceを決定論生成する。raw exportやsemantic dedupを推測せず、上流receipt gapを明示する。
- P7は実データ・実URLなしのSites互換UIとpure delivery runtimeを所有し、公開・hosting・deployは行わない。
- P8はsource-specific parserを作らず、Human-labeled gold recordとtyped candidateをhash/TCO/rightsで照合するoffline受入境界を作る。candidate失敗を黙って除外せずquarantine件数へ含める。
- P9は既存evaluator/state machineだけを合成し、scheduler/heartbeat、rights bundle、candidate batch、release manifest、例外、月次budgetを照合する。Human promotionを代行せず、current release用の短命serve leaseだけを発行する。
- P10は既存lockfileとsynthetic buildだけからSBOM・a11y/mobile/SEO evidenceを作り、threat modelとtyped assurance gateへ統合する。local passをpublic GOに読み替えず、実rights/Affiliate/demand/30日運用/Human approvalが欠ける限り公開はSTOPにする。
- P11は既存実装とL1–L11を証拠ベースで突き合わせ、外部操作を行わずにHuman handoffの完全性・署名真正性・再開可能性を上げる。実装候補を安全性だけでなく、最終公開・自動運用・収益検証へのクリティカルパス短縮で順位付けする。
- P12はL2 summaryの件数や自己申告receiptを信頼せず、固定producer key、signed run manifest、exclusive transaction rows、payout/funnel reconciliation、exact 8 fault identityからL3 Evidenceを再生成する。実データは作らない。
- P13はlocal contractをproduction authorityへ読み替えず、out-of-process adapter、shared CAS、fencing、external anchor、global STOP、P10+P9 two-stage check、actual probeを個別Human gate後に統合する。
- P14はP13 success条件を緩めず、provider事実のdurable pre-terminal journalと再起動時のSTOP回収を
  追加する。P11/P13を擬似atomic successへ昇格させず、曖昧なcrashは常に`UNKNOWN`のままにする。
- P15は11個の本番統合checkをpolicy固定・role署名・短命authorizationで検証し、production-shaped evidenceが
  揃うまでP13のclaim/redeem/provider/probeをSTOPにする。
- P16は既存gateのauthorityを置換せず、候補・scope・artifact・署名・期限・順序を一つの最終Human handoffへ
  固定する。完全でも`READY_FOR_FINAL_HUMAN_REVIEW`までとし、実行時は各authorityを再検証する。
- P17はP12のcomplete packetをingest時にruntimeで再実行し、公開後の連続30日factsをappend-only chainへ保存する。
  後日確定・返金は元cohortへ固定したsigned Settlement Amendmentと独立completeness署名からだけ反映する。
  単月の仮EPCやsynthetic observationでscaleせず、成熟後もHuman review勧告までに留める。
- P18はworking-tree候補の受理を会話や手書きhashへ依存させず、固定scope manifest、検証receipt、Human署名、
  half-open expiry、条件と除外事項を再計算する。local integration acceptanceとpublic/production/scale authorityを
  型で分離し、未署名・scope差分・検証不足・期限切れはPENDING/STOPへ戻す。
- P20は原目標を既存成果へ都合よく縮小せず、要件ごとに直接証拠を要求する。未充足のうち外部権限・実測を
  捏造せず、認証情報なしでなお実装可能な境界、adapter port、dry-run、監視・復旧contractが残る場合は先に閉じる。
- P21はP16 receiptの署名やcomponent hashを業務意味の証拠として扱わず、Gate 2–8のtyped payloadをconsumer側で
  再構築・再評価する。threshold、property/environment/release scope、currentness、upstream decisionを固定し、
  payload欠落・別scope・自己整合的再署名・semantic STOPはP16全後続gateをSTOPにする。

## Completion Audit

- roadmapの全Phaseにowner、entry、exit、stop、external gate、verificationがある。
- local implementationはnetworkなしで再現でき、期限切れ・権利切れ・CTA切れをfail-closedする。
- 実データがない項目をcomplete扱いせず、Human inputと再開commandが明記される。
- tests、schema、lock、secret scan、workflow verifierが通る。
