#!/usr/bin/env node
/**
 * beforeShellExecution: deny git commit --no-verify (harness anti-bypass).
 * Fail open on parse errors so unrelated commits are not blocked.
 */
const fs = await import("node:fs");

let input = "";
try {
  input = fs.readFileSync(0, "utf8");
} catch {
  process.stdout.write(JSON.stringify({ permission: "allow" }) + "\n");
  process.exit(0);
}

let cmd = "";
try {
  const payload = JSON.parse(input || "{}");
  cmd = String(payload.command || payload.tool_input?.command || "");
} catch {
  process.stdout.write(JSON.stringify({ permission: "allow" }) + "\n");
  process.exit(0);
}

const blocked = /\bgit\s+commit\b/.test(cmd) && /--no-verify\b/.test(cmd);
if (blocked) {
  process.stdout.write(
    JSON.stringify({
      permission: "deny",
      user_message:
        "Blocked: git commit --no-verify is forbidden (docs/harness/anti-bypass.md). Fix make gate / pre-commit instead.",
      agent_message:
        "Do not use --no-verify. Run make gate, fix failures, then commit with hooks enabled. See docs/harness/ops/runbook.md.",
    }) + "\n",
  );
  process.exit(0);
}

process.stdout.write(JSON.stringify({ permission: "allow" }) + "\n");
