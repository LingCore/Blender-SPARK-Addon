# 仓库地图

这个仓库是一个 Blender 4.2+ 插件项目，核心包名固定为 `bofu_enhanced`。

## 顶层文件

- `README.md`：总文档，已经写了架构、模块职责、打包与开发说明。
- `pack_addon.py`：按 `__init__.py` 里的版本号打包 zip，并排除缓存和无关文件。
- `pack_addon.bat`：Windows 一键打包入口。

## 插件包职责分布

- `bofu_enhanced/__init__.py`
  - `bl_info`
  - 热重载逻辑
  - 汇总导入
  - 统一注册 / 注销
  - handler 挂载
  - 菜单追加
  - 快捷键注册

- `bofu_enhanced/config.py`
  - 常量、默认值、颜色、阈值、枚举
  - 应保持纯数据模块，不反向依赖同级模块

- `bofu_enhanced/preferences.py`
  - 插件偏好设置

- `bofu_enhanced/properties.py`
  - `PropertyGroup`
  - `Scene` 挂载属性
  - 属性更新回调

- `bofu_enhanced/utils.py`
  - 共享工具函数
  - 格式化、几何辅助、原点和对齐辅助

- `bofu_enhanced/render_utils.py`
  - GPU 绘制辅助

- `bofu_enhanced/annotation.py`
  - 标注系统主体
  - 存储、绘制、恢复、清理

- `bofu_enhanced/ui.py`
  - 饼图菜单
  - 子菜单
  - 侧栏面板
  - 若菜单项来自弹出菜单，留意 `layout.operator_context = 'INVOKE_DEFAULT'`

- `bofu_enhanced/operators_object.py`
- `bofu_enhanced/operators_transform.py`
- `bofu_enhanced/operators_align.py`
- `bofu_enhanced/operators_export.py`
- `bofu_enhanced/operators_material.py`
- `bofu_enhanced/operators_measure.py`
- `bofu_enhanced/operators_kinematics.py`
- `bofu_enhanced/operators_render.py`
- `bofu_enhanced/operators_demo.py`
  - 每个文件负责一个功能域
  - 每个文件都有自己的 `classes` 元组

## 常见改动应该落在哪

### 新增功能操作符

- 优先加到现有 `operators_*.py`
- 如果是独立功能域，再新增一个 `operators_xxx.py`
- 新增模块后同步修改 `__init__.py`

### 新增 UI 入口

- `ui.py`
- 可能还要改 `__init__.py` 里的菜单追加或快捷键

### 新增 Scene 状态

- `properties.py`
- 然后把读取逻辑接进操作符 / UI

### 新增插件生命周期逻辑

- `__init__.py`
- 例如：`load_post`、`save_pre`、`depsgraph_update_post`

### 新增打包行为

- `pack_addon.py`

### 新增用户文档

- `README.md`

## 现有设计约束

- 以模块化结构为主，不回退到单文件巨型脚本。
- 注册顺序和注销顺序都已经有体系，改动时要保持对称。
- 处理器代码要尽量容错，避免在 Blender 事件循环里频繁抛异常。
- 用户看得见的文案以中文为主，和现有插件风格保持一致。
- 不要把版本号、打包根目录或插件包名写死到多个地方。

## 改新模块时的最小清单

1. 在 `bofu_enhanced/` 新建模块。
2. 在 `__init__.py` 热重载块里加 `importlib.reload(...)`。
3. 在 `__init__.py` 正常导入区加 `from . import ...`。
4. 把新模块的 `classes` 拼进 `all_classes`。
5. 如果要出现在 UI 或快捷键里，再改 `ui.py` / `__init__.py`。
