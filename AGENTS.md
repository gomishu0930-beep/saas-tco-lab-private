# Repository agent rules

この規律はリポジトリ全体に適用する。目的は、SaaS料金・利用上限・12か月TCOの比較データを、権利、証拠、再現性を失わずに扱うことである。

## 必須ゲート

- rights model v2を適用する。自動取得、価格DB保存、履歴DB化、canonical計算への採用は、sourceごとに取得・保存・履歴・派生利用の権利が記録され`approved`になるまで行わない。未指定、期限切れ、矛盾は`denied`としてfail-closedにする。
- Human Approverが公開価格を人手確認し、出典URL、観測日、次回確認日、値の入力者を記録した編集記事経路は、field-level書面許諾をlaunch blockerにしない。この例外は自動取得、価格DB、履歴DB、raw保存、無断転載、禁止回答済み行為を許可せず、価格・税・通貨・課金周期の推測も許可しない。
- raw HTML、PDF、メール等の全文保存は既定禁止。URL、取得時刻、hash、authority、必要最小限の引用を保存する。全文archiveは明示的な権利とHuman Approverの承認がある場合だけ許可する。
- AI、agent、plugin、MCP、外部LLMからcanonical DB、本番DB、公開release、affiliate URLへ直接writeしない。AI出力は候補値であり、型検証・決定論テスト・承認済みreleaseを経る。
- credential、token、Cookie、個人メール、PII、非公開報酬をrepo、fixture、log、promptへ入れない。外部送信もしない。

## 実装規律

- 2026-07-28以降、P0–P18はmaintenance onlyとし、P19以降の新phase、新署名層、新acceptance文書を追加しない。新規実装はlaunch trackの記事、計算機、審査route、domain準備、需要CSV受入、index/CTA gateに限定する。

- Pydantic modelをdata contractの正本、PythonのTCO純粋関数を計算の正本とする。JSON Schemaは生成物であり、手編集しない。
- 金額、通貨、税、請求周期、commitment、seat、quota、overage、addonを推測・補完しない。曖昧値と未知fieldはvalidation errorへ送る。
- 保存はappend-only observationを基本とし、既存証拠の上書き・履歴削除をしない。修正は新しいversionとして追加する。
- network accessは承認済みhost・methodだけに限定し、robots、規約、rate limit、`Retry-After`、認証境界を尊重する。CAPTCHA、login、403、地域制限、private networkへの回避を行わない。
- 変更には対象のunit/property/fixture testを追加し、`uv run pytest`、lock整合性、schema再生成、secret scanを通す。失敗した検証を無視して統合・公開しない。
- dependency、plugin、MCP、GitHub Actionはpublisher、license、権限、外送、撤去方法を監査し、version/SHA/digestを固定する。`latest`、未固定install、自動mergeは使わない。

## 所有と承認

- agentは割り当てられた所有ファイルだけを編集する。他者の変更をrevert・整形・移動せず、interface競合はIntegration/Release Operatorへhandoffする。
- handoffはversion付きartifact、入力根拠、検証結果、未解決事項、ownerを含める。会話やAI要約だけを承認記録にしない。
- Human Approverだけがsource rights、例外的な全文archive、外部account・課金・credential、production write、公開・rollback、affiliate link変更を承認できる。承認はscope、期限、条件を記録する。AIへの再委任は禁止する。
- 現在承認済みなのはP0–P10のローカルcode/docs/tests、Sites互換synthetic preview、署名付きcontrol/release-assurance boundary、監査済みlocal dependencyまで。外部source fetch、申請・送信、account、credential、billing、cloud、deploy、push、公開は別ゲートとする。
- FANZA運用とはbrand、domain、repo、credential、analyticsを共有しない。

詳細な役割、RACI、cadence、月720分の人手上限、障害時escalationは`docs/OPERATING_MODEL.md`に従う。
