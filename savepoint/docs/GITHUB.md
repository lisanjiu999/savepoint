# GitHub 仓库简介文案

## Repository name

```
savepoint
```

## Description（About 那一栏，建议用英文）

```
A local-first memory aid for your side projects.
Write one line while you work and months later you can still tell what you were doing.
```

如果想更有信息量：

```
Local-first project memory for Windows. Append-only logs, screenshot timeline,
and quick capture — so you can pick a project back up months later.
```

## Topics（仓库标签）

```
python  pyside6  qt  sqlite  local-first  offline  note-taking  project-management
windows-desktop  personal-knowledge-base  privacy
```

## 中文简介（发帖 / 分享用）

**一句话**

> 给并行推进多个项目的人，一个本地优先的「上下文存档点」。

**短版**

> 项目一多，时间一长，就忘了当时在做什么、为什么那么做、卡在哪。
> SavePoint 让你在做事时顺手留一行字，几个月后翻出来能立刻接上当时的思路。
> 纯本地、不联网，Windows 桌面应用，MIT 开源。

**长版**

> SavePoint 是一个 Windows 本地项目记忆工具。
>
> 它的核心不是「记笔记」，而是「留存档点」：每个项目下有一条只增不改的时间记录，
> 加上按时间排列的截图，形成一条能回看的思考轨迹。首页还有「长期未动」视图，
> 专门把那些你三个月没碰、但还在进行中的项目捞出来。
>
> 全局热键 `Ctrl+Alt+N` 在任何程序里唤起快速记录，打完字回车就完事。
> 所有数据存在本地 SQLite 和你自己的文件夹里，没有任何网络请求。
>
> Python + PySide6 + SQLite 实现，MIT 许可，约 1.6 万行代码。

## Release 说明模板

```markdown
## SavePoint v1.6.1

自用项目记忆工具的第一个公开版本。

### 功能
- 项目卡片：状态、标签、目录、一句话描述、下一步
- 追加式时间戳记录，只增不改
- 截图时间线：拖拽 / 粘贴 / 区域截图
- 笔记：分区树 + 就地编辑 + 自动保存
- 全局搜索（Ctrl+K）、活动流、回收站（30 天）
- 滚动备份与一键恢复
- 托盘常驻 + 全局热键（Ctrl+Alt+N）

### 安装
下载 `SavePoint-1.6.1-portable.zip`，解压到任意可写目录，
双击 `SavePoint.exe`。不需要安装 Python。

> 不要解压到 `C:\Program Files` 这类受保护目录。

### 要求
Windows 10 / 11，64 位。

### 许可证
MIT
```