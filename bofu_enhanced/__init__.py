# ==================== Blender 增强工具包入口 ====================
"""
bofu_enhanced/__init__.py

Blender 4.2+ 增强工具包
作者：杨博夫

模块化结构：
- utils.py: 共享工具函数
- properties.py: PropertyGroup 定义
- annotation.py: 标注系统
- operators_object.py: 对象级操作符（镜像、批量重命名）
- operators_transform.py: 变换复制操作符
- operators_align.py: 对齐工具操作符
- operators_export.py: 批量导出操作符
- operators_material.py: 批量材质操作符
- operators_measure.py: 智能测量操作符
- ui.py: 菜单和面板
"""

bl_info = {
    "name": "Blender_增强_by.bofu",
    "author": "杨博夫",
    "version": (3, 0, 0),
    "blender": (4, 2, 0),
    "location": "View3D > ` 键或鼠标侧键呼出饼图菜单, Ctrl+M, Ctrl+F",
    "description": "批量导出OBJ文件，高精度变换显示，批量材质管理，增强镜像功能，名称批量替换，饼图快捷菜单",
    "warning": "",
    "doc_url": "",
    "category": "3D View",
}

import bpy
import gc
from bpy.app.handlers import persistent

# ==================== 模块导入 ====================

from . import properties
from . import annotation
from . import operators_object
from . import operators_transform
from . import operators_align
from . import operators_export
from . import operators_material
from . import operators_measure
from . import ui


# ==================== 全局状态 ====================

# 存储被修改的面板原始 category，用于恢复
_original_panel_categories = {}

# 快捷键映射
addon_keymaps = []


# ==================== 处理器 ====================

@persistent
def transform_plus_origin_sync(scene, depsgraph):
    """原点同步处理器"""
    if not scene or not hasattr(scene, "transform_plus_props"):
        return
    props = scene.transform_plus_props
    if not props.only_modify_origin:
        return
    
    view_layer = None
    context = bpy.context
    if context and context.scene == scene:
        view_layer = context.view_layer
    if view_layer is None and len(scene.view_layers) > 0:
        view_layer = scene.view_layers[0]
    if view_layer is None:
        return
    
    obj = view_layer.objects.active
    if not obj or obj.type != 'MESH':
        if props.last_origin_object:
            props.last_origin_object = ""
        return
    
    if props.last_origin_object == obj.name:
        return
    
    props.last_origin_object = obj.name
    props.origin_location = obj.location.copy()


# ==================== 注册/注销 ====================

