<#
.SYNOPSIS
  Launch Claude Code (Windows) with telemetry content capture for this launch only.
.DESCRIPTION
  Sets the four OTEL_LOG_* content flags; -Detailed also sets ENABLE_BETA_TRACING_DETAILED and
  BETA_TRACING_ENDPOINT (from OTEL_EXPORTER_OTLP_ENDPOINT, else http://localhost:4318). Previous values
  are restored on exit. -Detailed can go anywhere in the arguments. Arguments pass straight through via $args: a param() block with [Parameter]
  attributes would make PowerShell treat claude's -p as ambiguous with its common parameters.
.EXAMPLE
  pwsh -File .\launchers\claude-traced.ps1 -Detailed -p "prompt"
#>
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
  Write-Error 'claude not found on PATH; install Claude Code first'
  exit 127
}

# -Detailed may appear anywhere; strip it so claude never sees it.
$Detailed = [bool]($args | Where-Object { $_ -eq '-Detailed' })
$ClaudeArgs = @($args | Where-Object { $_ -ne '-Detailed' })

$vars = [ordered]@{
  OTEL_LOG_USER_PROMPTS        = '1'
  OTEL_LOG_ASSISTANT_RESPONSES = '1'
  OTEL_LOG_TOOL_DETAILS        = '1'
  OTEL_LOG_TOOL_CONTENT        = '1'
}
if ($Detailed) {
  $endpoint = [Environment]::GetEnvironmentVariable('OTEL_EXPORTER_OTLP_ENDPOINT', 'Process')
  if (-not $endpoint) { $endpoint = 'http://localhost:4318' }
  $vars['ENABLE_BETA_TRACING_DETAILED'] = '1'
  $vars['BETA_TRACING_ENDPOINT'] = $endpoint
}

$previous = @{}
foreach ($name in $vars.Keys) {
  $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
  [Environment]::SetEnvironmentVariable($name, $vars[$name], 'Process')
}
try {
  & claude @ClaudeArgs
  exit $LASTEXITCODE
}
finally {
  foreach ($name in $vars.Keys) {
    [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process')
  }
}
