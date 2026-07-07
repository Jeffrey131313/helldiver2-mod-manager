# Helldivers 2 Mod Manager

PyQt6 版 Helldivers 2 Mod 管理器。项目已拆分为核心服务层和界面层，并兼容 HD2Arsenal 风格选项树管理 Mod 差分。

## 新数据格式

每个 Mod 会导入到 `mods/<mod-id>/`：

- `mod.yml`：名称、作者、链接、启用状态、排序、预览图等元信息。
- `options.yml`：选项、变体、子选项、描述、图片和选中状态。
- `payloads/<choice-id>/`：某个选项或变体实际包含的 `patch_` 文件。
- `images/`：Mod 预览图、选项图和变体图。

旧版 `mod_info.yml` + `files/` 结构会在启动或刷新时自动迁移成新格式。

## 目录结构

- `main.py`：PyQt6 应用入口。
- `hd2mm/core/`：配置、仓储、manifest 解析、导入、选项树和安装逻辑。
- `hd2mm/ui/`：现代化 PyQt6 主窗口和对话框。
- `mods/`：本地 Mod 数据目录。
- `other/`：额外全局 patch 文件目录。
- `temp/`：压缩包解压临时目录。

## 功能

- 导入文件夹、`.zip`、`.7z`、`.rar`。
- 兼容 HD2Arsenal 风格的 `Options`、`SubOptions`、`Include`、`Image`、`Description` 字段。
- 支持多个选项、变体和子选项，并显示选项图片、名称和描述。
- 支持运行时自动识别并迁移旧 Mod 目录。
- 启用、禁用、编辑、删除 Mod。
- 按排序把已启用 Mod 的已选 payload 安装到 Helldivers 2 `data` 目录。
- 清理游戏目录中的 `patch_` 文件。
- UI 使用缩略图缓存和按需详情加载，避免大量 Mod 和图片一次性阻塞。
