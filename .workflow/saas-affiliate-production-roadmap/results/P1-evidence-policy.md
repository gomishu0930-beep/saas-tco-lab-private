# P1 Evidence / Policy 結果

確認日: 2026-07-21

## Outcome

Semrush、SE Ranking、Mangools、Serpstat、HubSpotの公式一次情報を再確認し、取得、保存、比較表示、派生TCO、履歴、商標、Affiliate参加を別々に判定しました。

**3社gateは0/3で未達です。** 公開Affiliate Programは5社すべてで確認できましたが、実際に有効なaccount/tracking linkは0社で、price/limit dataを継続取得・保存・比較・TCO・履歴として商用利用する明示権利も0社です。よって全sourceを`denied_fail_closed`とし、Human Approverの照会・申請判断までfetchしません。

詳細matrix、会社別判断、推奨順、Human照会テンプレートは [docs/CANDIDATE_RIGHTS_RESEARCH.md](../../../docs/CANDIDATE_RIGHTS_RESEARCH.md) に記録しました。

## 重要な一次根拠

- Semrush: [Termsはscrapingを禁止](https://www.semrush.com/company/legal/terms-of-service/)、[API cacheは原則1か月まで](https://developer.semrush.com/api/v4/introduction/api-usage-restrictions/)、[Affiliateはcomparison pieceを想定するが審査制](https://www.semrush.com/lp/affiliate-program/en/)。データ再利用権とは分離した。
- SE Ranking: [Serviceはinternal use](https://seranking.com/legal/terms-of-service.html)、[Affiliate契約は30%、120日cookie、商標素材の限定license](https://seranking.com/legal/affiliate.html)。price/TCO/historyはunknown。
- Mangools: [IP利用はinternal business、commercial exploitationは明示許可が必要](https://mangools.com/conditions)。[Affiliateは審査なし、最大35%](https://mangools.com/affiliate-program)だが、Termsには24か月capの条件がある。
- Serpstat: [Websiteを含む商用利用にはprior written express consentが必要](https://serpstat.com/users/license-agreement/)。[公開Affiliate案内](https://serpstat.com/serpstat-discounts/)だけでは契約詳細を確認できない。
- HubSpot: [一般Site Contentは非商用利用に限定](https://legal.hubspot.com/website-terms-of-use)。[Affiliateは審査制でsoftware reviewer等を対象](https://www.hubspot.com/partners/affiliates)だが、comparison DB権は別途書面確認が必要。

## 推奨handoff

照会順は Mangools → SE Ranking → HubSpot → Semrush → Serpstat とします。上位3社に同一の8問を送り、権利軸ごとにYes / No / Conditional、適用規約、保持期間、終了時削除を回答してもらいます。送信、申請、loginは本packetでは行っていません。

## Verification

- [x] 5社を公式一次情報だけで再確認
- [x] 取得・保存・比較・TCO・履歴・商標・Affiliateを分離
- [x] 確認済み・推定・unknownを明記
- [x] 重要主張に直接公式URLを付与
- [x] Affiliate報酬とdata reuse権を混同していない
- [x] 3社gateを0/3としてfail-closed
- [x] Human Approver用の未送信テンプレートを作成
- [x] 申請、login、メール送信、source取得automationを未実行
