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
    """增强工具饼图菜单"""
    bl_idname = "VIEW3D_MT_PIE_bofu_tools"
    bl_label = "增强工具"

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


def _draw_material_sync_ui(layout, context):
    """绘制材质同步开关 UI（共享辅助函数）"""
    if hasattr(context.scene, 'misc_settings'):
        settings = context.scene.misc_settings
        icon = 'CHECKBOX_HLT' if settings.material_sync_enabled else 'CHECKBOX_DEHLT'
        layout.prop(settings, "material_sync_enabled", icon=icon)
        if settings.material_sync_enabled:
            row = layout.row()
            row.alert = True
            row.label(text="颜色/金属度/糙度 自动同步中", icon='LINKED')


class VIEW3D_MT_material_tools(Menu):
    """材质工具子菜单"""
    bl_idname = "VIEW3D_MT_material_tools"
    bl_label = "材质工具"
    
    def draw(self, context):
        layout = self.layout
        # 从饼图菜单弹出的子菜单中，operator_context 可能不是 INVOKE_DEFAULT，
        # 导致 invoke() 被跳过、invoke_props_dialog 无法弹出，必须显式设置。
        layout.operator_context = 'INVOKE_DEFAULT'
        
        # 批量应用材质
        layout.operator("material.apply_to_selected", text="批量应用材质", icon='MATERIAL')
        
        layout.separator()
        
        # 材质槽整理
        layout.operator("material.cleanup_slots", text="整理材质槽", icon='BRUSH_DATA')
        
        # 清理未使用材质
        layout.operator("material.cleanup_unused", text="清理未使用材质", icon='TRASH')
        
        layout.separator()
        
        # 材质同步开关
        _draw_material_sync_ui(layout, context)


class VIEW3D_MT_misc_tools(Menu):
    """杂项工具子菜单"""
    bl_idname = "VIEW3D_MT_misc_tools"
    bl_label = "杂项"
    
    def draw(self, context):
        layout = self.layout
        layout.operator_context = 'INVOKE_DEFAULT'
        
        # 一键优化模型
        layout.operator("mesh.optimize_mesh_plus", text="一键优化模型", icon='MODIFIER')
        
        layout.separator()
        
        # 所见即所得视口渲染
        layout.operator(
            "bofu.viewport_render_wysiwyg",
            text="渲染视口预览（所见即所得）",
            icon='RESTRICT_RENDER_OFF',
        )
        
        from .operators_render import has_saved_settings
        if has_saved_settings():
            row = layout.row()
            row.alert = True
            row.operator("bofu.restore_color_settings", icon='LOOP_BACK')
        
        layout.separator()
        
        # 视口帧率开关
        if hasattr(context.scene, 'misc_settings'):
            settings = context.scene.misc_settings
            fps_icon = 'CHECKBOX_HLT' if settings.show_viewport_fps else 'CHECKBOX_DEHLT'
            layout.prop(settings, "show_viewport_fps", icon=fps_icon)
        
        # 材质同步开关
        _draw_material_sync_ui(layout, context)


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
        # 从饼图菜单弹出的子菜单中，operator_context 可能不是 INVOKE_DEFAULT，
        # 导致 invoke() 被跳过、invoke_props_dialog 无法弹出，必须显式设置。
        layout.operator_context = 'INVOKE_DEFAULT'
        
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
    """呼出增强工具饼图菜单"""
    bl_idname = "bofu.call_pie_menu"
    bl_label = "增强工具"
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


# ==================== 性能测试：第二行工具标题栏绘制 ====================

