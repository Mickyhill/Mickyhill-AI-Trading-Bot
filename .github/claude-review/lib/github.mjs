// Minimal GitHub REST client with retries, timeouts and pagination.
// No dependencies: uses the global fetch built into Node 20+.

const RETRYABLE = new Set([408, 429, 500, 502, 503, 504]);

export class GitHubError extends Error {
  constructor(message, status, body) {
    super(message);
    this.name = "GitHubError";
    this.status = status;
    this.body = body;
  }
}

const sleepReal = (ms) => new Promise((r) => setTimeout(r, ms));

export function createClient({
  token,
  apiUrl = "https://api.github.com",
  fetchImpl = globalThis.fetch,
  sleep = sleepReal,
  maxAttempts = 4,
  timeoutMs = 30_000,
  log = () => {},
} = {}) {
  if (!token) throw new Error("GitHub token is required");

  async function request(method, path, { body, accept } = {}) {
    const url = path.startsWith("http") ? path : `${apiUrl}${path}`;
    let lastError;
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      let res;
      try {
        res = await fetchImpl(url, {
          method,
          headers: {
            Authorization: `Bearer ${token}`,
            Accept: accept || "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "claude-pr-review",
            ...(body ? { "Content-Type": "application/json" } : {}),
          },
          body: body ? JSON.stringify(body) : undefined,
          signal: AbortSignal.timeout(timeoutMs),
        });
      } catch (err) {
        lastError = new GitHubError(`${method} ${path} network error: ${err.message}`, 0);
        if (attempt < maxAttempts) {
          await sleep(backoff(attempt));
          continue;
        }
        throw lastError;
      }

      const text = await res.text();
      let data = text;
      try {
        data = text ? JSON.parse(text) : null;
      } catch {
        // non-JSON body (diff, html error page). Keep raw text.
      }

      // Secondary rate limits come back as 403 with a retry hint.
      const secondaryLimit =
        res.status === 403 &&
        (res.headers.get("retry-after") || /secondary rate limit/i.test(text));
      if ((RETRYABLE.has(res.status) || secondaryLimit) && attempt < maxAttempts) {
        const wait = retryAfterMs(res.headers) ?? backoff(attempt);
        log(`GitHub ${method} ${path} -> ${res.status}, retry ${attempt}/${maxAttempts - 1} in ${wait}ms`);
        await sleep(wait);
        continue;
      }
      if (!res.ok) {
        const msg = typeof data === "object" && data?.message ? data.message : String(text).slice(0, 200);
        throw new GitHubError(`${method} ${path} failed: ${res.status} ${msg}`, res.status, data);
      }
      return { data, headers: res.headers };
    }
    throw lastError;
  }

  async function paginate(path, { maxPages = 30 } = {}) {
    const out = [];
    let next = `${path}${path.includes("?") ? "&" : "?"}per_page=100`;
    for (let page = 0; next && page < maxPages; page++) {
      const { data, headers } = await request("GET", next);
      if (Array.isArray(data)) out.push(...data);
      next = parseNextLink(headers.get("link"));
    }
    return out;
  }

  return { request, paginate };
}

function backoff(attempt) {
  return Math.min(30_000, 1000 * 2 ** (attempt - 1));
}

function retryAfterMs(headers) {
  const ra = headers.get("retry-after");
  if (ra && /^\d+$/.test(ra)) return Math.min(60_000, Number(ra) * 1000);
  const reset = headers.get("x-ratelimit-reset");
  const remaining = headers.get("x-ratelimit-remaining");
  if (remaining === "0" && reset) {
    const ms = Number(reset) * 1000 - Date.now();
    if (ms > 0) return Math.min(60_000, ms);
  }
  return null;
}

function parseNextLink(link) {
  if (!link) return null;
  const m = link.split(",").map((s) => s.trim()).find((s) => s.endsWith('rel="next"'));
  return m ? m.slice(m.indexOf("<") + 1, m.indexOf(">")) : null;
}
