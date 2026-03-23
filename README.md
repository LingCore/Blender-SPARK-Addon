<a id="top"></a>

<p align="center">
  <a href="https://github.com/LingCore/Blender-SPARK-Addon"><img src="https://img.shields.io/badge/SPARK-Smart%20Precision%20Alignment%2C%20Rendering%20%26%20Kinematics-orange?logo=blender&logoColor=white" alt="SPARK"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-GPL--3.0-blue" alt="License"></a>
  <a href="bofu_enhanced/__init__.py"><img src="https://img.shields.io/badge/Version-3.3.1-green" alt="Version"></a>
  <a href="https://docs.blender.org/manual/en/latest/"><img src="https://img.shields.io/badge/Blender-4.2%2B-lightgrey?logo=blender" alt="Blender"></a>
</p>

<p align="center">
  <strong>文档语言 / Language</strong><br>
  <a href="#readme-zh"><img src="https://img.shields.io/badge/简体中文-阅读-red?style=for-the-badge" alt="简体中文"></a>
  &nbsp;
  <a href="#readme-en"><img src="https://img.shields.io/badge/English-Read-blue?style=for-the-badge" alt="English"></a>
</p>

---

<a id="readme-zh"></a>

## 简体中文

**SPARK**（**S**mart **P**recision **A**lignment, **R**endering & **K**inematics）是基于 Blender 官方 Python API（`bpy`）开发的 **4.2+ 视口工作流增强插件**。安装后在 3D 视图中提供测量与标注、对齐与变换、批量导出与材质、平面机构运动学、视口渲染与性能工具等；所有功能通过统一入口（饼图菜单与快捷键）组织，避免功能散落。

**重要说明（避免歧义）**

| 项目 | 说明 |
|------|------|
| 仓库与发行名 | 仓库与对外名称为 **Blender SPARK Addon** / **SPARK**。 |
| 插件包目录名 | Blender 识别的插件文件夹名为 **`bofu_enhanced`**（从本仓库安装 zip 时，zip 根目录下应为该文件夹）。 |
| 与 Blender 内置功能关系 | 本插件**不替换** Blender 核心，仅在侧栏、菜单、快捷键等位置**追加**操作符与面板；部分功能会调整默认变换面板所在标签（卸载插件可恢复）。 |

### 架构与模块（便于贡献者定位）

- **入口与生命周期**：`bofu_enhanced/__init__.py`（注册、快捷键、`depsgraph`/`save`/`load` 处理器、菜单挂载）。
- **场景与偏好**：`properties.py`（场景级设置）、`preferences.py`（插件偏好：标注样式、自动保存标注等）。
- **标注**：`annotation_core.py`、`annotation_draw.py`、`annotation.py`（持久化、视口绘制）。
- **功能操作符**：`operators_*.py`（测量、对齐、导出、材质、运动学、渲染、优化、演示、性能测试等）。
- **界面**：`ui.py`（饼图、子菜单、侧栏面板）。
- **打包**：仓库根目录 `pack_addon.py` / `pack_addon.bat` 生成带版本号的 `blender_spark_addon_v*.zip`。

### 功能概览

**智能测量与标注**  
两对象原点距离、边长、分轴距离、边/面夹角、顶点角、半径/直径、面面积、周长、弧长等；标注可随 `.blend` 存档；编辑网格时相关标注可随几何更新（受偏好与场景设置约束）。

**对齐与变换**  
对象/顶点多模式对齐（轴向与 min/center/max）、底部对齐、展平选区、沿边方向对齐、等距分布；高精度变换面板显示完整浮点精度；可选「仅改原点」时的原点同步逻辑。

**镜像与对象工具**  
增强镜像（修改器或复制镜像）、批量重命名（正则）。默认快捷键：`Ctrl+M`、`Ctrl+F`。

**批量与材质**  
批量导出 OBJ（含原点信息）、批量应用/整理/清理材质槽；可选材质属性同步（颜色/金属度/粗糙度等，见场景杂项设置）。

**运动学（2D）**  
平面机构 Newton–Raphson 求解；旋转/平移关节；驱动滑块与极限；含演示场景（如肘节夹钳）。**numpy 可选**，用于大量数值与求解加速。

**渲染与视口**  
「所见即所得」视口预览（临时 Standard 色彩管理，便于与最终输出一致）；视口 FPS 叠加。

**其它**  
一键网格优化、性能压力测试（大量物体）、智能定位（小键盘 `.`：单击居中 / 双击大纲定位）等。

### 安装

