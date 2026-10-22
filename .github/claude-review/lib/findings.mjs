// Validation, normalization, sanitizing and policy for Claude's review output.
// Everything Claude returns is treated as untrusted text: the merge verdict is
// computed here from severities alone, never from anything Claude "says".

export const SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"];
export const CATEGORIES = [
  "security",
  "architecture",
  "logic",
  "database",
  "performance",
  "error-handling",
  "bug",
  "testing",
  "prompt-injection",
];
const RANK = Object.fromEntries(SEVERITIES.map((s, i) => [s, i]));
export const MARKER_PREFIX = "<!-- claude-pr-review";
const MAX_FIELD = 4000;
const MAX_FINDINGS = 50;

export class InvalidReviewOutput extends Error {
  constructor(message) {
    super(message);
    this.name = "InvalidReviewOutput";
  }
}

// Parse the raw structured_output string. Throws InvalidReviewOutput.
export function parseReviewOutput(raw) {
  if (raw == null || String(raw).trim() === "") {
    throw new InvalidReviewOutput("Claude returned no structured output");
  }
  let data;
  try {
    data = typeof raw === "string" ? JSON.parse(raw) : raw;
  } catch (e) {
    throw new InvalidReviewOutput(`structured output is not valid JSON: ${e.message}`);
  }
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    throw new InvalidReviewOutput("structured output must be a JSON object");
  }
  if (!Array.isArray(data.findings)) {
    throw new InvalidReviewOutput("structured output is missing the findings array");
  }
  if (typeof data.summary !== "string") {
    throw new InvalidReviewOutput("structured output is missing the summary string");
  }

  const findings = data.findings.map((f, i) => normalizeFinding(f, i));
  return {
    summary: clean(data.summary),
    filesReviewed: Array.isArray(data.files_reviewed) ? data.files_reviewed.map(normPath).filter(Boolean) : [],
    promptInjectionDetected: data.prompt_injection_detected === true,
    findings: dedupe(findings).sort(bySeverity).slice(0, MAX_FINDINGS),
    truncated: findings.length > MAX_FINDINGS,
  };
}

function normalizeFinding(f, i) {
  const where = `findings[${i}]`;
  if (!f || typeof f !== "object") throw new InvalidReviewOutput(`${where} is not an object`);
  const severity = String(f.severity ?? "").trim().toUpperCase();
  if (!SEVERITIES.includes(severity)) {
    throw new InvalidReviewOutput(`${where} has unknown severity "${f.severity}"`);
  }
  const category = String(f.category ?? "").trim().toLowerCase();
  if (!CATEGORIES.includes(category)) {
    throw new InvalidReviewOutput(`${where} has unknown category "${f.category}"`);
  }
  const path = normPath(f.path);
  if (!path) throw new InvalidReviewOutput(`${where} has no file path`);
  const line = Number.isInteger(f.line) && f.line > 0 ? f.line : null;
  if (line === null) throw new InvalidReviewOutput(`${where} has no valid line number`);
  const endLine = Number.isInteger(f.end_line) && f.end_line > line ? f.end_line : null;
  for (const k of ["title", "explanation", "impact", "recommendation"]) {
    if (typeof f[k] !== "string" || !f[k].trim()) {
      throw new InvalidReviewOutput(`${where} is missing "${k}"`);
    }
  }
  return {
    severity,
    category,
    path,
    line,
    endLine,
    title: clean(f.title, 200),
    explanation: clean(f.explanation),
    impact: clean(f.impact),
    recommendation: clean(f.recommendation),
  };
}

