# ==================== Blender 增强工具包入口 ====================
"""
bofu_enhanced/__init__.py

Blender 4.2+ 增强工具包
作者：杨博夫

模块化结构：
- config.py: 配置常量
- render_utils.py: 绘制工具（Shader缓存、标签渲染器）
- preferences.py: 插件偏好设置
- utils.py: 共享工具函数
- properties.py: PropertyGroup 定义
- annotation.py: 标注系统（含持久化）
- operators_object.py: 对象级操作符（镜像、批量重命名）
- operators_transform.py: 变换复制操作符
- operators_align.py: 对齐工具操作符
- operators_export.py: 批量导出操作符
- operators_material.py: 批量材质操作符
- operators_measure.py: 智能测量操作符
- operators_kinematics.py: 机构运动学（求解器、关节、驱动极限自动计算）
- operators_demo.py: 演示场景
- ui.py: 菜单和面板
"""

bl_info = {
    "name": "Blender_增强_by.bofu",
    "author": "杨博夫",
    "version": (3, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > ` 键或鼠标侧键呼出饼图菜单, Ctrl+M, Ctrl+F",
    "description": "批量导出OBJ文件，高精度变换显示，批量材质管理，增强镜像功能，名称批量替换，饼图快捷菜单，智能测量标注，机构运动学求解器",
    "warning": "",
    "doc_url": "",
    "tracker_url": "",
    "category": "3D View",
}

import bpy
import gc
from bpy.app.handlers import persistent

# ==================== 模块导入（支持热重载）====================

# 热重载支持：如果子模块已经加载过，则强制刷新
if "config" in locals():
    import importlib
    importlib.reload(config)
    importlib.reload(render_utils)
    importlib.reload(preferences)
    importlib.reload(properties)
    importlib.reload(annotation)
    importlib.reload(operators_object)
    importlib.reload(operators_transform)
    importlib.reload(operators_align)
    importlib.reload(operators_export)
    importlib.reload(operators_material)
    importlib.reload(operators_measure)
    importlib.reload(operators_kinematics)
    importlib.reload(operators_demo)
    importlib.reload(ui)

from . import config
from . import render_utils
from . import preferences
from . import properties
from . import annotation
from . import operators_object
from . import operators_transform
from . import operators_align
from . import operators_export
from . import operators_material
from . import operators_measure
from . import operators_kinematics
from . import operators_demo
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


@persistent
def save_annotations_handler(dummy):
    """保存文件时自动保存标注数据"""
    try:
        # 检查偏好设置
        addon_prefs = bpy.context.preferences.addons.get('bofu_enhanced')
        if addon_prefs and hasattr(addon_prefs.preferences, 'auto_save_annotations'):
            if not addon_prefs.preferences.auto_save_annotations:
                return
        
        # 保存标注到当前场景
        if bpy.context.scene:
            annotation.AnnotationStorage.save_to_scene(bpy.context.scene)
    except Exception as e:
        print(f"⚠️ 自动保存标注失败: {e}")


@persistent
def load_annotations_handler(dummy):
    """加载文件时自动加载标注数据"""
    try:
        # 检查偏好设置
        addon_prefs = bpy.context.preferences.addons.get('bofu_enhanced')
        if addon_prefs and hasattr(addon_prefs.preferences, 'auto_load_annotations'):
            if not addon_prefs.preferences.auto_load_annotations:
                return
        
        # 从当前场景加载标注
        if bpy.context.scene:
            annotation.AnnotationStorage.load_from_scene(bpy.context.scene)
            annotation.ensure_draw_handler_enabled()
    except Exception as e:
        print(f"⚠️ 自动加载标注失败: {e}")


@persistent
def material_sync_handler(scene, depsgraph):
    """材质自动同步处理器"""
    try:
        if not scene or not hasattr(scene, 'misc_settings'):
            return
        
        if not scene.misc_settings.material_sync_enabled:
            return
        
        # 获取活动对象的活动材质
        context = bpy.context
        if not context or not context.active_object:
            return
        
        obj = context.active_object
        if obj.type != 'MESH' or not obj.active_material:
            return
        
        # 同步材质
        operators_material.sync_material_auto(obj.active_material)
    except Exception:
        pass  # 静默处理错误，避免干扰用户


# ==================== 注册/注销 ====================

def register():
    """注册插件"""
    global _original_panel_categories
    
    # 1. 注册偏好设置类（必须最先注册）
    for cls in preferences.classes:
        bpy.utils.register_class(cls)
    
    # 2. 注册所有其他类
    all_classes = (
        properties.classes +
        annotation.classes +
        operators_object.classes +
        operators_transform.classes +
        operators_align.classes +
        operators_export.classes +
        operators_material.classes +
        operators_measure.classes +
        operators_kinematics.classes +
        operators_demo.classes +
        ui.classes
    )
    
    for cls in all_classes:
        bpy.utils.register_class(cls)
    
    # 3. 注册属性
    properties.register_properties()
    
    # 4. 注册处理器
    if transform_plus_origin_sync not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(transform_plus_origin_sync)
    
    # 5. 注册材质同步处理器
    if material_sync_handler not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(material_sync_handler)
    
    # 6. 注册标注持久化处理器
    if save_annotations_handler not in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.append(save_annotations_handler)
    if load_annotations_handler not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(load_annotations_handler)
    
    # 7. 启用标注绘制处理器
    annotation.ensure_draw_handler_enabled()
    
    # 8. 添加到修改器菜单（先尝试移除旧的，避免重复）
    if hasattr(bpy.types, "OBJECT_MT_modifier_add_generate"):
        menu_type = bpy.types.OBJECT_MT_modifier_add_generate
    else:
        menu_type = bpy.types.OBJECT_MT_modifier_add
    
    try:
        menu_type.remove(operators_object.menu_func_mirror)
    except (ValueError, RuntimeError):
        pass
    menu_type.append(operators_object.menu_func_mirror)
    
    # 9. 注册快捷键
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
    
    # 10. 移动默认变换面板到隐藏标签页
    try:
        panel = getattr(bpy.types, 'VIEW3D_PT_transform', None)
        if panel and hasattr(panel, 'bl_category'):
            _original_panel_categories['VIEW3D_PT_transform'] = panel.bl_category
            panel.bl_category = "Item (旧版)"
    except Exception:
        pass
    
    print("[Blender增强工具] 插件已加载 v3.1.0")


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
    
    # 4. 移除持久化处理器
    if save_annotations_handler in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(save_annotations_handler)
    if load_annotations_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(load_annotations_handler)
    
    # 5. 移除快捷键
    for km, kmi in addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except (ReferenceError, RuntimeError):
            pass
    addon_keymaps.clear()
    
    # 6. 移除菜单
    if hasattr(bpy.types, "OBJECT_MT_modifier_add_generate"):
        try:
            bpy.types.OBJECT_MT_modifier_add_generate.remove(operators_object.menu_func_mirror)
        except (ValueError, RuntimeError):
            pass
    else:
        try:
            bpy.types.OBJECT_MT_modifier_add.remove(operators_object.menu_func_mirror)
        except (ValueError, RuntimeError):
            pass
    
    # 7. 移除处理器
    if transform_plus_origin_sync in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(transform_plus_origin_sync)
    if material_sync_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(material_sync_handler)
    
    # 8. 清除材质同步缓存
    operators_material.clear_material_cache()
    
    # 9. 注销属性
    properties.unregister_properties()
    
    # 10. 注销所有类（逆序）
    all_classes = (
        properties.classes +
        annotation.classes +
        operators_object.classes +
        operators_transform.classes +
        operators_align.classes +
        operators_export.classes +
        operators_material.classes +
        operators_measure.classes +
        operators_kinematics.classes +
        operators_demo.classes +
        ui.classes
    )
    
    for cls in reversed(all_classes):
        try:
            bpy.utils.unregister_class(cls)
        except (RuntimeError, ValueError):
            pass
    
    # 11. 注销偏好设置类（最后注销）
    for cls in reversed(preferences.classes):
        try:
            bpy.utils.unregister_class(cls)
        except (RuntimeError, ValueError):
            pass
    
    # 12. 清除 Shader 缓存
    render_utils.ShaderCache.clear()
    
    # 13. 恢复被移动的面板
    for name, original_category in _original_panel_categories.items():
        try:
            panel = getattr(bpy.types, name, None)
            if panel:
                panel.bl_category = original_category
        except Exception:
            pass
    _original_panel_categories.clear()
    
    # 14. 强制垃圾回收
    gc.collect()
    print("[Blender增强工具] 插件已卸载，内存已清理")


if __name__ == "__main__":
    register()
