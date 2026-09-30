param(
    [Parameter(Mandatory=$true)][string]$ArtifactDir,
    [string]$Python = 'python',
    [string]$Candidate = 'dusnx-vi-candidate'
)
$ErrorActionPreference = 'Stop'
if ($Candidate -notmatch '^dusnx-vi-[a-z0-9-]+$') { throw 'Use a separate dusnx-vi-* name; never overwrite base.' }
$projectRoot = Split-Path $PSScriptRoot -Parent
$artifactRoot = (Resolve-Path -LiteralPath $ArtifactDir).Path
$env:PYTHONPATH = Join-Path $projectRoot 'python/src'
& $Python (Join-Path $projectRoot 'python/scripts/export_llm.py') verify --root $artifactRoot
if ($LASTEXITCODE -ne 0) { throw 'Artifact checksum validation failed' }
$meta = Get-Content -LiteralPath (Join-Path $artifactRoot 'export_manifest.json') -Raw | ConvertFrom-Json
if ($meta.base_model -ne 'Qwen/Qwen2.5-0.5B-Instruct' -or $meta.base_revision -ne '7ae557604adf67be50417f59c2c2f167def9a775') { throw 'Unexpected base/revision' }
& ollama --version
$tags = Invoke-RestMethod 'http://localhost:11434/api/tags'
if ($tags.models.name -notcontains 'qwen2.5:0.5b') { throw 'Keep base qwen2.5:0.5b installed for rollback first' }
if ($tags.models.name -contains "$($Candidate):latest" -or $tags.models.name -contains $Candidate) { throw 'Candidate exists; use a new name to preserve previous model' }
$gguf = Join-Path $artifactRoot 'dusnx-vi-v1-f16.gguf'
if (-not (Test-Path -LiteralPath $gguf)) {
    $ggufs = @(Get-ChildItem -LiteralPath $artifactRoot -Filter '*.gguf' -File)
    if ($ggufs.Count -eq 1) { $gguf = $ggufs[0].FullName }
    else { throw "Expected a single GGUF file in $artifactRoot, found $($ggufs.Count)" }
}
$stream = [IO.File]::OpenRead($gguf)
try { $magic = New-Object byte[] 4; [void]$stream.Read($magic,0,4) } finally { $stream.Dispose() }
if ([Text.Encoding]::ASCII.GetString($magic) -ne 'GGUF') { throw 'Not a GGUF file' }
# Copy only the native template, parameters and license from installed base; replace FROM.
$baseFile = (& ollama show qwen2.5:0.5b --modelfile) -join "`n"
if ($LASTEXITCODE -ne 0) { throw 'Cannot read installed base template' }
$fromPath = $gguf.Replace('\','/')
if ($fromPath.Contains('"')) { throw 'Unsupported quote in artifact path' }
if ([regex]::Matches($baseFile,'(?m)^FROM .+$').Count -ne 1) { throw 'Expected exactly one FROM in base Modelfile' }
$candidateFile = [regex]::Replace($baseFile,'(?m)^FROM .+$',[System.Text.RegularExpressions.MatchEvaluator]{ param($match) 'FROM "'+$fromPath+'"' })
$modelfile = Join-Path $artifactRoot 'Modelfile.local'
[IO.File]::WriteAllText($modelfile,$candidateFile,[Text.UTF8Encoding]::new($false))
& ollama create $Candidate -f $modelfile
if ($LASTEXITCODE -ne 0) { throw 'Ollama import failed; base remains available' }
& ollama list
& ollama run $Candidate 'Trả lời bằng tiếng Việt: hãy nêu hai lợi ích của việc đọc sách.'
if ($LASTEXITCODE -ne 0) { throw 'Candidate smoke failed' }
Write-Host 'Imported for evaluation only. Run paired Gateway evaluation and human review before changing DUSNX_OLLAMA_MODEL.'
