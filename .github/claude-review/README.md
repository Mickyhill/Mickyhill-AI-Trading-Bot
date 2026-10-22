# Claude PR Review

Every pull request gets an automatic review from Claude. Findings show up as
inline comments with a severity. A commit status called **Claude PR Review**
passes or fails, and branch protection uses that status to block merges.

Built on the official action `anthropics/claude-code-action@v1`.

## How it works

```
PR opened / new commit / "/claude-review" comment / manual run
        │
        ▼
review job   (read-only token + ANTHROPIC_API_KEY)
  1. prepare.mjs    resolve PR, skip if this commit already has a review,
                    write diff + metadata to pr-review-input/
  2. checkout       PR head into pr-head/ (read only, never executed)
  3. Claude         tools: Read, Grep, Glob only. Returns JSON that must
                    match review-schema.json. One retry after 60s on failure.
        │  artifact: files.json + findings.json
        ▼
publish job  (pull-requests: write, statuses: write, NO Anthropic key)
  4. publish.mjs    validate JSON, compute verdict from severities,
                    post one review with inline comments + summary,
                    set the "Claude PR Review" status
```

## Severity and merge policy

| Severity | Meaning | Default effect |
|---|---|---|
| CRITICAL | Exploitable hole, data loss, auth bypass | Fails the check |
| HIGH | Serious security or functional defect | Fails the check |
| MEDIUM | Real bug, N+1 query, maintainability risk | Warning |
| LOW | Minor issue | Warning |
| INFO | Suggestion, unconfirmed concern | Warning |

HIGH policy is configurable with the repository variable
`CLAUDE_REVIEW_FAIL_ON`:

- `HIGH` (default, also used when the variable is missing or invalid): CRITICAL and HIGH fail.
- `CRITICAL`: only CRITICAL fails. HIGH becomes a warning.

The check never shows green when the review did not finish. Missing API key,
API errors, rate limits, timeouts, malformed output, or a failed comment post
all set the status to `error`, which blocks the merge.

## Setup (one time per repository)

1. Add the API key secret.
   Repo → Settings → Secrets and variables → Actions → New repository secret.
   Name: `ANTHROPIC_API_KEY`. Value: a key from console.anthropic.com.
   Never put the key in a file.

2. Optional: set the HIGH policy.
   Same page → Variables tab → New repository variable.
   Name: `CLAUDE_REVIEW_FAIL_ON`. Value: `HIGH` or `CRITICAL`.

3. Make Actions able to run.
   Settings → Actions → General → "Allow all actions and reusable workflows"
   (or allow `anthropics/claude-code-action`, `actions/checkout`,
   `actions/upload-artifact`, `actions/download-artifact`).
   Under "Fork pull request workflows", keep "Require approval for first-time
   contributors" on.

4. Turn on merge protection.
   Settings → Branches → Add branch ruleset (or classic branch protection rule)
   for `main`:
   - Require a pull request before merging.
   - Require status checks to pass. Add the check **Claude PR Review**.
     It appears in the search box after the workflow has run once on a PR.
   - Require branches to be up to date before merging (recommended).
   - Do not allow bypassing the above settings (recommended, includes admins).

5. Recommended: protect the review tooling itself.
   Add `.github/CODEOWNERS` with the line `/.github/ @Mickyhill` and turn on
   "Require review from Code Owners". A PR from the same repo runs the
   workflow and scripts from its own branch, so this stops a PR from quietly
   editing the reviewer that reviews it.

## Manual review

- Comment `/claude-review` on a PR. Only owners, members and collaborators
  trigger it, and the action re-checks write access.
- `/claude-review force` reviews again even if this commit already has a review.
- Actions tab → Claude PR Review → Run workflow → enter the PR number.

## Pull requests from forks

Fork PRs get no secrets on the `pull_request` event, by GitHub's design. The
`fork-notice` job fails with an explanation and no status is set, so the merge
stays blocked. A maintainer reads the diff, then comments `/claude-review`.
That run uses the base repository's workflow and secrets, checks the fork's
code out into `pr-head/` for reading only, and never runs it. The workflow
never uses `pull_request_target`.

Dependabot PRs behave like fork PRs: use `/claude-review`.

## Security model

- The API key lives only in the `review` job, which has a read-only GitHub token.
- Claude gets Read, Grep and Glob. Bash, file edits and web access are disallowed.
  Claude cannot post anything. The `publish` job posts, and it has no API key.
- PR code is never built, installed or executed.
- All PR content is untrusted. `REVIEW_INSTRUCTIONS.md` tells Claude to treat
  it as data and to report injection attempts as HIGH findings.
- The verdict is computed by `publish.mjs` from severities only. Text Claude
  returns cannot approve a PR. Output is sanitized: HTML comments, fake review
  markers, `<script>` style tags and `@mentions` are stripped.
- Duplicate reviews: each review carries a hidden marker with the commit SHA.
  Only markers written by `github-actions[bot]` count. Re-runs on the same
  commit reuse the stored result. A newer push cancels the older run.
- Step outputs reach shell scripts through environment variables only.
- `show_full_output` and `display_report` stay off so nothing leaks into logs.

## Tests

```
node --test .github/claude-review/tests/*.test.mjs
```

No dependencies, no network, no API key. The `Claude review self-test`
workflow runs them on PRs that change the tooling. They cover the critical
vulnerability, N+1, logic error, clean PR and prompt-injection scenarios, API
failures (5xx, 429, network errors, rejected inline comments, failed posts),
malformed output, the severity matrix, both policies, and dedupe.

The tests check the gate, not the model. For a live check of Claude itself,
use the files in `tests/sample-prs/`: on a test branch, paste each sample into
the target file named at its top, open a PR, and compare the result with the
"Expected" line. For the clean case, open a PR that only edits README.md.

Note: the samples contain deliberate vulnerabilities and an injection
attempt, so the PR that adds this system gets flagged too. That is expected.

## Files

| File | Purpose |
|---|---|
| `.github/workflows/claude-pr-review.yml` | The review workflow |
| `.github/workflows/claude-review-selftest.yml` | Runs the tests |
| `.github/claude-review/REVIEW_INSTRUCTIONS.md` | What Claude checks and how |
| `.github/claude-review/review-schema.json` | Required shape of Claude's output |
| `.github/claude-review/prepare.mjs` | Resolve PR, dedupe, write diff |
| `.github/claude-review/publish.mjs` | Validate, post review, set status |
| `.github/claude-review/lib/*.mjs` | GitHub client, diff and findings logic |
| `.github/claude-review/tests/` | Tests, fixtures, sample PRs |

## Cost and limits

Each review is one Claude Code session billed to your API key, up to 40 turns,
plus one retry on failure. Reviewing every push to a busy PR adds up. Very large
PRs: GitHub omits patches for huge files, so Claude reads those files directly
and some findings land in the summary instead of inline.
