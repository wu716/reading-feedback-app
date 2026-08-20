# 重新编译「书然」APK
# 前提：已安装 JDK 17，且本机已有 Android SDK / Gradle（由首次打包时自动准备）

$ErrorActionPreference = "Stop"
$env:Path = "C:\Windows\System32;C:\Windows;C:\Windows\System32\Wbem;C:\Windows\System32\WindowsPowerShell\v1.0;" + $env:Path

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$JavaHome = "C:\Program Files\Microsoft\jdk-17.0.20.8-hotspot"
$SdkRoot = Join-Path $env:LOCALAPPDATA "Android\Sdk"
$GradleBat = Join-Path $env:LOCALAPPDATA "shuran-android-tools\gradle-8.4\bin\gradle.bat"
$DistDir = Join-Path $ProjectDir "dist"

if (-not (Test-Path (Join-Path $JavaHome "bin\java.exe"))) {
    throw "未找到 JDK 17: $JavaHome"
}
if (-not (Test-Path $GradleBat)) {
    throw "未找到 Gradle: $GradleBat"
}
if (-not (Test-Path (Join-Path $SdkRoot "platforms\android-33\android.jar"))) {
    throw "未找到 Android SDK Platform 33，请先运行 python setup_sdk.py"
}

$env:JAVA_HOME = $JavaHome
$env:Path = "$(Join-Path $JavaHome 'bin');$env:Path"
$env:ANDROID_SDK_ROOT = $SdkRoot
$env:ANDROID_HOME = $SdkRoot

Set-Location $ProjectDir
python (Join-Path $ProjectDir "generate_icons.py")

$sdkUnix = ($SdkRoot -replace '\\', '/')
python -c "from pathlib import Path; import os; Path('local.properties').write_text('sdk.dir=' + Path(os.environ['ANDROID_SDK_ROOT']).as_posix() + chr(10), encoding='utf-8')"

if (-not (Test-Path (Join-Path $ProjectDir "keystore.properties"))) {
    throw "缺少 keystore.properties，请保留 mobile/android/keystore/ 后重试"
}

& $GradleBat --no-daemon assembleRelease
if ($LASTEXITCODE -ne 0) {
    throw "Gradle 构建失败，退出码 $LASTEXITCODE"
}

$built = Join-Path $ProjectDir "app\build\outputs\apk\release\app-release.apk"
if (-not (Test-Path $DistDir)) {
    New-Item -ItemType Directory -Path $DistDir | Out-Null
}
$outApk = Join-Path $DistDir "shuran-1.0.0.apk"
Copy-Item $built $outApk -Force

$repoRoot = (Resolve-Path (Join-Path $ProjectDir "..\..")).Path
$releaseDir = Join-Path $repoRoot "releases"
if (-not (Test-Path $releaseDir)) {
    New-Item -ItemType Directory -Path $releaseDir | Out-Null
}
$releaseApk = Join-Path $releaseDir "shuran.apk"
Copy-Item $built $releaseApk -Force

Write-Host "APK 已生成: $outApk"
Write-Host "下载目录: $releaseApk"
Write-Host "部署到服务器后，把该文件放到服务器项目的 releases/shuran.apk"
Write-Host "下载页: http://47.236.122.207:8000/download"