def register():
    """注册插件"""
    global _original_panel_categories
    
    # 1. 注册所有类
    all_classes = (
        properties.classes +
        annotation.classes +
        operators_object.classes +
        operators_transform.classes +
        operators_align.classes +
        operators_export.classes +
        operators_material.classes +
        operators_measure.classes +
        ui.classes
    )
    
    for cls in all_classes:
        bpy.utils.register_class(cls)
    
    # 2. 注册属性
    properties.register_properties()
    
    # 3. 注册处理器
    if transform_plus_origin_sync not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(transform_plus_origin_sync)
    
    # 4. 启用标注绘制处理器
    annotation.ensure_draw_handler_enabled()
    
    # 5. 添加到修改器菜单（先尝试移除旧的，避免重复）
    if hasattr(bpy.types, "OBJECT_MT_modifier_add_generate"):
        menu_type = bpy.types.OBJECT_MT_modifier_add_generate
    else:
        menu_type = bpy.types.OBJECT_MT_modifier_add
    
    try:
        menu_type.remove(operators_object.menu_func_mirror)
    except Exception:
        pass
    menu_type.append(operators_object.menu_func_mirror)
    
    # 6. 注册快捷键
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        # Ctrl+M: 镜像增强
        km = kc.keymaps.new(name="Object Mode", space_type="EMPTY")
        kmi = km.keymap_items.new(operators_object.OBJECT_OT_mirror_plus.bl_idname, type="M", value="PRESS", ctrl=True)
        addon_keymaps.append((km, kmi))
        km = kc.keymaps.new(name="3D View", space_type="VIEW_3D")
        kmi = km.keymap_items.new(operators_object.OBJECT_OT_mirror_plus.bl_idname, type="M", value="PRESS", ctrl=True)
        addon_keymaps.append((km, kmi))
        
        # Ctrl+F: 名称批量替换
        km = kc.keymaps.new(name="Object Mode", space_type="EMPTY")
        kmi = km.keymap_items.new(operators_object.OBJECT_OT_batch_rename.bl_idname, type="F", value="PRESS", ctrl=True)
        addon_keymaps.append((km, kmi))
        km = kc.keymaps.new(name="3D View", space_type="VIEW_3D")
        kmi = km.keymap_items.new(operators_object.OBJECT_OT_batch_rename.bl_idname, type="F", value="PRESS", ctrl=True)
        addon_keymaps.append((km, kmi))
        
        # 波浪键 (`): 饼图菜单
        km = kc.keymaps.new(name="3D View", space_type="VIEW_3D")
        kmi = km.keymap_items.new(ui.BOFU_OT_call_pie_menu.bl_idname, type="ACCENT_GRAVE", value="PRESS")
        addon_keymaps.append((km, kmi))
        km = kc.keymaps.new(name="Object Mode", space_type="EMPTY")
        kmi = km.keymap_items.new(ui.BOFU_OT_call_pie_menu.bl_idname, type="ACCENT_GRAVE", value="PRESS")
        addon_keymaps.append((km, kmi))
        
        # 鼠标侧键: 饼图菜单
        km = kc.keymaps.new(name="3D View", space_type="VIEW_3D")
        kmi = km.keymap_items.new(ui.BOFU_OT_call_pie_menu.bl_idname, type="BUTTON4MOUSE", value="PRESS")
        addon_keymaps.append((km, kmi))
        km = kc.keymaps.new(name="Object Mode", space_type="EMPTY")
        kmi = km.keymap_items.new(ui.BOFU_OT_call_pie_menu.bl_idname, type="BUTTON4MOUSE", value="PRESS")
        addon_keymaps.append((km, kmi))
    
    # 7. 移动默认变换面板到隐藏标签页
    try:
        panel = getattr(bpy.types, 'VIEW3D_PT_transform', None)
        if panel and hasattr(panel, 'bl_category'):
            _original_panel_categories['VIEW3D_PT_transform'] = panel.bl_category
            panel.bl_category = "Item (旧版)"
    except Exception:
        pass
    
    print("[Blender增强工具] 插件已加载")


def unregister():
    """注销插件"""
    global _original_panel_categories
    
    # 1. 移除标注绘制处理器
    annotation.disable_draw_handler()
    
    # 2. 清除标注数据
    annotation.clear_all_annotations()
    
    # 3. 清理绘制回调的属性
    if hasattr(annotation.unified_draw_callback, '_last_cleanup_time'):
        delattr(annotation.unified_draw_callback, '_last_cleanup_time')
    
    # 4. 移除快捷键
    for km, kmi in addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except (ReferenceError, RuntimeError):
            pass
    addon_keymaps.clear()
    
    # 5. 移除菜单
    if hasattr(bpy.types, "OBJECT_MT_modifier_add_generate"):
        try:
            bpy.types.OBJECT_MT_modifier_add_generate.remove(operators_object.menu_func_mirror)
        except Exception:
            pass
    else:
        try:
            bpy.types.OBJECT_MT_modifier_add.remove(operators_object.menu_func_mirror)
        except Exception:
            pass
    
    # 6. 移除处理器
    if transform_plus_origin_sync in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(transform_plus_origin_sync)
    
    # 7. 注销属性
    properties.unregister_properties()
    
    # 8. 注销所有类（逆序）
    all_classes = (
        properties.classes +
        annotation.classes +
        operators_object.classes +
        operators_transform.classes +
        operators_align.classes +
        operators_export.classes +
        operators_material.classes +
        operators_measure.classes +
        ui.classes
    )
    
    for cls in reversed(all_classes):
        bpy.utils.unregister_class(cls)
    
    # 9. 恢复被移动的面板
    for name, original_category in _original_panel_categories.items():
        try:
            panel = getattr(bpy.types, name, None)
            if panel:
                panel.bl_category = original_category
        except Exception:
            pass
    _original_panel_categories.clear()
    
    # 10. 强制垃圾回收
    gc.collect()
    print("[Blender增强工具] 插件已卸载，内存已清理")


if __name__ == "__main__":
    register()
