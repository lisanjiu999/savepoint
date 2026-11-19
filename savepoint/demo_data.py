"""示例数据：仅用于预览与运行检查，不会写进正式数据目录。"""
# SPDX-License-Identifier: MIT

from __future__ import annotations


def seed(repo, store) -> list[str]:
    from PIL import Image, ImageDraw

    samples = [
        ("爬虫工具集", "多线程版跑通了，卡在代理池限频", ["Python", "爬虫"],
         "第一版单线程能跑。\n改成线程池之后速度上去了，但代理池 5 分钟就限频。",
         "换住宅代理 / 加随机延时", "active"),
        ("副业站点", "静态博客，卡在部署脚本", ["副业", "前端"],
         "用 Astro 搭的，本地跑没问题。\n部署脚本在 Windows 下路径老出错。",
         "改用 GitHub Action 部署", "active"),
        ("数据标注小工具", "给数据集打标用，已交付", ["Python", "工具"],
         "PySide 写的标注界面，支持快捷键。\n导出 COCO 格式。",
         "", "done"),
        ("量化回测", "搁置，等有整块时间再做", ["Python", "金融"],
         "数据源用 akshare，回测框架还在选。\nbacktrader 文档太老，考虑自己写。",
         "先定数据源", "paused"),
        ("旧项目归档", "2025 年的小脚本合集", ["Python"],
         "各种一次性脚本，留着查参考。", "", "archived"),
    ]

    ids: list[str] = []
    for index, (name, summary, tags, notes, next_step, status) in enumerate(samples):
        project = repo.create_project(
            name,
            path=r"C:\Projects\spider" if index == 0 else "",
            summary=summary,
            status=status,
            tags=tags,
        )
        repo.update_project(project.id, notes=notes, next_step=next_step)
        ids.append(project.id)

    main_id = ids[0]
    for text in [
        "单线程版本能跑通 1000 条，用了 4 分钟。",
        "线程池改成 8 之后快很多，但目标站点开始返回 429。",
        "加了 0.5-1s 随机延时，还是限频。怀疑是 IP 段被盯上了。",
    ]:
        repo.add_entry(main_id, text)

    palette = [(46, 111, 235), (34, 158, 107), (217, 119, 6)]
    titles = ["首页", "列表页", "报错截图"]
    for index, (title, color) in enumerate(zip(titles, palette)):
        image = Image.new("RGB", (960, 600), (250, 250, 252))
        draw = ImageDraw.Draw(image)
        draw.rectangle([0, 0, 960, 56], fill=color)
        draw.rectangle([40, 96, 520, 116], fill=(214, 219, 228))
        draw.rectangle([40, 136, 700, 148], fill=(226, 230, 237))
        draw.rectangle([40, 166, 640, 178], fill=(226, 230, 237))
        draw.rectangle([40, 210, 920, 520], outline=(206, 212, 222), width=2)
        for row in range(4):
            draw.rectangle([60, 236 + row * 64, 900, 280 + row * 64], fill=(242, 245, 250))
        source = store.shot_dir.parent / f"demo-{index}.png"
        image.save(source)
        rel, thumb, digest, _ = store.save_bytes(main_id, source.read_bytes(), ".png")
        repo.add_screenshot(
            main_id,
            rel_path=rel,
            thumb_path=thumb,
            sha256=digest,
            caption=title + "：第一版界面",
        )
        source.unlink(missing_ok=True)
    return ids