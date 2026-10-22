// Sample PR for a live test of the Claude reviewer.
// Expected: HIGH logic finding (inverted pass check). Check fails with the default policy.
// Target: frontend/src/lib/schedule.js

export function hasPassed(score) {
  return score < 40;
}
