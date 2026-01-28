# ==================== 变换复制操作符模块 ====================
"""
bofu_enhanced/operators_transform.py

变换复制相关操作符
"""

import bpy
import bmesh
from bpy.types import Operator

from .utils import format_value


class TRANSFORM_OT_copy_location(Operator):
    """复制位置坐标到剪贴板（支持多选，编辑模式下复制选中元素位置）"""
    bl_idname = "transform.copy_location"
    bl_label = "复制位置"
    bl_options = {'REGISTER'}

    def execute(self, context):
        # 编辑模式：复制选中的点/线/面位置
        if context.mode == 'EDIT_MESH':
            return self.copy_edit_mode_location(context)
        
        # 对象模式：复制对象位置
        selected = [obj for obj in context.selected_objects]
        if not selected:
            self.report({'WARNING'}, "未选中任何对象")
            return {'CANCELLED'}
        
        lines = []
        for obj in selected:
            x = format_value(obj.location.x)
            y = format_value(obj.location.y)
            z = format_value(obj.location.z)
            lines.append(f"{obj.name}({x}, {y}, {z})")
        
        text = "\n".join(lines)
        context.window_manager.clipboard = text
        self.report({'INFO'}, f"已复制 {len(selected)} 个对象的位置")
        return {'FINISHED'}
    
    def copy_edit_mode_location(self, context):
        """编辑模式下复制选中元素的位置"""
        obj = context.edit_object
        if not obj or obj.type != 'MESH':
            self.report({'WARNING'}, "请在网格编辑模式下使用")
            return {'CANCELLED'}
        
        bm = bmesh.from_edit_mesh(obj.data)
        mw = obj.matrix_world
        
        # 获取选择模式
        select_mode = context.tool_settings.mesh_select_mode
        lines = []
        
        if select_mode[2]:  # 面模式
            selected_faces = [f for f in bm.faces if f.select]
            if not selected_faces:
                self.report({'WARNING'}, "未选中任何面")
                return {'CANCELLED'}
            
            for i, face in enumerate(selected_faces):
                # 计算面中心的世界坐标
                center_local = face.calc_center_median()
                center_world = mw @ center_local
                x = format_value(center_world.x)
                y = format_value(center_world.y)
                z = format_value(center_world.z)
                lines.append(f"面{face.index}({x}, {y}, {z})")
            
            element_name = "面"
            count = len(selected_faces)
            
        elif select_mode[1]:  # 边模式
            selected_edges = [e for e in bm.edges if e.select]
            if not selected_edges:
                self.report({'WARNING'}, "未选中任何边")
                return {'CANCELLED'}
            
            for edge in selected_edges:
                # 计算边中点的世界坐标
                v1_world = mw @ edge.verts[0].co
                v2_world = mw @ edge.verts[1].co
                center_world = (v1_world + v2_world) / 2
                x = format_value(center_world.x)
                y = format_value(center_world.y)
                z = format_value(center_world.z)
                # 同时显示边长
                length = (v2_world - v1_world).length
                lines.append(f"边{edge.index}({x}, {y}, {z}) 长度:{format_value(length)}")
            
            element_name = "边"
            count = len(selected_edges)
            
        else:  # 顶点模式
            selected_verts = [v for v in bm.verts if v.select]
            if not selected_verts:
                self.report({'WARNING'}, "未选中任何顶点")
                return {'CANCELLED'}
            
            for vert in selected_verts:
                # 计算顶点的世界坐标
                world_co = mw @ vert.co
                x = format_value(world_co.x)
                y = format_value(world_co.y)
                z = format_value(world_co.z)
                lines.append(f"顶点{vert.index}({x}, {y}, {z})")
            
            element_name = "顶点"
            count = len(selected_verts)
        
        text = "\n".join(lines)
        context.window_manager.clipboard = text
        self.report({'INFO'}, f"已复制 {count} 个{element_name}的位置")
        return {'FINISHED'}


class TRANSFORM_OT_copy_rotation(Operator):
    """复制旋转坐标到剪贴板（支持多选）"""
    bl_idname = "transform.copy_rotation"
    bl_label = "复制旋转"
    bl_options = {'REGISTER'}

    def execute(self, context):
        selected = [obj for obj in context.selected_objects]
        if not selected:
            self.report({'WARNING'}, "未选中任何对象")
            return {'CANCELLED'}
        
        lines = []
        for obj in selected:
            lines.append(f"{obj.name}")
            if obj.rotation_mode == 'QUATERNION':
                lines.append(f"  W {format_value(obj.rotation_quaternion[0])}")
                lines.append(f"  X {format_value(obj.rotation_quaternion[1])}")
                lines.append(f"  Y {format_value(obj.rotation_quaternion[2])}")
                lines.append(f"  Z {format_value(obj.rotation_quaternion[3])}")
            elif obj.rotation_mode == 'AXIS_ANGLE':
                lines.append(f"  W {format_value(obj.rotation_axis_angle[0], True)}")
                lines.append(f"  X {format_value(obj.rotation_axis_angle[1])}")
                lines.append(f"  Y {format_value(obj.rotation_axis_angle[2])}")
                lines.append(f"  Z {format_value(obj.rotation_axis_angle[3])}")
            else:
                lines.append(f"  X {format_value(obj.rotation_euler.x, True)}")
                lines.append(f"  Y {format_value(obj.rotation_euler.y, True)}")
                lines.append(f"  Z {format_value(obj.rotation_euler.z, True)}")
        
        text = "\n".join(lines)
        context.window_manager.clipboard = text
        self.report({'INFO'}, f"已复制 {len(selected)} 个对象的旋转")
        return {'FINISHED'}


class TRANSFORM_OT_copy_scale(Operator):
    """复制缩放坐标到剪贴板（支持多选）"""
    bl_idname = "transform.copy_scale"
    bl_label = "复制缩放"
    bl_options = {'REGISTER'}

    def execute(self, context):
        selected = [obj for obj in context.selected_objects]
        if not selected:
            self.report({'WARNING'}, "未选中任何对象")
            return {'CANCELLED'}
        
        lines = []
        for obj in selected:
            lines.append(f"{obj.name}")
            lines.append(f"  X {format_value(obj.scale.x)}")
            lines.append(f"  Y {format_value(obj.scale.y)}")
            lines.append(f"  Z {format_value(obj.scale.z)}")
        
        text = "\n".join(lines)
        context.window_manager.clipboard = text
        self.report({'INFO'}, f"已复制 {len(selected)} 个对象的缩放")
        return {'FINISHED'}


class TRANSFORM_OT_copy_dimensions(Operator):
    """复制尺寸到剪贴板（支持多选）"""
    bl_idname = "transform.copy_dimensions"
    bl_label = "复制尺寸"
    bl_options = {'REGISTER'}

    def execute(self, context):
        selected = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not selected:
            self.report({'WARNING'}, "未选中任何网格对象")
            return {'CANCELLED'}
        
        lines = []
        for obj in selected:
            lines.append(f"{obj.name}")
            lines.append(f"  X {format_value(obj.dimensions.x)} m")
            lines.append(f"  Y {format_value(obj.dimensions.y)} m")
            lines.append(f"  Z {format_value(obj.dimensions.z)} m")
        
        text = "\n".join(lines)
        context.window_manager.clipboard = text
        self.report({'INFO'}, f"已复制 {len(selected)} 个对象的尺寸")
        return {'FINISHED'}


# ==================== 类注册列表 ====================

classes = (
    TRANSFORM_OT_copy_location,
    TRANSFORM_OT_copy_rotation,
    TRANSFORM_OT_copy_scale,
    TRANSFORM_OT_copy_dimensions,
)
