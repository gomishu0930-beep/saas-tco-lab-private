# 許諾済みsource adapter境界

`source_access.fetch_approved_source`はcrawlerではない。Human-approved `SourcePolicy`の1 URLを、明示hostに限って低頻度で取得するためのPhase 4部品である。現時点の5候補は全社fail-closedであり、実network fetchは開始していない。

強制する条件:

- `fetch=approved`が現在有効。
- methodは`official_api / vendor_feed / direct_http`のいずれか。
- HTTPS/443、userinfo・fragmentなし、exact host allowlist。
- redirectごとにhostとDNSを再検証。
- 解決先は全件public/global IP。private、loopback、link-local等を拒否。
- HTTPXは環境proxy、cookie、authを継承しない新規clientを内部生成。
- statusは200/304。429/503は自動retryせず`Retry-After`をoperatorへ返す。
- content typeとdecoded bodyのbyte上限を強制。ETag/304を利用可能。
- transient bytes、URL、時刻、ETag、SHA-256を返すだけでraw archiveしない。

productionではcloud/network側のegress allowlistも併用する。application層のDNS検査だけでDNS rebindingやnetwork設定ミスを完全に防げるとは扱わない。API key、Cookie、login、CAPTCHA、403、region restrictionを必要とするsourceは、このadapterへsecretを足さず別のHuman gateへ戻す。

実sourceを追加する順序:

1. exact URL、host、method、頻度、保存/表示/派生/履歴scopeをrights dossierへ記録。
2. Human Approverが期限付きでpolicyを承認。
3. MockTransport/respx fixtureだけでparserとfailureを実装。
4. staging egress allowlistで1回手動実行。
5. 得られた候補値をcanonical DBへ直接writeせず、schema/証拠/TCO差分queueへ送る。
6. 403、CAPTCHA、予期しないredirect、Content-Type、schema driftでsource単位停止。
