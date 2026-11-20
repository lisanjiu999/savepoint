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
    check("user_version", current_version(conn) == 6)
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

    print("[4.5] 文档导入")
    from savepoint.core.documents import DocStore, extract_text, is_document
    from savepoint.testdata_docs import build_docx, build_pdf, build_pptx, build_xlsx

    docs_source = TEST_DIR / "docs"
    docs_source.mkdir(parents=True, exist_ok=True)
    build_docx(docs_source / "设计.docx")
    build_pptx(docs_source / "汇报.pptx")
    build_xlsx(docs_source / "名单.xlsx")
    build_pdf(docs_source / "手册.pdf")
    (docs_source / "说明.md").write_text("# 标题\n正文内容", encoding="utf-8")

    check("识别文档后缀", is_document(docs_source / "设计.docx"))
    check("图片不算文档", not is_document(docs_source / "sample.png"))

    cases = {
        "设计.docx": "数据库表结构",
        "汇报.pptx": "幻灯片标题",
        "名单.xlsx": "张三",
        "手册.pdf": "Hello SavePoint",
        "说明.md": "正文内容",
    }
    for name, expected in cases.items():
        text, warn = extract_text(docs_source / name)
        check(f"提取 {name}", expected in text, f"warn={warn}")

    doc_store = DocStore(TEST_DIR / "documents")
    src = docs_source / "设计.docx"
    doc_rel, doc_size, doc_hash = doc_store.save(src)
    check("文档落盘", doc_store.abs_path(doc_rel).is_file())
    check("文档大小正确", doc_size == src.stat().st_size)

    text, _warn = extract_text(src)
    saved_doc = repo.add_document(
        rel_path=doc_rel, orig_name="设计.docx", ext=".docx",
        size=doc_size, sha256=doc_hash, text_content=text, folder="工作",
    )
    check("文档入库", len(repo.list_documents()) == 1)
    check("文档有分区", repo.get_document(saved_doc.id).folder == "工作")
    check("文档内容已存", "接口设计" in repo.get_document(saved_doc.id).text_content)
    check("文档按哈希去重", repo.find_document_by_hash(doc_hash) is not None)
    check("搜索命中文档正文", any(
        r["kind"] == "document" for r in repo.search_all("接口设计")
    ))
    check("分区统计", ("工作", 1) in repo.document_folders())
    check("按分区筛选", len(repo.list_documents(folder="工作")) == 1)
    check("按分区筛选（无匹配）", repo.list_documents(folder="别的") == [])

    repo.rename_document_folder("工作", "资料")
    check("分区改名", repo.get_document(saved_doc.id).folder == "资料")
    repo.update_document(saved_doc.id, note="季度汇报用")
    check("文档备注", repo.get_document(saved_doc.id).note == "季度汇报用")

    repo.delete_document(saved_doc.id)
    check("删除文档后列表为空", repo.list_documents() == [])
    check("文档进回收站", any(
        item["kind"] == "document" for item in repo.trash_items()
    ))
    repo.restore_item("document", saved_doc.id)
    check("文档可恢复", len(repo.list_documents()) == 1)

    check("文档总数", repo.count_documents() == 1)

    print("[4.7] 文档分区：空分区也要存在")
    repo.create_document_folder("合同")
    check("空分区能建", ("合同", 0) in repo.document_folders(),
          str(repo.document_folders()))
    created = repo.create_document_folder("合同")
    check("重复建不重复", created == "合同" and
          len([n for n, _ in repo.document_folders() if n == "合同"]) == 1)
    check("分区大小写不重复",
          len([n for n, _ in repo.document_folders() if n.lower() == "合同"]) == 1)

    repo.update_document(saved_doc.id, folder="合同")
    check("文档移入分区", repo.get_document(saved_doc.id).folder == "合同")
    check("分区计数更新", ("合同", 1) in repo.document_folders())

    repo.rename_document_folder("合同", "已签合同")
    check("改名后文档跟着走", repo.get_document(saved_doc.id).folder == "已签合同")
    check("改名后分区还在", ("已签合同", 1) in repo.document_folders())
    check("旧分区名消失", "合同" not in [n for n, _ in repo.document_folders()])

    repo.delete_document_folder("已签合同")
    check("删分区后文档进回收站", repo.list_documents() == [])
    check("删掉的分区不再出现",
          "已签合同" not in [n for n, _ in repo.document_folders()],
          str(repo.document_folders()))
    repo.restore_item("document", saved_doc.id)
    repo.create_document_folder("已签合同")
    check("恢复文档后分区自动回来",
          ("已签合同", 1) in repo.document_folders(),
          str(repo.document_folders()))

    print("[4.6] v4 → v5 迁移（老库升级不丢文档）")
    import sqlite3

    from savepoint.core.db import MIGRATIONS, connect, migrate

    old_db = TEST_DIR / "upgrade" / "projects.db"
    old_db.parent.mkdir(parents=True, exist_ok=True)
    old_conn = connect(old_db)
    for target, script in MIGRATIONS:
        if target > 4:
            break
        old_conn.executescript(script)
        old_conn.execute(f"PRAGMA user_version = {target}")
    old_conn.commit()
    check("旧库停在 v4", old_conn.execute("PRAGMA user_version").fetchone()[0] == 4)

    old_conn.execute(
        "INSERT INTO projects (id, name, status, path, summary, notes, next_step,"
        " created_at, updated_at) VALUES ('p-old','老项目','active','','','','',"
        "'2026-01-01T00:00:00','2026-01-01T00:00:00')"
    )
    old_conn.execute(
        "INSERT INTO documents (id, project_id, rel_path, orig_name, ext, size,"
        " sha256, text_content, note, created_at)"
        " VALUES ('d-old','p-old','a.docx','旧文档.docx','.docx',123,'hash',"
        "'旧正文','','2026-01-01T00:00:00')"
    )
    old_conn.commit()

    migrate(old_conn)
    check("升级到最新版本", old_conn.execute("PRAGMA user_version").fetchone()[0] == 6)
    row = old_conn.execute("SELECT * FROM documents WHERE id='d-old'").fetchone()
    check("旧文档还在", row is not None)
    check("旧文档内容未丢", row["text_content"] == "旧正文" if row else False)
    check("旧文档归到默认分区", row["folder"] == "未分类" if row else False)
    check("旧文档保留原项目关联", row["project_id"] == "p-old" if row else False)

    # 项目删除后文档应保留（SET NULL），不再级联删除
    old_conn.execute("DELETE FROM projects WHERE id='p-old'")
    old_conn.commit()
    row = old_conn.execute("SELECT * FROM documents WHERE id='d-old'").fetchone()
    check("删项目后文档仍在", row is not None)
    check("删项目后关联置空", row["project_id"] is None if row else False)
    old_conn.close()

    print("[4.8] 按文件类型分类")
    from savepoint.core.documents import type_group_of

    check("docx 归 Word", type_group_of(".docx") == "Word")
    check("doc 也归 Word", type_group_of(".doc") == "Word")
    check("pdf 归 PDF", type_group_of(".PDF") == "PDF", "大小写不敏感")
    check("xlsx 归 Excel", type_group_of(".xlsx") == "Excel")
    check("md 归 Markdown", type_group_of(".md") == "Markdown")
    check("py 归 代码", type_group_of(".py") == "代码")
    check("未知后缀归其他", type_group_of(".psd") == "其他")

    # 往库里再放几份不同类型的文件
    for name, ext in (("笔记.md", ".md"), ("报表.pdf", ".pdf")):
        src2 = docs_source / name
        if not src2.is_file():
            if ext == ".md":
                src2.write_text("# 备忘\n一些内容", encoding="utf-8")
            else:
                build_pdf(src2)
        rel2, size2, hash2 = doc_store.save(src2)
        repo.add_document(
            rel_path=rel2, orig_name=name, ext=ext, size=size2, sha256=hash2,
            text_content=extract_text(src2)[0], folder="已签合同",
        )

    types = dict(repo.document_types())
    check("类型统计含 Word", types.get("Word") == 1, str(types))
    check("类型统计含 Markdown", types.get("Markdown") == 1, str(types))
    check("类型统计含 PDF", types.get("PDF") == 1, str(types))
    check("类型顺序固定", list(types) == ["Word", "PDF", "Markdown"], str(list(types)))

    only_md = repo.list_documents(suffixes=[".md"])
    check("按类型筛选只返回 md", len(only_md) == 1 and only_md[0].ext == ".md",
          str([d.orig_name for d in only_md]))
    only_office = repo.list_documents(suffixes=[".doc", ".docx"])
    check("Word 组包含 doc/docx", len(only_office) == 1, str(len(only_office)))
    check("空后缀列表返回空", repo.list_documents(suffixes=[]) == [])

    # 类型 + 分区可以叠加
    combo = repo.list_documents(folder="已签合同", suffixes=[".pdf"])
    check("类型和分区叠加筛选", len(combo) == 1 and combo[0].ext == ".pdf",
          str([d.orig_name for d in combo]))

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