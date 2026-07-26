/** Public-prelaunch allowlist; all data-bearing and operator routes fail closed. */

import {
  handleImageOptimization,
  DEFAULT_DEVICE_SIZES,
  DEFAULT_IMAGE_SIZES,
} from "vinext/server/image-optimization";
import handler from "vinext/server/app-router-entry";

interface ProductionEnv {
  ASSETS: Fetcher;
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

const SECURITY_HEADERS = {
  "Cache-Control": "no-store",
  "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
  "X-Robots-Tag": "noindex, nofollow, noarchive, nosnippet",
};

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

function withSecurityHeaders(response: Response): Response {
  const headers = new Headers(response.headers);
  for (const [name, value] of Object.entries(SECURITY_HEADERS)) {
    headers.set(name, value);
  }
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

async function withImpactVerificationMeta(
  response: Response,
  verificationValue: string | undefined,
): Promise<Response> {
  const value = verificationValue?.trim();
  const contentType = response.headers.get("content-type")?.toLowerCase() ?? "";
  if (
    response.status !== 200 ||
    !contentType.includes("text/html") ||
    !value ||
    !/^[a-z0-9-]{16,128}$/i.test(value)
  ) {
    return response;
  }

  const body = await response.text();
  const openingHead = body.match(/<head(?:\s[^>]*)?>/i);
  if (openingHead?.index === undefined) return response;

  const meta = `<meta name="impact-site-verification" value="${value}">`;
  const insertionPoint = openingHead.index + openingHead[0].length;
  const headers = new Headers(response.headers);
  headers.delete("content-length");
  return new Response(
    `${body.slice(0, insertionPoint)}${meta}${body.slice(insertionPoint)}`,
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

    if (url.pathname === "/healthz") {
      return new Response("ok\n", {
        status: 200,
        headers: { ...SECURITY_HEADERS, "Content-Type": "text/plain; charset=utf-8" },
      });
    }
    if (url.pathname === "/robots.txt") {
      return new Response("User-agent: *\nDisallow: /\n", {
        status: 200,
        headers: { ...SECURITY_HEADERS, "Content-Type": "text/plain; charset=utf-8" },
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
        await withImpactVerificationMeta(
          response,
          env.IMPACT_SITE_VERIFICATION,
        ),
      );
    }
    return new Response("Service Unavailable\n", {
      status: 503,
      headers: { ...SECURITY_HEADERS, "Content-Type": "text/plain; charset=utf-8" },
    });
  },
};

export default worker;