def draw_perftest_header(self, context):
    """在 3D 视口第二行（VIEW3D_HT_tool_header / TOOL_HEADER）绘制性能测试按钮，不占第一行主标题栏。"""
    has_settings = hasattr(context.scene, 'perftest_settings')
    if not has_settings:
        return

    settings = context.scene.perftest_settings
    is_running = settings.is_running
    has_cubes = settings.cube_count > 0

    layout = self.layout
    row = layout.row(align=True)

    # 创建模型
    sub = row.row(align=True)
    sub.enabled = not is_running
    sub.operator("bofu.perftest_create", text="创建测试", icon='MESH_CUBE')

    # 开始测试
    sub = row.row(align=True)
    sub.enabled = not is_running and has_cubes
    sub.operator("bofu.perftest_start", text="开始", icon='PLAY')

    # 停止测试
    sub = row.row(align=True)
    sub.enabled = is_running
    sub.operator("bofu.perftest_stop", text="停止", icon='PAUSE')

    # 运行状态指示
    if is_running:
        row.label(text="", icon='TIME')


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
            
            # ★ 性能优化 5：大量顶点时用 numpy 向量化计算
            n = len(selected_verts)
            if n > 50:
                try:
                    import numpy as np_ui
                    coords = np_ui.array([list(mw @ v.co) for v in selected_verts])
                    center_arr = coords.mean(axis=0)
                    min_arr = coords.min(axis=0)
                    max_arr = coords.max(axis=0)
                    center = Vector(center_arr)
                    size = Vector(max_arr - min_arr)
                except Exception:
                    # 回退到 Python 计算
                    center = Vector((0, 0, 0))
                    for v in selected_verts:
                        center += mw @ v.co
                    center /= n
                    min_co = Vector((float('inf'), float('inf'), float('inf')))
                    max_co = Vector((float('-inf'), float('-inf'), float('-inf')))
                    for v in selected_verts:
                        world_co = mw @ v.co
                        for i in range(3):
                            min_co[i] = min(min_co[i], world_co[i])
                            max_co[i] = max(max_co[i], world_co[i])
                    size = max_co - min_co
            else:
                # 小数量用原逻辑（避免 numpy 导入开销）
                center = Vector((0, 0, 0))
                for v in selected_verts:
                    center += mw @ v.co
                center /= n
                min_co = Vector((float('inf'), float('inf'), float('inf')))
                max_co = Vector((float('-inf'), float('-inf'), float('-inf')))
                for v in selected_verts:
                    world_co = mw @ v.co
                    for i in range(3):
                        min_co[i] = min(min_co[i], world_co[i])
                        max_co[i] = max(max_co[i], world_co[i])
                size = max_co - min_co
            
            col.label(text="中心点 (世界坐标):", icon='PIVOT_MEDIAN')
            sub = col.column(align=True)
            for i, axis in enumerate(['X', 'Y', 'Z']):
                sub.label(text=f"{axis}  {format_value(center[i])} m")
            
            # 显示选区尺寸
            col.separator()
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


# ==================== 运动学面板 ====================

class KINEMATICS_UL_joint_list(bpy.types.UIList):
    """关节列表 UIList"""
    bl_idname = "KINEMATICS_UL_joint_list"

    def draw_item(self, context, layout, data, item, icon, active_data, active_property, index):
        props = context.scene.kinematics_props
        is_driver = (index == props.driver_joint_index)

        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)

            # 关节类型图标
            if item.joint_type == 'REVOLUTE':
                type_icon = 'CURVE_BEZCIRCLE'
                type_label = "R"
            else:
                type_icon = 'EMPTY_SINGLE_ARROW'
                type_label = "P"

            # 驱动标记
            if is_driver:
                row.label(text="", icon='PLAY')
            else:
                row.label(text="", icon='DOT')

            # 类型标签
            row.label(text=f"[{type_label}]", icon=type_icon)

            # 对象名称
            a_label = "地面" if item.a_is_ground else (item.object_a.name if item.object_a else "?")
            b_label = item.object_b.name if item.object_b else "?"
            row.label(text=f"{a_label} ↔ {b_label}")

            # 附加信息
            if item.joint_type == 'REVOLUTE':
                p = item.pivot_world
                row.label(text=f"({p[0]:.2f},{p[1]:.2f},{p[2]:.2f})")
            else:
                row.label(text=f"↕{item.axis_direction}轴")


