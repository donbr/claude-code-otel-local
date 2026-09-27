#!/usr/bin/env bash
# Launch Claude Code with telemetry *content* capture for this launch only.
#   launchers/claude-traced.sh                 # interactive, content on
#   launchers/claude-traced.sh -p "prompt"     # headless
#   DETAILED=1 launchers/claude-traced.sh -p … # + response text on spans (headless; interactive
#                                              #   sessions need org allowlisting per Claude Code docs)
# Works because user settings leave these keys unset (user settings win over the shell for keys
# they do set). Captured text is stored in plain text, including anything the agent reads.
set -euo pipefail

export OTEL_LOG_USER_PROMPTS=1
export OTEL_LOG_ASSISTANT_RESPONSES=1
export OTEL_LOG_TOOL_DETAILS=1
export OTEL_LOG_TOOL_CONTENT=1

if [[ "${DETAILED:-0}" == "1" ]]; then
  export ENABLE_BETA_TRACING_DETAILED=1
  export BETA_TRACING_ENDPOINT="${OTEL_EXPORTER_OTLP_ENDPOINT:-http://localhost:4318}"
fi

exec claude "$@"
