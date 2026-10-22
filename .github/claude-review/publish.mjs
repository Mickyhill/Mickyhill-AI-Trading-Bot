#!/usr/bin/env node
// Step 2: runs in a separate job that has NO Anthropic credentials.
// Validates Claude's output, posts one PR review with inline comments,
// sets the "Claude PR Review" commit status, and exits non-zero when the
// merge must be blocked. Any failure path ends in a non-success status.

import { readFileSync, existsSync, appendFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createClient, GitHubError } from "./lib/github.mjs";
import { commentableLines } from "./lib/diff.mjs";
import {
  parseReviewOutput,
  decideVerdict,
  placeFindings,
  renderComment,
  renderSummary,
  InvalidReviewOutput,
} from "./lib/findings.mjs";

export const STATUS_CONTEXT = "Claude PR Review";

export async function publish(opts) {
  const {
    client,
    repo,
    prNumber,
    headSha,
    skipReview,
    previousState,
    upstreamOk,
    upstreamError,
    rawOutput,
    files,
    failOn,
    targetUrl,
    log = () => {},
  } = opts;

  if (!/^[0-9a-f]{40}$/.test(headSha || "")) throw new Error(`invalid head sha "${headSha}"`);

  // 1. Same commit already reviewed: re-apply the stored verdict, post nothing.
  if (skipReview && previousState) {
    await setStatus(client, repo, headSha, previousState, "Already reviewed this commit (reused result)", targetUrl);
    log(`Commit already reviewed. Reused state: ${previousState}`);
    return { state: previousState, reused: true, exitCode: previousState === "success" ? 0 : 1 };
  }

  // 2. Validate Claude's output. Missing or malformed output fails closed.
  let review = null;
  let error = null;
  if (!upstreamOk) {
    error = upstreamError || "The Claude review step did not finish (API error, rate limit, or timeout).";
  } else {
    try {
      review = parseReviewOutput(rawOutput);
    } catch (e) {
      if (!(e instanceof InvalidReviewOutput)) throw e;
      error = `Claude returned an unusable result: ${e.message}`;
    }
  }

  if (error) {
    log(`Review incomplete: ${error}`);
    const body = renderSummary({ sha: headSha, error });
    let posted = true;
    try {
      await postReview(client, repo, prNumber, headSha, body, []);
    } catch (e) {
      posted = false;
      log(`Could not post the failure notice: ${e.message}`);
    }
    await setStatus(client, repo, headSha, "error", "Review did not complete. Merge blocked until it runs.", targetUrl);
    return { state: "error", posted, exitCode: 1, error };
  }

  // 3. Verdict comes from severities only. Nothing Claude writes can change it.
  const verdict = decideVerdict(review.findings, failOn);
  const { inline, bodyOnly } = placeFindings(review.findings, commentableLines(files));
  const comments = inline.map((f) => toComment(f));

  let posted = false;
  try {
    await postReview(client, repo, prNumber, headSha, renderSummary({ sha: headSha, review, verdict, bodyOnly }), comments);
    posted = true;
  } catch (e) {
    // 422 usually means GitHub rejected an inline position. Retry with every
    // finding in the review body so nothing is lost.
    if (e instanceof GitHubError && e.status === 422 && comments.length) {
      log(`Inline comments rejected (${e.message}). Retrying with all findings in the summary.`);
      const body = renderSummary({ sha: headSha, review, verdict, bodyOnly: [...inline, ...bodyOnly] });
      try {
        await postReview(client, repo, prNumber, headSha, body, []);
        posted = true;
      } catch (e2) {
        log(`Fallback review failed: ${e2.message}`);
      }
    } else {
      log(`Posting the review failed: ${e.message}`);
    }
  }

  if (!posted) {
    // Findings never reached the PR. Do not let the check look green.
    await setStatus(client, repo, headSha, "error", "Review finished but could not be posted. Re-run the job.", targetUrl);
    return { state: "error", posted: false, exitCode: 1, verdict };
  }

  const c = verdict.counts;
  const desc =
    verdict.state === "failure"
      ? `Blocked: ${c.CRITICAL} critical, ${c.HIGH} high (policy: ${verdict.policy} and above)`
      : `Passed: ${c.MEDIUM} medium, ${c.LOW} low, ${c.INFO} info warnings`;
  await setStatus(client, repo, headSha, verdict.state, desc, targetUrl);
  return {
    state: verdict.state,
    posted,
    exitCode: verdict.state === "success" ? 0 : 1,
    verdict,
    inline: inline.length,
    bodyOnly: bodyOnly.length,
  };
}

function toComment(f) {
  const c = { path: f.path, line: f.line, side: "RIGHT", body: renderComment(f) };
  if (f.endLine) {
    c.start_line = f.line;
    c.start_side = "RIGHT";
    c.line = f.endLine;
  }
  return c;
}

async function postReview(client, repo, prNumber, sha, body, comments) {
  await client.request("POST", `/repos/${repo}/pulls/${prNumber}/reviews`, {
    body: { commit_id: sha, event: "COMMENT", body, comments },
  });
}

async function setStatus(client, repo, sha, state, description, targetUrl) {
  await client.request("POST", `/repos/${repo}/statuses/${sha}`, {
    body: {
      state,
      context: STATUS_CONTEXT,
      description: description.slice(0, 140),
      ...(targetUrl ? { target_url: targetUrl } : {}),
    },
  });
}

async function main() {
  const env = process.env;
  const client = createClient({ token: env.GITHUB_TOKEN, apiUrl: env.GITHUB_API_URL, log: console.log });
  const filesPath = env.FILES_FILE || "pr-review-input/files.json";
  const findingsPath = env.FINDINGS_FILE || "pr-review-input/findings.json";
  const files = existsSync(filesPath) ? JSON.parse(readFileSync(filesPath, "utf8")) : [];
  const rawOutput = existsSync(findingsPath) ? readFileSync(findingsPath, "utf8") : "";
  const upstreamOk = env.REVIEW_JOB_RESULT === "success" && env.CLAUDE_OUTCOME === "success";

  let result;
  try {
    result = await publish({
      client,
      repo: env.GITHUB_REPOSITORY,
      prNumber: Number(env.PR_NUMBER),
      headSha: env.HEAD_SHA,
      skipReview: env.SKIP_REVIEW === "true",
      previousState: env.PREVIOUS_STATE,
      upstreamOk,
      upstreamError: upstreamOk ? null : `review job=${env.REVIEW_JOB_RESULT || "unknown"}, claude step=${env.CLAUDE_OUTCOME || "unknown"}`,
      rawOutput,
      files,
      failOn: env.FAIL_ON,
      targetUrl: env.RUN_URL,
      log: console.log,
    });
  } catch (err) {
    console.error(`::error::Claude review publish failed: ${err.message}`);
    process.exit(1);
  }

  if (env.GITHUB_STEP_SUMMARY) {
    appendFileSync(
      env.GITHUB_STEP_SUMMARY,
      `### Claude PR Review\n\nState: **${result.state}**${result.reused ? " (reused)" : ""}\n\n` +
        (result.verdict ? `Counts: ${JSON.stringify(result.verdict.counts)}\n` : "") +
        (result.error ? `Reason: ${result.error}\n` : ""),
    );
  }
  if (result.exitCode !== 0) {
    console.log(`::error::Claude PR Review result: ${result.state}`);
  }
  process.exit(result.exitCode);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) main();
