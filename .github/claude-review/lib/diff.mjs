// Turns the GitHub "list pull request files" response into a reviewable diff
// and a map of lines that accept inline review comments (RIGHT side).

export function buildDiff(files) {
  const parts = [];
  for (const f of files) {
    const header =
      f.status === "renamed" && f.previous_filename
        ? `diff --git a/${f.previous_filename} b/${f.filename}`
        : `diff --git a/${f.filename} b/${f.filename}`;
    parts.push(header);
    parts.push(`# status: ${f.status}, +${f.additions ?? 0} -${f.deletions ?? 0}`);
    if (f.patch) {
      parts.push(`--- a/${f.previous_filename || f.filename}`);
      parts.push(`+++ b/${f.filename}`);
      parts.push(f.patch);
    } else {
      parts.push("# no patch available (binary, too large, or deleted). Read the file directly if needed.");
    }
    parts.push("");
  }
  return parts.join("\n");
}

// Returns Map<path, Set<lineNumber>> of new-file lines present in the patch
// (added or context lines). GitHub only accepts inline comments on these.
export function commentableLines(files) {
  const map = new Map();
  for (const f of files) {
    const lines = new Set();
    if (f.patch && f.status !== "removed") {
      let newLine = 0;
      for (const raw of f.patch.split("\n")) {
        const hunk = raw.match(/^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
        if (hunk) {
          newLine = Number(hunk[1]);
          continue;
        }
        if (raw.startsWith("-") || raw.startsWith("\\")) continue;
        if (raw.startsWith("+") || raw.startsWith(" ")) {
          lines.add(newLine);
          newLine++;
        }
      }
    }
    map.set(f.filename, lines);
  }
  return map;
}
