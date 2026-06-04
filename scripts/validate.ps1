param(
  [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
  [ValidateSet('template', 'publish')]
  [string]$Mode = 'template'
)

$ErrorActionPreference = 'Stop'

function Resolve-AiPath {
  param(
    [Parameter(Mandatory = $true)][string]$BaseDir,
    [Parameter(Mandatory = $true)][string]$Reference
  )

  $clean = $Reference
  if ($clean -match '_as_') {
    $clean = $clean -replace '_as_.*$', ''
  }
  $clean = $clean -replace '\\', '/'
  $clean = $clean.Trim()

  if ([string]::IsNullOrWhiteSpace($clean)) {
    return $null
  }

  if ($clean -match '^[a-zA-Z]+:') {
    return $null
  }

  return [System.IO.Path]::GetFullPath((Join-Path $BaseDir $clean))
}

function Assert-PathInsideRoot {
  param(
    [Parameter(Mandatory = $true)][string]$RootPath,
    [Parameter(Mandatory = $true)][string]$TargetPath
  )

  $rootFull = [System.IO.Path]::GetFullPath($RootPath).TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
  $targetFull = [System.IO.Path]::GetFullPath($TargetPath)
  $rootWithSeparator = $rootFull + [System.IO.Path]::DirectorySeparatorChar

  if ($targetFull -ne $rootFull -and -not $targetFull.StartsWith($rootWithSeparator, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Reference escapes repository root: $TargetPath"
  }
}

function Assert-FileOrDirectory {
  param(
    [Parameter(Mandatory = $true)][string]$RootPath,
    [Parameter(Mandatory = $true)][string]$TargetPath,
    [Parameter(Mandatory = $true)][string]$Source
  )

  Assert-PathInsideRoot -RootPath $RootPath -TargetPath $TargetPath
  if (-not (Test-Path -LiteralPath $TargetPath)) {
    throw "Broken reference from $Source -> $TargetPath"
  }
}

function Assert-RequiredJsonFields {
  param(
    [Parameter(Mandatory = $true)][object]$JsonObject,
    [Parameter(Mandatory = $true)][string[]]$Fields,
    [Parameter(Mandatory = $true)][string]$Source
  )

  foreach ($field in $Fields) {
    if (-not ($JsonObject.PSObject.Properties.Name -contains $field)) {
      throw "Missing required JSON field '$field' in $Source"
    }
  }
}

function Assert-JsonStringField {
  param(
    [Parameter(Mandatory = $true)][object]$JsonObject,
    [Parameter(Mandatory = $true)][string]$Field,
    [Parameter(Mandatory = $true)][string]$Source
  )

  if (-not ($JsonObject.PSObject.Properties.Name -contains $Field)) {
    throw "Missing string field '$Field' in $Source"
  }
  if (-not ($JsonObject.$Field -is [string]) -or [string]::IsNullOrWhiteSpace($JsonObject.$Field)) {
    throw "Invalid string field '$Field' in $Source"
  }
}

function Assert-JsonStringArrayField {
  param(
    [Parameter(Mandatory = $true)][object]$JsonObject,
    [Parameter(Mandatory = $true)][string]$Field,
    [Parameter(Mandatory = $true)][string]$Source
  )

  if (-not ($JsonObject.PSObject.Properties.Name -contains $Field)) {
    throw "Missing array field '$Field' in $Source"
  }
  if (-not ($JsonObject.$Field -is [array]) -or $JsonObject.$Field.Count -eq 0) {
    throw "Invalid array field '$Field' in $Source"
  }
  foreach ($item in $JsonObject.$Field) {
    if (-not ($item -is [string]) -or [string]::IsNullOrWhiteSpace($item)) {
      throw "Invalid array item in '$Field' in $Source"
    }
  }
}

function Assert-AllowedValue {
  param(
    [Parameter(Mandatory = $true)][string]$Value,
    [Parameter(Mandatory = $true)][string[]]$Allowed,
    [Parameter(Mandatory = $true)][string]$Field,
    [Parameter(Mandatory = $true)][string]$Source
  )

  if ($Allowed -notcontains $Value) {
    throw "Invalid value '$Value' for '$Field' in $Source"
  }
}

function Parse-YamlBlock {
  param(
    [Parameter(Mandatory = $true)][string]$Content,
    [Parameter(Mandatory = $true)][string]$Source
  )

  $match = [regex]::Match($Content, '(?s)```yaml\s*(.*?)\s*```')
  if (-not $match.Success) {
    throw "Missing yaml block in $Source"
  }

  $map = @{}
  foreach ($line in ($match.Groups[1].Value -split "`r?`n")) {
    if ($line -match '^\s*#' -or [string]::IsNullOrWhiteSpace($line)) {
      continue
    }
    if ($line -match '^\s*([A-Za-z0-9_-]+):\s*(.*)\s*$') {
      $key = $matches[1]
      $value = $matches[2].Trim()
      if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
        $value = $value.Substring(1, $value.Length - 2)
      }
      $map[$key] = $value
    }
  }
  return $map
}

function Assert-IsoDateField {
  param(
    [Parameter(Mandatory = $true)][object]$JsonObject,
    [Parameter(Mandatory = $true)][string]$Field,
    [Parameter(Mandatory = $true)][string]$Source
  )

  Assert-JsonStringField -JsonObject $JsonObject -Field $Field -Source $Source
  if ($JsonObject.$Field -notmatch '^\d{4}-\d{2}-\d{2}$') {
    throw "Invalid date field '$Field' in $Source. Expected YYYY-MM-DD."
  }
}

function Assert-NoPublishPlaceholder {
  param(
    [Parameter(Mandatory = $true)][string]$Value,
    [Parameter(Mandatory = $true)][string]$Field,
    [Parameter(Mandatory = $true)][string]$Source
  )

  if ($Value -match 'replace-with|YYYY-MM-DD|Describe what this page covers|Example Page|Replace this') {
    throw "Publish placeholder found in '$Field' in $Source"
  }
}

$Root = (Resolve-Path -LiteralPath $Root).Path
Write-Output "VALIDATION_MODE $Mode"

$isPageBundle = (Test-Path -LiteralPath (Join-Path $Root 'page.html')) -and (Test-Path -LiteralPath (Join-Path $Root 'ai/page.json'))

if ($isPageBundle) {
  Write-Output "VALIDATION_TARGET page_bundle"
  $required = @(
    'page.html',
    'ai/page.json',
    'ai/routes.json',
    'ai/canon.md',
    'ai/evidence',
    'ai/examples.md',
    'ai/changelog.md',
    'ai/tests.md'
  )
} else {
  Write-Output "VALIDATION_TARGET repository"
  $required = @(
    'README.md',
    'SPEC.md',
    'LICENSE',
    'template/page.html',
    'template/ai/page.json',
    'template/ai/routes.json',
    'template/ai/canon.md',
    'template/ai/evidence/EVIDENCE_CARD_TEMPLATE.md',
    'template/ai/evidence/example-card.md',
    'template/ai/examples.md',
    'template/ai/changelog.md',
    'template/ai/tests.md',
    'template/ai/schemas/AI_PAGE_MANIFEST.schema.json',
    'template/ai/schemas/ROUTES.schema.json',
    'template/ai/schemas/EVIDENCE_CARD.schema.json',
    'example/page.html',
    'example/ai/page.json',
    'example/ai/routes.json',
    'example/ai/canon.md',
    'example/ai/evidence/sample-claim.md',
    'example/ai/examples.md',
    'example/ai/changelog.md',
    'example/ai/tests.md'
  )
}

$missing = @()
foreach ($relative in $required) {
  $path = Join-Path $Root $relative
  if (-not (Test-Path -LiteralPath $path)) {
    $missing += $relative
  }
}

if ($missing.Count -gt 0) {
  Write-Error ("Missing required files:`n" + ($missing -join "`n"))
}

$jsonFiles = Get-ChildItem -LiteralPath $Root -Recurse -Filter '*.json' -File
foreach ($file in $jsonFiles) {
  $null = Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json
  Write-Output "JSON_OK $($file.FullName)"
}

$pageFiles = Get-ChildItem -LiteralPath $Root -Recurse -Filter 'page.json' -File
foreach ($pageFile in $pageFiles) {
  if (-not $isPageBundle -and $Mode -eq 'publish' -and $pageFile.FullName -match '\\template\\') {
    continue
  }
  $page = Get-Content -LiteralPath $pageFile.FullName -Raw | ConvertFrom-Json
  $aiDir = Split-Path -Parent $pageFile.FullName

  Assert-RequiredJsonFields -JsonObject $page -Fields @('ai_page_id', 'standard_version', 'human_url', 'title', 'scope', 'last_updated', 'last_verified', 'surfaces', 'answer_policy') -Source $pageFile.FullName
  foreach ($field in @('ai_page_id', 'standard_version', 'human_url', 'title', 'scope', 'last_updated', 'last_verified')) {
    Assert-JsonStringField -JsonObject $page -Field $field -Source $pageFile.FullName
  }
  if ($Mode -eq 'publish') {
    Assert-IsoDateField -JsonObject $page -Field 'last_updated' -Source $pageFile.FullName
    Assert-IsoDateField -JsonObject $page -Field 'last_verified' -Source $pageFile.FullName
    foreach ($field in @('ai_page_id', 'title', 'scope')) {
      Assert-NoPublishPlaceholder -Value $page.$field -Field $field -Source $pageFile.FullName
    }
  }
  Assert-RequiredJsonFields -JsonObject $page.surfaces -Fields @('routes', 'canon', 'evidence', 'examples', 'trace') -Source $pageFile.FullName
  Assert-RequiredJsonFields -JsonObject $page.answer_policy -Fields @('use_as_evidence', 'do_not_use_as_evidence') -Source $pageFile.FullName
  Assert-JsonStringArrayField -JsonObject $page.answer_policy -Field 'use_as_evidence' -Source $pageFile.FullName
  Assert-JsonStringArrayField -JsonObject $page.answer_policy -Field 'do_not_use_as_evidence' -Source $pageFile.FullName

  foreach ($surfaceName in $page.surfaces.PSObject.Properties.Name) {
    $value = $page.surfaces.$surfaceName
    if ($value -is [string]) {
      $target = Resolve-AiPath -BaseDir $aiDir -Reference $value
      if ($null -ne $target) {
        Assert-FileOrDirectory -RootPath $Root -TargetPath $target -Source $pageFile.FullName
      }
    }
  }
}

$routeFiles = Get-ChildItem -LiteralPath $Root -Recurse -Filter 'routes.json' -File
foreach ($routeFile in $routeFiles) {
  if (-not $isPageBundle -and $Mode -eq 'publish' -and $routeFile.FullName -match '\\template\\') {
    continue
  }
  $routes = Get-Content -LiteralPath $routeFile.FullName -Raw | ConvertFrom-Json
  $aiDir = Split-Path -Parent $routeFile.FullName

  Assert-RequiredJsonFields -JsonObject $routes -Fields @('routes') -Source $routeFile.FullName
  if (-not ($routes.routes -is [array]) -or $routes.routes.Count -eq 0) {
    throw "Invalid routes array in $($routeFile.FullName)"
  }

  foreach ($route in $routes.routes) {
    Assert-RequiredJsonFields -JsonObject $route -Fields @('question_type', 'read_first', 'stop_when') -Source $routeFile.FullName
    Assert-JsonStringField -JsonObject $route -Field 'question_type' -Source $routeFile.FullName
    Assert-JsonStringArrayField -JsonObject $route -Field 'read_first' -Source $routeFile.FullName
    Assert-JsonStringField -JsonObject $route -Field 'stop_when' -Source $routeFile.FullName

    foreach ($property in @('read_first', 'read_next', 'do_not_use_as_evidence')) {
      if ($route.PSObject.Properties.Name -contains $property) {
        foreach ($reference in $route.$property) {
          $target = Resolve-AiPath -BaseDir $aiDir -Reference $reference
          if ($null -ne $target) {
            Assert-FileOrDirectory -RootPath $Root -TargetPath $target -Source $routeFile.FullName
          }
        }
      }
    }
  }
}

$evidenceFiles = Get-ChildItem -LiteralPath $Root -Recurse -Filter '*.md' -File | Where-Object {
  $_.FullName -match '\\ai\\evidence\\' -and $_.Name -ne 'EVIDENCE_CARD_TEMPLATE.md'
}
foreach ($evidenceFile in $evidenceFiles) {
  if (-not $isPageBundle -and $Mode -eq 'publish' -and $evidenceFile.FullName -match '\\template\\') {
    continue
  }
  $content = Get-Content -LiteralPath $evidenceFile.FullName -Raw
  $yaml = Parse-YamlBlock -Content $content -Source $evidenceFile.FullName

  $requiredEvidenceFields = @('id', 'title', 'subject', 'source', 'claim_supported', 'evidence_summary', 'last_checked', 'verification_status', 'confidence')
  foreach ($field in $requiredEvidenceFields) {
    if (-not $yaml.ContainsKey($field) -or [string]::IsNullOrWhiteSpace($yaml[$field])) {
      throw "Missing evidence field '$field' in $($evidenceFile.FullName)"
    }
  }

  if ($yaml.ContainsKey('source_type') -and -not [string]::IsNullOrWhiteSpace($yaml['source_type'])) {
    Assert-AllowedValue -Value $yaml['source_type'] -Allowed @('original', 'official', 'first_party', 'external', 'derived', 'user_submitted') -Field 'source_type' -Source $evidenceFile.FullName
  }
  Assert-AllowedValue -Value $yaml['verification_status'] -Allowed @('verified', 'unverified', 'partial', 'disputed', 'stale') -Field 'verification_status' -Source $evidenceFile.FullName
  Assert-AllowedValue -Value $yaml['confidence'] -Allowed @('high', 'medium', 'low') -Field 'confidence' -Source $evidenceFile.FullName
  if ($yaml.ContainsKey('security_class') -and -not [string]::IsNullOrWhiteSpace($yaml['security_class'])) {
    Assert-AllowedValue -Value $yaml['security_class'] -Allowed @('trusted', 'untrusted', 'mixed') -Field 'security_class' -Source $evidenceFile.FullName
  }
  if ($Mode -eq 'publish') {
    if ($yaml['last_checked'] -notmatch '^\d{4}-\d{2}-\d{2}$') {
      throw "Invalid evidence date field 'last_checked' in $($evidenceFile.FullName). Expected YYYY-MM-DD."
    }
    foreach ($field in @('id', 'title', 'subject', 'source', 'claim_supported', 'evidence_summary', 'limits', 'do_not_use_beyond')) {
      Assert-NoPublishPlaceholder -Value $yaml[$field] -Field $field -Source $evidenceFile.FullName
    }
  }
}

$markdownFiles = Get-ChildItem -LiteralPath $Root -Recurse -Filter '*.md' -File | Where-Object {
  $_.FullName -match '\\ai\\' -and $_.Name -in @('canon.md', 'tests.md')
}
foreach ($mdFile in $markdownFiles) {
  if (-not $isPageBundle -and $Mode -eq 'publish' -and $mdFile.FullName -match '\\template\\') {
    continue
  }
  $content = Get-Content -LiteralPath $mdFile.FullName -Raw
  $baseDir = Split-Path -Parent $mdFile.FullName

  $matches = [regex]::Matches($content, '(?m)^\s*-\s+(\./[^\s]+\.md|[A-Za-z0-9_\-/]+\.md)(?:\s*)$')
  foreach ($match in $matches) {
    $reference = $match.Groups[1].Value
    $target = Resolve-AiPath -BaseDir $baseDir -Reference $reference
    if ($null -ne $target) {
      Assert-FileOrDirectory -RootPath $Root -TargetPath $target -Source $mdFile.FullName
    }
  }
}

$leakPatterns = @(
  '[A-Za-z]:\\',
  '/Users/[^/\s]+/',
  'C:\\Users\\',
  'SECRET[_-]?KEY',
  'API[_-]?KEY',
  'PRIVATE[_-]?TOKEN',
  'ACCESS[_-]?TOKEN',
  'sk-[A-Za-z0-9_-]{20,}'
)

$textFiles = Get-ChildItem -LiteralPath $Root -Recurse -File | Where-Object {
  $_.Extension -in @('.md', '.json', '.html', '.ps1', '') -and $_.Name -ne 'validate.ps1'
}

$leaks = @()
foreach ($file in $textFiles) {
  $content = Get-Content -LiteralPath $file.FullName -Raw
  foreach ($pattern in $leakPatterns) {
    if ($content -match $pattern) {
      $leaks += "$($file.FullName) :: $pattern"
    }
  }
}

if ($leaks.Count -gt 0) {
  Write-Error ("Potential sensitive content found:`n" + ($leaks -join "`n"))
}

Write-Output "VALIDATION_OK $Root"
