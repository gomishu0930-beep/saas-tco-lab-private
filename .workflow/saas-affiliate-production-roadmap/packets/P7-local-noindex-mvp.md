# P7 Local noindex MVP

- Objective: 実データ・実Affiliate URL・公開URLなしで、公開前MVPの画面、release artifact、serve-time expiry、CTA redaction、robots/security header、health、rollback faultをlocalに再現する。
- Owner: Integration/Release。
- Ownership: `site/`、preview contract/rendering、local site/runtime integration tests、schema/docs、P7 result。
- Do: canonical Python TCO outputだけを表示入力にする。region/tax/currency/commitment、適合理由、根拠/更新/期限、方法論、広告表示を構造化する。data/rights/affiliateをrequest時刻でfail-closed。noindexをHTML/header/robotsで三重化する。
- Do not: 実vendor price、実Affiliate URL、公開domain、Sites project作成、hosting/deploy、external analytics、credential、browser tracking、UI側TCO再計算。
- Expected output: responsive multi-route local site、release bundle hash、pure serve response、local build、synthetic E2E/fault tests。
- Verification: expiry boundary、CTA mismatch/redaction、artifact tamper、unknown route/method、robots、CSP、accessibility landmarks、mobile build、rollbackをnetworkなしfixtureで検証する。
