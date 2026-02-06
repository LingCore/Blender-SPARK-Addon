# ==================== UI 模块 ====================
"""
bofu_enhanced/ui.py

菜单和面板定义
"""

import bpy
import bmesh
from bpy.types import Menu, Panel, Operator
from mathutils import Vector

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
        
        # 下 (South) - 材质工具（弹出独立菜单）
        pie.operator("bofu.popup_material_menu", text="材质工具", icon='MATERIAL')
        
        # 上 (North) - 批量导出OBJ
        pie.operator("export.batch_obj_with_origin", text="批量导出OBJ", icon='EXPORT')
        
        # 左上 (Northwest) - 复制位置（根据模式动态显示）
        if context.mode == 'EDIT_MESH':
            select_mode = context.tool_settings.mesh_select_mode
            if select_mode[2]:
                copy_text = "复制面位置"
            elif select_mode[1]:
                copy_text = "复制边位置"
            else:
                copy_text = "复制顶点位置"
        else:
            copy_text = "复制位置"
        pie.operator("transform.copy_location", text=copy_text, icon='ORIENTATION_GLOBAL')
        
        # 右上 (Northeast) - 标注管理（弹出独立菜单，不打断饼图）
        pie.operator("bofu.popup_annotation_menu", text="标注管理", icon='FONT_DATA')
        
        # 左下 (Southwest) - 智能测量
        pie.operator("object.connect_origins", text="智能测量", icon='DRIVER_DISTANCE')
        
        # 右下 (Southeast) - 对齐工具（弹出独立菜单，不打断饼图）
        pie.operator("bofu.popup_align_menu", text="对齐工具", icon='ALIGN_CENTER')


class VIEW3D_MT_material_tools(Menu):
    """材质工具子菜单"""
    bl_idname = "VIEW3D_MT_material_tools"
    bl_label = "材质工具"
    
    def draw(self, context):
        layout = self.layout
        
        # 批量应用材质
        layout.operator("material.apply_to_selected", text="批量应用材质", icon='MATERIAL')
        
        layout.separator()
        
        # 材质槽整理
        layout.operator("material.cleanup_slots", text="整理材质槽", icon='BRUSH_DATA')
        
        # 清理未使用材质
        layout.operator("material.cleanup_unused", text="清理未使用材质", icon='TRASH')
        
        layout.separator()
        
        # 材质同步开关
        if hasattr(context.scene, 'misc_settings'):
            settings = context.scene.misc_settings
            icon = 'CHECKBOX_HLT' if settings.material_sync_enabled else 'CHECKBOX_DEHLT'
            layout.prop(settings, "material_sync_enabled", icon=icon)
            if settings.material_sync_enabled:
                row = layout.row()
                row.alert = True
                row.label(text="颜色/金属度/糙度 自动同步中", icon='LINKED')


class VIEW3D_MT_misc_tools(Menu):
    """杂项工具子菜单"""
    bl_idname = "VIEW3D_MT_misc_tools"
    bl_label = "杂项"
    
    def draw(self, context):
        layout = self.layout
        
        # 材质同步开关
        if hasattr(context.scene, 'misc_settings'):
            settings = context.scene.misc_settings
            icon = 'CHECKBOX_HLT' if settings.material_sync_enabled else 'CHECKBOX_DEHLT'
            row = layout.row()
            row.prop(settings, "material_sync_enabled", icon=icon)
            if settings.material_sync_enabled:
                row = layout.row()
                row.alert = True  # 使用警告色（橙黄色）更显眼
                row.label(text="颜色/金属度/糙度 自动同步中", icon='LINKED')


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
        layout.operator("bofu.cleanup_demo", text="清理演示对象", icon='SCULPTMODE_HLT')
        layout.separator()
        layout.operator("bofu.annotation_info", text="标注信息", icon='INFO')
        
        # 杂项设置
        layout.separator()
        layout.menu("VIEW3D_MT_misc_tools", text="杂项设置", icon='THREE_DOTS')


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


class BOFU_OT_popup_annotation_menu(Operator):
    """弹出标注管理菜单"""
    bl_idname = "bofu.popup_annotation_menu"
    bl_label = "标注管理"
    bl_options = {'REGISTER'}

    def execute(self, context):
        bpy.ops.wm.call_menu(name="VIEW3D_MT_annotation_manage")
        return {'FINISHED'}


