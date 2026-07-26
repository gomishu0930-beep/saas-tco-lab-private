# P7 Result: Local noindex MVP

## Accepted

- `site/`へresponsiveなhome、comparison、methodology、disclosure、readiness、robotsを実装した。
- 表示dataは事前計算済みsynthetic fixtureだけで、実vendor price、実Affiliate URL、analytics、credentialを含まない。
- preview contract v2へregion/tax/billing/commitment/fit/evidence timingを追加し、schemaを再生成した。
- `mvp.py`へcontent-addressed artifact、CTA destination/disclosure hash、serve-time release/TTL、CTA redaction、generic unavailable、robots、health、security headerを実装した。
- UIはTCO算定を行わず、canonical Python結果の表示境界だけを持つ。
- Sites starter skeletonと未使用Drizzleを除去し、Cloudflare/Vite/Wrangler/Nextを安全なcurrent patchへ更新、PostCSS override後に`npm audit` 0件とした。

## Faults closed

- data/rights/affiliateのexact expiryで比較本文・金額・CTAを503へfail-closed。
- manifestとartifact SHA-256が違うcandidateを配信しない。
- destinationまたはdisclosure hash不一致ならCTAだけredact。
- rollback後はcurrent pointerが選ぶartifact以外を停止。
- unknown route、POST、query付き比較、HEAD、health、robotsを安全に処理。
- inactive CTA fixtureへtracking URLや`sponsored` linkを残さない。

## Verification

- Python: 179 tests passed。
- Web: vinext production build、4 rendered-route tests、ESLint合格。
- npm audit: 0 vulnerabilities。
- 12 JSON Schema再生成。
- compileall、uv lock、Gitleaks合格。

## External gate unchanged

公開・hosting・deploy、外部source fetch、Affiliate申請、実URL、domain、account、credential、billingは実行していない。rights 0/3、Affiliate 0/3、JP需要・confirmed EPC・30日shadow実績なしのため、事業判定はSTOPのまま。
