# ⚡ Blender SPARK Addon

**SPARK** — **S**mart **P**recision **A**lignment, **R**endering & **K**inematics

> Common tools live behind a **pie menu + hotkeys**. The add-on also fills gaps Blender doesn’t provide or makes painful: measurements that save with the file, batch OBJ export with optional origin metadata, 2D linkage solving, and fixing **Filmic/AgX** look-dev where the viewport and **OpenGL render** don’t match.

**简体中文文档：** [README.md](README.md)

![Blender](https://img.shields.io/badge/Blender-4.2+-orange?logo=blender&logoColor=white)
![License](https://img.shields.io/badge/License-GPL--3.0-blue)
![Version](https://img.shields.io/badge/Version-3.3.4-green)

![SPARK preview](docs/preview.png)

---

## ✨ Features

### 📐 Smart measurement & annotations

Built-in measure tools don’t stay in the scene as a reference. Here, results are **viewport labels** that **save with the file**, can be cleared, and respect style settings; in edit mode, relevant labels can track geometry changes.

- Distances, angles, radius/diameter, area, perimeter, arc length; prefs for auto save/load, fonts, and distance culling.

### 🎯 Alignment & high-precision transform

Aligning many objects (bottom to floor, even spacing, etc.) gets click-heavy with defaults. This groups several align modes in one place. The **Transform (enhanced)** sidebar shows **full-precision** numbers so you can match drawings or external data. Optional origin sync when you use origin-only workflows.

- Object/vertex align, bottom align, flatten, align to edge, distribute.

### 🪞 Mirror plus (`Ctrl+M`)

Blender already has Mirror—but batching objects, using **another object as the mirror plane**, or switching between **modifier-only** and **duplicate-then-mirror** still takes many steps, so this wraps them behind one operator.

- **Modifier only**: batch Mirror on a selection; the plane comes from a **mirror object** (any reference), not only the mesh’s own axes; **clip / merge** on the seam are optional.
- **Copy & mirror**: duplicate → temporary mirror → **bake to real mesh** → **delete geometry on one side of the plane** → optionally **move the origin** to the mirrored side. You end up with **no Mirror modifier left**—handy for subdivision, export, or avoiding long-lived mirror **seam shading and mid-edge topology** issues.

### 📦 Batch export / rename / materials

Renaming, exporting OBJ, and assigning materials doesn’t scale: you repeat the same work per asset. This adds **batch OBJ** (optional **origin info** sidecar), **regex rename** with conflict handling (skip / replace / suffix), and **material tools** (quick sync to a chosen material, batch apply, tidy slots, purge unused).

- Origin info can be written as `ObjectName: { -2.350247f, 0.003200f, 0.911799f }`, JSON objects, or CSV, so developers can copy coordinates directly.
- `Ctrl + Alt + M` opens a material picker and replaces selected mesh objects with the chosen material.

### 🔧 2D kinematics

Blender doesn’t ship a **planar linkage solver** for fixtures and mechanisms. This adds **2D** solving (e.g. Newton–Raphson), joints, drivers, limits, and demo scenes—for **2D linkages**, not character rigging.

### 🎨 WYSIWYG viewport render

With **Filmic / AgX** view transforms, what you **see in the viewport** and what you get from **viewport OpenGL render** often **don’t match**, which misleads material work. This tool **temporarily switches to Standard** for that render, then you **restore** color settings from the menu.

### Other tools

| Feature | What it does |
|---------|----------------|
| **FPS overlay** | Live FPS in the corner; updates even when nothing moves. |
| **Rotation snapshot / restore** | Alt+R clears rotation after saving a snapshot; Alt+Shift+R restores it. |
| **Mode switch pie** | Hold Tab for a mode-switch pie; tap Tab still toggles Object/Edit mode. |
| **Perf test** | Creates 500 random shaded cubes moving randomly—rough stress test. |
| **One-click optimize** | Merge by distance, delete interior faces, dissolve degenerate geometry, decimate—one pass. |
| **Smart numpad .** | Single click: frame selection; double click: **find the active object in the Outliner**. |

---

## 🧭 Where to find things

| Entry | What it does |
|--------|----------------|
| **`` ` ``** (Accent Grave) | Opens the **enhanced tools pie menu** (main hub). |
| **Mouse side button** (often Button4) | Same as above. |
| **Hold Tab** | Opens the **mode switch pie**; tap Tab still toggles Object/Edit mode. |
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
| Hold `Tab` | **Mode switch pie** |
| `Ctrl + M` | Mirror plus |
| `Ctrl + F` | Batch rename |
| `Ctrl + Alt + M` | Sync selected objects to a chosen material |
| `Alt + R` | Clear rotation after saving a snapshot |
| `Alt + Shift + R` | Restore rotation snapshot |
| Numpad `.` | Smart frame / outliner focus |

> Hotkeys apply when the add-on is enabled and **no other add-on** uses the same bindings. Adjust under **Preferences → Keymap** if needed (search for `bofu` / `SPARK`).

---

## 📋 Requirements

| Component | Notes |
|-----------|--------|
| **Blender** | ≥ 4.2 (matches `bl_info`). |
| **Python** | Bundled with Blender. |
| **NumPy** | **Optional**; measurement / kinematics use it when available for heavy data. |

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
