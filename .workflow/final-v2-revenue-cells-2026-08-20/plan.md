# SaaS TCO Lab Final V2 Revenue Cells 14-day Sprint

## Goal

confirmed commission月20万円へ近づく確率を上げるため、2026-08-20〜2026-09-02の最小scopeで、Revenue Cell A（SVR01比較型）とRevenue Cell B（高意図単独型）の収益ファネルを、PII・affiliate URL全文・推測値を保存せず観測できるようにする。

## Success Criteria

- event contractでcalculator result、CTA view、outbound click、CTA eligible sessionを安全に集計できる。
- disabled CTA・不正destination・unknown条件では計測もactivationもfail-closedになる。
- 上位3 vendorのmachine-readable evidence matrixがPydanticで検証される。
- SVR01は1 primary＋最大1 alternative、SVR02〜SVR09は記事意図別にSVR01へ接続される。
- Cell BはSVR04を暫定候補とし、vendorのHuman GOがなければaffiliate CTAを無効のままにする。
- 20記事のindex監査表、配信draft、Option Lane評価表、Human Action Queueを生成する。
- 変更後の`./scripts/check-all.sh`がPASSする。

## Current Context

- branch: `codex/site-funnel-affiliate-ux`
- baseline HEAD: `0b801b69988a4c1a4004e46ea9ac31c3d0817b91`
- dirty tree: tracked 46 files modified、staged 0、複数untracked artifactあり。既存変更は保持する。
- production read-back: sitemap 20/20、公開20記事はHTTP 200 / index,follow / self-canonical。P11はnoindex,follow・CTA無効。
- production SVR01は6 sponsored CTA。本番はローカルの1 primary＋1 alternative変更をまだ含まない。
- deployment commit: public responseからは確認不能のためunknown。
- shared GSC/GA4値は2026-08-19のHuman観測であり、この作業中の再取得値ではない。

## Constraints

- rights model v2、Human editorial path、unknown保持、Pydantic/Python正本、PR先行、runtime destination validationを維持する。
- P11、公開20記事、sitemap、homepage/hub noindexをHuman GOなしに変更しない。
- raw query、PII、Cookie、credential、affiliate URL全文、tracking parameter全文を保存・表示しない。
- commit／push／deploy／GA4管理画面変更／外部投稿は実行しない。
- 新規記事、embed本格実装、大規模rewrite・title変更・schema目的外拡張は行わない。

## Risks

- dirty treeの既存変更と今回scopeが同じsite/worker・article filesに重なる。
- localでPASSしても、exact deployment commitを外部から証明できない。
- GSC page別状態とASPのchannel/deep-link/confirmation periodはHuman画面確認が必要。
- GA4 internal filterがtestのため、既存値は収益証拠にできない。

## Approval Required

- local implementation/test: granted by this instruction.
- commit/push/deploy/index/CTA activation/GA4 admin change/external post: not granted in this instruction.

## Work Packets

1. T1 audit and baseline — complete.
2. T2 safe event contract and aggregate — implement locally.
3. T3 merchant evidence matrix — implement validated derived artifact; unknown remains unknown.
4. T4 Cell A/B and internal funnel — implement fail-closed UI/config/tests.
5. T5 index audit — repository + production facts; GSC columns remain unknown.
6. T6 distribution — drafts only, no external posting.
7. T7 option lane — comparison only, no implementation.

## Integration Policy

- Existing uncommitted work is not reverted or reformatted.
- V2 changes receive a file manifest and are rollbackable by inverse patch before any commit.
- Overlapping files are tested against the full dirty tree; they are not presented as isolated clean-branch changes.

## Verification

- Baseline: `./scripts/check-all.sh` PASS (863 Python, 62 typed site, 22 UI, 1 startup, 18 production).
- After change: focused tests, schema export/diff, full check-all, safe production read-back definitions.

## Reusable Artifacts

- revenue event schema and aggregate contract
- merchant evidence matrix and Human intake
- 20-URL index audit template
- distribution drafts and campaign registry
- Option Lane scorecard
- Human Action Queue
