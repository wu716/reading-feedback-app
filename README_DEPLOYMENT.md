# 书然服务器部署说明

当前生产环境使用 Ubuntu、Docker Compose 和 PostgreSQL；部署文件在 [`deploy/aliyun/docker-compose.yml`](deploy/aliyun/docker-compose.yml)。旧 Railway 读书笔记应用的部署步骤已不适用于现在的书然，不要按历史说明重建数据库或覆盖服务器配置。

截至 2026-10-16，GitHub `main` 已有 `2.0.1` 产品转向代码，生产服务器仍运行 `1.5.25`。服务器更新由用户执行；代码推送成功不表示线上已更新。

部署前须分别备份书然 PostgreSQL 数据库和完整上传卷，并在服务器外另存副本；若同机运行 `reader-app`，还须独立备份知间的 `reader_db` 和书籍目录。核对服务器现有 `.env`、本地 APK 文件、Git 工作树状态及磁盘余量。历史阅读数据和未涉及板块的数据都要保留。迁移只新增必要表、列和索引，不执行 `DROP TABLE`、`TRUNCATE`、批量 `DELETE` 或清空卷。具体边界与验证项目见[产品转向审计](docs/product/2026-10-15-product-turn-audit.md)。

完成备份及核对后，按服务器当前实际状态更新 Git 检出并重建应用容器；通过 `http://127.0.0.1:8000/health` 核对运行版本，再检查旧阅读入口和专用路由已退出、项目与“记”可用、历史表及上传文件仍在。不要手工按名称递归删除服务器文件，不要执行 `docker compose down -v` 或 `docker system prune --volumes`。

数据库密码、API 密钥、`.env`、keystore 与上传文件不得写入 Git 仓库。Android 签名包须另行完成构建与验证，不能用网页源码版本替代 APK 版本判断。
