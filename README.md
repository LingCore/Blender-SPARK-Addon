# ⚡ Blender SPARK Addon

**SPARK** — **S**mart **P**recision **A**lignment, **R**endering & **K**inematics

> 把常用工具收进 **饼图菜单 + 快捷键**（`ui.py` / `__init__.py` 注册），并在 Blender 未内置或默认流程较绕的领域补全能力（测量持久化、批量 OBJ+原点信息、2D 机构求解、视口 OpenGL 与色彩管理不一致等）。

**English documentation:** [README_EN.md](README_EN.md)

![Blender](https://img.shields.io/badge/Blender-4.2+-orange?logo=blender&logoColor=white)
![License](https://img.shields.io/badge/License-GPL--3.0-blue)
![Version](https://img.shields.io/badge/Version-3.3.1-green)

![SPARK 插件预览](docs/preview.png)

---

## ✨ 功能与动机（与源码一致）

### 📐 智能测量与标注

**代码依据**：`annotation_core` / `annotation.py` 把标注写入场景数据并随文件保存；测量在 `operators_measure.py` 里创建/更新标注，编辑模式下可随几何刷新。

**为何要做**：自带测量不会长期留在场景里做对照；这里需要 **可存档、可清理、可调绘制样式** 的标注流。

- 距离、角度、半径/直径、面积、周长、弧长等；偏好里可关自动存读、调字体与视距裁剪。

### 🎯 对齐与高精度变换

**代码依据**：`operators_align.py` 用活动对象与 **边界框 min/max/中心/底顶** 等基准做对象对齐；`ui.py` 里 `TRANSFORM_PT_precise_panel` 用 `utils.format_value` 显示 **完整小数**，避免侧栏读数被截断。

**为何要做**：多对象对齐若手点要对齐到「底对齐到地面」等，默认要多次操作；高精度读数方便和外部尺寸表核对。

- 对象/顶点对齐、底部对齐、展平、沿边对齐、等距分布；`properties` + `depsgraph` 下的原点同步（仅在你开启相关选项时）。

### 🪞 镜像增强（`Ctrl+M`，替代默认镜像快捷键）

**代码依据**：`OBJECT_OT_mirror_plus`（`operators_object.py`）。

- **仅添加修改器**：对多选 Mesh **批量** 加 Mirror，并用 **「镜像物体」** 作为 `mirror_object`——对称平面跟 **任意参照物体** 走，而不只是本物体局部轴；**Clip / Merge** 可关可开（镜像面上合并与否自己定）。
- **复制并镜像**：复制对象 → 临时 Mirror → **`bake_modifiers_to_mesh` 烘焙** → 按镜像平面 **`delete_side_by_plane_world` 删掉一侧** → 可选 **`move_origin_keep_world_mesh` 把原点挪到对称侧**。得到的是 **已应用后的实体网格**，不再长期挂 Mirror。

**为何还要做镜像**：默认流程要自己加修改器、设轴、设参照；这里一步里选模式。**「复制并镜像」** 这条路径是刻意做成 **烘焙 + 删半侧**：需要导出、加细分、或避免镜像面 **Merge/裁切** 带来的接缝着色、中缝拓扑问题时，用实体网格比一直开着 Mirror 修改器更干净（你说的「伪影」在工程里多指这类镜像缝/着色问题；仓库里未写「伪影」二字，逻辑在 `bake` + `delete_side`）。

### 📦 批量导出 / 重命名 / 材质

**代码依据**：`operators_export.py` 批量 OBJ，可选 **导出原点信息**；`OBJECT_OT_batch_rename` 支持正则与 **重名冲突策略**；`operators_material.py` 批量应用、整理槽、清理未用，以及场景里 **材质同步**（`depsgraph_update_post` 里按活动材质同步通道）。

**为何要做**：多资产重复同一套导出/改名/套材质，默认要逐个对象点。

### 🔧 2D 运动学

**代码依据**：`operators_kinematics.py`（模块头注释）：平面机构、**Newton–Raphson**、滑块驱动、**驱动极限** 搜索、肘节夹钳演示等。

**为何要做**：Blender 没有平面连杆机构数值求解这一套；用于夹具、连杆等 **2D 机构** 摆位置，而不是靠手摆。

### 🎨 所见即所得视口渲染

**代码依据**：`operators_render.py` 文件头：**默认 `bpy.ops.render.opengl` 在 Filmic / AgX 等视图变换下，与视口所见颜色不一致**；操作符 **临时把 `view_settings` 切到 Standard** 再渲染 OpenGL，并可用「恢复色彩设置」还原。

**为何要做**：调材质时，视口和「渲一张 OpenGL 图」若不同管线，对色会偏。

### 其它

| 功能 | 代码依据 | 一句话 |
|------|----------|--------|
| **FPS 叠加** | `fps_overlay.py` | Modal Timer 驱动重绘 + 滑动平均，静止也能看到 FPS。 |
| **性能测试** | `operators_perftest.py` | 大量随机材质立方体 + Modal 随机运动，粗测场景压力。 |
| **一键优化** | `operators_optimize.py` | 合并近点、删内部面、溶解退化几何、减面等集成在一个操作符里。 |
| **小键盘 · 智能定位** | `BOFU_OT_smart_numpad_period` | 单击 `view_selected`；双击在 **大纲** `show_active`，方便找物体。 |

---

## 🧭 界面与入口（在哪里找功能）

| 入口 | 说明 |
|------|------|
| **`` ` `` 键**（重音键，常与 Esc 下方同键） | 打开 **增强工具饼图菜单**，是主功能入口。 |
| **鼠标侧键**（常见为前进键 / Button4） | 与 `` ` `` 相同，呼出同一饼图菜单。 |
| **3D 视图侧栏** | 插件提供多个面板（变换增强、测量、对齐、运动学等，随 Blender 版本与布局可能略有差异）。 |
| **视图（View）菜单** | 含 **所见即所得视口渲染** 等入口。 |
| **添加修改器菜单** | 含 **镜像（增强）** 等入口。 |
| **3D 视图 Header** | 提供 **性能测试** 等快捷入口。 |

---

## 🚀 安装与更新

### 方式一：下载发行包（推荐）

1. 打开 [Releases](https://github.com/LingCore/Blender-SPARK-Addon/releases) 下载 `blender_spark_addon_v*.zip`（或由本仓库 `pack_addon.py` 本地生成）。
2. Blender → **编辑** → **偏好设置** → **插件** → **从磁盘安装**，选中 zip。
3. 列表中勾选启用 **Blender SPARK Addon**。

### 方式二：直接使用源码目录

1. 克隆或下载本仓库。
2. 将 **`bofu_enhanced`** 整个文件夹复制到 Blender 用户插件目录，例如 Windows：

   `%APPDATA%\Blender Foundation\Blender\4.2\scripts\addons\`

3. 在 **偏好设置 → 插件** 中搜索并启用 **Blender SPARK Addon**。

### 版本与兼容性

- 插件 **最低 Blender 版本** 以 `bofu_enhanced/__init__.py` 中 `bl_info["blender"]` 为准（当前为 **4.2+**）。
- 若你使用 **4.3 / 5.x**，请优先在对应版本下测试；若遇 API 变更，欢迎通过 Issue 反馈。

---

## 🎮 快捷键速查

| 快捷键 | 功能 |
|--------|------|
| `` ` `` / 鼠标侧键 | 打开 **增强工具饼图菜单**（主入口） |
| `Ctrl + M` | 镜像增强 |
| `Ctrl + F` | 批量重命名 |
| 小键盘 `.` | 智能定位 |

> 快捷键在 **插件启用** 且 **键位映射未冲突** 时生效；若与其它插件冲突，可在 **偏好设置 → 键位映射** 中搜索 `bofu` / `SPARK` 相关项自行调整。

---

## 📋 依赖说明

| 组件 | 说明 |
|------|------|
| **Blender** | ≥ 4.2（与 `bl_info` 一致）。 |
| **Python** | 使用 Blender 内置解释器即可，无需单独安装。 |
| **NumPy** | **可选**；`operators_measure` / 运动学等在大量数据时会尝试使用。 |

---

## 📦 从源码打包

```bash
python pack_addon.py
```

或在 Windows 下双击 **`pack_addon.bat`**。生成的 zip 文件名包含版本号，版本取自 **`bofu_enhanced/__init__.py`** 中的 **`bl_info["version"]`**。

---

## 🗂 源码结构（给贡献者）

| 路径 | 职责 |
|------|------|
| `bofu_enhanced/__init__.py` | 注册/注销、快捷键、`depsgraph` / 保存 / 加载 处理器、菜单挂载 |
| `bofu_enhanced/properties.py` | 场景 PropertyGroup |
| `bofu_enhanced/preferences.py` | 插件偏好（标注样式、自动保存标注等） |
| `bofu_enhanced/annotation*.py` | 标注核心、绘制与持久化 |
| `bofu_enhanced/operators_*.py` | 各功能操作符 |
| `bofu_enhanced/ui.py` | 饼图、子菜单、面板 |
| `pack_addon.py` | 打包脚本 |

---

## 📄 许可证

[GPL-3.0](LICENSE)

---

**Made with ❤️ by [LingCore](https://github.com/LingCore)**
