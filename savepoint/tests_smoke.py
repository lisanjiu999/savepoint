"""无头冒烟测试：核心逻辑 + 界面可构建性。

用法（在项目根目录）：
    .venv\\Scripts\\python.exe -m savepoint.tests_smoke
"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
import shutil
import sys

from savepoint.console import ensure_utf8_console
import traceback
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

BASE = Path(__file__).resolve().parent.parent
TEST_DIR = BASE / ".smoke-data"
if TEST_DIR.exists():
    shutil.rmtree(TEST_DIR, ignore_errors=True)
TEST_DIR.mkdir(parents=True, exist_ok=True)
os.environ["SAVEPOINT_DATA_DIR"] = str(TEST_DIR)

failures: list[str] = []
_APP = None
_WINDOW = None


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  OK   {name}")
    else:
        failures.append(f"{name} {detail}")
        print(f"  FAIL {name} {detail}")


def main() -> int:
    global _APP, _WINDOW
    ensure_utf8_console()
    from savepoint import config
    from savepoint.core import backup as backup_mod
    from savepoint.core.db import current_version, open_database
    from savepoint.core.repo import Repo
    from savepoint.core.storage import ShotStore

    print("[1] 数据库与迁移")
    conn = open_database(config.DB_PATH)
    check("user_version", current_version(conn) == 3)
    fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    check("foreign_keys 开启", fk == 1)

    repo = Repo(conn)
    print("[2] 项目 CRUD")
    project = repo.create_project(
        "爬虫工具集", path=r"C:\Projects\spider", summary="多线程版本，卡在代理池",
        tags=["Python", "爬虫", "#副业"],
    )
    check("创建项目", repo.get_project(project.id) is not None)
    check("标签去重/去井号", sorted(project.tags) == ["Python", "副业", "爬虫"], str(project.tags))

    repo.update_project(project.id, notes="第一版跑通了", next_step="换代理池")
    check("更新字段", repo.get_project(project.id).notes == "第一版跑通了")

    second = repo.create_project("副业站点", summary="静态博客", tags=["副业"])
    repo.set_status(second.id, "paused")
    check("状态筛选", len(repo.list_projects(status="paused")) == 1)
    check("标签筛选", len(repo.list_projects(tag="副业")) == 2)
    check("标签大小写", len(repo.list_projects(tag="python")) == 1)

    entry = repo.add_entry(project.id, "  卡在代理池限频  ")
    check("记录去空白", entry.body == "卡在代理池限频")
    check("搜索命中记录", len(repo.list_projects(query="代理池限频")) == 1)
    check("搜索命中备注", len(repo.list_projects(query="跑通")) == 1)

    print("[3] 笔记")
    note = repo.create_note(
        folder="密钥与账号", title="OpenAI Key", content="sk-123456", project_id=project.id
    )
    check("创建笔记", repo.get_note(note.id) is not None)
    check("笔记落在指定目录", repo.get_note(note.id).folder == "密钥与账号")
    check("目录统计", ("密钥与账号", 1) in repo.note_folders())
    check("按正文搜索", len(repo.list_notes(query="sk-123456")) == 1)

    repo.update_note(note.id, content="sk-654321")
    check("更新正文", repo.get_note(note.id).content == "sk-654321")

    second_note = repo.create_note(folder="提示词", title="常用 Prompt", content="你是一个助手")
    check("按目录筛选", len(repo.list_notes(folder="提示词")) == 1)
    check("目录数量", len(repo.note_folders()) == 2)
    check("笔记总数", repo.count_notes() == 2)
    check("笔记无加密字段", "is_sensitive" not in [
        col["name"] for col in conn.execute("PRAGMA table_info(notes)")
    ])

    print("[3.2] 笔记右键操作")
    repo.rename_note(second_note.id, "周报模板")
    check("重命名笔记", repo.get_note(second_note.id).title == "周报模板")

    moved = repo.rename_folder("提示词", "常用模板")
    check("重命名分区", moved == 1 and repo.get_note(second_note.id).folder == "常用模板",
          str(moved))
    check("旧分区已不存在", "提示词" not in [name for name, _ in repo.note_folders()])

    repo.move_note(second_note.id, "密钥与账号")
    check("移动笔记到分区", repo.get_note(second_note.id).folder == "密钥与账号")
    repo.move_note(second_note.id, "常用模板")

    removed = repo.delete_folder("常用模板")
    check("删除分区进回收站", removed == 1 and repo.get_note(second_note.id) is None,
          str(removed))
    check("回收站里能找到这篇笔记",
          any(item["kind"] == "note" for item in repo.trash_items()))
    repo.restore_item("note", second_note.id)
    check("恢复后回到原分区", repo.get_note(second_note.id).folder == "常用模板")

    print("[3.5] 回收站与搜索")
    entry2 = repo.add_entry(project.id, "这条要被删掉")
    repo.delete_entry(entry2.id)
    check("软删除后列表看不到", len(repo.list_entries(project.id)) == 1)
    trash = repo.trash_items()
    check("回收站能查到", any(item["id"] == entry2.id for item in trash), str(len(trash)))
    repo.restore_item("entry", entry2.id)
    check("恢复后回到列表", len(repo.list_entries(project.id)) == 2)

    repo.delete_entry(entry2.id)
    repo.purge_item("entry", entry2.id)
    check("彻底删除后回收站也没有", not any(
        item["id"] == entry2.id for item in repo.trash_items()
    ))

    found = repo.search_all("代理池")
    check("全局搜索命中记录", any(r["kind"] == "entry" for r in found), str(len(found)))
    check("全局搜索命中项目", any(r["kind"] == "project" for r in repo.search_all("爬虫")))
    check("全局搜索命中笔记", any(r["kind"] == "note" for r in repo.search_all("助手")))
    stream = repo.activity(days=7)
    check("活动流有记录", len(stream) >= 1, str(len(stream)))

    print("[4] 截图存储")
    from PIL import Image

    store = ShotStore()
    source = TEST_DIR / "sample.png"
    Image.new("RGB", (1200, 800), (40, 120, 220)).save(source)
    rel, thumb_rel, digest, duplicated = store.save_bytes(project.id, source.read_bytes(), ".png")
    check("原图落盘", store.abs_shot(rel).is_file())
    check("缩略图生成", bool(thumb_rel) and store.abs_thumb(thumb_rel).is_file())
    with Image.open(store.abs_thumb(thumb_rel)) as thumb:
        check("缩略图被缩小", max(thumb.size) <= config.THUMB_MAX, str(thumb.size))
    check("sha256 长度", len(digest) == 64)
    repo.add_screenshot(project.id, rel_path=rel, thumb_path=thumb_rel, sha256=digest, caption="首页截图")
    check("截图入库", len(repo.list_screenshots(project.id)) == 1)
    check("按哈希去重", repo.find_screenshot_by_hash(project.id, digest) is not None)

    print("[5] 备份恢复")
    snap = backup_mod.make_snapshot(min_interval_hours=0, keep=3)
    check("生成快照", snap is not None and snap.is_file())
    if snap:
        import zipfile

        with zipfile.ZipFile(snap) as zf:
            names = zf.namelist()
        check("快照含数据库", "projects.db" in names, str(names[:5]))
        check("快照含截图", any(n.startswith("screenshots/") for n in names))

        # 在隔离目录里验证「恢复」真的能把数据退回去
        demo = TEST_DIR / "restore-demo"
        demo.mkdir(parents=True, exist_ok=True)
        demo_db = demo / "projects.db"
        demo_conn = open_database(demo_db)
        demo_repo = Repo(demo_conn)
        demo_repo.create_project("恢复前")
        demo_conn.close()

        demo_snap = backup_mod.make_snapshot(
            db_path=demo_db,
            shot_dir=demo / "screenshots",
            thumb_dir=demo / "thumbnails",
            backup_dir=demo / "backups",
            keep=5,
            min_interval_hours=0,
        )
        demo_conn = open_database(demo_db)
        demo_repo = Repo(demo_conn)
        demo_repo.create_project("恢复后新增")
        demo_conn.close()

        safety = backup_mod.restore_snapshot(demo_snap, data_dir=demo, db_path=demo_db)
        demo_conn = open_database(demo_db)
        demo_repo = Repo(demo_conn)
        recovered = [p.name for p in demo_repo.list_projects()]
        check("恢复回到快照状态", recovered == ["恢复前"], str(recovered))
        check("恢复前自动留了备份", safety.is_dir())
        demo_conn.close()

    print("[6] 界面构建（offscreen）")
    from PySide6.QtWidgets import QApplication

    from savepoint.ui.main_window import MainWindow
    from savepoint.ui.style import QSS

    app = QApplication.instance() or QApplication(sys.argv)
    _APP = app
    app.setStyleSheet(QSS)
    window = MainWindow(repo, store)
    _WINDOW = window
    window.resize(1180, 760)
    check("主窗口构建", window.project_list.count() >= 1, f"count={window.project_list.count()}")
    window.refresh_all()
    window.detail.bind_project(project.id)
    check("详情页绑定", window.detail.title_label.text() == "爬虫工具集")
    check("侧栏笔记树有节点", window.notes_tree.topLevelItemCount() == 1)
    window.open_notes()
    check("笔记窗口", window.notes_window is not None)
    tree = window.notes_window.tree
    check("分区树有分区", tree.topLevelItemCount() == 2, str(tree.topLevelItemCount()))
    folder_item = tree.topLevelItem(0)
    check("分区下挂文档", folder_item.childCount() >= 1, str(folder_item.childCount()))
    check("文档条目可选中", window.notes_window._current_id is not None)  # noqa: SLF001
    window.notes_window.close()

    print("[7] 级联删除")
    repo.delete_project(project.id)
    check("项目已删", repo.get_project(project.id) is None)
    check("记录级联删除", conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 0)
    check("截图记录级联删除", conn.execute("SELECT COUNT(*) FROM screenshots").fetchone()[0] == 0)
    check("笔记项目引用置空", repo.get_note(note.id).project_id is None)

    conn.close()
    app.quit()

    print()
    if failures:
        print(f"失败 {len(failures)} 项：")
        for item in failures:
            print(" -", item)
        return 1
    print("全部通过")
    return 0


def _raises(exc_type, func) -> bool:
    try:
        func()
    except exc_type:
        return True
    except Exception:  # noqa: BLE001
        return False
    return False


if __name__ == "__main__":
    try:
        code = main()
    except Exception:
        traceback.print_exc()
        code = 2
    from savepoint.shutdown import hard_exit

    hard_exit(code)