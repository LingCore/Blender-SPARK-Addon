---
name: bofu-blender-addon
description: 开发和维护本仓库中的 `bofu_enhanced` Blender 插件。用于修改 `bofu_enhanced/`、`pack_addon.py`、Blender `bpy` 操作符、菜单、面板、PropertyGroup、handler、注册/注销、视口绘制、插件打包，以及相关 README 功能文档。优先在涉及 Blender 4.2+ 插件行为、UI 入口、场景属性、生命周期或发布包时触发。不要用于与 Blender 插件无关的普通 Python 任务、简历文件或通用 Git 操作。
---

# Bofu Blender Addon

按这个仓库现有结构开发，不要把插件逻辑做成散落补丁。

## 目标

先判断需求属于哪一类，再去对应文件落改动：

- 新操作符
- UI 菜单或面板
- Scene 属性 / PropertyGroup
- 持久化或 handler
- 标注 / 绘制 / 视口渲染
- 打包与发布
- 文档同步

优先扩展现有模块。只有在现有模块已经明显失去内聚性时，才新增模块。

## 快速定位

- 入口与生命周期：`bofu_enhanced/__init__.py`
- 常量与默认值：`bofu_enhanced/config.py`
- 场景属性：`bofu_enhanced/properties.py`
- 公共工具：`bofu_enhanced/utils.py`
- 标注系统：`bofu_enhanced/annotation.py`
- UI：`bofu_enhanced/ui.py`
- 功能操作符：`bofu_enhanced/operators_*.py`
- 打包脚本：`pack_addon.py`
- 项目文档：`README.md`

需要更细的文件职责时，先读 `references/repo-map.md`。

## 仓库内固定模式

- 插件包内部一律优先使用相对导入。
- 每个功能模块维护自己的 `classes` 元组。
- `__init__.py` 统一聚合注册、注销、菜单挂载、handler、快捷键。
- Scene 级属性集中放在 `properties.py`，并通过 `register_properties()` / `unregister_properties()` 绑定到 `bpy.types.Scene`。
- 新增模块时，同步更新 `__init__.py` 的热重载块、导入区和 `all_classes` 聚合。
- handler 需要可重复注册、可安全失败，且放在 `__init__.py` 管生命周期。
- 从弹出菜单里调用需要弹窗的操作符时，注意 `layout.operator_context = 'INVOKE_DEFAULT'`。
- 用户可见功能变化后，补 `README.md`，尤其是入口、快捷键、面板位置、使用步骤和版本信息。

## 实施流程

1. 先判定需求影响面，读取相关模块。
2. 如果变更会影响注册、属性、UI 入口或持久化，再补读 `references/change-playbooks.md`。
3. 直接在现有模式上实现，避免引入与仓库风格不一致的新抽象。
4. 改完先做静态检查，再决定是否需要打包验证。
5. 如果改动影响交互或 Blender 行为，给出最小手工验证步骤。
6. 如果当前环境没有 Blender 运行时，明确说明只完成静态校验，未完成真机验证。

## 常用检查

静态语法检查：

```bash
python -m compileall bofu_enhanced pack_addon.py
```

非交互打包检查：

```bash
python -c "import os, pack_addon; ok = pack_addon.pack_addon(os.getcwd()); print('OK' if ok else 'FAIL')"
```

只有在任务确实涉及发布包时，再执行打包检查。

## 任务套路

### 新操作符

- 放进语义最接近的 `operators_*.py`。
- 保持清晰的 `bl_idname`、`bl_label`、中文说明文案。
- 加入该模块的 `classes`。
- 需要入口时，补到 `ui.py` 或 `__init__.py` 快捷键。

### 新 Scene 属性

- 定义在 `properties.py`。
- 在 `register_properties()` / `unregister_properties()` 中成对处理。
- 再接入 UI 和操作符，不要把状态散落到多个模块。

### 新菜单 / 面板入口

- 优先挂到现有饼图、子菜单或侧栏面板。
- 保持现有中文命名和 icon 风格。
- 弹窗型操作符注意 `INVOKE_DEFAULT`。

### 新 handler / 持久化

- 生命周期接线写在 `__init__.py`。
- 使用 `@persistent` 的场景，要同时考虑加载旧文件、切换文件、注销清理和重复注册。
- 缓存类逻辑要考虑跨文件污染。

### 打包 / 发布

- 保持 zip 根目录为 `bofu_enhanced/`。
- 版本号以 `__init__.py` 的 `bl_info["version"]` 为准。
- 不要把缓存文件、临时文件或无关产物打进包。

## 需要时再读

- 仓库结构、改动落点、现有约束：`references/repo-map.md`
- 常见改动清单、验证建议、提问点：`references/change-playbooks.md`
