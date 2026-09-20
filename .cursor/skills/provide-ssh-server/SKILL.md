---
name: provide-ssh-server
description: >-
  After code changes in reading-feedback-app, update and verify the production
  server through SSH. Use when finishing features/fixes, pushing to GitHub,
  deploying, 上传服务器, 部署, 更新服务器, or 启动服务器.
---

# 代码改动后自动更新服务器

本项目约定：只要本轮改了代码，并且用户没有明确说“先不上线”，推送 GitHub 后必须自动通过 SSH 更新生产服务器，并检查健康状态。

## 何时执行

完成后立刻执行（不要等用户再问）：

- 功能、修复、页面等代码改动已经做完，并已推到 GitHub
- 用户说「部署」「上传服务器」「更新服务器」「启动服务器」
- 按 `auto-push-github` 推送成功后，需要服务器拉取新代码

不要执行：

- 只回答问题、没改文件、也不涉及部署
- 纯本地实验、明确说先不上线

## 自动部署命令

```bash
ssh ubuntu@43.161.238.165 "sudo bash -lc 'cd /opt/shuran-app && git pull origin main && cd deploy/aliyun && docker compose up -d --build && curl -fsS http://127.0.0.1:8000/health'"
```

自动 SSH 失败时，报告失败原因，并提供手动登录命令 `ssh ubuntu@43.161.238.165` 和同样的服务器更新命令。

## 回复要求

推送和部署结束后，回复中包含：

1. 已推到 GitHub 的哪个分支
2. 服务器部署是否成功
3. `/health` 检查是否通过

若自动部署失败，再附上手动登录和部署命令。

线上：`http://43.161.238.165:8000`，仓库：`https://github.com/wu716/reading-feedback-app`。
