# 书然项目协作流程

## 产品与交互原则

- 一个位置只承担一类功能；不将不同语义、不同任务的控件混在同一交互区域。
- 属性标注、顺序调整、状态操作必须分区或分模式呈现，避免点击、拖动与页面滚动互相冲突。
- 优先使用直接、可见、可预期的单一操作，不为同一位置叠加隐藏手势或第二层含义。

## 每次代码改动后的固定流程

完成用户要求的代码改动后，不要等待用户再次要求提交或部署。除非用户明确说“先不要提交”“先不要推送”或“先不上线”，必须按以下顺序完成收尾：

1. 检查 `git status`、本次 diff 和必要的测试结果。
2. 只暂存本次任务相关文件，不得夹带工作区中用户已有的其他改动。
3. 使用简洁的英文提交说明创建 commit，不使用 `--amend`、`--force`、`--no-verify` 或 `--no-gpg-sign`。
4. 推送当前提交到 GitHub 的 `origin/main`。
5. 通过 SSH 更新香港生产服务器：

```bash
ssh ubuntu@43.161.238.165
```

登录后执行：

```bash
sudo -i
cd /opt/shuran-app && git pull origin main && cd deploy/aliyun && docker compose up -d --build
curl -fsS http://127.0.0.1:8000/health
```

6. 向用户报告 GitHub 推送结果、服务器部署结果和验证情况；若 SSH、权限、网络或部署失败，清楚说明失败步骤，并提供可直接执行的补救命令。

## 提交安全边界

- 不提交 `.env`、密钥、keystore、`mobile/android/local.properties`、APK 或 `releases/*.apk`。
- 不提交 `docs/ops/未来规划与待办.md` 和 `docs/ops/快速唤起记-硬件与商店入口.md`。
- 不回滚、不覆盖、不提交与当前任务无关的本地改动。
- 不对 `main`/`master` 强制推送，不执行 `git reset --hard`。
