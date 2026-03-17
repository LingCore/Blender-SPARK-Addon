# ==================== 标注系统模块（重导出入口） ====================
"""
bofu_enhanced/annotation.py

标注系统的公共 API 入口。所有外部引用继续通过此模块访问，
内部实现拆分到 annotation_core 和 annotation_draw。
"""

from bpy.types import Operator

from .annotation_core import (
    AnnotationKeyGenerator,
    AnnotationManager,
    AnnotationStorage,
    AnnotationCleaner,
    get_annotation_position_key,
    register_annotation,
    unregister_annotation,
    clear_all_annotations,
    clear_temp_annotations,
    get_temp_annotation_count,
    get_bound_annotation_count,
    toggle_annotations_visibility,
    cleanup_deleted_objects,
    ensure_draw_handler_enabled,
    disable_draw_handler,
    ensure_cleanup_timer,
    stop_cleanup_timer,
)

from .annotation_draw import unified_draw_callback


# ==================== 标注管理操作符 ====================

class BOFU_OT_clear_temp_annotations(Operator):
    """清除所有临时标注"""
    bl_idname = "bofu.clear_temp_annotations"
    bl_label = "清除临时标注"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        count = clear_temp_annotations()
        AnnotationCleaner.refresh_view(context)
        if count > 0:
            self.report({'INFO'}, f"已清除 {count} 个临时标注")
        else:
            self.report({'INFO'}, "没有临时标注需要清除")
        return {'FINISHED'}


class BOFU_OT_clear_selected_annotations(Operator):
    """智能清除标注"""
    bl_idname = "bofu.clear_selected_annotations"
    bl_label = "清除选中的标注"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        if context.mode == 'EDIT_MESH':
            return any(obj.type == 'MESH' for obj in context.objects_in_mode)
        elif context.mode == 'OBJECT':
            return bool(context.selected_objects)
        return False
    
    def execute(self, context):
        if context.mode == 'EDIT_MESH':
            cleared_count = AnnotationCleaner.clear_selected_in_edit_mode(context)
            AnnotationCleaner.refresh_view(context)
            select_mode = context.tool_settings.mesh_select_mode
            mode_name = "面" if select_mode[2] else ("边" if select_mode[1] else "顶点")
            if cleared_count > 0:
                self.report({'INFO'}, f"已清除 {cleared_count} 个与选中{mode_name}相关的标注")
            else:
                self.report({'INFO'}, f"选中的{mode_name}没有关联的标注")
        else:
            cleared_count, deleted_count = AnnotationCleaner.clear_selected_in_object_mode(context)
            AnnotationCleaner.refresh_view(context)
            if cleared_count > 0 or deleted_count > 0:
                msg = f"已清除 {cleared_count} 个标注"
                if deleted_count > 0:
                    msg += f"，删除 {deleted_count} 个测量对象"
                self.report({'INFO'}, msg)
            else:
                self.report({'INFO'}, "选中的对象没有关联的标注")
        return {'FINISHED'}


class BOFU_OT_clear_all_annotations(Operator):
    """清除所有标注"""
    bl_idname = "bofu.clear_all_annotations"
    bl_label = "清除所有标注"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        count = len(AnnotationManager.get_registry())
        clear_all_annotations()
        AnnotationCleaner.refresh_view(context)
        if count > 0:
            self.report({'INFO'}, f"已清除 {count} 个标注")
        else:
            self.report({'INFO'}, "没有标注需要清除")
        return {'FINISHED'}


class BOFU_OT_toggle_annotations(Operator):
    """显示/隐藏所有标注"""
    bl_idname = "bofu.toggle_annotations"
    bl_label = "显示/隐藏标注"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        visible = toggle_annotations_visibility()
        AnnotationCleaner.refresh_view(context)
        self.report({'INFO'}, f"标注已{'显示' if visible else '隐藏'}")
        return {'FINISHED'}


class BOFU_OT_annotation_info(Operator):
    """显示当前标注统计信息"""
    bl_idname = "bofu.annotation_info"
    bl_label = "标注信息"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        temp_count = get_temp_annotation_count()
        bound_count = get_bound_annotation_count()
        total = temp_count + bound_count
        self.report({'INFO'}, f"标注总数: {total}（临时: {temp_count}, 绑定对象: {bound_count}）")
        return {'FINISHED'}


class BOFU_OT_save_annotations(Operator):
    """保存标注到场景"""
    bl_idname = "bofu.save_annotations"
    bl_label = "保存标注"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        if AnnotationStorage.save_to_scene(context.scene):
            self.report({'INFO'}, "标注数据已保存")
        else:
            self.report({'WARNING'}, "保存标注数据失败")
        return {'FINISHED'}


class BOFU_OT_load_annotations(Operator):
    """从场景加载标注"""
    bl_idname = "bofu.load_annotations"
    bl_label = "加载标注"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        count = AnnotationStorage.load_from_scene(context.scene)
        ensure_draw_handler_enabled()
        AnnotationCleaner.refresh_view(context)
        if count > 0:
            self.report({'INFO'}, f"已加载 {count} 个标注")
        else:
            self.report({'INFO'}, "没有找到保存的标注数据")
        return {'FINISHED'}


# ==================== 类注册列表 ====================

classes = (
    BOFU_OT_clear_temp_annotations,
    BOFU_OT_clear_selected_annotations,
    BOFU_OT_clear_all_annotations,
    BOFU_OT_toggle_annotations,
    BOFU_OT_annotation_info,
    BOFU_OT_save_annotations,
    BOFU_OT_load_annotations,
)
