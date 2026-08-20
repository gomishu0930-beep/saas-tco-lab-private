/** Public-prelaunch allowlist; all data-bearing and operator routes fail closed. */

import {
  handleImageOptimization,
  DEFAULT_DEVICE_SIZES,
  DEFAULT_IMAGE_SIZES,
} from "vinext/server/image-optimization";
import handler from "vinext/server/app-router-entry";
import editorialLaunchState from "../../docs/EDITORIAL_LAUNCH_STATE.json";

interface ProductionEnv {
  ASSETS: Fetcher;
  GA4_ANALYTICS_ENABLED?: string;
  GA4_MEASUREMENT_ID?: string;
  GOOGLE_SITE_VERIFICATION?: string;
  IMPACT_SITE_VERIFICATION?: string;
  INDEX_GO?: string;
  INDEX_APPROVED_ARTICLES?: string;
  INDEX_APPROVED_SERVER_ARTICLES?: string;
  HUB_INDEX_GO?: string;
  INDEX_APPROVED_HUBS?: string;
  SERVER_CTA_APPROVED_SERVER_ARTICLES?: string;
  CTA_GO?: string;
  CTA_APPROVED_PARTNER?: string;
  MANGOOLS_AFFILIATE_APPROVAL_CURRENT?: string;
  MANGOOLS_AFFILIATE_DESTINATION?: string;
  SERVER_CTA_GO?: string;
  A8NET_XSERVER_BUSINESS_AFFILIATE_APPROVAL_CURRENT?: string;
  A8NET_XSERVER_BUSINESS_AFFILIATE_DESTINATION?: string;
  MOSHIMO_LOLIPOP_AFFILIATE_APPROVAL_CURRENT?: string;
  MOSHIMO_LOLIPOP_AFFILIATE_DESTINATION?: string;
  MOSHIMO_CONOHA_WING_AFFILIATE_APPROVAL_CURRENT?: string;
  MOSHIMO_CONOHA_WING_AFFILIATE_DESTINATION?: string;
  MOSHIMO_ONAMAE_SERVER_AFFILIATE_APPROVAL_CURRENT?: string;
  MOSHIMO_ONAMAE_SERVER_AFFILIATE_DESTINATION?: string;
  MOSHIMO_SHIN_RENTAL_SERVER_AFFILIATE_APPROVAL_CURRENT?: string;
  MOSHIMO_SHIN_RENTAL_SERVER_AFFILIATE_DESTINATION?: string;
  VALUECOMMERCE_ABLENET_AFFILIATE_APPROVAL_CURRENT?: string;
  VALUECOMMERCE_ABLENET_AFFILIATE_DESTINATION?: string;
  IMAGES: {
    input(stream: ReadableStream): {
      transform(options: Record<string, unknown>): {
        output(options: {
          format: string;
          quality: number;
        }): Promise<{ response(): Response }>;
      };
    };
  };
}

interface ProductionExecutionContext {
  waitUntil(promise: Promise<unknown>): void;
  passThroughOnException(): void;
}

const BASE_SECURITY_HEADERS = {
  "Cache-Control": "no-store",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
  "X-Robots-Tag": "noindex, nofollow, noarchive, nosnippet",
};

const NOINDEX_FOLLOW_ROBOTS = "noindex, follow, noarchive, nosnippet";

const LEGACY_PUBLIC_HOST = "saas-tco-lab-jp.shukun0930.chatgpt.site";
const CANONICAL_PUBLIC_HOST = "saastcolab.jp";
const CANONICAL_PUBLIC_ORIGIN = `https://${CANONICAL_PUBLIC_HOST}`;

const RESTRICTED_CONTENT_SECURITY_POLICY =
  "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'";

const CONSENT_GATED_ANALYTICS_CONTENT_SECURITY_POLICY =
  "default-src 'self'; script-src 'self' 'unsafe-inline' https://www.googletagmanager.com; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://www.google-analytics.com https://region1.google-analytics.com; connect-src 'self' https://www.google-analytics.com https://region1.google-analytics.com; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'";

const EMBEDDABLE_RESTRICTED_CONTENT_SECURITY_POLICY =
  RESTRICTED_CONTENT_SECURITY_POLICY.replace("frame-ancestors 'none'", "frame-ancestors https:");

const EMBEDDABLE_ANALYTICS_CONTENT_SECURITY_POLICY =
  CONSENT_GATED_ANALYTICS_CONTENT_SECURITY_POLICY.replace("frame-ancestors 'none'", "frame-ancestors https:");

const PUBLIC_ROUTES = new Set([
  "/",
  "/methodology",
  "/disclosure",
  "/pilot",
  "/pilot/annual-vs-monthly",
  "/pilot/migration-cost",
  "/pilot/evidence-method",
  "/pilot/pricing-calculator",
  "/pilot/plan-comparison",
  "/pilot/alternatives",
  "/pilot/small-team-fit",
  "/pilot/enterprise-fit",
  "/pilot/usage-overage",
  "/pilot/addon-cost",
  "/pilot/japan-tax",
  "/pilot/break-even",
  "/about",
  "/operator-information",
  "/privacy",
  "/contact",
  "/advertising-policy",
  "/embed/tco-calculator",
  "/servers/business-server-pricing",
  "/servers/server-renewal-cost",
  "/servers/server-first-year-total",
  "/servers/server-migration-cost",
  "/servers/business-rental-server",
  "/servers/small-business-server",
  "/servers/ec-server-cost",
  "/servers/business-mail-server",
  "/servers/ec-server-requirements",
]);

// Crawling and indexing are separate controls. These public navigation and
// policy routes may be crawled so Googlebot can follow links to approved
// articles, while their response metadata remains noindex, follow.
const CRAWLABLE_NON_ARTICLE_ROUTES = new Set([
  "/",
  "/about",
  "/advertising-policy",
  "/contact",
  "/disclosure",
  "/embed/tco-calculator",
  "/methodology",
  "/operator-information",
  "/pilot",
  "/privacy",
]);

const ARTICLE_PATH_TO_ID = new Map([
  ["/pilot/pricing-calculator", "P01"],
  ["/pilot/plan-comparison", "P02"],
  ["/pilot/alternatives", "P03"],
  ["/pilot/small-team-fit", "P04"],
  ["/pilot/enterprise-fit", "P05"],
  ["/pilot/annual-vs-monthly", "P06"],
  ["/pilot/usage-overage", "P07"],
  ["/pilot/addon-cost", "P08"],
  ["/pilot/migration-cost", "P09"],
  ["/pilot/japan-tax", "P10"],
  ["/pilot/break-even", "P11"],
  ["/pilot/evidence-method", "P12"],
]);

const SERVER_ARTICLE_PATH_TO_ID = new Map([
  ["/servers/business-server-pricing", "SVR01"],
  ["/servers/small-business-server", "SVR02"],
  ["/servers/ec-server-cost", "SVR03"],
  ["/servers/server-first-year-total", "SVR04"],
  ["/servers/server-renewal-cost", "SVR05"],
  ["/servers/server-migration-cost", "SVR06"],
  ["/servers/business-rental-server", "SVR07"],
  ["/servers/ec-server-requirements", "SVR08"],
  ["/servers/business-mail-server", "SVR09"],
]);

const HUB_PATH_TO_ID = new Map([
  ["/", "HOME"],
  ["/pilot", "SEO_TOOLS"],
]);

