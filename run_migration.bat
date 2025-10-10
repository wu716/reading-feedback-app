@echo off
chcp 65001 >nul
echo ============================================================
echo 执行数据库迁移
echo ============================================================
python migrate_add_new_features.py
pause

