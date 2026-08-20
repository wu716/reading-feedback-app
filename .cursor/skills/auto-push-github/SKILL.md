---
name: auto-push-github
description: >-
  After finishing code changes in reading-feedback-app, commit relevant files
  and git push to GitHub without waiting to be asked. Use when a feature, fix,
  or UI change is complete, or when the user mentions 推送, push, GitHub, 部署,
  or 更新代码.
---

# 代码更新后自动推到 GitHub

本项目约定：完成用户要求的代码改动后，**不要等用户再说「提交/推送」**，直接 commit 并 `git push` 到 GitHub。

这覆盖 Cursor 默认的「未明确要求就不 commit」规则，但仅限本仓库。

## 何时执行

在以下情况完成后立刻执行：

- 功能、修复、页面改动已经做完
- 用户说「改好了」「推一下」「部署」等
- 本轮有实质文件改动，且不是纯问答

不要执行：

- 只回答问题、没改文件
- 用户明确说先不要提交 / 先不要推
- 改动还没做完、还在等用户拍板

## 步骤

按顺序在仓库根目录执行。Windows 上用 PowerShell；需要写 git 或访问网络时申请相应权限。

1. `git status`
2. `git diff` 与 `git diff --cached`
3. `git log -8 --oneline`（跟现有英文 commit 风格）
4. 只暂存本次相关文件。**不要**加入：
   - `.env`、密钥、`*.apk`、`releases/*.apk`
   - `mobile/android/local.properties`、keystore
   - 无关的未跟踪文件
5. Commit 信息用 1–2 句英文，写 **why**，不要堆文件清单。PowerShell 示例：

```powershell
git commit -m "Fix homepage recording flow and live stats."
```

6. `git push -u origin HEAD`
7. 成功后告诉用户：已推到哪个分支，并给出服务器更新命令（见下方）。**不要擅自 SSH 登录服务器**，除非用户当场要求代登。

## 安全

- 不要 `git config`
- 不要 `--force` 推 `main`/`master`
- 不要 `--no-verify` / `--no-gpg-sign`
- 不要 `reset --hard`、不要改已推送的 commit
- 钩子失败则修问题后 **新建** commit，不要 amend 已失败的提交

## 服务器更新（推送后发给用户）

GitHub 更新后，生产机需要再拉一次。默认命令：

```bash
cd /opt/shuran-app && git pull origin main && cd deploy/aliyun && docker compose up -d --build
```

线上：`http://47.236.122.207:8000`，仓库：`https://github.com/wu716/reading-feedback-app`。
