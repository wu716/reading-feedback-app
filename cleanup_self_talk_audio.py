# -*- coding: utf-8 -*-
"""
清理 Self-talk 孤儿音频文件。

删除以下文件：
1. 数据库中已软删除（前端已删）记录对应的音频
2. 磁盘上存在但数据库无任何记录引用的音频

保留：deleted_at 为空的活跃记录所引用的音频。

用法：
  python cleanup_self_talk_audio.py          # 仅预览，不删除
  python cleanup_self_talk_audio.py --apply  # 实际删除
"""
from __future__ import annotations

import argparse
import os
import sys

# 将项目根目录加入 path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.models import SelfTalk

UPLOAD_DIR = "uploads/self_talks"


def collect_referenced_paths(db) -> tuple[set[str], set[str]]:
    """返回 (活跃记录路径, 全部记录路径含已删除)"""
    active: set[str] = set()
    all_refs: set[str] = set()
    for row in db.query(SelfTalk.audio_path).all():
        name = os.path.basename(row.audio_path)
        all_refs.add(name)
    for row in db.query(SelfTalk.audio_path).filter(SelfTalk.deleted_at.is_(None)).all():
        active.add(os.path.basename(row.audio_path))
    return active, all_refs


def main() -> int:
    parser = argparse.ArgumentParser(description="清理 Self-talk 孤儿音频")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际执行删除（默认仅预览）",
    )
    args = parser.parse_args()

    if not os.path.isdir(UPLOAD_DIR):
        print(f"目录不存在: {UPLOAD_DIR}")
        return 0

    db = SessionLocal()
    try:
        active_paths, all_db_paths = collect_referenced_paths(db)
    finally:
        db.close()

    disk_files = [
        f for f in os.listdir(UPLOAD_DIR)
        if os.path.isfile(os.path.join(UPLOAD_DIR, f))
    ]

    to_delete: list[str] = []
    for filename in disk_files:
        if filename in active_paths:
            continue
        to_delete.append(filename)

    if not to_delete:
        print("没有需要清理的孤儿音频文件。")
        return 0

    print(f"磁盘文件总数: {len(disk_files)}")
    print(f"活跃记录引用: {len(active_paths)}")
    print(f"待删除孤儿文件: {len(to_delete)}")
    print("-" * 40)
    for name in sorted(to_delete):
        reason = "已在前端删除" if name in all_db_paths else "数据库无引用"
        print(f"  [{reason}] {name}")

    if not args.apply:
        print("-" * 40)
        print("以上为预览。确认后执行: python cleanup_self_talk_audio.py --apply")
        return 0

    deleted = 0
    failed = 0
    for name in to_delete:
        path = os.path.join(UPLOAD_DIR, name)
        try:
            os.remove(path)
            deleted += 1
            print(f"已删除: {name}")
        except OSError as e:
            failed += 1
            print(f"删除失败 {name}: {e}")

    print("-" * 40)
    print(f"完成: 删除 {deleted} 个, 失败 {failed} 个")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
