# Blender 增强工具包 (bofu_enhanced)

> **版本**: v3.1.0  
> **作者**: 杨博夫  
> **Blender 版本要求**: 4.2+  
> **分类**: 3D View

一个功能丰富的 Blender 增强插件，提供智能测量标注、批量材质管理、对齐工具、镜像增强、批量导出、高精度变换显示、2D 机构运动学求解器、所见即所得视口渲染等功能。

---

## 目录

- [项目结构](#项目结构)
- [架构总览](#架构总览)
- [模块依赖关系](#模块依赖关系)
- [核心模块详解](#核心模块详解)
  - [入口模块 \_\_init\_\_.py](#入口模块-__init__py)
  - [配置模块 config.py](#配置模块-configpy)
  - [偏好设置 preferences.py](#偏好设置-preferencespy)
  - [属性定义 properties.py](#属性定义-propertiespy)
  - [工具函数 utils.py](#工具函数-utilspy)
  - [绘制工具 render\_utils.py](#绘制工具-render_utilspy)
  - [标注系统 annotation.py](#标注系统-annotationpy)
  - [UI 模块 ui.py](#ui-模块-uipy)
- [操作符模块详解](#操作符模块详解)
  - [对象操作 operators\_object.py](#对象操作-operators_objectpy)
  - [变换复制 operators\_transform.py](#变换复制-operators_transformpy)
  - [对齐工具 operators\_align.py](#对齐工具-operators_alignpy)
  - [批量导出 operators\_export.py](#批量导出-operators_exportpy)
  - [材质管理 operators\_material.py](#材质管理-operators_materialpy)
  - [智能测量 operators\_measure.py](#智能测量-operators_measurepy)
  - [运动学求解 operators\_kinematics.py](#运动学求解-operators_kinematicspy)
  - [视口渲染 operators\_render.py](#视口渲染-operators_renderpy)
  - [演示场景 operators\_demo.py](#演示场景-operators_demopy)
- [关键系统深入分析](#关键系统深入分析)
  - [标注系统架构](#标注系统架构)
  - [测量系统工作流](#测量系统工作流)
  - [运动学求解器](#运动学求解器)
  - [材质同步机制](#材质同步机制)
- [注册与生命周期](#注册与生命周期)
- [快捷键映射](#快捷键映射)
- [打包与发布](#打包与发布)
- [开发指南](#开发指南)

---

## 项目结构

```
blender插件/
├── README.md                                    # 本文档
├── pack_addon.py                                # 打包脚本
├── pack_addon.bat                               # Windows 一键打包
├── blender 增强 by bofu（此文件不修改）.py          # 旧版单文件插件 (v1.5.0, ~5400行, 已废弃)
├── blender_enhanced_by_bofu_v3.1.0.zip          # 打包产物
│
└── bofu_enhanced/                               # 插件主目录（Blender 识别的 addon 包）
    ├── __init__.py                              # 入口：注册/注销、处理器、快捷键
    ├── config.py                                # 配置常量与枚举
    ├── preferences.py                           # 偏好设置面板
    ├── properties.py                            # PropertyGroup 定义 + 更新回调
    ├── utils.py                                 # 共享工具函数
    ├── render_utils.py                          # GPU 绘制工具（Shader 缓存、标签渲染）
    ├── annotation.py                            # 标注系统（管理、存储、绘制、操作符）
    ├── ui.py                                    # 饼图菜单、子菜单、面板
    ├── operators_object.py                      # 镜像增强、批量重命名
    ├── operators_transform.py                   # 复制位置/旋转/缩放/尺寸
    ├── operators_align.py                       # 对象/顶点对齐、展平、分布
    ├── operators_export.py                      # 批量 OBJ 导出
    ├── operators_material.py                    # 批量材质、清理、同步
    ├── operators_measure.py                     # 智能测量（多模式）
    ├── operators_kinematics.py                  # 2D 机构运动学求解器
    ├── operators_render.py                      # 所见即所得视口渲染
    ├── operators_demo.py                        # 测量演示场景
    └── blender_material_loader.cpp              # C++ 源文件（当前未使用）
```

---

## 架构总览

插件采用**分层模块化架构**，从底层基础设施到上层 UI 共分为四层：

```
┌──────────────────────────────────────────────────────────┐
│                    UI 层 (ui.py)                         │
│         饼图菜单 · 子菜单 · 变换面板 · 运动学面板          │
├──────────────────────────────────────────────────────────┤
│                  操作符层 (operators_*.py)                │
│   object · transform · align · export · material ·       │
│   measure · kinematics · render · demo                    │
├──────────────────────────────────────────────────────────┤
│                  核心服务层                               │
│    annotation.py     render_utils.py     utils.py        │
│    (标注管理/绘制)    (GPU Shader缓存)    (通用工具)       │
├──────────────────────────────────────────────────────────┤
│                  基础设施层                               │
│   config.py          preferences.py     properties.py    │
│   (常量/枚举)         (偏好设置)          (场景属性)       │
└──────────────────────────────────────────────────────────┘
                           │
                    __init__.py (粘合层)
              注册/注销 · 处理器 · 快捷键 · 热重载
```

**数据流向**：`config` → 被所有模块引用 → `preferences` / `properties` 提供运行时配置 → `utils` / `render_utils` 提供工具方法 → `annotation` 管理标注生命周期 → `operators_*` 实现具体功能 → `ui` 将操作符组织成菜单/面板 → `__init__` 完成注册和全局事件绑定。

---

## 模块依赖关系

```
config.py ─────────────────────────────────────────────────┐
    │                                                      │
    ├── preferences.py (读取默认值)                          │
    ├── properties.py                                      │
    ├── utils.py (读取阈值常量)                              │
    ├── render_utils.py (读取字体/颜色默认值)                 │
    └── annotation.py (读取标注类型/限制)                     │
                                                           │
render_utils.py ←── annotation.py (标签渲染、Shader)        │
                                                           │
utils.py ←── annotation.py (坐标获取、弧长计算)              │
         ←── operators_object.py (镜像向量/原点工具)          │
         ←── operators_align.py (对齐辅助)                   │
         ←── operators_measure.py (格式化/几何计算)           │
         ←── ui.py (format_value)                           │
                                                           │
annotation.py ←── operators_measure.py (注册标注)            │
              ←── __init__.py (处理器、保存/加载)             │
                                                           │
properties.py ←── operators_*.py (读取场景属性)              │
              ←── ui.py (面板绘制属性)                       │
                                                           │
operators_material.py ←── __init__.py (缓存清理、同步处理器) │
operators_kinematics.py ←── __init__.py (缓存失效)          │
```

> **关键原则**：所有模块只通过相对导入 (`from . import ...`) 互相引用，不存在循环依赖。`config` 是纯数据模块，不导入任何同级模块。

---

## 核心模块详解

### 入口模块 `__init__.py`

**职责**：插件生命周期管理，是 Blender 识别插件包的入口文件。

| 组件 | 说明 |
|------|------|
| `bl_info` | 插件元数据（名称、版本、Blender 版本要求、分类等） |
| 热重载块 | 检测 `"config" in locals()` 判断是否为重载，若是则 `importlib.reload` 所有子模块 |
| `register()` | 按序注册：偏好设置 → 类 → 属性 → 处理器 → 菜单 → 快捷键 → 面板迁移 |
| `unregister()` | 逆序清理：绘制处理器 → 标注数据 → 持久化 → 快捷键 → 菜单 → 处理器 → 属性 → 类 → Shader 缓存 → 面板恢复 → GC |

**注册的四个全局处理器**：

| 处理器 | 挂载点 | 作用 |
|--------|--------|------|
| `transform_plus_origin_sync` | `depsgraph_update_post` | 在"只修改原点"模式下，同步跟踪活动对象切换 |
| `material_sync_handler` | `depsgraph_update_post` | 材质双向同步——当启用时，自动将活动材质的颜色/金属度/糙度同步到同名材质 |
| `save_annotations_handler` | `save_pre` | 保存 .blend 文件前自动将标注数据序列化到场景自定义属性 |
| `load_annotations_handler` | `load_post` | 打开 .blend 文件后自动从场景恢复标注，同时清理材质缓存和运动学求解器缓存 |

---

### 配置模块 `config.py`

**职责**：集中管理所有常量和默认值，零外部依赖。

```python
class Config:
    # 标注系统限制
    MAX_ANNOTATIONS = 500
    MAX_TEMP_ANNOTATIONS = 100
    CLEANUP_INTERVAL = 5.0          # 自动清理间隔 (秒)

    # 绘制样式
    DEFAULT_FONT_SIZE = 28
    LABEL_PADDING = 10
    LINE_HEIGHT = 35

    class Colors:                   # 嵌套类，分组管理 RGBA 颜色
        DISTANCE_BG = (0.2, 0.2, 0.2, 0.5)
        AXIS_X = (1.0, 0.5, 0.5, 1.0)
        ...

    # 数值阈值
    EPSILON = 1e-6
    COORDINATE_EPSILON = 0.0001

    class Kinematics:               # 运动学求解器参数
        MAX_ITERATIONS = 50
        CONVERGENCE_TOL = 1e-10
        JACOBIAN_EPSILON = 1e-12

class AnnotationType:               # 标注类型枚举 + 兼容性判断
class MeasureMode:                   # 测量模式枚举
```

**设计要点**：使用嵌套类 (`Colors`, `Kinematics`, `KinematicsColors`) 进行逻辑分组，避免扁平化命名冲突。`AnnotationType.are_compatible()` 方法支持临时标注与持久标注的兼容性覆盖。

---

### 偏好设置 `preferences.py`

**职责**：定义 `AddonPreferences` 面板，用户可在 `编辑 > 偏好设置 > 插件` 中自定义。

**可配置项**：

| 分类 | 属性 | 说明 |
|------|------|------|
| 标注显示 | `annotation_font_size` | 字体大小 (12-48) |
| | `enable_distance_culling` | 是否启用视距裁剪 |
| | `annotation_max_distance` | 最大显示距离 |
| 颜色 | `distance_bg_color` 等 6 种 | 各类标注的背景色 (RGBA) |
| 功能 | `auto_save_annotations` | 保存文件时自动保存标注 |
| | `auto_load_annotations` | 打开文件时自动加载标注 |
| | `default_create_geometry` | 测量时默认创建辅助几何体 |
| 精度 | `distance_precision` | 距离小数位数 (1-10) |
| | `angle_precision` | 角度小数位数 (0-6) |

还包含一个操作符 `BOFU_OT_reset_annotation_colors`，用于一键重置所有标注颜色到默认值。

---

### 属性定义 `properties.py`

**职责**：定义所有挂载到 `bpy.types.Scene` 的 `PropertyGroup`，供操作符和 UI 读写。

| PropertyGroup | 挂载属性名 | 用途 |
|---------------|-----------|------|
| `BatchObjExportProperties` | `scene.batch_obj_export` | 批量导出路径、是否导出原点信息 |
| `BatchMaterialProperties` | `scene.batch_material` | 批量材质指针、是否包含子物体 |
| `AnnotationSettings` | `scene.annotation_settings` | 标注显示覆盖设置 |
| `MiscSettings` | `scene.misc_settings` | 材质同步开关等杂项 |
| `TransformPlusProperties` | `scene.transform_plus_props` | "只修改原点"模式状态、原点坐标 |
| `KinematicJointProperties` | (CollectionProperty) | 运动学关节数据：类型、连接对象、铰接点 |
| `KinematicMechanismProperties` | `scene.kinematics_mechanism` | 驱动角度、自动极限、可视化开关 |

**关键更新回调**：
- `update_origin_location()`：当用户在面板中修改原点坐标时，反向移动网格顶点以保持世界坐标不变
- `update_only_modify_origin()`：切换"只修改原点"模式时记录/恢复原点位置

---

### 工具函数 `utils.py`

**职责**：提供全插件共用的纯工具函数，不持有任何状态。

| 分类 | 函数 | 用途 |
|------|------|------|
| 格式化 | `format_value(value, is_angle)` | 统一数值格式化，自动移除末尾零 |
| 镜像 | `axis_to_vec(axis)` | 轴向字符串 → 向量 |
| | `reflect_point_across_plane()` | 点关于平面的反射 |
| | `move_origin_keep_world_mesh()` | 移动原点但保持网格世界位置 |
| 对齐 | `AlignHelper` (类) | 对齐操作的通用辅助 |
| 实时数据 | `get_vertex_world_coord_realtime()` | 实时获取顶点世界坐标（支持编辑模式） |
| | `get_edge_world_coords_realtime()` | 实时获取边端点世界坐标 |
| 弧长 | `calc_arc_data()` | 由三点计算弧长、半径、圆心等 |

---

### 绘制工具 `render_utils.py`

**职责**：封装 GPU 绘制底层细节，供 `annotation.py` 调用。

| 组件 | 说明 |
|------|------|
| `ShaderCache` | GPU Shader 缓存，避免重复编译，提供 `clear()` 方法在插件卸载时释放 |
| `LabelRenderer` | 标签渲染器——计算文本尺寸、绘制带背景的文本标签、处理多行文本 |
| `get_font_size()` | 从偏好设置读取字体大小，降级到 `Config` 默认值 |
| `get_bg_color(ann_type)` | 根据标注类型从偏好设置读取对应背景色 |

---

### 标注系统 `annotation.py`

**职责**：整个插件最复杂的模块（~1700 行），实现完整的标注生命周期管理。

详见 [标注系统架构](#标注系统架构) 章节。

---

### UI 模块 `ui.py`

**职责**：定义所有菜单和面板，将操作符组织成用户可见的界面。

| 类 | 类型 | 说明 |
|----|------|------|
| `VIEW3D_MT_PIE_bofu_tools` | 饼图菜单 | 主入口，8 个方向分别放置核心功能 |
| `VIEW3D_MT_material_tools` | 子菜单 | 材质工具集合 |
| `VIEW3D_MT_annotation_manage` | 子菜单 | 标注管理（清理、显示切换） |
| `VIEW3D_MT_align_tools` | 子菜单 | 对齐工具集合 |
| `BOFU_OT_call_pie_menu` | 操作符 | 调用饼图菜单 |
| `BOFU_OT_popup_material_menu` | 操作符 | 弹出材质工具菜单 |
| `BOFU_OT_popup_annotation_menu` | 操作符 | 弹出标注管理菜单 |
| `BOFU_OT_popup_align_menu` | 操作符 | 弹出对齐工具菜单 |
| `TRANSFORM_PT_precise_panel` | 面板 | 替代默认变换面板，显示高精度数值 + "只修改原点"开关 |
| `KINEMATICS_PT_main_panel` | 面板 | 运动学机构面板：关节列表、驱动控制、求解 |

**饼图菜单布局**：

```
         ┌──────────────────────┐
         │    批量导出 OBJ (N)   │
    ┌────┼────────────────────┼────┐
    │    │                    │    │
  复制位置     [饼图中心]     标注管理
   (NW)  │                    │  (NE)
    │    │                    │    │
    └────┼────────────────────┼────┘
  镜像增强                    名称替换
    (W)  │                    │  (E)
    ┌────┼────────────────────┼────┐
    │    │                    │    │
  智能测量                    对齐工具
   (SW)  │                    │  (SE)
    │    │                    │    │
    └────┼────────────────────┼────┘
         │    材质工具 (S)     │
         └──────────────────────┘
```

---

## 操作符模块详解

### 对象操作 `operators_object.py`

| 操作符 | bl_idname | 快捷键 | 功能 |
|--------|-----------|--------|------|
| `OBJECT_OT_mirror_plus` | `object.mirror_plus` | Ctrl+M | 增强镜像：支持"添加 Mirror 修改器"和"复制并镜像"两种模式，可选轴向 (X/Y/Z)，复制模式下正确处理原点和网格反射 |
| `OBJECT_OT_batch_rename` | `object.batch_rename_plus` | Ctrl+F | 批量重命名：支持正则表达式查找替换，作用于选中对象名称 |

### 变换复制 `operators_transform.py`

| 操作符 | bl_idname | 功能 |
|--------|-----------|------|
| `TRANSFORM_OT_copy_location` | `transform.copy_location` | 复制活动对象位置到剪贴板；编辑模式下复制选中顶点/边/面的位置 |
| `TRANSFORM_OT_copy_rotation` | `transform.copy_rotation` | 复制旋转值到剪贴板 |
| `TRANSFORM_OT_copy_scale` | `transform.copy_scale` | 复制缩放值到剪贴板 |
| `TRANSFORM_OT_copy_dimensions` | `transform.copy_dimensions` | 复制尺寸值到剪贴板 |

### 对齐工具 `operators_align.py`

**对象模式**：

| 操作符 | 功能 |
|--------|------|
| `OBJECT_OT_align_objects` | 将选中对象对齐到活动对象（支持 X/Y/Z 轴向、最小/中心/最大对齐点） |
| `OBJECT_OT_quick_align` | 快速对齐——自动检测单轴差异 |
| `OBJECT_OT_distribute_objects` | 等距分布选中对象 |
| `OBJECT_OT_align_to_active_direction` | 对齐到活动对象的法线方向 |

**编辑模式**：

| 操作符 | 功能 |
|--------|------|
| `MESH_OT_align_vertices` | 顶点对齐到活动顶点 |
| `MESH_OT_quick_align_axis` | 快速轴向对齐 |
| `MESH_OT_flatten_selection` | 展平选中顶点到平面 |
| `MESH_OT_align_to_edge` | 对齐到选中边的方向 |

### 批量导出 `operators_export.py`

| 操作符 | 功能 |
|--------|------|
| `EXPORT_OT_batch_obj_with_origin` | 批量导出选中网格为 OBJ 文件，同时可导出每个对象的原点坐标信息文件 |

### 材质管理 `operators_material.py`

| 操作符/组件 | 功能 |
|-------------|------|
| `MATERIAL_OT_apply_to_selected` | 将指定材质应用到所有选中对象 |
| `MATERIAL_OT_cleanup_unused` | 清理场景中未使用的材质 |
| `MATERIAL_OT_cleanup_slots` | 整理对象材质槽（去重、清空槽） |
| `MATERIAL_PT_quick_preview` | 材质快速预览面板 |
| `sync_material_auto()` | 材质自动同步核心函数——被 `material_sync_handler` 调用 |
| `clear_material_cache()` | 清除材质同步的缓存数据 |

### 智能测量 `operators_measure.py`

| 操作符 | 功能 |
|--------|------|
| `OBJECT_OT_connect_origins` | 统一的智能测量操作符，根据 `MeasureMode` 执行不同测量 |

**支持的测量模式** (通过 `MeasureMode` 枚举)：

| 模式 | 说明 | 输入要求 |
|------|------|----------|
| `CENTER_DISTANCE` | 两对象原点距离 | 选中 2 个对象 |
| `EDGE_LENGTH` | 边长度 | 编辑模式，选中边 |
| `XYZ_SPLIT` | XYZ 分轴距离 | 选中 2 个对象/顶点 |
| `ANGLE_EDGES` | 两边夹角 | 选中 2 条边 |
| `ANGLE_FACES` | 两面夹角 | 选中 2 个面 |
| `ANGLE_VERTS` | 顶点角度 | 选中 3 个顶点 |
| `RADIUS` | 半径/直径 | 选中 3+ 顶点 |
| `FACE_AREA` | 面面积 | 选中面 |
| `PERIMETER` | 周长 | 选中面/边环 |
| `ARC_LENGTH` | 弧长 | 选中 3 个顶点 |

### 运动学求解 `operators_kinematics.py`

| 组件 | 类型 | 功能 |
|------|------|------|
| `PlanarMechanismSolver` | 类 | 2D 平面机构 Newton-Raphson 迭代求解器 |
| `BOFU_OT_add_revolute_joint` | 操作符 | 添加旋转关节 |
| `BOFU_OT_add_prismatic_joint` | 操作符 | 添加平移关节 |
| `BOFU_OT_set_driver` | 操作符 | 设置驱动关节 |
| `BOFU_OT_solve_mechanism` | 操作符 | 求解机构运动 |
| `BOFU_OT_auto_limits` | 操作符 | 自动计算驱动极限 |
| `invalidate_solver_cache()` | 函数 | 清除求解器缓存 |

### 视口渲染 `operators_render.py`

**解决的问题**：Blender 默认的"渲染视图预览"（`bpy.ops.render.opengl()`）会经过场景的色彩管理（Filmic / AgX 等色调映射），导致实体模式下渲染结果色彩偏暗、与视口不一致。

**原理**：临时将色彩管理切换为 Standard（直通 sRGB，不做额外色调映射），渲染完成后由用户手动恢复。

| 操作符 | bl_idname | 功能 |
|--------|-----------|------|
| `BOFU_OT_viewport_render_wysiwyg` | `bofu.viewport_render_wysiwyg` | 临时切换到 Standard 色彩管理，执行视口渲染，确保输出色彩与视口完全一致 |
| `BOFU_OT_restore_color_settings` | `bofu.restore_color_settings` | 恢复渲染前的色彩管理设置（Filmic / AgX 等） |

**访问方式**：
- 3D 视口 → `视图` 菜单底部
- 饼图菜单 → 标注管理 → 杂项设置

### 演示场景 `operators_demo.py`

| 操作符 | 功能 |
|--------|------|
| `OBJECT_OT_measure_demo` | 创建测量演示场景，自动放置示例对象供用户体验测量功能 |
| `BOFU_OT_cleanup_demo` | 清理由演示创建的所有对象 |

---

## 关键系统深入分析

### 标注系统架构

标注系统是插件的核心子系统，由以下组件协作：

```
┌─────────────────────────────────────────────────┐
│             AnnotationKeyGenerator              │
│    根据标注元素(顶点/边/面)生成唯一性键             │
│    确保重复测量同一元素时覆盖而非重复               │
└──────────────────────┬──────────────────────────┘
                       │ 生成 key
                       ▼
┌─────────────────────────────────────────────────┐
│              AnnotationManager                  │
│    全局注册表 _annotation_registry (dict)        │
│    register() → 注册/覆盖标注                    │
│    自动去重（相同 key + 兼容类型 → 覆盖）          │
│    容量控制（超出 MAX_ANNOTATIONS → 拒绝）        │
└──────────────────────┬──────────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
   AnnotationStorage  绘制回调    AnnotationCleaner
   save_to_scene()    统一绘制    clean_by_vertex()
   load_from_scene()  各类型的    clean_by_edge()
   (JSON序列化到       draw_*()   clean_by_object()
    场景自定义属性)     函数
```

**标注数据结构**：每条标注是一个 dict，包含以下核心字段：
- `type`: 标注类型 (AnnotationType)
- `key`: 唯一性键 (由 AnnotationKeyGenerator 生成)
- `points`: 世界坐标点列表
- `vertex_refs` / `edge_refs`: 顶点/边引用 (用于实时更新)
- `value`: 计算值 (距离/角度等)
- `label`: 显示文本

**实时更新机制**：编辑模式下修改顶点位置时，标注通过 `vertex_refs` 引用实时追踪变化，调用 `get_vertex_world_coord_realtime()` 获取最新坐标。

---

### 测量系统工作流

```
用户操作 → OBJECT_OT_connect_origins.execute()
              │
              ├── 根据 MeasureMode 分派到对应处理分支
              │
              ├── 计算测量值（距离/角度/面积等）
              │
              ├── 生成 annotation key
              │     └── AnnotationKeyGenerator.for_distance() / for_angle() / ...
              │
              ├── 注册标注到 AnnotationManager
              │     └── 自动去重检查
              │
              ├── (可选) 创建辅助几何体
              │     └── 连接线、标记点等 Blender 对象
              │
              └── 返回结果信息到状态栏
```

---

### 运动学求解器

基于 **Newton-Raphson 迭代法** 的 2D 平面机构求解器：

```
输入：关节列表 + 驱动角度/位移
  │
  ├── 构建约束方程组 F(q) = 0
  │     ├── 旋转关节约束：铰接点重合
  │     └── 平移关节约束：沿轴线滑动
  │
  ├── 计算雅可比矩阵 J = ∂F/∂q
  │
  ├── 求解 J·Δq = -F
  │
  ├── 更新 q = q + Δq
  │
  └── 收敛检查 (||F|| < CONVERGENCE_TOL)
        ├── 是 → 输出求解结果，更新 Blender 对象位置/旋转
        └── 否 → 继续迭代（最多 MAX_ITERATIONS 次）
```

**特性**：
- 支持旋转关节 (Revolute) 和平移关节 (Prismatic)
- 自动极限计算功能
- 驱动滑块实时控制
- 可选 numpy 加速（缺失时降级到纯 Python）
- 求解器缓存机制，避免重复构建

---

### 材质同步机制

```
material_sync_handler (depsgraph_update_post)
  │
  ├── 检查 misc_settings.material_sync_enabled
  │
  ├── 获取活动对象的活动材质
  │
  └── sync_material_auto(material)
        ├── 读取材质的 Base Color / Metallic / Roughness
        ├── 查找同名材质（按命名规则匹配）
        └── 同步属性到匹配的材质
```

---

## 注册与生命周期

### register() 执行顺序

```
1. 注册 preferences.classes          ← 必须最先，其他模块可能读取偏好
2. 注册 properties + annotation +     ← 所有 PropertyGroup 和操作符
   operators_* + ui 的 classes
3. properties.register_properties()   ← 将 PropertyGroup 挂载到 Scene
4. 挂载 depsgraph_update_post 处理器  ← 原点同步 + 材质同步
5. 挂载 save_pre / load_post 处理器   ← 标注持久化
6. annotation.ensure_draw_handler()   ← 启动 GPU 绘制回调
7. 注入镜像菜单项                     ← 添加到修改器菜单
8. 注入所见即所得渲染菜单项            ← 添加到 3D 视口 View 菜单
9. 注册快捷键 (Ctrl+M, Ctrl+F, `, BUTTON4MOUSE)
10. 迁移默认变换面板到 "Item (旧版)"   ← 让位给增强版变换面板
```

### unregister() 执行顺序

```
1.  移除标注绘制处理器
2.  清除标注数据
3.  清理绘制回调属性
4.  移除 save_pre / load_post 处理器
5.  移除快捷键
6.  移除所见即所得渲染菜单
7.  移除镜像菜单注入
8.  移除 depsgraph 处理器
8.  清除材质同步缓存
8.1 清除运动学求解器缓存
9.  unregister_properties()
10. 逆序注销所有 classes
11. 逆序注销 preferences.classes
12. ShaderCache.clear()
13. 恢复被迁移的面板
14. gc.collect()
```

---

## 快捷键映射

| 快捷键 | 上下文 | 功能 |
|--------|--------|------|
| `` ` `` (波浪键/反引号) | 3D 视口 / 对象模式 | 呼出饼图菜单 |
| 鼠标侧键 (BUTTON4MOUSE) | 3D 视口 / 对象模式 | 呼出饼图菜单 |
| `Ctrl + M` | 对象模式 / 3D 视口 | 镜像增强 |
| `Ctrl + F` | 对象模式 / 3D 视口 | 名称批量替换 |

---

## 打包与发布

### 打包脚本 `pack_addon.py`

自动化打包流程：

1. **版本检测**：正则匹配 `__init__.py` 中的 `"version": (x, y, z)`，失败则使用日期戳
2. **文件过滤**：排除 `__pycache__`、`*.pyc`、`.git`、`.gitignore`、`.DS_Store`、`Thumbs.db`、`*.blend1/2`
3. **打包**：使用 `zipfile.ZIP_DEFLATED` 压缩整个 `bofu_enhanced/` 目录
4. **输出**：`blender_enhanced_by_bofu_v{version}.zip`

### 使用方法

```bash
# 方式一：双击 bat 文件
pack_addon.bat

# 方式二：命令行
python pack_addon.py
```

### 安装到 Blender

1. 打开 Blender → `编辑` → `偏好设置` → `插件`
2. 点击 `从磁盘安装`
3. 选择生成的 `.zip` 文件
4. 启用插件 `Blender_增强_by.bofu`

---

## 开发指南

### 添加新操作符

1. 创建 `operators_xxx.py`，定义操作符类
2. 在文件末尾导出 `classes` 元组：
   ```python
   classes = (
       MY_OT_new_operator,
   )
   ```
3. 在 `__init__.py` 中添加导入和热重载支持
4. 在 `ui.py` 中将操作符添加到合适的菜单位置

### 添加新属性

1. 在 `properties.py` 中定义新的 `PropertyGroup`
2. 在 `register_properties()` / `unregister_properties()` 中注册/注销
3. 在操作符或 UI 中通过 `context.scene.xxx` 访问

### 添加新标注类型

1. 在 `config.py` 的 `AnnotationType` 中添加新类型常量
2. 在 `annotation.py` 中：
   - 在 `AnnotationKeyGenerator` 添加对应的键生成方法
   - 编写 `draw_xxx_annotation()` 绘制函数
   - 在 `unified_draw_callback()` 中添加分派逻辑
3. 在 `operators_measure.py` 中添加测量逻辑
4. 在 `config.py` 的 `MeasureMode` 中添加对应模式

### 热重载机制

开发时修改代码后，在 Blender 中按 `F3` → 搜索 `Reload Scripts` 即可热重载。`__init__.py` 顶部的重载块会检测模块是否已加载过，若是则对所有子模块执行 `importlib.reload()`。

### 代码规范

- 操作符命名：`{CATEGORY}_OT_{name}`（如 `OBJECT_OT_mirror_plus`）
- 面板命名：`{CATEGORY}_PT_{name}`（如 `TRANSFORM_PT_precise_panel`）
- 菜单命名：`VIEW3D_MT_{name}`（如 `VIEW3D_MT_PIE_bofu_tools`）
- 每个模块底部必须导出 `classes` 元组
- 使用 `from .config import Config` 引用常量，不硬编码
