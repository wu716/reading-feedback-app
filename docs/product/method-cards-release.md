# 书然方法卡：交付与发布步骤

本地 Codex 接手时，先完整阅读 [产品与代码交接](shuran-local-codex-handoff.md)。其中包含产品思考、已取消的发布前试验门槛、首发范围、后续规划、验证边界与接手任务。本文件保留简明发布命令。

## 已完成的版本

网页与 Android 源码：**1.5.25 / versionCode 41**。静态版本：`20261010methods1`。

默认首页改为方法卡，必填「情境」和「第一步」，支持搜索、暂放、恢复、来源导入和逐次反馈。访客可在本浏览器体验，主动提交产品意见；登录后可选择把体验卡片存入账号。站长页面增加实际使用汇总与意见列表。完整设计见 `method-cards-launch.md`。

新表追加创建，旧表和旧数据不清空。卡片和反馈接口禁用缓存，账号切换清除旧显示；双窗口开始同一张卡片时，数据库避免重复的待反馈记录。

当前环境已完成修改与本地验证。GitHub 写入凭据未配置，SSH 到 `43.161.238.165:22` 返回 `Network is unreachable`，因此本次**尚未成功推送 GitHub，也尚未更新香港生产服务器**。本地完成不代表线上已更新。

## 验证结果

- 新增 10 项 HTTP 接口测试通过：真实数据库写入、权限隔离、重复保存、双窗口并发、反馈改正、多次尝试、来源保护、搜索、匿名意见、统计口径、备份与注销。
- 4 项前端模拟交互检查通过：访客保存与转义、尝试反馈、提交失败重试、部分导入重试与切换账号。该检查使用 jsdom，不代替浏览器视觉验收或 Android 真机验收。
- 应用整体导入、自动添加新表、首页、访客接口、受保护接口和带版本的健康检查通过。
- 修改的外部 JavaScript 与首页内联 JavaScript 语法通过；方法页面新增 ID 无重复。
- 全套 Python 测试结果：46 通过、3 失败。相同 3 项在未修改的基线 `1aee89b` 上同样失败，分别为两项旧 APK 下载元数据断言和一项旧日程设计模式断言。本次未改动这些业务实现；新手机导航的既有断言按新的入口安排更新。
- Android 源码已递增版本，**本次未生成新的 APK**。`releases/latest.json` 保留实际现有构建产物信息；已有 WebView 可以通过服务器更新获取新网页。

后端检查：在安装 `requirements.txt`、`pytest` 和 `httpx<0.28` 的环境运行 `python -m pytest -q`。前端模拟检查：在 `tests/frontend` 下运行 `npm install` 和 `npm test`；该目录的依赖仅用于检查，不进入生产镜像。

## Windows PowerShell：应用补丁并推送

先下载交付的 `shuran-1.5.25.patch`，保存到下载目录。以下流程创建独立 worktree，保留原工作区已有改动。若补丁保存到其他位置，修改 `$releasePatchPath`。任一步出错会停止；不要强制推送或重置原工作区。

```powershell
$releasePatchPath = Join-Path $env:USERPROFILE 'Downloads\shuran-1.5.25.patch'
$releaseWorktreePath = 'D:\projects\shuran-method-cards-1.5.25'

function Invoke-ReleaseGit {
    & git @args
    if ($LASTEXITCODE -ne 0) { throw "Git 操作失败，请检查上方错误后再继续。" }
}

if (-not (Test-Path $releasePatchPath)) { throw "请先下载补丁，或修改 releasePatchPath。" }
Set-Location 'D:\projects\reading-feedback-app'
Invoke-ReleaseGit status --short
Invoke-ReleaseGit diff --stat
Invoke-ReleaseGit fetch origin
Invoke-ReleaseGit worktree add -b release/method-cards-1.5.25 $releaseWorktreePath origin/main
Set-Location $releaseWorktreePath

Invoke-ReleaseGit apply --check $releasePatchPath
# --index 只暂存本次补丁包含的文件。
Invoke-ReleaseGit apply --index $releasePatchPath
Invoke-ReleaseGit status --short
Invoke-ReleaseGit diff --cached --stat
Invoke-ReleaseGit -c core.whitespace=cr-at-eol diff --cached --check
Invoke-ReleaseGit commit -m 'Launch method cards with usage feedback'
Invoke-ReleaseGit push origin HEAD:main

# 比较下面两个提交哈希，确认新提交已在 origin/main。
Invoke-ReleaseGit rev-parse HEAD
Invoke-ReleaseGit ls-remote origin refs/heads/main
```

若 GitHub 提示登录，用你当前 Git 的正常登录流程获取仓库写权限。若独立 worktree 或同名分支已存在，先查看其状态，不要覆盖；可以复用此前已创建的干净发布工作区。若 `git apply --check` 失败，说明本地基线与补丁存在差异，保留错误输出后处理冲突，不要跳过检查。

## 香港服务器：更新与验证

仅在上一节确认 GitHub 推送成功后执行。先在本机登录：

```powershell
ssh ubuntu@43.161.238.165
```

SSH 登录后，以下命令在服务器 Linux shell 中执行：

```bash
sudo -i
set -e
cd /opt/shuran-app
git pull --ff-only origin main
git rev-parse HEAD
cd deploy/aliyun
docker compose up -d --build
curl -fsS http://127.0.0.1:8000/health
```

健康检查必须包含 `"status":"healthy"`、`"version":"1.5.25"` 和 `"ui_version":"20261010methods1"`。只看到旧版健康状态还不能确认这次更新已生效。若构建或健康检查失败，在 `deploy/aliyun` 执行 `docker compose logs --tail=100` 查看错误；不要反复强制拉取或清空数据库。

## 发布后入口与反馈

部署验证成功后再对外发送 `http://43.161.238.165:8000/#methods`。站长用已有站长账号进入「我的 → 站长开通」，查看近 7 天使用与主动意见。新账号目前仍需一次性邀请码，访客体验可先使用。

关注实际保存、试过、跨日使用和具体意见。访问会话不等于独立用户数，示例与访客体验不计入正式尝试，分项计数不能直接相除作为转化率。
