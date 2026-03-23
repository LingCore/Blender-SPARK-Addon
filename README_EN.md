# ⚡ Blender SPARK Addon

**SPARK** — **S**mart **P**recision **A**lignment, **R**endering & **K**inematics

> Pulls scattered viewport workflows into a **pie menu + a few hotkeys**, and fills gaps Blender doesn’t cover out of the box (saved measurements, batch asset ops, 2D linkage solving, etc.).

**简体中文文档：** [README.md](README.md)

![Blender](https://img.shields.io/badge/Blender-4.2+-orange?logo=blender&logoColor=white)
![License](https://img.shields.io/badge/License-GPL--3.0-blue)
![Version](https://img.shields.io/badge/Version-3.3.1-green)

![SPARK preview](docs/preview.png)

---

## ✨ Features

### 📐 Smart measurement & annotations

**Why**: Built-in measure tools are ephemeral—hard to keep in the scene for reference. Here, common dimensions become **persistent, stylable** viewport labels that can track edits where applicable.

- Distances, angles, radius/diameter, area, perimeter, arc length; saved in the `.blend`; prefs for auto save/load, fonts, culling.

### 🎯 Precise alignment & transform

**Why**: Alignment is spread across menus; doing min/center/max and even spacing on many objects takes repeated clicks. This groups those workflows and shows **full-precision** transform readouts so values match external references.

- Object/vertex align, bottom, flatten, align to edge, distribute; optional origin-only sync.

### 🪞 Mirror plus (default `Ctrl+M`)

**Why**: Blender already mirrors—but **adding a modifier, picking an axis, or duplicating first** is still several steps. This **one-shot** picks **modifier-only** vs **duplicate then mirror**, tied to the pie menu and `Ctrl+M`, so symmetry workflows stay short.

- X/Y/Z; same entry under **Add Modifier**.

### 📦 Batch tools

**Why**: Exporting, renaming, and fixing materials are **repeat asset tasks**. Defaults make you redo the same actions per object. Here: multi-selection **batch OBJ**, **regex rename** (`Ctrl+F`), batch materials / cleanup / optional channel sync.

### 🔧 2D kinematics solver

**Why**: Blender targets animation/rigging—there’s **no** planar linkage solver for mechanisms. For linkages and fixtures, this runs **2D iterative solving** in-scene with drivers, sliders, and demo files.

- Revolute/prismatic joints, limits; **NumPy** optional for speed.

### 🎨 Other tools

**Why**: When viewport and final render use **different color management**, material tweaks look wrong in the viewport—**Standard** WYSIWYG preview fixes that; the rest are small quality-of-life tools.

- **WYSIWYG viewport** (View menu): temporary match to output.
- **FPS overlay**, **stress test**, **one-click cleanup**, **numpad .** smart frame (optional outliner sync).

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
