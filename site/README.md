# SaaS TCO Lab — local pre-public MVP

Sites/vinextで動く公開前比較UIです。表示値は合成fixtureで、実価格、実Affiliate URL、
credential、external analyticsを含みません。公開・deployはHuman GO後の別工程です。

## Prerequisites

- Node.js `>=22.13.0`

## Quick Start

```bash
npm install
npm run dev
npm test
```

## Safety boundary

- 全routeをnoindexとし、`robots.txt`は全crawlを拒否します。
- UIはTCOを計算せず、`app/lib/synthetic-data.ts`の事前計算済み値だけを表示します。
- release hash、serve-time TTL、CTA redaction、security headerはPython側
  `saas_preflight.mvp`が正本です。
- 公開前fixtureのCTAは常に無効です。
- `npm run dev`と`npm run build:local`だけが`worker/local-preview.ts`の合成fixture UIを使います。
- `npm run build`/`npm run start`はproduction workerを使い、署名検証adapterの別承認までhealth/robots以外を503にします。

## Useful Commands

- `npm run dev`: synthetic-only local previewを起動
- `npm run build:local`: local preview entryをbuild
- `npm run build`: fail-closed production entryをbuild
- `npm test`: local UI/assurance 9件、production起動境界1件、production actual-HTTP boundary 3件を別buildで検証

## Learn More

- [vinext Documentation](https://github.com/cloudflare/vinext)
