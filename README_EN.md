# ⚡ Blender SPARK Addon

**SPARK** — **S**mart **P**recision **A**lignment, **R**endering & **K**inematics

> Tools are grouped behind a **pie menu + hotkeys** (`ui.py` / `__init__.py`). The add-on also covers workflows Blender doesn’t ship or makes tedious: persistent measurements, batch OBJ with origin metadata, 2D linkage solving, and **OpenGL viewport capture vs Filmic/AgX** mismatch.

**简体中文文档：** [README.md](README.md)

![Blender](https://img.shields.io/badge/Blender-4.2+-orange?logo=blender&logoColor=white)
![License](https://img.shields.io/badge/License-GPL--3.0-blue)
![Version](https://img.shields.io/badge/Version-3.3.1-green)

![SPARK preview](docs/preview.png)

---

## ✨ Why each feature exists (matches the code)

### 📐 Smart measurement & annotations

**In code**: `annotation_core` / `annotation.py` store labels in the scene and persist with the file; `operators_measure.py` creates/updates annotations and can refresh in edit mode.

**Why**: Built-in measure tools don’t stay in the scene as reference. This adds **saved, styleable, clearable** viewport labels.

### 🎯 Alignment & high-precision transform

**In code**: `operators_align.py` aligns to the active object using **bbox min/max/center/bottom/top** references; `TRANSFORM_PT_precise_panel` in `ui.py` uses `utils.format_value` for **full-precision** readouts (not truncated).

**Why**: Common alignments like “sit objects on the floor” are many clicks by hand; precise numbers help match external dimensions.

### 🪞 Mirror plus (`Ctrl+M`, overrides the default mirror binding)

**In code**: `OBJECT_OT_mirror_plus` in `operators_object.py`.

- **Modifier only**: batch-add Mirror for selected meshes, with **`mirror_object`** pointing at a **reference object**—the mirror plane follows that object, not only the mesh local axis; **Clip / merge** are optional.
- **Copy & mirror**: duplicate → temporary Mirror → **`bake_modifiers_to_mesh`** → **`delete_side_by_plane_world`** (one side removed) → optional **`move_origin_keep_world_mesh`**. Result is **real mesh** without a live Mirror modifier.

**Why not “just use Blender mirror”**: fewer manual steps; **copy & mirror** is explicitly a **bake + bisect** path for export, subdivision, or avoiding long-lived Mirror **merge/seam** shading and center-edge topology issues (often what people call “artifacts” on the mirror plane—the repo doesn’t use that word; the logic is `bake` + `delete_side`).

### 📦 Batch export / rename / materials

**In code**: `operators_export.py` (batch OBJ, optional **origin info** file); `OBJECT_OT_batch_rename` (regex + **name conflict** modes); `operators_material.py` (batch apply, slot cleanup, unused purge, optional **material sync** via `depsgraph_update_post`).

**Why**: Repeating the same export/rename/material ops per object is slow.

### 🔧 2D kinematics

**In code**: `operators_kinematics.py` (module header): planar linkages, **Newton–Raphson**, slider drivers, **driver limit** search, demo scenes (e.g. toggle clamp).

**Why**: Blender has no built-in planar linkage solver for fixtures and 2D mechanisms.

### 🎨 WYSIWYG viewport render

**In code**: `operators_render.py` header: default **`bpy.ops.render.opengl`** under Filmic/AgX **does not match** what you see in the viewport; the operator **temporarily switches `view_settings` to Standard** for the capture, then you can **restore** previous settings.

**Why**: Color-matching when comparing viewport and OpenGL renders during look-dev.

### Other tools

| Feature | In code | One-liner |
|---------|---------|-----------|
| **FPS overlay** | `fps_overlay.py` | Modal timer + sliding average so FPS updates even when the view is still. |
| **Perf test** | `operators_perftest.py` | Many random shaded cubes + random motion for a rough stress test. |
| **One-click optimize** | `operators_optimize.py` | Merge by distance, delete interior faces, dissolve degenerate, decimate, etc. in one op. |
| **Smart numpad .** | `BOFU_OT_smart_numpad_period` | Single click: `view_selected`; double: **Outliner** `show_active`. |

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