class KINEMATICS_PT_main_panel(bpy.types.Panel):
    """机构运动学面板"""
    bl_label = "机构运动学"
    bl_idname = "KINEMATICS_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "运动学"
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        props = context.scene.kinematics_props

        # ==================== 工作平面 ====================
        row = layout.row(align=True)
        row.label(text="工作平面:")
        row.prop(props, "working_plane", text="")
        row.enabled = not props.is_active

        layout.separator()

        # ==================== 快速上手提示 ====================
        if len(props.joints) == 0 and not props.is_active:
            box = layout.box()
            col = box.column(align=True)
            col.label(text="快速上手", icon='LIGHT')
            col.label(text="  1. 选中对象 → 点 + 添加关节")
            col.label(text="  2. 选中关节 → 设为驱动")
            col.label(text="  3. 点击「激活机构」→ 拖动滑块")
            col.separator()
            col.label(text="或者一键体验：")
            row = col.row()
            row.scale_y = 1.3
            row.operator("bofu.kinematics_demo",
                         text="创建演示: 肘节夹钳", icon='PLAY')
            layout.separator()

        # ==================== 关节列表 ====================
        row = layout.row()
        row.template_list(
            "KINEMATICS_UL_joint_list", "",
            props, "joints",
            props, "active_joint_index",
            rows=3,
            maxrows=6,
        )

        # 关节列表操作按钮
        col = row.column(align=True)
        col.operator("bofu.add_revolute_joint", icon='CURVE_BEZCIRCLE', text="")
        col.operator("bofu.add_prismatic_joint", icon='EMPTY_SINGLE_ARROW', text="")
        col.separator()
        col.operator("bofu.remove_joint", icon='REMOVE', text="")
        col.enabled = not props.is_active

        # ==================== 选中关节的详情 ====================
        if len(props.joints) > 0 and 0 <= props.active_joint_index < len(props.joints):
            joint = props.joints[props.active_joint_index]
            box = layout.box()
            box.enabled = not props.is_active

            # 关节类型和对象
            row = box.row()
            type_name = "旋转关节" if joint.joint_type == 'REVOLUTE' else "平移关节"
            row.label(text=f"{type_name} #{props.active_joint_index}", icon='CONSTRAINT')

            if joint.joint_type == 'REVOLUTE':
                row = box.row()
                row.prop(joint, "pivot_world", text="铰接点")
                box.operator("bofu.update_pivot_from_cursor",
                             text="铰接点 ← 3D游标", icon='PIVOT_CURSOR')
            else:
                box.prop(joint, "axis_direction", text="滑动方向")

            # 设为驱动按钮
            box.separator()
            is_driver = (props.active_joint_index == props.driver_joint_index)
            if is_driver:
                row = box.row()
                row.alert = True
                row.label(text="当前为驱动关节", icon='PLAY')
            else:
                box.operator("bofu.set_driver_joint", text="设为驱动", icon='PLAY')

        layout.separator()

        # ==================== 驱动设置 ====================
        box = layout.box()
        box.label(text="驱动设置", icon='DRIVER')

        if props.driver_joint_index >= 0 and props.driver_joint_index < len(props.joints):
            dj = props.joints[props.driver_joint_index]
            a_name = "地面" if dj.a_is_ground else (dj.object_a.name if dj.object_a else "?")
            b_name = dj.object_b.name if dj.object_b else "?"
            jtype = "旋转" if dj.joint_type == 'REVOLUTE' else "平移"
            box.label(text=f"  [{jtype}] {a_name} ↔ {b_name}", icon='PINNED')

            unit = "°" if dj.joint_type == 'REVOLUTE' else "m"

            row = box.row(align=True)
            row.enabled = not props.is_active
            row.prop(props, "driver_min", text=f"最小({unit})")
            row.prop(props, "driver_max", text=f"最大({unit})")
            row.operator("bofu.auto_compute_limits", text="", icon='FILE_REFRESH')
        else:
            box.label(text="  未设置驱动关节", icon='ERROR')

        layout.separator()

        # ==================== 自由度显示 ====================
        if len(props.joints) > 0:
            try:
                from .operators_kinematics import PlanarMechanismSolver, check_numpy
                if check_numpy():
                    solver = PlanarMechanismSolver(props.working_plane)
                    solver.build_from_scene(context)
                    dof = solver.compute_dof()

                    row = layout.row()
                    if dof == 1:
                        row.label(text=f"自由度: {dof}  (正常)", icon='CHECKMARK')
                    elif dof == 0:
                        row.alert = True
                        row.label(text=f"自由度: {dof}  (过约束)", icon='ERROR')
                    else:
                        row.alert = True
                        row.label(text=f"自由度: {dof}  (欠约束)", icon='ERROR')

                    row = layout.row()
                    row.label(text=f"  活动对象: {len(solver.moving_objects)}")
                else:
                    layout.label(text="需要 numpy 计算自由度", icon='INFO')
            except Exception:
                pass

        layout.separator()

        # ==================== 控制按钮 ====================
        if props.is_active:
            # 激活状态：显示滑块和停用按钮
            box = layout.box()
            box.label(text="驱动控制", icon='ANIM')

            # 驱动滑块
            box.prop(props, "driver_progress", text="驱动进度", slider=True)

            # 显示实际值
            if props.driver_joint_index >= 0 and props.driver_joint_index < len(props.joints):
                dj = props.joints[props.driver_joint_index]
                progress = props.driver_progress
                if progress <= 0.5:
                    actual_val = props.driver_min * (1.0 - progress * 2.0)
                else:
                    actual_val = props.driver_max * (progress * 2.0 - 1.0)
                if dj.joint_type == 'REVOLUTE':
                    box.label(text=f"  当前: {actual_val:.2f}°")
                else:
                    box.label(text=f"  当前: {actual_val:.6f} m")

            row = box.row(align=True)
            row.operator("bofu.reset_to_start", text="回到初始位置", icon='REW')

            layout.separator()
            row = layout.row()
            row.alert = True
            row.operator("bofu.deactivate_mechanism", text="停用机构（恢复位置）", icon='CANCEL')
        else:
            # 未激活：显示激活按钮
            can_activate = (len(props.joints) > 0 and props.driver_joint_index >= 0)
            row = layout.row()
            row.enabled = can_activate
            row.scale_y = 1.5
            row.operator("bofu.activate_mechanism", text="激活机构", icon='PLAY')

            if not can_activate and len(props.joints) > 0:
                layout.label(text="请先设置驱动关节", icon='INFO')

        # ==================== 工具 ====================
        layout.separator()
        row = layout.row(align=True)
        row.enabled = not props.is_active
        row.operator("bofu.clear_all_joints", text="清除关节", icon='TRASH')
        row.operator("bofu.kinematics_demo", text="演示场景", icon='PLAY')


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
    KINEMATICS_UL_joint_list,
    KINEMATICS_PT_main_panel,
)
