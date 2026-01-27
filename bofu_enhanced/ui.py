# ==================== UI 模块 ====================
"""
bofu_enhanced/ui.py

菜单和面板定义
"""

import bpy
from bpy.types import Menu, Panel, Operator

from .utils import format_value


# ==================== 饼图菜单 ====================

class VIEW3D_MT_PIE_bofu_tools(Menu):
    """小夫的增强工具饼图菜单"""
    bl_idname = "VIEW3D_MT_PIE_bofu_tools"
    bl_label = "小夫的增强工具"

    def draw(self, context):
        layout = self.layout
        pie = layout.menu_pie()
        
        # 左 (West) - 镜像增强
        pie.operator("object.mirror_plus", text="镜像（增强）", icon='MOD_MIRROR')
        
        # 右 (East) - 名称批量替换
        pie.operator("object.batch_rename_plus", text="名称批量替换", icon='SORTALPHA')
        
        # 下 (South) - 批量材质
        pie.operator("material.apply_to_selected", text="批量应用材质", icon='MATERIAL')
        
        # 上 (North) - 批量导出OBJ
        pie.operator("export.batch_obj_with_origin", text="批量导出OBJ", icon='EXPORT')
        
        # 左上 (Northwest) - 复制位置
        pie.operator("transform.copy_location", text="复制位置", icon='ORIENTATION_GLOBAL')
        
        # 右上 (Northeast) - 标注管理子菜单
        pie.menu("VIEW3D_MT_annotation_manage", text="标注管理", icon='FONT_DATA')
        
        # 左下 (Southwest) - 智能测量
        pie.operator("object.connect_origins", text="智能测量", icon='DRIVER_DISTANCE')
        
        # 右下 (Southeast) - 对齐工具子菜单
        pie.menu("VIEW3D_MT_align_tools", text="对齐工具", icon='ALIGN_CENTER')


class VIEW3D_MT_annotation_manage(Menu):
    """标注管理子菜单"""
    bl_idname = "VIEW3D_MT_annotation_manage"
    bl_label = "标注管理"
    
    def draw(self, context):
        layout = self.layout
        
        # 自动覆盖开关
        if hasattr(context.scene, 'annotation_settings'):
            settings = context.scene.annotation_settings
            icon = 'CHECKBOX_HLT' if settings.auto_overwrite else 'CHECKBOX_DEHLT'
            layout.prop(settings, "auto_overwrite", icon=icon)
            layout.separator()
        
        layout.operator("bofu.toggle_annotations", text="显示/隐藏标注", icon='HIDE_OFF')
        layout.separator()
        
        # 根据当前模式显示不同的提示
        if context.mode == 'EDIT_MESH':
            select_mode = context.tool_settings.mesh_select_mode
            mode_name = "面" if select_mode[2] else ("边" if select_mode[1] else "顶点")
            layout.operator("bofu.clear_selected_annotations", text=f"清除选中{mode_name}的标注", icon='PANEL_CLOSE')
        else:
            layout.operator("bofu.clear_selected_annotations", text="清除选中对象的标注", icon='PANEL_CLOSE')
        
        layout.operator("bofu.clear_temp_annotations", text="清除临时标注", icon='X')
        layout.operator("bofu.clear_all_annotations", text="清除所有标注", icon='TRASH')
        layout.separator()
        layout.operator("bofu.annotation_info", text="标注信息", icon='INFO')


class VIEW3D_MT_align_tools(Menu):
    """对齐工具子菜单"""
    bl_idname = "VIEW3D_MT_align_tools"
    bl_label = "对齐工具"
    
    def draw(self, context):
        layout = self.layout
        
        # 根据当前模式显示不同选项
        if context.mode == 'EDIT_MESH':
            layout.operator("mesh.align_vertices_plus", text="对齐顶点（增强）", icon='ALIGN_CENTER')
            layout.operator("mesh.flatten_selection", text="展平选区", icon='MESH_PLANE')
            layout.operator("mesh.align_to_edge", text="对齐到边", icon='IPO_LINEAR')
            layout.separator()
            op = layout.operator("object.align_to_active_direction", text="对齐到活动面法线", icon='ORIENTATION_NORMAL')
            op.align_mode = 'FACE_NORMAL'
            
            # 快速对齐
            layout.separator()
            op = layout.operator("mesh.quick_align_axis", text="快速对齐 X", icon='EVENT_X')
            op.axis = 'X'
            op.target = 'ACTIVE'
            op = layout.operator("mesh.quick_align_axis", text="快速对齐 Y", icon='EVENT_Y')
            op.axis = 'Y'
            op.target = 'ACTIVE'
            op = layout.operator("mesh.quick_align_axis", text="快速对齐 Z", icon='EVENT_Z')
            op.axis = 'Z'
            op.target = 'ACTIVE'
        else:
            layout.operator("object.align_objects_plus", text="对齐（增强）", icon='ALIGN_CENTER')
            op = layout.operator("object.align_to_active_direction", text="对齐到活动对象局部轴", icon='ORIENTATION_LOCAL')
            op.align_mode = 'ACTIVE_AXIS'
            layout.operator("object.quick_align", text="快速底部对齐 Z", icon='ALIGN_BOTTOM').align_axis = 'Z'
            layout.separator()
            layout.operator("object.distribute_objects", text="均匀分布", icon='ALIGN_JUSTIFY')


