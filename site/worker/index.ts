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

const LEGACY_PUBLIC_HOST = "saas-tco-lab-jp.shukun0930.chatgpt.site";
const CANONICAL_PUBLIC_HOST = "saastcolab.jp";

const RESTRICTED_CONTENT_SECURITY_POLICY =
  "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'";

const CONSENT_GATED_ANALYTICS_CONTENT_SECURITY_POLICY =
  "default-src 'self'; script-src 'self' 'unsafe-inline' https://www.googletagmanager.com; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://www.google-analytics.com https://region1.google-analytics.com; connect-src 'self' https://www.google-analytics.com https://region1.google-analytics.com; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'";

const PUBLIC_ROUTES = new Set([
  "/",
  "/methodology",
  "/disclosure",
  "/pilot/annual-vs-monthly",
  "/pilot/migration-cost",
  "/pilot/evidence-method",
]);

function normalizePath(pathname: string): string {
  return pathname === "/" ? pathname : pathname.replace(/\/+$/, "");
}

function securityHeaders(analyticsEnabled = false): Record<string, string> {
  return {
    ...BASE_SECURITY_HEADERS,
    "Content-Security-Policy": analyticsEnabled
      ? CONSENT_GATED_ANALYTICS_CONTENT_SECURITY_POLICY
      : RESTRICTED_CONTENT_SECURITY_POLICY,
  };
}

function withSecurityHeaders(
  response: Response,
  analyticsEnabled = false,
): Response {
  const headers = new Headers(response.headers);
  for (const [name, value] of Object.entries(securityHeaders(analyticsEnabled))) {
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

function consentGatedAnalyticsBootstrap(measurementId: string): string {
  return `<script data-saastco-analytics-consent>(()=>{const m=${JSON.stringify(measurementId)},k="saas_tco_lab_analytics_consent_v1",p=location.pathname;let l=false,q=false;const g=function(){window.dataLayer=window.dataLayer||[];window.dataLayer.push(arguments)},u=()=>location.origin+location.pathname,e=(n,v={})=>g("event",n,{content_path:p,...v}),s=()=>{if(q||document.visibilityState!=="visible")return;q=true;e("qualified_session",{qualification_seconds:30})},o=()=>{if(l)return;l=true;g("consent","default",{analytics_storage:"denied",ad_storage:"denied",ad_user_data:"denied",ad_personalization:"denied",wait_for_update:500});g("consent","update",{analytics_storage:"granted"});g("js",new Date);g("config",m,{send_page_view:false,allow_google_signals:false,allow_ad_personalization_signals:false,page_location:u(),page_referrer:""});const t=document.createElement("script");t.async=true;t.src="https://www.googletagmanager.com/gtag/js?id="+encodeURIComponent(m);t.referrerPolicy="no-referrer";document.head.appendChild(t);e("page_view",{page_location:u(),page_title:document.title});setTimeout(s,30000);document.addEventListener("visibilitychange",s,{passive:true});document.addEventListener("click",t=>{const a=t.target instanceof Element?t.target.closest("a[href],button,[role=button]"):null;if(!a||a.closest("[data-analytics-consent-ui]"))return;if(a instanceof HTMLAnchorElement){const h=new URL(a.href,location.href);if(h.origin!==location.origin){e("outbound_click",{link_domain:h.hostname});return}}if(a.closest('[data-analytics-scope="comparison"]')||a.getAttribute("data-analytics-event")==="comparison_interaction")e("comparison_interaction",{interaction_type:a.tagName.toLowerCase()})},{passive:true})},c=v=>{localStorage.setItem(k,v);document.querySelector("[data-analytics-consent-banner]")?.remove();if(v==="granted")o()},b=()=>{if(document.querySelector("[data-analytics-consent-banner]"))return;const d=document.createElement("div");d.dataset.analyticsConsentBanner="";d.dataset.analyticsConsentUi="";d.setAttribute("role","dialog");d.setAttribute("aria-label","アクセス解析の同意");d.style.cssText="position:fixed;z-index:2147483647;right:16px;bottom:16px;max-width:360px;padding:16px;border:1px solid #1d2420;background:#fff;color:#1d2420;box-shadow:4px 4px 0 #1d2420;font:14px/1.55 system-ui,sans-serif";d.innerHTML='<strong>アクセス解析について</strong><p style="margin:8px 0 12px">改善のため匿名の利用状況を計測します。同意するまでGoogleへの通信は行いません。</p><button type="button" data-consent="granted" style="margin-right:8px">同意する</button><button type="button" data-consent="denied">拒否する</button>';d.addEventListener("click",t=>{const v=t.target instanceof Element?t.target.getAttribute("data-consent"):null;if(v==="granted"||v==="denied")c(v)});document.body.appendChild(d)},r=()=>{let x=document.querySelector("[data-analytics-settings]");if(x)return;x=document.createElement("button");x.type="button";x.dataset.analyticsSettings="";x.dataset.analyticsConsentUi="";x.textContent="アクセス解析設定";x.style.cssText="position:fixed;z-index:2147483646;left:12px;bottom:12px;padding:6px 8px;border:1px solid #1d2420;background:#fff;color:#1d2420;font:12px system-ui,sans-serif";x.addEventListener("click",b);document.body.appendChild(x)};addEventListener("DOMContentLoaded",()=>{r();const v=localStorage.getItem(k);if(v==="granted")o();else if(v!=="denied")b()},{once:true})})();</script>`;
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

async function withRuntimeHeadControls(
  response: Response,
  controls: RuntimeHeadControls,
): Promise<Response> {
  const contentType = response.headers.get("content-type")?.toLowerCase() ?? "";
  if (
    response.status !== 200 ||
    !contentType.includes("text/html") ||
    !controls.markup
  ) {
    return response;
  }

  const body = await response.text();
  const openingHead = body.match(/<head(?:\s[^>]*)?>/i);
  if (openingHead?.index === undefined) return response;

  const insertionPoint = openingHead.index + openingHead[0].length;
  const headers = new Headers(response.headers);
  headers.delete("content-length");
  return new Response(
    `${body.slice(0, insertionPoint)}${controls.markup}${body.slice(insertionPoint)}`,
    {
      status: response.status,
      statusText: response.statusText,
      headers,
    },
  );
}

const worker = {
  async fetch(
    request: Request,
    env: ProductionEnv,
    ctx: ProductionExecutionContext,
  ): Promise<Response> {
    const url = new URL(request.url);
    const runtimeControls = runtimeHeadControls(env);

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
      return new Response("User-agent: *\nDisallow: /\n", {
        status: 200,
        headers: { ...securityHeaders(), "Content-Type": "text/plain; charset=utf-8" },
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
    if (PUBLIC_ROUTES.has(normalizePath(url.pathname))) {
      const response = await handler.fetch(request, env, ctx);
      return withSecurityHeaders(
        await withRuntimeHeadControls(response, runtimeControls),
        runtimeControls.analyticsEnabled,
      );
    }
    return new Response("Service Unavailable\n", {
      status: 503,
      headers: { ...securityHeaders(), "Content-Type": "text/plain; charset=utf-8" },
    });
  },
};

export default worker;
