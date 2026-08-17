/** Public-prelaunch allowlist; all data-bearing and operator routes fail closed. */

import {
  handleImageOptimization,
  DEFAULT_DEVICE_SIZES,
  DEFAULT_IMAGE_SIZES,
} from "vinext/server/image-optimization";
import handler from "vinext/server/app-router-entry";

interface ProductionEnv {
  ASSETS: Fetcher;
  GA4_ANALYTICS_ENABLED?: string;
  GA4_MEASUREMENT_ID?: string;
  GOOGLE_SITE_VERIFICATION?: string;
  IMPACT_SITE_VERIFICATION?: string;
  INDEX_GO?: string;
  INDEX_APPROVED_ARTICLES?: string;
  INDEX_APPROVED_SERVER_ARTICLES?: string;
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
]);

// Source-level Human editorial approval. Runtime INDEX_GO alone must never
// promote an unreviewed server candidate into the public index.
const SOURCE_APPROVED_SERVER_ARTICLE_IDS = new Set(["SVR01"]);

function approvedIndexPaths(env: ProductionEnv): ReadonlySet<string> {
  if (env.INDEX_GO?.trim() !== "GO") return new Set();
  const values = (env.INDEX_APPROVED_ARTICLES ?? "").split(",").map((item) => item.trim()).filter(Boolean);
  if (values.some((item) => !/^P(?:0[1-9]|1[0-2])$/.test(item)) || new Set(values).size !== values.length) {
    return new Set();
  }
  const approved = new Set(values);
  const paths = new Set([...ARTICLE_PATH_TO_ID].filter(([, id]) => approved.has(id)).map(([path]) => path));
  const serverValues = (env.INDEX_APPROVED_SERVER_ARTICLES ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  if (
    serverValues.some((item) => !/^SVR(?:0[1-9]|1[0-9]|20)$/.test(item))
    || new Set(serverValues).size !== serverValues.length
  ) return paths;
  const approvedServers = new Set(serverValues);
  for (const [path, id] of SERVER_ARTICLE_PATH_TO_ID) {
    if (approvedServers.has(id) && SOURCE_APPROVED_SERVER_ARTICLE_IDS.has(id)) paths.add(path);
  }
  return paths;
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

function consentGatedAnalyticsBootstrap(measurementId: string): string {
  return `<script data-saastco-analytics-consent>(()=>{const m=${JSON.stringify(measurementId)},k="saas_tco_lab_analytics_consent_v1",p=location.pathname;let l=false,q=false;const g=function(){window.dataLayer=window.dataLayer||[];window.dataLayer.push(arguments)},u=()=>location.origin+location.pathname,e=(n,v={})=>g("event",n,{content_path:p,...v}),s=()=>{if(q||document.visibilityState!=="visible")return;q=true;e("qualified_session",{qualification_seconds:30})},o=()=>{if(l)return;l=true;g("consent","default",{analytics_storage:"denied",ad_storage:"denied",ad_user_data:"denied",ad_personalization:"denied",wait_for_update:500});g("consent","update",{analytics_storage:"granted"});g("js",new Date);g("config",m,{send_page_view:false,allow_google_signals:false,allow_ad_personalization_signals:false,page_location:u(),page_referrer:""});const t=document.createElement("script");t.async=true;t.src="https://www.googletagmanager.com/gtag/js?id="+encodeURIComponent(m);t.referrerPolicy="no-referrer";document.head.appendChild(t);e("page_view",{page_location:u(),page_title:document.title});setTimeout(s,30000);document.addEventListener("visibilitychange",s,{passive:true});document.addEventListener("click",t=>{const a=t.target instanceof Element?t.target.closest("a[href],button,[role=button]"):null;if(!a||a.closest("[data-analytics-consent-ui]"))return;if(a instanceof HTMLAnchorElement){const h=new URL(a.href,location.href);if(h.origin!==location.origin){e("outbound_click",{link_domain:h.hostname});return}}if(a.closest('[data-analytics-scope="comparison"]')||a.getAttribute("data-analytics-event")==="comparison_interaction")e("comparison_interaction",{interaction_type:a.tagName.toLowerCase()})},{passive:true})},c=v=>{localStorage.setItem(k,v);document.querySelector("[data-analytics-consent-banner]")?.remove();if(v==="granted")o()},b=()=>{if(document.querySelector("[data-analytics-consent-banner]"))return;const d=document.createElement("div");d.dataset.analyticsConsentBanner="";d.dataset.analyticsConsentUi="";d.setAttribute("role","dialog");d.setAttribute("aria-label","アクセス解析の同意");d.style.cssText="position:fixed;z-index:2147483647;right:12px;bottom:12px;width:min(420px,calc(100vw - 24px));padding:14px;border:1px solid #1d2420;background:#fff;color:#1d2420;box-shadow:4px 4px 0 #1d2420;font:14px/1.55 system-ui,sans-serif";d.innerHTML='<strong>アクセス解析について</strong><p style="margin:7px 0 10px">改善のため匿名の利用状況を計測します。同意するまでGoogleへの通信は行いません。</p><div style="display:flex;gap:8px;flex-wrap:wrap"><button type="button" data-consent="granted" style="min-height:40px;padding:8px 14px">同意する</button><button type="button" data-consent="denied" style="min-height:40px;padding:8px 14px">拒否する</button></div>';d.addEventListener("click",t=>{const v=t.target instanceof Element?t.target.getAttribute("data-consent"):null;if(v==="granted"||v==="denied")c(v)});document.body.appendChild(d)},r=()=>{let x=document.querySelector("[data-analytics-settings]");if(x)return;x=document.createElement("button");x.type="button";x.dataset.analyticsSettings="";x.dataset.analyticsConsentUi="";x.textContent="アクセス解析設定";x.style.cssText="position:fixed;z-index:2147483646;left:12px;bottom:12px;min-height:36px;padding:6px 9px;border:1px solid #1d2420;background:#fff;color:#1d2420;font:12px system-ui,sans-serif";x.addEventListener("click",b);document.body.appendChild(x)};addEventListener("DOMContentLoaded",()=>{r();const v=localStorage.getItem(k);if(v==="granted")o();else if(v!=="denied")b()},{once:true})})();</script>`;
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
  const requested = (env.SERVER_CTA_GO ?? "")
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
  if (
    requested.length === 0
    || new Set(requested).size !== requested.length
    || requested.some((item) => !SERVER_AFFILIATE_PARTNER_IDS.includes(item as ServerAffiliatePartnerId))
  ) return { enabled: false, mode: "disabled", partners: [] };

  const partners: ServerAffiliatePartnerControl[] = [];
  for (const partnerId of requested as ServerAffiliatePartnerId[]) {
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
  if (partners.length === 0) return { enabled: false, mode: "disabled", partners: [] };
  return {
    enabled: true,
    mode: partners.length >= 2 ? "comparison" : "single",
    partners,
  };
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
  return `<script data-saastco-affiliate-cta>(()=>{const u=${destination},a=new Set(${approvedPaths}),n=()=>location.pathname==="/"?"/":location.pathname.replace(/\\/+$/,"");let q=false;const r=()=>{q=false;if(!u||!a.has(n()))return;const d=document.querySelector('[data-affiliate-disclosure-status]'),s=document.querySelector('[data-affiliate-cta-state]'),p=document.querySelector('[data-affiliate-cta-placeholder="mangools"]'),x=document.querySelector('a[data-affiliate-cta-partner="mangools"]');if(!d||!s||(!p&&!x))return;const c=p||x;if(!(d.compareDocumentPosition(c)&Node.DOCUMENT_POSITION_FOLLOWING))return;d.dataset.affiliateDisclosureStatus="enabled";d.textContent="この記事にはMangoolsのアフィリエイトリンクが含まれます。";s.dataset.affiliateCtaState="enabled";s.textContent="ACTIVE — MANGOOLS";if(p){const l=document.createElement("a");l.className="cta-active";l.dataset.affiliateCtaPartner="mangools";l.href=u;l.target="_blank";l.rel="sponsored noopener noreferrer";l.setAttribute("aria-describedby","article-pr-disclosure");l.textContent="Mangools公式サイトを見る";p.replaceWith(l)}},t=()=>{if(q)return;q=true;queueMicrotask(r)};new MutationObserver(t).observe(document.documentElement,{subtree:true,childList:true});addEventListener("popstate",t,{passive:true});addEventListener("DOMContentLoaded",r,{once:true});r()})();</script>`;
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

  const destination = escapeHtmlAttribute(controls.destination);
  let body = originalBody
    .replace(
      disclosurePattern,
      '<span data-affiliate-disclosure-status="enabled">この記事にはMangoolsのアフィリエイトリンクが含まれます。</span>',
    )
    .replace(
      statePattern,
      '<span data-affiliate-cta-state="enabled">ACTIVE — MANGOOLS</span>',
    )
    .replace(
      placeholderPattern,
      `<a class="cta-active" data-affiliate-cta-partner="mangools" href="${destination}" target="_blank" rel="sponsored noopener noreferrer" aria-describedby="article-pr-disclosure">Mangools公式サイトを見る</a>`,
    );
  const openingHead = body.match(/<head(?:\s[^>]*)?>/i);
  if (openingHead?.index === undefined) {
    return new Response(originalBody, {
      status: response.status,
      statusText: response.statusText,
      headers: response.headers,
    });
  }
  const insertionPoint = openingHead.index + openingHead[0].length;
  body = `${body.slice(0, insertionPoint)}${affiliateCtaBootstrap(controls)}${body.slice(insertionPoint)}`;
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

  let body = originalBody
    .replace(
      disclosurePattern,
      '<span data-affiliate-disclosure-status="enabled">この記事には承認済みサーバーサービスのアフィリエイトリンクが含まれます。</span>',
    )
    .replace(
      statePattern,
      `<span data-server-affiliate-cta-state="enabled">ACTIVE — ${controls.mode.toUpperCase()}</span>`,
    )
    .replace(/data-server-cta-mode=["']disabled["']/i, `data-server-cta-mode="${controls.mode}"`);
  for (const { partner, pattern } of placeholderMatches) {
    body = body.replace(
      pattern,
      `<a class="cta-active" data-server-affiliate-cta-partner="${partner.id}" href="${escapeHtmlAttribute(partner.destination)}" target="_blank" rel="sponsored noopener noreferrer" aria-describedby="article-pr-disclosure">${partner.label}</a>`,
    );
  }
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
    const indexPaths = approvedIndexPaths(env);
    const indexable = url.search === "" && indexPaths.has(normalizedPath);
    const followableNoindex = url.search === ""
      && PUBLIC_ROUTES.has(normalizedPath)
      && !ARTICLE_PATH_TO_ID.has(normalizedPath)
      && !SERVER_ARTICLE_PATH_TO_ID.has(normalizedPath);
    const gatedPath = indexable ? normalizedPath : "";
    const ctaControls = affiliateCtaControls(env, indexPaths, gatedPath);
    const serverCtaControls = serverAffiliateCtaControls(env, indexPaths, gatedPath);

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
        headers: { ...securityHeaders(), "Content-Type": "text/plain; charset=utf-8" },
      });
    }
    if (url.pathname === "/robots.txt") {
      const allowed = [...indexPaths].sort().map((path) => `Allow: ${path}$`).join("\n");
      const body = allowed
        ? `User-agent: *\nAllow: /$\nAllow: /assets/\nAllow: /favicon.svg$\nAllow: /sitemap.xml$\n${allowed}\nDisallow: /\nSitemap: ${CANONICAL_PUBLIC_ORIGIN}/sitemap.xml\n`
        : "User-agent: *\nDisallow: /\n";
      return new Response(body, {
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
      const response = await handler.fetch(request, env, ctx);
      const embeddable = normalizedPath === "/embed/tco-calculator";
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
              indexable ? indexPaths : new Set(),
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
