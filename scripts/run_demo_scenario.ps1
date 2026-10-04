param(
  [string]$GatewayUrl = 'http://127.0.0.1:8080',
  [string]$OutputDir = 'runtime/post-week4-demo'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$checkpoint = Join-Path $root 'training-results/colab-run-01/extracted/dusnx-router-full-01/router.pt'
$expectedHash = '56f56e6d61afc264fb02d690d2872fb3ac5db9749a659c8493fd9d99eab7e7b1'
$health = Invoke-RestMethod "$GatewayUrl/v1/health"
if ($health.service -ne 'dusnx-ai-api' -or !$health.checkpoint_loaded -or $health.runtime_mode -ne 'trained_dusnx') { throw 'DUSN-X trained runtime is not healthy' }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $checkpoint).Hash.ToLowerInvariant() -ne $expectedHash) { throw 'Checkpoint hash mismatch' }
if (!$health.provider_ok -or $health.provider.configured_model -ne 'qwen2.5:0.5b') { throw 'Ollama/base model is unavailable' }

$suffix = [guid]::NewGuid().ToString('N').Substring(0,12)
$username = "demo_$suffix"; $password = "Demo-$suffix-A9!"
Invoke-RestMethod "$GatewayUrl/v1/auth/register" -Method Post -ContentType application/json -Body (@{username=$username;password=$password}|ConvertTo-Json) | Out-Null
$login = Invoke-RestMethod "$GatewayUrl/v1/auth/login" -Method Post -ContentType application/json -Body (@{username=$username;password=$password}|ConvertTo-Json)
$headers = @{Authorization="Bearer $($login.token)"}
function New-Session($title) { Invoke-RestMethod "$GatewayUrl/v1/sessions" -Method Post -Headers $headers -ContentType application/json -Body (@{title=$title}|ConvertTo-Json) }
function Send-Chat($sid,$text,$id) {
  $json = @{session_id=$sid;message=$text;request_id=$id;preferred_language='auto'} | ConvertTo-Json
  Invoke-RestMethod "$GatewayUrl/v1/chat" -Method Post -Headers $headers -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($json))
}
$session = New-Session 'Post Week 4 demo'
$saved = Send-Chat $session.session_id 'Hãy nhớ quyết định: dùng PostgreSQL cho dự án Atlas.' "demo-$suffix-save"
$proposal = Send-Chat $session.session_id 'Hãy đổi quyết định PostgreSQL của dự án Atlas thành MySQL.' "demo-$suffix-propose"
$confirmed = Send-Chat $session.session_id 'Đồng ý.' "demo-$suffix-confirm"
$newSession = New-Session 'Recall demo'
$recall = Send-Chat $newSession.session_id 'Quyết định cơ sở dữ liệu của dự án Atlas là gì?' "demo-$suffix-recall"
$ambiguous = Send-Chat $newSession.session_id 'Hãy đổi quyết định đó.' "demo-$suffix-ambiguous"
$memories = Invoke-RestMethod "$GatewayUrl/v1/memories" -Headers $headers
$evidence = [ordered]@{
  generated_at=(Get-Date).ToUniversalTime().ToString('o'); service=$health.service; runtime_mode=$health.runtime_mode
  checkpoint_loaded=$health.checkpoint_loaded; checkpoint_sha256=$expectedHash; configured_model=$health.provider.configured_model
  synthetic_user=$username; token_persisted=$false; session_ids=@($session.session_id,$newSession.session_id)
  steps=@(
    @{name='save';intent=$saved.intent;response_source=$saved.response_source},
    @{name='propose';intent=$proposal.intent;next_action=$proposal.next_action},
    @{name='confirm';intent=$confirmed.intent;memory_ids_used=$confirmed.memory_ids_used},
    @{name='new_session_recall';intent=$recall.intent;memory_ids_used=$recall.memory_ids_used},
    @{name='ambiguous';intent=$ambiguous.intent;next_action=$ambiguous.next_action}
  ); active_memories=@($memories | Where-Object is_active | ForEach-Object { @{memory_id=$_.memory_id;info_type=$_.info_type;version=$_.version} })
}
$target = Join-Path $root $OutputDir; New-Item -ItemType Directory -Force -Path $target | Out-Null
$evidence | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 (Join-Path $target 'demo.json')
$evidence | ConvertTo-Json -Depth 8
