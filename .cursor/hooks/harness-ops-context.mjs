#!/usr/bin/env node
/**
 * sessionStart: inject confirmed harness ops map for agents.
 */
const context = [
  "SYSTEM: zhvault harness ops (confirmed flows).",
  "Read docs/harness/ops/README.md, architecture.md, flows.md, runbook.md before changing backup/--user/deploy/gate.",
  "Regenerate architecture map after src/ structure changes: make docs-arch.",
  "Before claiming done: make gate (docs/harness/verify.md). Never git commit --no-verify (docs/harness/anti-bypass.md).",
  "Other-profile backup: zhvault backup --source people --user <url_token> --json (placeholders only in docs).",
].join("\n");

process.stdout.write(JSON.stringify({ additional_context: context }) + "\n");