// Claude reads the PR head under pr-head/. Report paths relative to the repo root.
export function normPath(p) {
  if (typeof p !== "string") return "";
  let s = p.trim().replace(/\\/g, "/").replace(/^\.\//, "");
  s = s.replace(/^(\/home\/runner\/work\/[^/]+\/[^/]+\/)/, "");
  s = s.replace(/^pr-head\//, "");
  if (s.includes("..") || s.startsWith("/")) return "";
  return s;
}

// Neutralize text so a hostile PR cannot use Claude's output to ping people,
// spoof our dedupe marker, inject HTML, or blow up the comment size.
export function clean(text, max = MAX_FIELD) {
  let s = String(text ?? "");
  s = s.replace(/<!--[\s\S]*?(-->|$)/g, ""); // drop HTML comments, incl. fake markers
  s = s.replace(/claude-pr-review/gi, "claude pr review");
  s = s.replace(/<\/?(script|iframe|img|details|summary|a)\b[^>]*>/gi, "");
  s = s.replace(/(^|[^\w`])@(?=[A-Za-z0-9])/g, "$1@​"); // no @mentions
  if (s.length > max) s = s.slice(0, max) + " …(truncated)";
  return s.trim();
}

function dedupe(findings) {
  const best = new Map();
  for (const f of findings) {
    const key = `${f.path}:${f.line}:${f.category}`;
    const prev = best.get(key);
    if (!prev || RANK[f.severity] < RANK[prev.severity]) best.set(key, f);
  }
  return [...best.values()];
}

function bySeverity(a, b) {
  return RANK[a.severity] - RANK[b.severity] || a.path.localeCompare(b.path) || a.line - b.line;
}

export function countBySeverity(findings) {
  const counts = Object.fromEntries(SEVERITIES.map((s) => [s, 0]));
  for (const f of findings) counts[f.severity]++;
  return counts;
}

// failOn: "CRITICAL" or "HIGH". Anything else falls back to the safer HIGH.
export function resolvePolicy(raw) {
  const v = String(raw || "").trim().toUpperCase();
  return v === "CRITICAL" ? "CRITICAL" : "HIGH";
}

export function decideVerdict(findings, failOn) {
  const policy = resolvePolicy(failOn);
  const counts = countBySeverity(findings);
  const blocking = counts.CRITICAL + (policy === "HIGH" ? counts.HIGH : 0);
  return {
    state: blocking > 0 ? "failure" : "success",
    policy,
    counts,
    blocking,
  };
}

// Split findings into inline comments (line is in the diff) and body-only.
export function placeFindings(findings, commentable) {
  const inline = [];
  const bodyOnly = [];
  for (const f of findings) {
    const lines = commentable.get(f.path);
    if (lines && lines.has(f.line)) {
      const multi = f.endLine && lines.has(f.endLine) && rangeInside(lines, f.line, f.endLine);
      inline.push({ ...f, endLine: multi ? f.endLine : null });
    } else {
      bodyOnly.push(f);
    }
  }
  return { inline, bodyOnly };
}

function rangeInside(lines, a, b) {
  for (let i = a; i <= b; i++) if (!lines.has(i)) return false;
  return true;
}

const LABEL = {
  security: "Security",
  architecture: "Architecture",
  logic: "Logic error",
  database: "Database",
  performance: "Performance",
  "error-handling": "Error handling",
  bug: "Bug",
  testing: "Tests",
  "prompt-injection": "Prompt injection attempt",
};
const ICON = { CRITICAL: "🔴", HIGH: "🟠", MEDIUM: "🟡", LOW: "🔵", INFO: "⚪" };

export function renderComment(f) {
  return [
    `${ICON[f.severity]} **${f.severity}** · ${LABEL[f.category]} · **${f.title}**`,
    "",
    f.explanation,
    "",
    `**Impact:** ${f.impact}`,
    "",
    `**Recommended fix:** ${f.recommendation}`,
  ].join("\n");
}

export function marker(sha, state) {
  return `${MARKER_PREFIX} sha=${sha} state=${state} -->`;
}

export function parseMarker(body) {
  const m = String(body || "").match(/<!-- claude-pr-review sha=([0-9a-f]{40}) state=(success|failure|error) -->/);
  return m ? { sha: m[1], state: m[2] } : null;
}

export function renderSummary({ sha, review, verdict, bodyOnly, error }) {
  const out = [];
  if (error) {
    out.push("## Claude PR Review: did not complete");
    out.push("");
    out.push(`The automated review failed, so this commit is **not** approved by the review check. Reason: ${clean(error, 500)}`);
    out.push("");
    out.push("Comment `/claude-review` on this PR to retry, or review the change manually.");
    out.push("");
    out.push(marker(sha, "error"));
    return out.join("\n");
  }
  const { counts, state, policy } = verdict;
  const head = state === "failure" ? "❌ Merge blocked" : "✅ No blocking findings";
  out.push(`## Claude PR Review: ${head}`);
  out.push("");
  out.push(`Commit \`${sha.slice(0, 7)}\` · Blocking policy: ${policy === "HIGH" ? "CRITICAL and HIGH fail the check" : "only CRITICAL fails the check"}`);
  out.push("");
  out.push("| Severity | Count |");
  out.push("|---|---|");
  for (const s of SEVERITIES) out.push(`| ${ICON[s]} ${s} | ${counts[s]} |`);
  out.push("");
  if (review.promptInjectionDetected) {
    out.push("⚠️ This PR contains text aimed at manipulating the AI reviewer. A human should read the flagged lines.");
    out.push("");
  }
  if (bodyOnly.length) {
    out.push("### Findings outside the changed lines");
    out.push("");
    for (const f of bodyOnly) {
      out.push(`- \`${f.path}:${f.line}\` ${renderComment(f).replace(/\n\n/g, " ").replace(/\n/g, " ")}`);
    }
    out.push("");
  }
  if (review.truncated) {
    out.push("_More than 50 findings were returned. Only the 50 most severe are shown._");
    out.push("");
  }
  out.push("### Summary");
  out.push("");
  out.push(review.summary || "_No summary provided._");
  out.push("");
  out.push("<sub>Automated review by Claude. Findings are advisory except where the policy above blocks the merge.</sub>");
  out.push("");
  out.push(marker(sha, state));
  return out.join("\n");
}