const SOURCE_APPROVED_HUB_IDS = new Set(
  (editorialLaunchState.index_approved_hubs ?? [])
    .filter((hubId) => /^(?:HOME|SEO_TOOLS)$/.test(hubId)),
);

// Source-level Human editorial approval. Runtime INDEX_GO alone must never
// promote an unreviewed server candidate into the public index. The local
// decision record is the sole source; invalid values fail closed.
const SOURCE_APPROVED_SERVER_ARTICLE_IDS = new Set(
  Object.entries(editorialLaunchState.server_articles ?? {})
    .filter(([, state]) => state === "approved")
    .map(([articleId]) => articleId)
    .filter((articleId) => /^SVR(?:0[1-9]|1[0-9]|20)$/.test(articleId)),
);

// Article-level CTA approval is deliberately narrower than article indexing.
// An index release must never inherit the global partner GO automatically.
const SOURCE_CTA_APPROVED_SERVER_ARTICLE_IDS = new Set(
  (editorialLaunchState.server_cta_approved_articles ?? [])
    .filter((articleId) => /^SVR(?:0[1-9]|1[0-9]|20)$/.test(articleId))
    .filter((articleId) => SOURCE_APPROVED_SERVER_ARTICLE_IDS.has(articleId)),
);

interface IndexApprovalState {
  approvedArticlesValid: boolean;
  approvedServerArticlesValid: boolean;
  approvedHubsValid: boolean;
  hubIndexGateActive: boolean;
  indexGateActive: boolean;
  paths: ReadonlySet<string>;
}

