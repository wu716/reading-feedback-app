# 当前目录可在仓库根或本目录执行。
# 目的：编出 Windows 桌面壳 exe（不提交 git）。
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$project = Join-Path $here "Shuran.Desktop\Shuran.Desktop.csproj"
$repoRoot = (Resolve-Path (Join-Path $here "..\..")).Path
$outDir = Join-Path $here "Shuran.Desktop\publish"
$releaseDir = Join-Path $repoRoot "releases"
$projectXml = [xml](Get-Content -LiteralPath $project -Raw)
$version = [string]$projectXml.Project.PropertyGroup.Version

dotnet publish $project -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:EnableCompressionInSingleFile=true -p:PublishTrimmed=false -p:DebugType=None -p:DebugSymbols=false -o $outDir
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
$exe = Join-Path $outDir "Shuran.exe"
$dest = Join-Path $releaseDir "shuran-windows.exe"
$zipDest = Join-Path $releaseDir "shuran-windows-$version.zip"
Copy-Item $exe $dest -Force
$sizeMb = [Math]::Round((Get-Item $dest).Length / 1MB, 1)
$sha256 = (Get-FileHash -Algorithm SHA256 $dest).Hash.ToLowerInvariant()
if (Test-Path -LiteralPath $zipDest) {
    Remove-Item -LiteralPath $zipDest -Force
}
Compress-Archive -LiteralPath $dest -DestinationPath $zipDest -CompressionLevel Optimal
$zipSizeMb = [Math]::Round((Get-Item $zipDest).Length / 1MB, 1)
$zipSha256 = (Get-FileHash -Algorithm SHA256 $zipDest).Hash.ToLowerInvariant()
Write-Host "Built $dest ($sizeMb MB)"
Write-Host "SHA256 $sha256"
Write-Host "WeChat package $zipDest ($zipSizeMb MB)"
Write-Host "ZIP SHA256 $zipSha256"
Write-Host "Do not git add this exe. Upload with:"
Write-Host "scp `"$dest`" ubuntu@43.161.238.165:/opt/shuran-app/releases/shuran-windows.exe"
