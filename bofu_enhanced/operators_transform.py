# ==================== 变换复制操作符模块 ====================
"""
bofu_enhanced/operators_transform.py

变换复制相关操作符
"""

import bpy
from bpy.types import Operator

from .utils import format_value


class TRANSFORM_OT_copy_location(Operator):
    """复制位置坐标到剪贴板（支持多选）"""
    bl_idname = "transform.copy_location"
    bl_label = "复制位置"
    bl_options = {'REGISTER'}

    def execute(self, context):
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
