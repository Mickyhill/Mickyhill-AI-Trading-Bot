#!/usr/bin/env node
// Step 1 of the review job. Runs with a READ-ONLY token.
// Resolves the PR, checks whether this exact commit already has a review,
// and writes the diff + metadata Claude will read.

import { mkdirSync, readFileSync, writeFileSync, appendFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { createClient } from "./lib/github.mjs";
import { buildDiff } from "./lib/diff.mjs";
import { parseMarker } from "./lib/findings.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
export const BOT_LOGIN = "github-actions[bot]";

export async function prepare({ client, repo, prNumber, force, outDir }) {
  const { data: pr } = await client.request("GET", `/repos/${repo}/pulls/${prNumber}`);
  if (pr.state !== "open") throw new Error(`PR #${prNumber} is ${pr.state}, nothing to review`);
  const headSha = pr.head.sha;
  const isFork = !!pr.head.repo && pr.head.repo.full_name !== repo;

  // Dedupe: a review we already posted for this exact commit.
  const reviews = await client.paginate(`/repos/${repo}/pulls/${prNumber}/reviews`);
  let previous = null;
  for (const r of reviews) {
    if (r.user?.login !== BOT_LOGIN) continue; // ignore markers typed by humans
    const m = parseMarker(r.body);
    if (m && m.sha === headSha) previous = m;
  }
  const skipReview = !!previous && !force;

  const files = await client.paginate(`/repos/${repo}/pulls/${prNumber}/files`);
  mkdirSync(outDir, { recursive: true });
  writeFileSync(join(outDir, "files.json"), JSON.stringify(files.map(trimFile)));
  writeFileSync(join(outDir, "diff.patch"), buildDiff(files));
  writeFileSync(
    join(outDir, "pr.json"),
    JSON.stringify(
      {
        number: pr.number,
        head_sha: headSha,
        base_ref: pr.base.ref,
        head_ref: pr.head.ref,
        is_fork: isFork,
        changed_files: files.length,
        // Author-controlled text. Claude is told to treat it as data only.
        untrusted_title: pr.title,
        untrusted_body: (pr.body || "").slice(0, 5000),
      },
      null,
      2,
    ),
  );

  return {
    pr_number: String(pr.number),
    head_sha: headSha,
    base_ref: pr.base.ref,
    is_fork: String(isFork),
    skip_review: String(skipReview),
    previous_state: previous ? previous.state : "",
    changed_files: String(files.length),
  };
}

function trimFile(f) {
  return {
    filename: f.filename,
    previous_filename: f.previous_filename,
    status: f.status,
    additions: f.additions,
    deletions: f.deletions,
    patch: f.patch,
  };
}

export function loadSchema() {
  const raw = readFileSync(join(HERE, "review-schema.json"), "utf8");
  const compact = JSON.stringify(JSON.parse(raw));
  if (compact.includes("'")) throw new Error("review-schema.json must not contain single quotes");
  return compact;
}

export function resolvePrNumber(env, event) {
  const n = env.PR_NUMBER || event?.pull_request?.number || event?.issue?.number || event?.inputs?.pr_number;
  const num = Number(n);
  if (!Number.isInteger(num) || num <= 0) throw new Error(`Could not resolve a PR number (got "${n}")`);
  return num;
}

function setOutputs(outputs) {
  const file = process.env.GITHUB_OUTPUT;
  for (const [k, v] of Object.entries(outputs)) {
    const line = `${k}=${String(v).replace(/[\r\n]/g, " ")}\n`;
    if (file) appendFileSync(file, line);
    else process.stdout.write(line);
  }
}

async function main() {
  const env = process.env;
  const event = env.GITHUB_EVENT_PATH ? JSON.parse(readFileSync(env.GITHUB_EVENT_PATH, "utf8")) : {};
  const client = createClient({ token: env.GITHUB_TOKEN, apiUrl: env.GITHUB_API_URL, log: console.log });
  const result = await prepare({
    client,
    repo: env.GITHUB_REPOSITORY,
    prNumber: resolvePrNumber(env, event),
    force: env.FORCE_REVIEW === "true",
    outDir: env.OUT_DIR || "pr-review-input",
  });
  setOutputs({ ...result, json_schema: loadSchema() });
  console.log(
    `PR #${result.pr_number} head=${result.head_sha} fork=${result.is_fork} files=${result.changed_files} skip=${result.skip_review}`,
  );
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  main().catch((err) => {
    console.error(`::error::Claude review prepare failed: ${err.message}`);
    process.exit(1);
  });
}
