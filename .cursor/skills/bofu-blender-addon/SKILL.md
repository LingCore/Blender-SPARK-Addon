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
- BoolProperty 的 `update` 回调若需跨模块调用，**必须用模块级函数 + 局部 `from . import` 导入**，不要用 `lambda + __import__('importlib').import_module()` 写法——Blender 的属性系统会静默吞掉异常，导致回调失效且无任何报错。
- 用户可见功能变化后，补 `README.md`，尤其是入口、快捷键、面板位置、使用步骤和版本信息。

## 编码质量规范

### Python 风格

- 遵循 PEP 8；类名 CamelCase，模块名和函数名小写下划线。
- 枚举值用单引号 `'FINISHED'`，普通字符串用双引号 `"hello"`。
- 明确导入，不要 `import *`。
- 包内一律相对导入：`from .utils import helper`。

### 类型注解

- **不要**使用 `from __future__ import annotations`。
- 工具函数可以加类型注解提升 IDE 支持。
- `bpy.props` 属性定义不是标准类型注解，IDE 报假阳性时忽略即可。
- 需要 IDE 补全可在虚拟环境安装 `fake-bpy-module`。

### Operator 写法

- 始终指定清晰的 `bl_idname`、`bl_label`、中文 `bl_description`。
- 会改数据的操作符加 `bl_options = {'REGISTER', 'UNDO'}`。
- 能写 `poll()` 就写 `poll()`，把上下文限制前置。
- `execute` 内优先使用传入的 `context`，不要无脑用 `bpy.context`。
- `execute` 保持精简——核心逻辑抽到独立函数或 `utils.py`，便于测试和复用。
- 失败时通过 `self.report({'WARNING'}, msg)` 反馈，返回 `{'CANCELLED'}`。

### 错误处理

- 不要使用根日志器 `logging.basicConfig()`。
- 使用 `logger = logging.getLogger(__name__)` 创建模块级日志器。
- 高频回调（draw handler、modal、depsgraph handler）中避免异常流程控制。
- Operator 失败优先用 `self.report()` 通知用户。

### 性能注意

- draw handler 每帧调用——缓存计算结果，不要每帧重算。
- 大量 mesh 数据操作用 `foreach_get()` / `foreach_set()` + NumPy。
- 字符串拼接用 `"".join()` 或 f-string，不要用 `+` 循环拼接。
- 列表处理优先用推导式。
- 成员检测用 `set` 不用 `list`。

### 上下文管理

- 需要覆盖上下文时，使用 `context.temp_override()`，不要用旧版字典覆盖。
- `temp_override()` 只在 `with` 块内生效。

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
- `execute` 保持精简，核心逻辑抽到独立函数。
- 需要入口时，补到 `ui.py` 或 `__init__.py` 快捷键。

### 新 Scene 属性

- 定义在 `properties.py`。
- 在 `register_properties()` / `unregister_properties()` 中成对处理。
- 再接入 UI 和操作符，不要把状态散落到多个模块。
- Blender 5.x 上不要用 dict 风格访问 `bpy.props` 定义的属性。

### 新菜单 / 面板入口

- 优先挂到现有饼图、子菜单或侧栏面板。
- 保持现有中文命名和 icon 风格。
- 弹窗型操作符注意 `INVOKE_DEFAULT`。
- 面板 `draw()` 只负责 UI 展示，不堆业务逻辑。

### 新 handler / 持久化

- 生命周期接线写在 `__init__.py`。
- 使用 `@persistent` 的场景，要同时考虑加载旧文件、切换文件、注销清理和重复注册。
- 缓存类逻辑要考虑跨文件污染。
- msgbus 订阅在加载新文件时会被清除，需在 `load_post` handler 中重新注册。
- **热重载陷阱**：`draw_handler_add` 捕获的是注册时的函数引用。`importlib.reload()` 会创建新函数对象，但旧 handler 仍引用旧函数。改了 draw callback 代码后，必须**重启 Blender**，不能靠重新安装插件。

### GPU / 绘制

- 不要使用 `bgl`（5.0 已移除）。
- 用 `gpu` 模块和当前推荐的 shader 写法。
- draw handler 中不做 `bpy.ops` 调用。
- 缓存 shader 和 batch，不要每帧重建。
- **必须 `shader.bind()`**：调用 `shader.uniform_float()` 前必须先 `shader.bind()`，否则 uniform 不生效、图形不渲染，且无任何报错。
- **blend 状态**：`blf.draw()` 绘制文字时，GPU blend 状态应为 `'ALPHA'`，在 `blf.draw()` 完成后再 `gpu.state.blend_set('NONE')`。
- **高 DPI 适配**：Blender 的 `region.width`/`region.height` 返回的是设备像素值。在高 DPI 显示器上，必须用 `bpy.context.preferences.system.ui_scale * pixel_size` 缩放字体大小(`blf.size`)和坐标偏移量，否则文字会极小几乎不可见。
- draw handler 中推荐用 `try-except` 包裹全部绘制逻辑，异常时 `print` 到系统控制台，否则绘制错误会被 Blender 静默吞掉。

### 打包 / 发布

- 保持 zip 根目录为 `bofu_enhanced/`。
- 版本号以 `__init__.py` 的 `bl_info["version"]` 为准。
- 不要把缓存文件、临时文件或无关产物打进包。

## 需要时再读

- 仓库结构、改动落点、现有约束：`references/repo-map.md`
- 常见改动清单、验证建议、提问点：`references/change-playbooks.md`
