---
name: provide-ssh-server
description: >-
  After code changes in reading-feedback-app that need uploading or restarting
  the production server, give the user the SSH login command. Use when finishing
  features/fixes, pushing to GitHub, deploying, 上传服务器, 部署, 更新服务器, or 启动服务器.
---

# 代码上服务器时提供 SSH 命令

本项目约定：只要本轮改了代码，并且需要上传 / 更新 / 重启生产服务器，**回复里必须给出下面这条 SSH 命令**，方便用户登录并启动服务器。

不要擅自 SSH 登录，除非用户当场要求代登。

## 何时给出

完成后立刻给出（不要等用户再问）：

- 功能、修复、页面等代码改动已经做完，并已推到 GitHub
- 用户说「部署」「上传服务器」「更新服务器」「启动服务器」
- 按 `auto-push-github` 推送成功后，需要用户去服务器拉代码

不要给出：

- 只回答问题、没改文件、也不涉及部署
- 纯本地实验、明确说先不上线

## 必须原样提供

```bash
ssh root@47.236.122.207
```

同时附上服务器更新命令：

```bash
cd /opt/shuran-app && git pull origin main && cd deploy/aliyun && docker compose up -d --build
```

## 回复模板

推送成功后，用类似下面的结构发给用户：

1. 已推到 GitHub 的哪个分支
2. 登录服务器：

```bash
ssh root@47.236.122.207
```

3. 登录后执行：

```bash
cd /opt/shuran-app && git pull origin main && cd deploy/aliyun && docker compose up -d --build
```