function indexApprovalState(env: ProductionEnv): IndexApprovalState {
  const values = (env.INDEX_APPROVED_ARTICLES ?? "").split(",").map((item) => item.trim()).filter(Boolean);
  const serverValues = (env.INDEX_APPROVED_SERVER_ARTICLES ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  const hubValues = (env.INDEX_APPROVED_HUBS ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  const approvedArticlesValid =
    values.every((item) => /^P(?:0[1-9]|1[0-2])$/.test(item))
    && new Set(values).size === values.length;
  const approvedServerArticlesValid =
    serverValues.every((item) => /^SVR(?:0[1-9]|1[0-9]|20)$/.test(item))
    && new Set(serverValues).size === serverValues.length;
  const approvedHubsValid =
    hubValues.every((item) => /^(?:HOME|SEO_TOOLS)$/.test(item))
    && new Set(hubValues).size === hubValues.length;
  const indexGateActive = env.INDEX_GO?.trim() === "GO";
  const hubIndexGateActive = env.HUB_INDEX_GO?.trim() === "GO";
  if (!indexGateActive || !approvedArticlesValid) {
    return {
      approvedArticlesValid,
      approvedServerArticlesValid,
      approvedHubsValid,
      hubIndexGateActive,
      indexGateActive,
      paths: new Set(),
    };
  }
  const approved = new Set(values);
  const paths = new Set([...ARTICLE_PATH_TO_ID].filter(([, id]) => approved.has(id)).map(([path]) => path));
  if (!approvedServerArticlesValid) {
    return {
      approvedArticlesValid,
      approvedServerArticlesValid,
      approvedHubsValid,
      hubIndexGateActive,
      indexGateActive,
      paths,
    };
  }
  const approvedServers = new Set(serverValues);
  for (const [path, id] of SERVER_ARTICLE_PATH_TO_ID) {
    if (approvedServers.has(id) && SOURCE_APPROVED_SERVER_ARTICLE_IDS.has(id)) paths.add(path);
  }
  if (hubIndexGateActive && approvedHubsValid) {
    const approvedHubs = new Set(hubValues);
    const approvedPilotPaths = [...ARTICLE_PATH_TO_ID]
      .filter(([, id]) => id !== "P11")
      .map(([path]) => path);
    const approvedServerPaths = [...SERVER_ARTICLE_PATH_TO_ID]
      .filter(([, id]) => SOURCE_APPROVED_SERVER_ARTICLE_IDS.has(id))
      .map(([path]) => path);
    for (const [path, id] of HUB_PATH_TO_ID) {
      const requiredPaths = id === "HOME"
        ? [...approvedPilotPaths, ...approvedServerPaths]
        : approvedPilotPaths;
      if (
        approvedHubs.has(id)
        && SOURCE_APPROVED_HUB_IDS.has(id)
        && requiredPaths.every((requiredPath) => paths.has(requiredPath))
      ) paths.add(path);
    }
  }
  return {
    approvedArticlesValid,
    approvedServerArticlesValid,
    approvedHubsValid,
    hubIndexGateActive,
    indexGateActive,
    paths,
  };
}

function robotsTxt(indexPaths: ReadonlySet<string>): string {
  const exactPaths = [...new Set([...CRAWLABLE_NON_ARTICLE_ROUTES, ...indexPaths])]
    .filter((path) => path !== "/")
    .sort();
  return [
    "User-agent: *",
    "Allow: /$",
    "Allow: /assets/",
    "Allow: /favicon.svg$",
    "Allow: /sitemap.xml$",
    ...exactPaths.map((path) => `Allow: ${path}$`),
    "Disallow: /",
    `Sitemap: ${CANONICAL_PUBLIC_ORIGIN}/sitemap.xml`,
    "",
  ].join("\n");
}

function normalizePath(pathname: string): string {
  return pathname === "/" ? pathname : pathname.replace(/\/+$/, "");
}

function securityHeaders(
  analyticsEnabled = false,
  indexable = false,
  embeddable = false,
  followableNoindex = false,
): Record<string, string> {
  return {
    ...BASE_SECURITY_HEADERS,
    "X-Robots-Tag": indexable
      ? "index, follow"
      : followableNoindex
        ? NOINDEX_FOLLOW_ROBOTS
        : BASE_SECURITY_HEADERS["X-Robots-Tag"],
    "Content-Security-Policy": analyticsEnabled
      ? embeddable ? EMBEDDABLE_ANALYTICS_CONTENT_SECURITY_POLICY : CONSENT_GATED_ANALYTICS_CONTENT_SECURITY_POLICY
      : embeddable ? EMBEDDABLE_RESTRICTED_CONTENT_SECURITY_POLICY : RESTRICTED_CONTENT_SECURITY_POLICY,
  };
}

function withSecurityHeaders(
  response: Response,
  analyticsEnabled = false,
  indexable = false,
  embeddable = false,
  followableNoindex = false,
): Response {
  const headers = new Headers(response.headers);
  for (const [name, value] of Object.entries(
    securityHeaders(analyticsEnabled, indexable, embeddable, followableNoindex),
  )) {
    headers.set(name, value);
  }
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

interface RuntimeHeadControls {
  analyticsEnabled: boolean;
  markup: string;
}

interface AffiliateCtaControls {
  approvedPaths: readonly string[];
  destination: string | null;
  enabled: boolean;
}

type ServerAffiliatePartnerId =
  | "a8net-xserver-business"
  | "moshimo-conoha-wing"
  | "moshimo-lolipop-rental-server"
  | "moshimo-onamae-rental-server"
  | "moshimo-shin-rental-server"
  | "valuecommerce-ablenet-shared-server";

interface ServerAffiliatePartnerControl {
  destination: string;
  id: ServerAffiliatePartnerId;
  label: string;
}

interface ServerAffiliateCtaControls {
  enabled: boolean;
  mode: "disabled" | "single" | "comparison";
  partners: readonly ServerAffiliatePartnerControl[];
}

const SERVER_AFFILIATE_PARTNER_IDS: readonly ServerAffiliatePartnerId[] = [
  "a8net-xserver-business",
  "moshimo-conoha-wing",
  "moshimo-lolipop-rental-server",
  "moshimo-onamae-rental-server",
  "moshimo-shin-rental-server",
  "valuecommerce-ablenet-shared-server",
];

const SERVER_AFFILIATE_VENDOR_IDS: Readonly<Record<ServerAffiliatePartnerId, string>> = {
  "a8net-xserver-business": "xserver-business",
  "moshimo-conoha-wing": "conoha-wing",
  "moshimo-lolipop-rental-server": "lolipop-rental-server",
  "moshimo-onamae-rental-server": "onamae-rental-server",
  "moshimo-shin-rental-server": "shin-rental-server",
  "valuecommerce-ablenet-shared-server": "ablenet-shared-server",
};

// The 14-day revenue experiment keeps the already-reviewed SVR01 ordering:
// XServer is the article-specific primary and ConoHa is the only displayed
// alternative. Other approved programs remain in the ledger/runtime but are
// intentionally excluded from this page experiment.
const SERVER_REVENUE_EXPERIMENT_PARTNER_IDS: readonly ServerAffiliatePartnerId[] = [
  "a8net-xserver-business",
  "moshimo-conoha-wing",
];

function consentGatedAnalyticsBootstrap(measurementId: string): string {
  return `<script data-saastco-analytics-consent>(()=>{const m=${JSON.stringify(measurementId)},k="saas_tco_lab_analytics_consent_v1",p=location.pathname;let l=false,q=false;const g=function(){window.dataLayer=window.dataLayer||[];window.dataLayer.push(arguments)},u=()=>location.origin+location.pathname,e=(n,v={})=>g("event",n,{content_path:p,...v}),s=()=>{if(q||document.visibilityState!=="visible")return;q=true;e("qualified_session",{qualification_seconds:30})},o=()=>{if(l)return;l=true;g("consent","default",{analytics_storage:"denied",ad_storage:"denied",ad_user_data:"denied",ad_personalization:"denied",wait_for_update:500});g("consent","update",{analytics_storage:"granted"});g("js",new Date);g("config",m,{send_page_view:false,allow_google_signals:false,allow_ad_personalization_signals:false,page_location:u(),page_referrer:""});const t=document.createElement("script");t.async=true;t.src="https://www.googletagmanager.com/gtag/js?id="+encodeURIComponent(m);t.referrerPolicy="no-referrer";document.head.appendChild(t);e("page_view",{page_location:u(),page_title:document.title});setTimeout(s,30000);document.addEventListener("visibilitychange",s,{passive:true});document.addEventListener("click",t=>{const a=t.target instanceof Element?t.target.closest("a[href],button,[role=button]"):null;if(!a||a.closest("[data-analytics-consent-ui]"))return;if(a instanceof HTMLAnchorElement){if(a.matches("a[data-affiliate-cta-partner],a[data-server-affiliate-cta-partner]"))return;const h=new URL(a.href,location.href);if(h.origin!==location.origin){e("external_link_click",{link_domain:h.hostname});return}}if(a.closest('[data-analytics-scope="comparison"]')||a.getAttribute("data-analytics-event")==="comparison_interaction")e("comparison_interaction",{interaction_type:a.tagName.toLowerCase()})},{passive:true})},c=v=>{localStorage.setItem(k,v);document.querySelector("[data-analytics-consent-banner]")?.remove();if(v==="granted")o()},b=()=>{if(document.querySelector("[data-analytics-consent-banner]"))return;const d=document.createElement("div");d.dataset.analyticsConsentBanner="";d.dataset.analyticsConsentUi="";d.setAttribute("role","dialog");d.setAttribute("aria-label","アクセス解析の同意");d.style.cssText="position:fixed;z-index:2147483647;right:12px;bottom:12px;width:min(420px,calc(100vw - 24px));padding:14px;border:1px solid #1d2420;background:#fff;color:#1d2420;box-shadow:4px 4px 0 #1d2420;font:14px/1.55 system-ui,sans-serif";d.innerHTML='<strong>アクセス解析について</strong><p style="margin:7px 0 10px">改善のため匿名の利用状況を計測します。同意するまでGoogleへの通信は行いません。</p><div style="display:flex;gap:8px;flex-wrap:wrap"><button type="button" data-consent="granted" style="min-height:40px;padding:8px 14px">同意する</button><button type="button" data-consent="denied" style="min-height:40px;padding:8px 14px">拒否する</button></div>';d.addEventListener("click",t=>{const v=t.target instanceof Element?t.target.getAttribute("data-consent"):null;if(v==="granted"||v==="denied")c(v)});document.body.appendChild(d)},r=()=>{let x=document.querySelector("[data-analytics-settings]");if(x)return;x=document.createElement("button");x.type="button";x.dataset.analyticsSettings="";x.dataset.analyticsConsentUi="";x.textContent="アクセス解析設定";x.style.cssText="position:fixed;z-index:2147483646;left:12px;bottom:12px;min-height:36px;padding:6px 9px;border:1px solid #1d2420;background:#fff;color:#1d2420;font:12px system-ui,sans-serif";x.addEventListener("click",b);document.body.appendChild(x)};addEventListener("DOMContentLoaded",()=>{r();const v=localStorage.getItem(k);if(v==="granted")o();else if(v!=="denied")b()},{once:true})})();</script>`;
}

function revenueFunnelMeasurementBootstrap(): string {
  return `<script data-saastco-funnel-measurement>(()=>{const k="saas_tco_lab_analytics_consent_v1",p=location.pathname,w=new WeakSet(),x=new WeakSet(),j=new WeakMap(),h=new Set(["mangools.com","px.a8.net","af.moshimo.com","ck.jp.ap.valuecommerce.com"]),z=new Set(["direct","organic","note","x","partner","internal","unknown"]);let i=null,r=false,q=false;const g=function(){window.dataLayer=window.dataLayer||[];window.dataLayer.push(arguments)},a=()=>document.querySelector("main[data-article-id]"),d=()=>{let c="direct",m="baseline";try{const u=new URL(location.href),hp=new URLSearchParams(u.hash.startsWith("#")?u.hash.slice(1):""),rc=hp.get("ch"),rm=hp.get("cid"),sc=sessionStorage.getItem("saas_tco_lab_channel_v1"),sm=sessionStorage.getItem("saas_tco_lab_campaign_v1");if(rc&&z.has(rc)){c=rc;sessionStorage.setItem("saas_tco_lab_channel_v1",c)}else if(sc&&z.has(sc))c=sc;else if(document.referrer){const rh=new URL(document.referrer).hostname.toLowerCase();c=rh===location.hostname?"internal":/(?:^|\\.)(?:google\\.|bing\\.com$|search\\.yahoo\\.)/.test(rh)?"organic":"unknown"}if(rm&&/^[a-z0-9]+(?:[a-z0-9-]{0,62}[a-z0-9])?$/.test(rm)){m=rm;sessionStorage.setItem("saas_tco_lab_campaign_v1",m)}else if(sm&&/^[a-z0-9]+(?:[a-z0-9-]{0,62}[a-z0-9])?$/.test(sm))m=sm}catch{}let ts="external";try{if(navigator.webdriver)ts="bot";else if(localStorage.getItem("saas_tco_lab_traffic_scope_v1")==="internal")ts="internal"}catch{}let tf=false;try{tf=localStorage.getItem("saas_tco_lab_test_traffic_v1")==="1"}catch{}const root=a();return{article_id:root?.getAttribute("data-article-id")||"unknown",revenue_cell_id:root?.getAttribute("data-revenue-cell-id")||"none",channel:c,campaign_id:m,environment:"production",traffic_scope:ts,test_flag:tf}},e=(n,v={})=>g("event",n,{content_path:p,...d(),...v}),c=t=>t.getAttribute("data-server-cta-position")||t.getAttribute("data-cta-position")||"article_action",y=t=>t.getAttribute("data-vendor-id")||(t.getAttribute("data-affiliate-cta-partner")==="mangools"?"mangools":"unknown"),o=t=>t.getAttribute("data-server-cta-type")||t.getAttribute("data-cta-type")||(t.hasAttribute("data-server-affiliate-cta-partner")?"affiliate_comparison":"saas_affiliate"),v=t=>{if(w.has(t))return;w.add(t);const n={vendor_id:y(t),cta_position:c(t),cta_type:o(t)};e("cta_view",n);try{const s="saas_tco_lab_cta_eligible_v2";if(sessionStorage.getItem(s)!=="1"){sessionStorage.setItem(s,"1");e("cta_eligible_session",{...n,eligibility_rule:"active_cta_view"})}}catch{}},f=t=>{if(x.has(t))return;x.add(t);e("calculator_result_view",{vendor_id:"none",cta_position:"none",cta_type:"none",calculator_kind:"server_zero_input"})},b=()=>{if(localStorage.getItem(k)!=="granted")return;if(!i)i=new IntersectionObserver(es=>es.forEach(en=>{if(!en.isIntersecting)return;const t=en.target;if(t.matches("a[data-affiliate-cta-partner],a[data-server-affiliate-cta-partner]"))v(t);else if(t.matches('[data-server-template-step="result"]'))f(t)}),{threshold:.25});document.querySelectorAll("a[data-affiliate-cta-partner],a[data-server-affiliate-cta-partner]").forEach(t=>i.observe(t));document.querySelectorAll('[data-server-template-step="result"]').forEach(t=>i.observe(t));if(!r){document.addEventListener("click",t=>{if(localStorage.getItem(k)!=="granted")return;const l=t.target instanceof Element?t.target.closest("a[data-affiliate-cta-partner],a[data-server-affiliate-cta-partner]"):null;if(l instanceof HTMLAnchorElement){const u=new URL(l.href,location.href),n=Date.now(),last=j.get(l)||0;if(u.origin===location.origin||!h.has(u.hostname.toLowerCase())||n-last<750)return;j.set(l,n);e("outbound_click",{vendor_id:y(l),cta_position:c(l),cta_type:o(l)});return}const it=t.target instanceof Element?t.target.closest('a[data-analytics-event="server_internal_funnel"]'):null;if(it instanceof HTMLAnchorElement){const u=new URL(it.href,location.href);if(u.origin===location.origin)e("server_internal_funnel",{destination_path:u.pathname})}},{passive:true});r=true}},s=()=>{if(q)return;q=true;queueMicrotask(()=>{q=false;b()})};new MutationObserver(s).observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:["data-affiliate-cta-partner","data-server-affiliate-cta-partner"]});addEventListener("DOMContentLoaded",b,{once:true});b()})();</script>`;
}

function runtimeHeadControls(env: ProductionEnv): RuntimeHeadControls {
  const impactValue = env.IMPACT_SITE_VERIFICATION?.trim();
  const googleValue = env.GOOGLE_SITE_VERIFICATION?.trim();
  const measurementId = env.GA4_MEASUREMENT_ID?.trim().toUpperCase();
  const analyticsEnabled =
    env.GA4_ANALYTICS_ENABLED?.trim().toLowerCase() === "true" &&
    Boolean(measurementId && /^G-[A-Z0-9]{6,20}$/.test(measurementId));
  const markup: string[] = [];

  if (impactValue && /^[a-z0-9-]{16,128}$/i.test(impactValue)) {
    markup.push(
      `<meta name="impact-site-verification" value="${impactValue}">`,
    );
  }
  if (googleValue && /^[a-z0-9_-]{20,128}$/i.test(googleValue)) {
    markup.push(
      `<meta name="google-site-verification" content="${googleValue}">`,
    );
  }
  if (analyticsEnabled && measurementId) {
    markup.push(consentGatedAnalyticsBootstrap(measurementId));
    markup.push(revenueFunnelMeasurementBootstrap());
  }
  return { analyticsEnabled, markup: markup.join("") };
}

function affiliateCtaControls(
  env: ProductionEnv,
  indexPaths: ReadonlySet<string>,
  path: string,
): AffiliateCtaControls {
  if (
    !indexPaths.has(path) ||
    env.CTA_GO?.trim() !== "GO" ||
    env.CTA_APPROVED_PARTNER?.trim().toLowerCase() !== "mangools" ||
    env.MANGOOLS_AFFILIATE_APPROVAL_CURRENT?.trim().toLowerCase() !== "true"
  ) {
    return { approvedPaths: [], destination: null, enabled: false };
  }

  const rawDestination = env.MANGOOLS_AFFILIATE_DESTINATION?.trim();
  if (!rawDestination) return { approvedPaths: [], destination: null, enabled: false };

  try {
    const destination = new URL(rawDestination);
    const approvedHost = destination.hostname.toLowerCase() === "mangools.com";
    const approvedAffiliateId = /^#[a-z0-9]{16,64}$/i.test(destination.hash);
    if (
      destination.protocol !== "https:" ||
      !approvedHost ||
      destination.pathname !== "/" ||
      destination.search !== "" ||
      destination.username !== "" ||
      destination.password !== "" ||
      !approvedAffiliateId
    ) {
      return { approvedPaths: [], destination: null, enabled: false };
    }
    return { approvedPaths: [...indexPaths].sort(), destination: destination.href, enabled: true };
  } catch {
    return { approvedPaths: [], destination: null, enabled: false };
  }
}

function validatedServerAffiliateDestination(
  partnerId: ServerAffiliatePartnerId,
  rawDestination: string | undefined,
): string | null {
  const raw = rawDestination?.trim();
  if (!raw) return null;
  try {
    const destination = new URL(raw);
    if (
      destination.protocol !== "https:"
      || destination.username !== ""
      || destination.password !== ""
      || destination.hash !== ""
      || destination.search === ""
    ) return null;
    if (
      partnerId === "a8net-xserver-business"
      && destination.hostname.toLowerCase() === "px.a8.net"
      && destination.pathname === "/svt/ejp"
    ) return destination.href;
    if (
      partnerId.startsWith("moshimo-")
      && destination.hostname.toLowerCase() === "af.moshimo.com"
      && destination.pathname === "/af/c/click"
      && ["a_id", "p_id", "pc_id", "pl_id"].every((key) => Boolean(destination.searchParams.get(key)))
    ) return destination.href;
    if (
      partnerId === "valuecommerce-ablenet-shared-server"
      && destination.hostname.toLowerCase() === "ck.jp.ap.valuecommerce.com"
      && destination.pathname === "/servlet/referral"
    ) return destination.href;
    return null;
  } catch {
    return null;
  }
}

function serverAffiliateCtaControls(
  env: ProductionEnv,
  indexPaths: ReadonlySet<string>,
  path: string,
): ServerAffiliateCtaControls {
  if (!indexPaths.has(path) || env.CTA_GO?.trim() !== "GO") {
    return { enabled: false, mode: "disabled", partners: [] };
  }
  const articleId = SERVER_ARTICLE_PATH_TO_ID.get(path);
  const approvedArticleValues = (env.SERVER_CTA_APPROVED_SERVER_ARTICLES ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  const approvedArticleValuesValid =
    approvedArticleValues.length > 0
    && approvedArticleValues.every((item) => /^SVR(?:0[1-9]|1[0-9]|20)$/.test(item))
    && new Set(approvedArticleValues).size === approvedArticleValues.length;
  const runtimeApprovedArticles = new Set(approvedArticleValues);
  if (
    !articleId
    || !approvedArticleValuesValid
    || !runtimeApprovedArticles.has(articleId)
    || !SOURCE_CTA_APPROVED_SERVER_ARTICLE_IDS.has(articleId)
  ) {
    return { enabled: false, mode: "disabled", partners: [] };
  }
  const requested = (env.SERVER_CTA_GO ?? "")
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
  if (
    requested.length === 0
    || new Set(requested).size !== requested.length
    || requested.some((item) => !SERVER_AFFILIATE_PARTNER_IDS.includes(item as ServerAffiliatePartnerId))
  ) return { enabled: false, mode: "disabled", partners: [] };

  if (!requested.includes(SERVER_REVENUE_EXPERIMENT_PARTNER_IDS[0])) {
    return { enabled: false, mode: "disabled", partners: [] };
  }
  const experimentRequested = (requested as ServerAffiliatePartnerId[])
    .filter((partnerId) => (
      (SERVER_REVENUE_EXPERIMENT_PARTNER_IDS as readonly ServerAffiliatePartnerId[]).includes(partnerId)
    ));

  const partners: ServerAffiliatePartnerControl[] = [];
  for (const partnerId of experimentRequested) {
    if (partnerId === "a8net-xserver-business") {
      if (env.A8NET_XSERVER_BUSINESS_AFFILIATE_APPROVAL_CURRENT?.trim().toLowerCase() !== "true") continue;
      const destination = validatedServerAffiliateDestination(
        partnerId,
        env.A8NET_XSERVER_BUSINESS_AFFILIATE_DESTINATION,
      );
      if (destination) partners.push({ destination, id: partnerId, label: "XServerビジネス公式サイトを見る" });
      continue;
    }
    if (partnerId === "moshimo-lolipop-rental-server") {
      if (env.MOSHIMO_LOLIPOP_AFFILIATE_APPROVAL_CURRENT?.trim().toLowerCase() !== "true") continue;
      const destination = validatedServerAffiliateDestination(
        partnerId,
        env.MOSHIMO_LOLIPOP_AFFILIATE_DESTINATION,
      );
      if (destination) partners.push({ destination, id: partnerId, label: "ロリポップ！公式サイトを見る" });
      continue;
    }
    if (partnerId === "moshimo-conoha-wing") {
      if (env.MOSHIMO_CONOHA_WING_AFFILIATE_APPROVAL_CURRENT?.trim().toLowerCase() !== "true") continue;
      const destination = validatedServerAffiliateDestination(
        partnerId,
        env.MOSHIMO_CONOHA_WING_AFFILIATE_DESTINATION,
      );
      if (destination) partners.push({ destination, id: partnerId, label: "ConoHa WING公式サイトを見る" });
      continue;
    }
    if (partnerId === "moshimo-onamae-rental-server") {
      if (env.MOSHIMO_ONAMAE_SERVER_AFFILIATE_APPROVAL_CURRENT?.trim().toLowerCase() !== "true") continue;
      const destination = validatedServerAffiliateDestination(
        partnerId,
        env.MOSHIMO_ONAMAE_SERVER_AFFILIATE_DESTINATION,
      );
      if (destination) partners.push({ destination, id: partnerId, label: "お名前.com レンタルサーバー公式サイトを見る" });
      continue;
    }
    if (partnerId === "moshimo-shin-rental-server") {
      if (env.MOSHIMO_SHIN_RENTAL_SERVER_AFFILIATE_APPROVAL_CURRENT?.trim().toLowerCase() !== "true") continue;
      const destination = validatedServerAffiliateDestination(
        partnerId,
        env.MOSHIMO_SHIN_RENTAL_SERVER_AFFILIATE_DESTINATION,
      );
      if (destination) partners.push({ destination, id: partnerId, label: "シンレンタルサーバー公式サイトを見る" });
      continue;
    }
    if (partnerId === "valuecommerce-ablenet-shared-server") {
      if (env.VALUECOMMERCE_ABLENET_AFFILIATE_APPROVAL_CURRENT?.trim().toLowerCase() !== "true") continue;
      const destination = validatedServerAffiliateDestination(
        partnerId,
        env.VALUECOMMERCE_ABLENET_AFFILIATE_DESTINATION,
      );
      if (destination) partners.push({ destination, id: partnerId, label: "ABLENET公式サイトを見る" });
    }
  }
  if (partners[0]?.id !== SERVER_REVENUE_EXPERIMENT_PARTNER_IDS[0]) {
    return { enabled: false, mode: "disabled", partners: [] };
  }
  return {
    enabled: true,
    mode: partners.length >= 2 ? "comparison" : "single",
    partners,
  };
}

function publicCtaCategoryCount(
  env: ProductionEnv,
  indexPaths: ReadonlySet<string>,
): number {
  const seoPath = [...ARTICLE_PATH_TO_ID.keys()].find((path) => indexPaths.has(path));
  const serverPath = [...SERVER_ARTICLE_PATH_TO_ID.keys()].find((path) => indexPaths.has(path));
  return Number(Boolean(seoPath && affiliateCtaControls(env, indexPaths, seoPath).enabled))
    + Number(Boolean(serverPath && serverAffiliateCtaControls(env, indexPaths, serverPath).enabled));
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

async function withPublicHomeState(
  response: Response,
  env: ProductionEnv,
  indexPaths: ReadonlySet<string>,
): Promise<Response> {
  const contentType = response.headers.get("content-type")?.toLowerCase() ?? "";
  if (response.status !== 200 || !contentType.includes("text/html")) return response;

  const originalBody = await response.text();
  const documentEnd = originalBody.lastIndexOf("</html>") + "</html>".length;
  let body = documentEnd >= "</html>".length
    ? originalBody.slice(0, documentEnd)
    : originalBody;
  const hydrationPayload = documentEnd >= "</html>".length
    ? originalBody.slice(documentEnd)
    : "";
  const knownArticlePaths = [
    ...ARTICLE_PATH_TO_ID.keys(),
    ...SERVER_ARTICLE_PATH_TO_ID.keys(),
  ];
  for (const path of knownArticlePaths) {
    if (indexPaths.has(path)) continue;
    const escapedPath = escapeRegExp(path);
    body = body.replace(
      new RegExp(
        `<(article|li)\\b(?=[^>]*data-public-article-path=["']${escapedPath}["'])[^>]*>[\\s\\S]*?<\\/\\1>`,
        "gi",
      ),
      "",
    );
    body = body.replace(
      new RegExp(
        `<a\\b(?=[^>]*data-public-article-link=["']${escapedPath}["'])[^>]*>[\\s\\S]*?<\\/a>`,
        "gi",
      ),
      "",
    );
  }
  const categories = new Set(
    [...indexPaths].map((path) => path.startsWith("/servers/") ? "servers" : "seo_tools"),
  );
  body = body
    .replace(
      /(<dd\b[^>]*data-public-article-count[^>]*>)[\s\S]*?(<\/dd>)/i,
      `$1${indexPaths.size}本$2`,
    )
    .replace(
      /(<dd\b[^>]*data-public-category-count[^>]*>)[\s\S]*?(<\/dd>)/i,
      `$1${categories.size}カテゴリ$2`,
    )
    .replace(
      /(<dd\b[^>]*data-public-cta-category-count[^>]*>)[\s\S]*?(<\/dd>)/i,
      `$1${publicCtaCategoryCount(env, indexPaths)}カテゴリ稼働$2`,
    );
  const openingHead = body.match(/<head(?:\s[^>]*)?>/i);
  if (openingHead?.index !== undefined) {
    const insertionPoint = openingHead.index + openingHead[0].length;
    const approvedPaths = JSON.stringify([...indexPaths].sort()).replaceAll("<", "\\u003c");
    const counts = JSON.stringify({
      articles: indexPaths.size,
      categories: categories.size,
      ctaCategories: publicCtaCategoryCount(env, indexPaths),
    });
    const bootstrap = `<script data-public-home-index-gate>(()=>{const a=new Set(${approvedPaths}),c=${counts};let q=false;const r=()=>{q=false;document.querySelectorAll('[data-public-article-path]').forEach(e=>{if(!a.has(e.getAttribute('data-public-article-path')||''))e.remove()});document.querySelectorAll('[data-public-article-link]').forEach(e=>{if(!a.has(e.getAttribute('data-public-article-link')||''))e.remove()});const u=(s,v)=>{const e=document.querySelector(s);if(e&&e.textContent!==v)e.textContent=v};u('[data-public-article-count]',c.articles+'本');u('[data-public-category-count]',c.categories+'カテゴリ');u('[data-public-cta-category-count]',c.ctaCategories+'カテゴリ稼働')},t=()=>{if(q)return;q=true;queueMicrotask(r)};new MutationObserver(t).observe(document.documentElement,{subtree:true,childList:true});addEventListener('DOMContentLoaded',r,{once:true});r()})();</script>`;
    body = `${body.slice(0, insertionPoint)}${bootstrap}${body.slice(insertionPoint)}`;
  }
  const headers = new Headers(response.headers);
  headers.delete("content-length");
  return new Response(body + hydrationPayload, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

function escapeHtmlAttribute(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function decodeHtmlAttribute(value: string): string {
  return value
    .replaceAll("&quot;", '"')
    .replaceAll("&#39;", "'")
    .replaceAll("&#x27;", "'")
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">")
    .replaceAll("&amp;", "&");
}

function htmlAttribute(tag: string, name: string): string | null {
  const match = tag.match(new RegExp(`\\b${name}=["']([^"']*)["']`, "i"));
  return match ? decodeHtmlAttribute(match[1]) : null;
}

async function withNextReading(
  response: Response,
  indexPaths: ReadonlySet<string>,
  currentPath: string,
): Promise<Response> {
  const contentType = response.headers.get("content-type")?.toLowerCase() ?? "";
  if (
    response.status !== 200
    || !contentType.includes("text/html")
    || !indexPaths.has(currentPath)
  ) return response;

  const body = await response.text();
  const placeholderPattern = /<div\b(?=[^>]*data-next-reading-placeholder=["'][^"']+["'])[^>]*>[\s\S]*?<\/div>/i;
  const placeholder = body.match(placeholderPattern)?.[0];
  if (!placeholder) return new Response(body, response);

  const candidateByPath = new Map([...placeholder.matchAll(/<template\b[^>]*>/gi)]
    .map((match) => ({
      path: htmlAttribute(match[0], "data-next-reading-path"),
      title: htmlAttribute(match[0], "data-next-reading-title"),
      outcome: htmlAttribute(match[0], "data-next-reading-outcome"),
    }))
    .filter((candidate) => (
      candidate.path
      && candidate.title
      && candidate.outcome
      && candidate.path !== currentPath
      && indexPaths.has(candidate.path)
    ))
    .map((candidate) => [candidate.path as string, candidate]));
  const orderedIndexablePaths = [...ARTICLE_PATH_TO_ID.keys()].filter((path) => indexPaths.has(path));
  const currentIndex = orderedIndexablePaths.indexOf(currentPath);
  const rotatedPaths = currentIndex < 0
    ? orderedIndexablePaths
    : [
        ...orderedIndexablePaths.slice(currentIndex + 1),
        ...orderedIndexablePaths.slice(0, currentIndex),
      ];
  const candidates = rotatedPaths
    .map((path) => candidateByPath.get(path))
    .filter((candidate): candidate is { path: string; title: string; outcome: string } => Boolean(candidate))
    .slice(0, 3);
  const replacement = candidates.length
    ? `<section class="shell page-section next-reading" aria-labelledby="runtime-next-reading"><div class="section-heading"><p class="eyebrow">次に読む</p><h2 id="runtime-next-reading">関連する料金記事</h2></div><ul>${candidates.map((candidate) => `<li><a href="${escapeHtmlAttribute(candidate.path as string)}">${escapeHtmlAttribute(candidate.title as string)}</a><span>${escapeHtmlAttribute(candidate.outcome as string)}</span></li>`).join("")}</ul></section>`
    : "";
  const headers = new Headers(response.headers);
  headers.delete("content-length");
  return new Response(body.replace(placeholderPattern, replacement), {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

function affiliateCtaBootstrap(controls: AffiliateCtaControls): string {
  const destination = JSON.stringify(controls.destination).replaceAll("<", "\\u003c");
  const approvedPaths = JSON.stringify(controls.approvedPaths).replaceAll("<", "\\u003c");
  return `<script data-saastco-affiliate-cta>(()=>{const u=${destination},a=new Set(${approvedPaths}),n=()=>location.pathname==="/"?"/":location.pathname.replace(/\\/+$/,""),dt="この記事にはMangoolsのアフィリエイトリンクが含まれます。",st="ACTIVE — MANGOOLS";let q=false,o=null;const r=()=>{q=false;if(!u||!a.has(n()))return;const d=document.querySelector('[data-affiliate-disclosure-status]'),s=document.querySelector('[data-affiliate-cta-state]'),p=document.querySelector('[data-affiliate-cta-placeholder="mangools"]'),x=document.querySelector('a[data-affiliate-cta-partner="mangools"]');if(!d||!s||(!p&&!x))return;const c=p||x;if(!(d.compareDocumentPosition(c)&Node.DOCUMENT_POSITION_FOLLOWING))return;if(d.dataset.affiliateDisclosureStatus!=="enabled")d.dataset.affiliateDisclosureStatus="enabled";if(d.textContent!==dt)d.textContent=dt;if(s.dataset.affiliateCtaState!=="enabled")s.dataset.affiliateCtaState="enabled";if(s.textContent!==st)s.textContent=st;if(p){const l=document.createElement("a");l.className="cta-active";l.dataset.affiliateCtaPartner="mangools";l.dataset.vendorId="mangools";l.dataset.ctaPosition="article_action";l.dataset.ctaType="saas_affiliate";l.href=u;l.target="_blank";l.rel="sponsored noopener noreferrer";l.setAttribute("aria-describedby","article-pr-disclosure");l.textContent="Mangools公式サイトを見る";p.replaceWith(l)}},t=()=>{if(q)return;q=true;queueMicrotask(r)},i=()=>{if(o)return;o=new MutationObserver(t);o.observe(document.documentElement,{subtree:true,childList:true});r()};addEventListener("popstate",t,{passive:true});if(document.readyState==="complete")setTimeout(i,0);else addEventListener("load",()=>setTimeout(i,0),{once:true})})();</script>`;
}

async function withAffiliateCta(
  response: Response,
  controls: AffiliateCtaControls,
): Promise<Response> {
  const contentType = response.headers.get("content-type")?.toLowerCase() ?? "";
  if (!controls.enabled || !controls.destination || response.status !== 200 || !contentType.includes("text/html")) {
    return response;
  }

  const originalBody = await response.text();
  const disclosurePattern = /<span\s+data-affiliate-disclosure-status=["']disabled["']>[^<]*<\/span>/i;
  const statePattern = /<span\s+data-affiliate-cta-state=["']disabled["']>[^<]*<\/span>/i;
  const placeholderPattern = /<span\b(?=[^>]*data-affiliate-cta-placeholder=["']mangools["'])[^>]*>[\s\S]*?<\/span>/i;
  const disclosureMatch = originalBody.match(disclosurePattern);
  const stateMatch = originalBody.match(statePattern);
  const placeholderMatch = originalBody.match(placeholderPattern);
  if (
    disclosureMatch?.index === undefined ||
    stateMatch?.index === undefined ||
    placeholderMatch?.index === undefined ||
    disclosureMatch.index >= placeholderMatch.index ||
    originalBody.match(new RegExp(disclosurePattern.source, "gi"))?.length !== 1 ||
    originalBody.match(new RegExp(statePattern.source, "gi"))?.length !== 1 ||
    originalBody.match(new RegExp(placeholderPattern.source, "gi"))?.length !== 1
  ) {
    return new Response(originalBody, {
      status: response.status,
      statusText: response.statusText,
      headers: response.headers,
    });
  }

  const openingHead = originalBody.match(/<head(?:\s[^>]*)?>/i);
  if (openingHead?.index === undefined) {
    return new Response(originalBody, {
      status: response.status,
      statusText: response.statusText,
      headers: response.headers,
    });
  }
  const insertionPoint = openingHead.index + openingHead[0].length;
  const body = `${originalBody.slice(0, insertionPoint)}${affiliateCtaBootstrap(controls)}${originalBody.slice(insertionPoint)}`;
  const headers = new Headers(response.headers);
  headers.delete("content-length");
  return new Response(body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

async function withServerAffiliateCta(
  response: Response,
  controls: ServerAffiliateCtaControls,
): Promise<Response> {
  const contentType = response.headers.get("content-type")?.toLowerCase() ?? "";
  if (!controls.enabled || response.status !== 200 || !contentType.includes("text/html")) {
    return response;
  }

  const originalBody = await response.text();
  const disclosurePattern = /<span\s+data-affiliate-disclosure-status=["']disabled["']>[^<]*<\/span>/i;
  const statePattern = /<span\s+data-server-affiliate-cta-state=["']disabled["']>[\s\S]*?<\/span>/i;
  const disclosureMatch = originalBody.match(disclosurePattern);
  const stateMatch = originalBody.match(statePattern);
  const placeholderMatches = controls.partners.map((partner) => {
    const pattern = new RegExp(
      `<span\\b(?=[^>]*data-server-affiliate-cta-placeholder=["']${partner.id}["'])[^>]*>[\\s\\S]*?<\\/span>`,
      "i",
    );
    return { match: originalBody.match(pattern), partner, pattern };
  });
  if (
    disclosureMatch?.index === undefined
    || stateMatch?.index === undefined
    || disclosureMatch.index >= stateMatch.index
    || originalBody.match(new RegExp(disclosurePattern.source, "gi"))?.length !== 1
    || originalBody.match(new RegExp(statePattern.source, "gi"))?.length !== 1
    || placeholderMatches.some(({ match, pattern }) => (
      match?.index === undefined
      || disclosureMatch.index! >= match.index
      || originalBody.match(new RegExp(pattern.source, "gi"))?.length !== 1
    ))
  ) {
    return new Response(originalBody, {
      status: response.status,
      statusText: response.statusText,
      headers: response.headers,
    });
  }
  const openingHead = originalBody.match(/<head(?:\s[^>]*)?>/i);
  if (openingHead?.index === undefined) {
    return new Response(originalBody, {
      status: response.status,
      statusText: response.statusText,
      headers: response.headers,
    });
  }
  const runtimePartners = controls.partners.map((partner) => ({
    destination: partner.destination,
    id: partner.id,
    label: partner.label,
    position: partner.id === SERVER_REVENUE_EXPERIMENT_PARTNER_IDS[0] ? "primary" : "alternative",
    vendorId: SERVER_AFFILIATE_VENDOR_IDS[partner.id],
  }));
  const serializedPartners = JSON.stringify(runtimePartners).replaceAll("<", "\\u003c");
  const serializedMode = JSON.stringify(controls.mode);
  const bootstrap = `<script data-saastco-server-affiliate-cta>(()=>{const ps=${serializedPartners},m=${serializedMode},dt="この記事には承認済みサーバーサービスのアフィリエイトリンクが含まれます。",st="ACTIVE — "+m.toUpperCase();let q=false,o=null;const r=()=>{q=false;const d=document.querySelector('[data-affiliate-disclosure-status]'),s=document.querySelector('[data-server-affiliate-cta-state]'),c=document.querySelector('[data-server-cta-mode]');if(!d||!s||!c||!ps.length)return;const ns=ps.map(p=>document.querySelector('[data-server-affiliate-cta-placeholder="'+p.id+'"]')||document.querySelector('a[data-server-affiliate-cta-partner="'+p.id+'"]'));if(ns.some(n=>!n)||ns.some(n=>!(d.compareDocumentPosition(n)&Node.DOCUMENT_POSITION_FOLLOWING)))return;if(d.dataset.affiliateDisclosureStatus!=="enabled")d.dataset.affiliateDisclosureStatus="enabled";if(d.textContent!==dt)d.textContent=dt;if(s.dataset.serverAffiliateCtaState!=="enabled")s.dataset.serverAffiliateCtaState="enabled";if(s.textContent!==st)s.textContent=st;if(c.dataset.serverCtaMode!==m)c.dataset.serverCtaMode=m;ps.forEach((p,i)=>{const n=ns[i];if(n instanceof HTMLAnchorElement)return;const a=document.createElement("a");a.className="cta-active";a.dataset.serverAffiliateCtaPartner=p.id;a.dataset.vendorId=p.vendorId;a.dataset.serverCtaPosition=p.position;a.dataset.serverCtaType="affiliate_comparison";a.href=p.destination;a.target="_blank";a.rel="sponsored noopener noreferrer";a.setAttribute("aria-describedby","article-pr-disclosure");a.textContent=p.label;n.replaceWith(a)})},t=()=>{if(q)return;q=true;queueMicrotask(r)},i=()=>{if(o)return;o=new MutationObserver(t);o.observe(document.documentElement,{subtree:true,childList:true});r()};addEventListener("popstate",t,{passive:true});if(document.readyState==="complete")setTimeout(i,0);else addEventListener("load",()=>setTimeout(i,0),{once:true})})();</script>`;
  const insertionPoint = openingHead.index + openingHead[0].length;
  const body = `${originalBody.slice(0, insertionPoint)}${bootstrap}${originalBody.slice(insertionPoint)}`;
  const headers = new Headers(response.headers);
  headers.delete("content-length");
  return new Response(body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

async function withRuntimeHeadControls(
  response: Response,
  controls: RuntimeHeadControls,
  indexable: boolean,
  followableNoindex: boolean,
  canonicalPath: string,
): Promise<Response> {
  const contentType = response.headers.get("content-type")?.toLowerCase() ?? "";
  if (
    response.status !== 200 ||
    !contentType.includes("text/html") ||
    (!controls.markup && !indexable && !followableNoindex)
  ) {
    return response;
  }

  let body = await response.text();
  if (indexable) {
    body = body.replace(
      /<meta\s+name=["']robots["'][^>]*>/i,
      '<meta name="robots" content="index, follow">',
    );
  } else if (followableNoindex) {
    body = body.replace(
      /<meta\s+name=["']robots["'][^>]*>/i,
      `<meta name="robots" content="${NOINDEX_FOLLOW_ROBOTS}">`,
    );
  }
  const openingHead = body.match(/<head(?:\s[^>]*)?>/i);
  if (openingHead?.index === undefined) return response;

  const insertionPoint = openingHead.index + openingHead[0].length;
  const canonicalMarkup = indexable
    ? `<link rel="canonical" href="${CANONICAL_PUBLIC_ORIGIN}${canonicalPath}">`
    : "";
  const headers = new Headers(response.headers);
  headers.delete("content-length");
  return new Response(
    `${body.slice(0, insertionPoint)}${canonicalMarkup}${controls.markup}${body.slice(insertionPoint)}`,
    {
      status: response.status,
      statusText: response.statusText,
      headers,
    },
  );
}

function sitemapXml(indexPaths: ReadonlySet<string>): string {
  const urls = [...indexPaths]
    .map((path) => `  <url><loc>${CANONICAL_PUBLIC_ORIGIN}${path}</loc></url>`)
    .join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`;
}

function embedLoaderScript(requestUrl: string): string {
  const origin = new URL(requestUrl).origin;
  const iframeUrl = `${origin}/embed/tco-calculator`;
  return `(()=>{const s=document.currentScript;if(!s)return;const f=document.createElement("iframe");f.src=${JSON.stringify(iframeUrl)};f.title="SaaS TCO Lab 12か月TCO計算機";f.loading="lazy";f.referrerPolicy="no-referrer";f.style.cssText="width:100%;height:"+(s.dataset.height||"760")+"px;border:0;display:block";s.insertAdjacentElement("afterend",f)})();`;
}

const worker = {
  async fetch(
    request: Request,
    env: ProductionEnv,
    ctx: ProductionExecutionContext,
  ): Promise<Response> {
    const url = new URL(request.url);
    const runtimeControls = runtimeHeadControls(env);
    const normalizedPath = normalizePath(url.pathname);
    const indexApproval = indexApprovalState(env);
    const indexPaths = indexApproval.paths;
    const articleIndexPaths = new Set(
      [...indexPaths].filter((path) => (
        ARTICLE_PATH_TO_ID.has(path) || SERVER_ARTICLE_PATH_TO_ID.has(path)
      )),
    );
    const indexable = url.search === "" && indexPaths.has(normalizedPath);
    const serverArticleId = SERVER_ARTICLE_PATH_TO_ID.get(normalizedPath);
    const followableNoindex = url.search === ""
      && PUBLIC_ROUTES.has(normalizedPath)
      && !indexable
      && (
        serverArticleId === undefined
        || SOURCE_APPROVED_SERVER_ARTICLE_IDS.has(serverArticleId)
      );
    const gatedArticlePath = url.search === "" && articleIndexPaths.has(normalizedPath)
      ? normalizedPath
      : "";
    const ctaControls = affiliateCtaControls(env, articleIndexPaths, gatedArticlePath);
    const serverCtaControls = serverAffiliateCtaControls(env, articleIndexPaths, gatedArticlePath);

    if (url.hostname.toLowerCase() === LEGACY_PUBLIC_HOST) {
      const target = new URL(request.url);
      target.protocol = "https:";
      target.host = CANONICAL_PUBLIC_HOST;
      return new Response(null, {
        status: 301,
        headers: {
          ...securityHeaders(),
          Location: target.toString(),
        },
      });
    }

    if (url.pathname === "/healthz") {
      return new Response("ok\n", {
        status: 200,
        headers: {
          ...securityHeaders(),
          "Content-Type": "text/plain; charset=utf-8",
          "X-Index-Approval-Active": String(indexApproval.indexGateActive),
          "X-Index-Articles-Config-Valid": String(indexApproval.approvedArticlesValid),
          "X-Index-Server-Articles-Config-Valid": String(indexApproval.approvedServerArticlesValid),
          "X-Index-Hubs-Config-Valid": String(indexApproval.approvedHubsValid),
          "X-Index-Hubs-Approval-Active": String(indexApproval.hubIndexGateActive),
        },
      });
    }
    if (url.pathname === "/robots.txt") {
      return new Response(robotsTxt(indexPaths), {
        status: 200,
        headers: { ...securityHeaders(), "Content-Type": "text/plain; charset=utf-8" },
      });
    }
    if (url.pathname === "/sitemap.xml") {
      if (indexPaths.size === 0) {
        return new Response("Service Unavailable\n", {
          status: 503,
          headers: { ...securityHeaders(), "Content-Type": "text/plain; charset=utf-8" },
        });
      }
      return new Response(sitemapXml(indexPaths), {
        status: 200,
        headers: { ...securityHeaders(), "Content-Type": "application/xml; charset=utf-8" },
      });
    }
    if (normalizedPath === "/embed/tco-calculator.js") {
      return new Response(embedLoaderScript(request.url), {
        status: 200,
        headers: {
          ...securityHeaders(),
          "Access-Control-Allow-Origin": "*",
          "Content-Type": "application/javascript; charset=utf-8",
        },
      });
    }
    if (url.pathname.startsWith("/assets/") || url.pathname === "/favicon.svg") {
      return withSecurityHeaders(await env.ASSETS.fetch(request));
    }
    if (url.pathname === "/_vinext/image") {
      const allowedWidths = [...DEFAULT_DEVICE_SIZES, ...DEFAULT_IMAGE_SIZES];
      const response = await handleImageOptimization(
        request,
        {
          fetchAsset: (path) =>
            env.ASSETS.fetch(new Request(new URL(path, request.url))),
          transformImage: async (body, { width, format, quality }) => {
            const result = await env.IMAGES.input(body)
              .transform(width > 0 ? { width } : {})
              .output({ format, quality });
            return result.response();
          },
        },
        allowedWidths,
      );
      return withSecurityHeaders(response);
    }
    if (PUBLIC_ROUTES.has(normalizedPath)) {
      let response = await handler.fetch(request, env, ctx);
      const embeddable = normalizedPath === "/embed/tco-calculator";
      if (normalizedPath === "/") {
        response = await withPublicHomeState(response, env, articleIndexPaths);
      }
      return withSecurityHeaders(
        await withServerAffiliateCta(
          await withAffiliateCta(
            await withNextReading(
              await withRuntimeHeadControls(
                response,
                runtimeControls,
                indexable,
                followableNoindex,
                normalizedPath,
              ),
              gatedArticlePath ? articleIndexPaths : new Set(),
              normalizedPath,
            ),
            ctaControls,
          ),
          serverCtaControls,
        ),
        runtimeControls.analyticsEnabled,
        indexable,
        embeddable,
        followableNoindex,
      );
    }
    return new Response("Service Unavailable\n", {
      status: 503,
      headers: { ...securityHeaders(), "Content-Type": "text/plain; charset=utf-8" },
    });
  },
};

export default worker;
