# 当前目录可在仓库根或本目录执行。
# 目的：编出 Windows 桌面壳 exe（不提交 git）。
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$project = Join-Path $here "Shuran.Desktop\Shuran.Desktop.csproj"
$repoRoot = (Resolve-Path (Join-Path $here "..\..")).Path
$outDir = Join-Path $here "Shuran.Desktop\publish"
$releaseDir = Join-Path $repoRoot "releases"

dotnet publish $project -c Release -r win-x64 --self-contained false -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -o $outDir
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
$exe = Join-Path $outDir "Shuran.exe"
$dest = Join-Path $releaseDir "shuran-windows.exe"
Copy-Item $exe $dest -Force
Write-Host "Built $dest"
Write-Host "Do not git add this exe. Upload with:"
Write-Host "scp `"$dest`" root@47.236.122.207:/opt/shuran-app/releases/shuran-windows.exe"