class BOFU_OT_popup_align_menu(Operator):
    """弹出对齐工具菜单"""
    bl_idname = "bofu.popup_align_menu"
    bl_label = "对齐工具"
    bl_options = {'REGISTER'}

    def execute(self, context):
        bpy.ops.wm.call_menu(name="VIEW3D_MT_align_tools")
        return {'FINISHED'}


class BOFU_OT_popup_misc_menu(Operator):
    """弹出杂项工具菜单"""
    bl_idname = "bofu.popup_misc_menu"
    bl_label = "杂项"
    bl_options = {'REGISTER'}

    def execute(self, context):
        bpy.ops.wm.call_menu(name="VIEW3D_MT_misc_tools")
        return {'FINISHED'}


class BOFU_OT_popup_material_menu(Operator):
    """弹出材质工具菜单"""
    bl_idname = "bofu.popup_material_menu"
    bl_label = "材质工具"
    bl_options = {'REGISTER'}

    def execute(self, context):
        bpy.ops.wm.call_menu(name="VIEW3D_MT_material_tools")
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
        
        # 编辑模式：显示顶点坐标
        if context.mode == 'EDIT_MESH' and obj.type == 'MESH':
            self.draw_edit_mode(context, layout, obj)
            return
        
        # 对象模式：显示对象变换
        self.draw_object_mode(context, layout, obj)
    
    def draw_edit_mode(self, context, layout, obj):
        """编辑模式下绘制顶点坐标"""
        col = layout.column(align=True)
        col.scale_x = 1.2
        
        bm = bmesh.from_edit_mesh(obj.data)
        mw = obj.matrix_world
        
        selected_verts = [v for v in bm.verts if v.select]
        
        if not selected_verts:
            col.label(text="未选中顶点", icon='INFO')
            return
        
        # 复制位置按钮
        row = col.row(align=True)
        row.operator("transform.copy_location", text="复制顶点位置", icon='ORIENTATION_GLOBAL', emboss=True)
        col.separator()
        
        if len(selected_verts) == 1:
            # 单个顶点：显示世界坐标（可编辑）
            vert = selected_verts[0]
            world_co = mw @ vert.co
            
            col.label(text=f"顶点 {vert.index} (世界坐标):", icon='VERTEXSEL')
            sub = col.column(align=True)
            for i, axis in enumerate(['X', 'Y', 'Z']):
                value = world_co[i]
                sub.label(text=f"{axis}  {format_value(value)} m")
            
            col.separator()
            col.label(text="局部坐标:", icon='ORIENTATION_LOCAL')
            sub = col.column(align=True)
            for i, axis in enumerate(['X', 'Y', 'Z']):
                value = vert.co[i]
                sub.label(text=f"{axis}  {format_value(value)} m")
        else:
            # 多个顶点：显示中心点和边界
            col.label(text=f"选中 {len(selected_verts)} 个顶点", icon='VERTEXSEL')
            col.separator()
            
            # 计算中心点
            center = Vector((0, 0, 0))
            for v in selected_verts:
                center += mw @ v.co
            center /= len(selected_verts)
            
            col.label(text="中心点 (世界坐标):", icon='PIVOT_MEDIAN')
            sub = col.column(align=True)
            for i, axis in enumerate(['X', 'Y', 'Z']):
                sub.label(text=f"{axis}  {format_value(center[i])} m")
            
            # 计算边界范围
            col.separator()
            min_co = Vector((float('inf'), float('inf'), float('inf')))
            max_co = Vector((float('-inf'), float('-inf'), float('-inf')))
            for v in selected_verts:
                world_co = mw @ v.co
                for i in range(3):
                    min_co[i] = min(min_co[i], world_co[i])
                    max_co[i] = max(max_co[i], world_co[i])
            
            size = max_co - min_co
            col.label(text="选区尺寸:", icon='ARROW_LEFTRIGHT')
            sub = col.column(align=True)
            for i, axis in enumerate(['X', 'Y', 'Z']):
                sub.label(text=f"{axis}  {format_value(size[i])} m")
    
    def draw_object_mode(self, context, layout, obj):
        """对象模式下绘制对象变换"""
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
    VIEW3D_MT_material_tools,
    VIEW3D_MT_misc_tools,
    VIEW3D_MT_annotation_manage,
    VIEW3D_MT_align_tools,
    BOFU_OT_call_pie_menu,
    BOFU_OT_popup_annotation_menu,
    BOFU_OT_popup_align_menu,
    BOFU_OT_popup_misc_menu,
    BOFU_OT_popup_material_menu,
    TRANSFORM_PT_precise_panel,
)
