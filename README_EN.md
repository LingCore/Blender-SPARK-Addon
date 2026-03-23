# ⚡ Blender SPARK Addon

**SPARK** — **S**mart **P**recision **A**lignment, **R**endering & **K**inematics

> A Blender 4.2+ viewport workflow add-on: measurement & annotations, alignment & transform, batch export & materials, planar kinematics, viewport rendering, and performance tools. After installation, a **pie menu** and **hotkeys** provide a single entry point so features are easy to find.

**简体中文文档：** [README.md](README.md)

![Blender](https://img.shields.io/badge/Blender-4.2+-orange?logo=blender&logoColor=white)
![License](https://img.shields.io/badge/License-GPL--3.0-blue)
![Version](https://img.shields.io/badge/Version-3.3.1-green)

![SPARK preview](docs/preview.png)

---

## ✨ Features

### 📐 Smart measurement & annotations

- **Geometry**: distance between origins, edge length, per-axis deltas, angles between edges or faces, vertex angles, radius/diameter, face area, perimeter, arc length, and more.
- **Persistence**: annotation data is stored in the `.blend`; preferences can control auto save/load on file operations.
- **Edit mode**: measurements tied to mesh elements can update when geometry changes (behavior depends on annotation type and selection).
- **Display**: font size, colors, distance culling, etc. are configurable in **Add-on Preferences** to keep the viewport readable.

### 🎯 Precise alignment & transform

- **Alignment**: object/vertex alignment along X/Y/Z (min/center/max), bottom align, flatten selection, align to edge direction, and equal spacing between objects.
- **High-precision transform**: readouts show **full floating-point precision** for verification.
- **Origin workflows**: optional origin sync when using origin-only workflows (wired via `depsgraph`, registered only when needed).

### 🪞 Mirror plus (default `Ctrl+M`)

- Choose between **Mirror modifier** workflows and **duplicate + mirror**, with **X/Y/Z** axes.
- Also available from the **Add Modifier** menu (same entry as the pie menu).

### 📦 Batch tools

- **Batch OBJ export**: export selected meshes with **origin/coordinate** metadata as implemented in `operators_export`.
- **Batch rename** (default `Ctrl+F`): **regex** find/replace on object names.
- **Batch materials**: apply to selection, clean up slots, remove unused materials; optional **material sync** in scene **misc** settings (e.g. base color, metallic, roughness) for consistent look across objects.

### 🔧 2D kinematics solver

- **Newton–Raphson**-style iteration for **2D planar** linkages.
- **Revolute** and **prismatic** joints; drivers, sliders, and limit-related helpers.
- **Demo scenes** (e.g. toggle clamp) to learn the workflow.
- **NumPy** is optional but recommended for heavier solves and large meshes.

### 🎨 Other tools

- **WYSIWYG viewport render**: temporary **Standard** view transform for closer match to final output (see **View** menu entries added by the add-on).
- **Viewport FPS overlay** for frame-rate monitoring.
- **Performance stress test** spawns many objects to stress Blender.
- **One-click mesh optimization** for common cleanup (see operator labels).
- **Smart numpad period**: **single click** frames the view; **double click** can focus the **outliner** (see `operators_object`).

---

## 🧭 Where to find things

| Entry | What it does |
|--------|----------------|
| **`` ` ``** (Accent Grave) | Opens the **enhanced tools pie menu** (main hub). |
| **Mouse side button** (often Button4) | Same as above. |
| **3D View sidebars** | Panels for transform, measure, align, kinematics, etc. |
| **View** menu | WYSIWYG viewport render and related entries. |
| **Add Modifier** menu | Mirror plus and related entries. |
| **3D View header** | Performance test shortcut. |

---

## 🚀 Installation & updates

### Option A: Release zip (recommended)

1. Download `blender_spark_addon_v*.zip` from [Releases](https://github.com/LingCore/Blender-SPARK-Addon/releases) (or build locally with `pack_addon.py`).
2. Blender → **Edit** → **Preferences** → **Add-ons** → **Install…**, pick the zip.
3. Enable **Blender SPARK Addon** in the list.

### Option B: Source folder

1. Clone or download this repository.
2. Copy the **`bofu_enhanced`** folder into the user add-ons directory, e.g. on Windows:

   `%APPDATA%\Blender Foundation\Blender\4.2\scripts\addons\`

3. Enable the add-on under **Preferences → Add-ons**.

### Compatibility

- Minimum Blender version follows `bl_info["blender"]` in `bofu_enhanced/__init__.py` (**4.2+**).
- Test on your target **4.3 / 5.x** build if you use newer Blender; report API issues via **Issues**.

---

## 🎮 Hotkeys

| Hotkey | Action |
|--------|--------|
| `` ` `` / side button | **Enhanced tools pie menu** (main hub) |
| `Ctrl + M` | Mirror plus |
| `Ctrl + F` | Batch rename |
| Numpad `.` | Smart frame / outliner focus |

> Hotkeys apply when the add-on is enabled and **no other add-on** uses the same bindings. Adjust under **Preferences → Keymap** if needed (search for `bofu` / `SPARK`).

---

## 📋 Requirements

| Component | Notes |
|-----------|--------|
| **Blender** | ≥ 4.2 (matches `bl_info`). |
| **Python** | Bundled with Blender. |
| **NumPy** | **Optional**; recommended for measurement and kinematics performance. |

---

## 📦 Build from source

```bash
python pack_addon.py
```

Or on Windows run **`pack_addon.bat`**. The output zip name includes the version from **`bl_info["version"]`** in `bofu_enhanced/__init__.py`.

---

## 🗂 Source layout (contributors)

| Path | Role |
|------|------|
| `bofu_enhanced/__init__.py` | Register/unregister, keymaps, handlers, menu hooks |
| `bofu_enhanced/properties.py` | Scene `PropertyGroup` |
| `bofu_enhanced/preferences.py` | Add-on preferences |
| `bofu_enhanced/annotation*.py` | Annotation core, drawing, persistence |
| `bofu_enhanced/operators_*.py` | Feature operators |
| `bofu_enhanced/ui.py` | Pie menus, submenus, panels |
| `pack_addon.py` | Packaging script |

---

## 📄 License

[GPL-3.0](LICENSE)

---

**Made with ❤️ by [LingCore](https://github.com/LingCore)**