class BOFU_OT_call_pie_menu(Operator):
    """呼出小夫的增强工具饼图菜单"""
    bl_idname = "bofu.call_pie_menu"
    bl_label = "小夫的增强工具"
    bl_options = {'REGISTER'}

    def execute(self, context):
        bpy.ops.wm.call_menu_pie(name="VIEW3D_MT_PIE_bofu_tools")
        return {'FINISHED'}


# ==================== 面板定义 ====================

class TRANSFORM_PT_precise_panel(Panel):
    """高精度变换面板（增强版）"""
    bl_label = "变换（增强）"
    bl_idname = "TRANSFORM_PT_precise_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Item"
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        obj = context.active_object
        
        if obj is None:
            layout.label(text="未选中对象", icon='INFO')
            return
        
        col = layout.column(align=True)
        col.scale_x = 1.2
        
        # 位置
        row = col.row(align=True)
        row.operator("transform.copy_location", text="位置 (点击复制)", icon='ORIENTATION_GLOBAL', emboss=True)
        
        transform_props = context.scene.transform_plus_props
        if obj.type == 'MESH':
            box = col.box()
            box.prop(transform_props, "only_modify_origin", text="只修改原点位置", toggle=True)
        
        sub = col.column(align=True)
        if obj.type == 'MESH' and transform_props.only_modify_origin:
            for i in range(3):
                axis = ['X', 'Y', 'Z'][i]
                value = transform_props.origin_location[i]
                row = sub.row(align=True)
                row.prop(transform_props, "origin_location", index=i, text=f"{axis}  {format_value(value)}")
                row.prop(obj, "lock_location", index=i, text="", icon_only=True, emboss=False)
        else:
            for i in range(3):
                axis = ['X', 'Y', 'Z'][i]
                value = [obj.location.x, obj.location.y, obj.location.z][i]
                row = sub.row(align=True)
                row.prop(obj, "location", index=i, text=f"{axis}  {format_value(value)}")
                row.prop(obj, "lock_location", index=i, text="", icon_only=True, emboss=False)
        
        col.separator()
        
        # 旋转
        row = col.row(align=True)
        row.operator("transform.copy_rotation", text="旋转 (点击复制)", icon='ORIENTATION_GIMBAL', emboss=True)
        col.separator(factor=0.5)
        col.prop(obj, "rotation_mode", text="")
        col.separator(factor=0.5)
        
        sub = col.column(align=True)
        if obj.rotation_mode == 'QUATERNION':
            for i, axis in enumerate(['W', 'X', 'Y', 'Z']):
                value = obj.rotation_quaternion[i]
                row = sub.row(align=True)
                row.prop(obj, "rotation_quaternion", index=i, text=f"{axis}  {format_value(value, axis != 'W')}")
                if i == 0:
                    row.prop(obj, "lock_rotation_w", text="", icon_only=True, emboss=False)
                else:
                    row.prop(obj, "lock_rotation", index=i-1, text="", icon_only=True, emboss=False)
        elif obj.rotation_mode == 'AXIS_ANGLE':
            for i, axis in enumerate(['W', 'X', 'Y', 'Z']):
                value = obj.rotation_axis_angle[i]
                row = sub.row(align=True)
                row.prop(obj, "rotation_axis_angle", index=i, text=f"{axis}  {format_value(value, i == 0)}")
                if i > 0:
                    row.prop(obj, "lock_rotation", index=i-1, text="", icon_only=True, emboss=False)
                else:
                    row.label(text="", icon='BLANK1')
        else:
            for i, axis in enumerate(['X', 'Y', 'Z']):
                value = [obj.rotation_euler.x, obj.rotation_euler.y, obj.rotation_euler.z][i]
                row = sub.row(align=True)
                row.prop(obj, "rotation_euler", index=i, text=f"{axis}  {format_value(value, True)}")
                row.prop(obj, "lock_rotation", index=i, text="", icon_only=True, emboss=False)

        col.separator()
        
        # 缩放
        row = col.row(align=True)
        row.operator("transform.copy_scale", text="缩放 (点击复制)", icon='FULLSCREEN_EXIT', emboss=True)
        sub = col.column(align=True)
        for i in range(3):
            axis = ['X', 'Y', 'Z'][i]
            value = [obj.scale.x, obj.scale.y, obj.scale.z][i]
            row = sub.row(align=True)
            row.prop(obj, "scale", index=i, text=f"{axis}  {format_value(value)}")
            row.prop(obj, "lock_scale", index=i, text="", icon_only=True, emboss=False)
        
        # 尺寸（仅网格对象）
        if obj.type == 'MESH':
            col.separator()
            row = col.row(align=True)
            row.operator("transform.copy_dimensions", text="尺寸 (点击复制)", icon='ARROW_LEFTRIGHT', emboss=True)
            sub = col.column(align=True)
            for i in range(3):
                axis = ['X', 'Y', 'Z'][i]
                value = [obj.dimensions.x, obj.dimensions.y, obj.dimensions.z][i]
                sub.prop(obj, "dimensions", index=i, text=f"{axis}  {format_value(value)} m")


# ==================== 类注册列表 ====================

classes = (
    VIEW3D_MT_PIE_bofu_tools,
    VIEW3D_MT_annotation_manage,
    VIEW3D_MT_align_tools,
    BOFU_OT_call_pie_menu,
    TRANSFORM_PT_precise_panel,
)
