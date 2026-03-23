# ⚡ Blender SPARK Addon

**SPARK** — **S**mart **P**recision **A**lignment, **R**endering & **K**inematics

> 把常用但分散在菜单里的操作，收成 **一张饼图 + 几个快捷键**；并补上 Blender 未覆盖或不够顺手的工作流（如机构求解、可存档测量、批量资产操作）。

**English documentation:** [README_EN.md](README_EN.md)

![Blender](https://img.shields.io/badge/Blender-4.2+-orange?logo=blender&logoColor=white)
![License](https://img.shields.io/badge/License-GPL--3.0-blue)
![Version](https://img.shields.io/badge/Version-3.3.1-green)

![SPARK 插件预览](docs/preview.png)

---

## ✨ 功能一览

### 📐 智能测量与标注

**为何**：自带测量多为「量完即走」，不好留在场景里反复对照。这里把常用几何量做成 **可存档、可调样式** 的视口标注，改模型时相关项还能跟着更新。

- 距离、夹角、半径/直径、面积、周长、弧长等；随 `.blend` 保存；偏好里可关自动存读、调字体与裁剪。

### 🎯 精确对齐与变换

**为何**：对齐选项散在多处，多物体 **min/中心/max、等距排布** 容易反复点菜单。这里把一批对齐方式收在一起；变换读数给 **全精度**，避免和参考数据对不上。

- 对象/顶点对齐、底部对齐、展平、沿边对齐、等距分布；可选仅改原点时的原点同步。

### 🪞 镜像增强（默认 `Ctrl+M`）

**为何**：Blender 当然有镜像——但要 **加修改器、改轴向、或先复制再镜像** 时，步骤并不少。这里 **一键** 在「只加 Mirror 修改器」和「复制一份再镜像」之间选，并和饼图、`Ctrl+M` 绑在一起，对称类操作少跑几趟菜单。

- 支持 X/Y/Z；也可从 **添加修改器** 菜单进同一套入口。

### 📦 批量操作

**为何**：出包、改名、理材质是资产流程 **高频重复活**，用默认流程要同一动作做好几遍。这里针对 **多选对象** 做导出、正则改名、批量套材质/清槽/同步通道。

- 批量 OBJ（含原点相关信息）、`Ctrl+F` 正则重命名、批量材质与可选材质同步。

### 🔧 运动学求解器（2D）

**为何**：Blender 面向动画与绑定，**没有**「平面连杆机构求位置」这类求解器。做夹具、连杆机构时，要么手算，要么外接工具；这里在场景里直接 **2D 迭代求解** + 驱动/滑块与演示场景。

- 旋转/平移关节、驱动与极限；可选装 **NumPy** 加速。

### 🎨 其他工具

**为何**：视口与最终渲染 **色彩管理不一致** 时调材质会偏色——提供临时 **Standard** 视口预览；其余是顺手的小工具。

- **所见即所得视口**：视图菜单入口，临时对齐显示与输出。
- **FPS 叠加**、**压力测试**（大量物体）、**一键优化**、小键盘 **·** 智能定位（可联动大纲）。

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
| **NumPy** | **可选**；建议安装以获得更好的测量与运动学性能。 |

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
