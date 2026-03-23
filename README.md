# ⚡ Blender SPARK Addon

**SPARK** — **S**mart **P**recision **A**lignment, **R**endering & **K**inematics

> 一个功能丰富的 Blender 4.2+ 增强插件，为 3D 工作流提供智能测量、精确对齐、批量材质管理、运动学求解等专业工具。

![Blender](https://img.shields.io/badge/Blender-4.2+-orange?logo=blender&logoColor=white)
![License](https://img.shields.io/badge/License-GPL--3.0-blue)
![Version](https://img.shields.io/badge/Version-3.3.1-green)

---

## ✨ 功能一览

### 📐 智能测量与标注
- 两对象原点距离、边长、XYZ 分轴距离
- 两边/两面夹角、顶点角度
- 半径/直径、面面积、周长、弧长
- 标注持久化保存，跟随文件存档
- 实时编辑模式追踪（修改顶点时标注自动更新）

### 🎯 精确对齐工具
- 对象/顶点多模式对齐（X/Y/Z 轴向、最小/中心/最大）
- 快速底部对齐、展平选区、对齐到边方向
- 等距分布选中对象

### 🪞 镜像增强 `Ctrl+M`
- 添加 Mirror 修改器 / 复制并镜像两种模式
- 支持 X/Y/Z 轴向选择

### 📦 批量操作
- **批量导出 OBJ** — 一键导出选中网格，支持原点坐标信息
- **批量重命名** `Ctrl+F` — 正则表达式查找替换对象名称
- **批量材质** — 应用 / 清理 / 整理材质槽

### 🔧 运动学求解器
- 2D 平面机构 Newton-Raphson 迭代求解
- 旋转关节 & 平移关节
- 驱动滑块实时控制 + 自动极限计算
- 内置演示场景（肘节夹钳）

### 🎨 其他工具
- **所见即所得渲染** — 临时切换 Standard 色彩管理，视口输出颜色 100% 一致
- **高精度变换面板** — 替代默认变换面板，显示完整精度数值
- **视口 FPS 显示** — 实时帧率监测
- **性能压力测试** — 创建大量物体测试 Blender 性能
- **一键模型优化** — 快速清理网格

---

## 🚀 安装方法

### 方式一：下载安装包（推荐）

1. 到 [Releases](../../releases) 页面下载最新的 `.zip` 文件
2. 打开 Blender → `编辑` → `偏好设置` → `插件`
3. 点击 `从磁盘安装`，选择下载的 `.zip` 文件
4. 勾选启用 `Blender SPARK Addon`

### 方式二：直接下载源码

1. 下载本仓库的 `.zip` 并解压
2. 将 `bofu_enhanced` 文件夹复制到 Blender 插件目录：
   ```
   %APPDATA%\Blender Foundation\Blender\4.2\scripts\addons\
   ```
3. 在 Blender 偏好设置中启用插件

---

## 🎮 快速上手

安装后按 **`` ` ``**（波浪键）或 **鼠标侧键** 即可呼出饼图快捷菜单：

| 快捷键 | 功能 |
|--------|------|
| `` ` `` / 鼠标侧键 | 饼图菜单（全部功能入口） |
| `Ctrl + M` | 镜像增强 |
| `Ctrl + F` | 批量重命名 |
| `小键盘 .` | 智能定位 |

---

## 📋 版本要求

- **Blender** ≥ 4.2.0
- **Python** — Blender 内置即可
- **numpy**（可选）— 大量顶点计算加速 & 运动学求解器

---

## 📄 License

[GPL-3.0](LICENSE)

---

**Made with ❤️ by [LingCore](https://github.com/LingCore)**