**方式一：发行包（推荐）**  
在 [Releases](https://github.com/LingCore/Blender-SPARK-Addon/releases) 下载 `blender_spark_addon_v*.zip`（或由 `pack_addon.py` 本地生成）。Blender → **编辑 → 偏好设置 → 插件 → 从磁盘安装**，选中 zip，启用 **Blender SPARK Addon**。zip 内顶层须为 **`bofu_enhanced`** 文件夹。

**方式二：源码目录**  
克隆或下载本仓库，将 **`bofu_enhanced`** 整个文件夹复制到 Blender 用户插件目录，例如 Windows：

`%APPDATA%\Blender Foundation\Blender\4.2\scripts\addons\`

然后在偏好设置中勾选启用。

### 快速上手（快捷键）

| 快捷键 | 作用 |
|--------|------|
| `` ` ``（重音键，常与 Esc 下方同键） | 打开 **增强工具饼图菜单**（主入口） |
| 鼠标侧键（常见为前进键 / Button4） | 同上 |
| `Ctrl+M` | 镜像（增强） |
| `Ctrl+F` | 名称批量替换 |
| 小键盘 `.` | 智能定位 |

更多入口：**视图** 菜单中的视口渲染项、**添加修改器** 菜单中的镜像增强、3D 视图 Header 上的性能测试入口等。

### 依赖

- **Blender** ≥ 4.2（与 `bl_info` 一致）。
- **Python**：随 Blender。
- **numpy**：可选；建议安装以提升大量顶点与运动学计算体验。

### 从源码打包

```bash
python pack_addon.py
```

或在 Windows 下双击 `pack_addon.bat`。版本号取自 `bofu_enhanced/__init__.py` 中 `bl_info["version"]`。

### 许可证

[GPL-3.0](LICENSE)

<p align="right"><a href="#top"><strong>↑ 返回顶部</strong></a> &nbsp;|&nbsp; <a href="#readme-en"><strong>English →</strong></a></p>

---

<a id="readme-en"></a>

## English

**SPARK** (**S**mart **P**recision **A**lignment, **R**endering & **K**inematics) is a **Blender 4.2+ viewport workflow add-on** built on Blender’s Python API (`bpy`). After installation it adds measurement & annotations, alignment & transform helpers, batch export & material tools, a 2D planar kinematics solver, viewport rendering helpers, and performance utilities—all reachable from a **single pie menu and hotkeys**.

**Disambiguation**

| Topic | Detail |
|--------|--------|
| Product name | **Blender SPARK Addon** / **SPARK**. |
| Add-on package folder | The folder Blender loads is **`bofu_enhanced`** (the release `.zip` must contain this folder at the top level). |
| Relation to Blender | This add-on **extends** Blender via operators, menus, and panels; it does **not** replace core Blender. Some UI moves the default transform panel to another tab; disabling the add-on restores it. |

### Architecture (for contributors)

- **Lifecycle**: `bofu_enhanced/__init__.py` (registration, keymaps, handlers, menu hooks).
- **Data**: `properties.py`, `preferences.py`.
- **Annotations**: `annotation_*.py`, `annotation.py`.
- **Operators**: `operators_*.py` (measure, align, export, materials, kinematics, render, optimize, demo, perf test, …).
- **UI**: `ui.py`.
- **Packaging**: `pack_addon.py` / `pack_addon.bat` → `blender_spark_addon_v*.zip`.

### Feature summary

**Measurement & annotations** — Distances, edge lengths, per-axis deltas, angles, vertex angles, radius/diameter, face area, perimeter, arc length; saved in the `.blend`; updates with mesh edits where applicable.

**Alignment & transform** — Object/vertex alignment modes, bottom align, flatten selection, align to edge, distribute spacing; high-precision transform readout; optional origin sync when using origin-only workflows.

**Mirroring & object tools** — Enhanced mirror (modifier or duplicated mirror), batch rename (regex). Defaults: `Ctrl+M`, `Ctrl+F`.

**Batch & materials** — Batch OBJ export with origin metadata; batch assign / clean / organize material slots; optional live sync for common material channels (see scene misc settings).

**Kinematics (2D)** — Planar linkage solver (Newton–Raphson), revolute & prismatic joints, drivers & limits, demo scenes. **NumPy optional** but recommended for heavier solves.

**Rendering & viewport** — WYSIWYG viewport preview (temporary Standard view transform), FPS overlay.

**Other** — One-click mesh cleanup, performance stress test, smart numpad period navigation.

### Installation

**Release zip (recommended)** — Download `blender_spark_addon_v*.zip` from [Releases](https://github.com/LingCore/Blender-SPARK-Addon/releases) (or build locally). **Edit → Preferences → Add-ons → Install**, select the zip, enable **Blender SPARK Addon**. The archive root must contain **`bofu_enhanced`**.

**From source folder** — Copy the **`bofu_enhanced`** folder into the user add-ons path, e.g. on Windows:

`%APPDATA%\Blender Foundation\Blender\4.2\scripts\addons\`

Then enable the add-on in Preferences.

### Quick start (hotkeys)

| Hotkey | Action |
|--------|--------|
| `` ` `` (Accent Grave) | **Enhanced tools pie menu** (main hub) |
| Mouse side button (often Button4) | Same as above |
| `Ctrl+M` | Enhanced mirror |
| `Ctrl+F` | Batch rename |
| Numpad `.` | Smart frame / outliner focus |

Additional entries: **View** menu (WYSIWYG viewport render), **Add Modifier** menu (mirror plus), 3D View header (perf test), etc.

### Requirements

- **Blender** ≥ 4.2 (matches `bl_info`).
- **Python**: bundled with Blender.
- **NumPy**: optional; recommended for large meshes and kinematics.

### Build from source

```bash
python pack_addon.py
```

Version is read from `bl_info["version"]` in `bofu_enhanced/__init__.py`.

### License

[GPL-3.0](LICENSE)

<p align="right"><a href="#top"><strong>↑ Back to top</strong></a> &nbsp;|&nbsp; <a href="#readme-zh"><strong>← 简体中文</strong></a></p>

---

**Made with care by [LingCore](https://github.com/LingCore)**
