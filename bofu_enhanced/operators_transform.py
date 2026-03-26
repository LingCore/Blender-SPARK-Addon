# ==================== 变换复制操作符模块 ====================
"""
bofu_enhanced/operators_transform.py

变换复制相关操作符
"""

import bpy
import bmesh
from bpy.types import Operator

from .utils import format_value


# ==================== 通用复制辅助函数 ====================

def _copy_to_clipboard(operator, context, prop_label, format_fn, mesh_only=False):
    """通用变换属性复制到剪贴板的辅助函数
    
    Args:
        operator: 调用者操作符（用于 report）
        context: Blender 上下文
        prop_label: 属性名称（如 "位置"、"缩放"）
        format_fn: 格式化函数 (obj) -> list[str]
        mesh_only: 是否仅限网格对象
    """
    if mesh_only:
        selected = [obj for obj in context.selected_objects if obj.type == 'MESH']
    else:
        selected = list(context.selected_objects)
    
    if not selected:
        obj_type = "网格对象" if mesh_only else "对象"
        operator.report({'WARNING'}, f"未选中任何{obj_type}")
        return {'CANCELLED'}
    
    lines = []
    for obj in selected:
        lines.extend(format_fn(obj))
    
    context.window_manager.clipboard = "\n".join(lines)
    operator.report({'INFO'}, f"已复制 {len(selected)} 个对象的{prop_label}")
    return {'FINISHED'}


# ==================== 操作符 ====================

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
        def fmt(obj):
            x = format_value(obj.location.x)
            y = format_value(obj.location.y)
            z = format_value(obj.location.z)
            return [f"{obj.name}({x}, {y}, {z})"]
        
        return _copy_to_clipboard(self, context, "位置", fmt)
    
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
            
            for face in selected_faces:
                center_world = mw @ face.calc_center_median()
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
                v1_world = mw @ edge.verts[0].co
                v2_world = mw @ edge.verts[1].co
                center_world = (v1_world + v2_world) / 2
                x = format_value(center_world.x)
                y = format_value(center_world.y)
                z = format_value(center_world.z)
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
        def fmt(obj):
            result = [f"{obj.name}"]
            if obj.rotation_mode == 'QUATERNION':
                q = obj.rotation_quaternion
                result.extend([
                    f"  W {format_value(q[0])}",
                    f"  X {format_value(q[1])}",
                    f"  Y {format_value(q[2])}",
                    f"  Z {format_value(q[3])}",
                ])
            elif obj.rotation_mode == 'AXIS_ANGLE':
                aa = obj.rotation_axis_angle
                result.extend([
                    f"  W {format_value(aa[0], True)}",
                    f"  X {format_value(aa[1])}",
                    f"  Y {format_value(aa[2])}",
                    f"  Z {format_value(aa[3])}",
                ])
            else:
                e = obj.rotation_euler
                result.extend([
                    f"  X {format_value(e.x, True)}",
                    f"  Y {format_value(e.y, True)}",
                    f"  Z {format_value(e.z, True)}",
                ])
            return result
        
        return _copy_to_clipboard(self, context, "旋转", fmt)


class TRANSFORM_OT_copy_scale(Operator):
    """复制缩放坐标到剪贴板（支持多选）"""
    bl_idname = "transform.copy_scale"
    bl_label = "复制缩放"
    bl_options = {'REGISTER'}

    def execute(self, context):
        def fmt(obj):
            return [
                f"{obj.name}",
                f"  X {format_value(obj.scale.x)}",
                f"  Y {format_value(obj.scale.y)}",
                f"  Z {format_value(obj.scale.z)}",
            ]
        
        return _copy_to_clipboard(self, context, "缩放", fmt)


class TRANSFORM_OT_copy_dimensions(Operator):
    """复制尺寸到剪贴板（支持多选）"""
    bl_idname = "transform.copy_dimensions"
    bl_label = "复制尺寸"
    bl_options = {'REGISTER'}

    def execute(self, context):
        def fmt(obj):
            return [
                f"{obj.name}",
                f"  X {format_value(obj.dimensions.x)} m",
                f"  Y {format_value(obj.dimensions.y)} m",
                f"  Z {format_value(obj.dimensions.z)} m",
            ]
        
        return _copy_to_clipboard(self, context, "尺寸", fmt, mesh_only=True)


# ==================== 旋转快照辅助函数 ====================

# Custom Property 键名前缀
_SNAP_PREFIX = "_spark_saved_rotation"


def _save_rotation_to_obj(obj):
    """将对象当前旋转保存到 Custom Properties"""
    obj[f"{_SNAP_PREFIX}_mode"] = obj.rotation_mode

    if obj.rotation_mode == 'QUATERNION':
        q = obj.rotation_quaternion
        obj[f"{_SNAP_PREFIX}_quaternion"] = [q[0], q[1], q[2], q[3]]
    elif obj.rotation_mode == 'AXIS_ANGLE':
        aa = obj.rotation_axis_angle
        obj[f"{_SNAP_PREFIX}_axis_angle"] = [aa[0], aa[1], aa[2], aa[3]]
    else:
        # Euler（含 XYZ / XZY / YXZ 等各种顺序）
        e = obj.rotation_euler
        obj[f"{_SNAP_PREFIX}_euler"] = [e.x, e.y, e.z]
        obj[f"{_SNAP_PREFIX}_euler_order"] = obj.rotation_mode


def _has_saved_rotation(obj):
    """检查对象是否有旋转快照"""
    return f"{_SNAP_PREFIX}_mode" in obj


def _restore_rotation_to_obj(obj):
    """从 Custom Properties 还原旋转，返回 True/False"""
    key_mode = f"{_SNAP_PREFIX}_mode"
    if key_mode not in obj:
        return False

    saved_mode = obj[key_mode]

    if saved_mode == 'QUATERNION':
        key = f"{_SNAP_PREFIX}_quaternion"
        if key not in obj:
            return False
        vals = list(obj[key])
        obj.rotation_mode = 'QUATERNION'
        obj.rotation_quaternion = vals
    elif saved_mode == 'AXIS_ANGLE':
        key = f"{_SNAP_PREFIX}_axis_angle"
        if key not in obj:
            return False
        vals = list(obj[key])
        obj.rotation_mode = 'AXIS_ANGLE'
        obj.rotation_axis_angle = vals
    else:
        key = f"{_SNAP_PREFIX}_euler"
        if key not in obj:
            return False
        vals = list(obj[key])
        # 恢复 Euler 顺序（如 XYZ / XZY 等）
        key_order = f"{_SNAP_PREFIX}_euler_order"
        order = obj.get(key_order, saved_mode)
        obj.rotation_mode = order
        obj.rotation_euler = vals

    return True


def _clear_saved_rotation(obj):
    """清除对象上的旋转快照数据"""
    for suffix in ("_mode", "_quaternion", "_axis_angle", "_euler", "_euler_order"):
        key = f"{_SNAP_PREFIX}{suffix}"
        if key in obj:
            del obj[key]


# ==================== 旋转快照操作符 ====================

class TRANSFORM_OT_save_rotation(Operator):
    """保存选中对象的当前旋转到快照（可在 Alt+R 后还原）"""
    bl_idname = "transform.save_rotation"
    bl_label = "保存旋转"
    bl_description = "将选中对象的当前旋转角度保存为快照，以便在 Alt+R 清除后还原"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and len(context.selected_objects) > 0

    def execute(self, context):
        selected = list(context.selected_objects)
        for obj in selected:
            _save_rotation_to_obj(obj)

        self.report({'INFO'}, f"已保存 {len(selected)} 个对象的旋转快照")
        return {'FINISHED'}


class TRANSFORM_OT_restore_rotation(Operator):
    """还原选中对象的旋转到之前保存的快照"""
    bl_idname = "transform.restore_rotation"
    bl_label = "还原旋转"
    bl_description = "将选中对象的旋转还原到之前保存的快照角度"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and len(context.selected_objects) > 0

    def execute(self, context):
        selected = list(context.selected_objects)

        restored = 0
        skipped = 0
        for obj in selected:
            if _restore_rotation_to_obj(obj):
                restored += 1
            else:
                skipped += 1

        if restored == 0:
            self.report({'WARNING'}, "选中的对象没有旋转快照")
            return {'CANCELLED'}

        msg = f"已还原 {restored} 个对象的旋转"
        if skipped > 0:
            msg += f"（{skipped} 个无快照，已跳过）"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class TRANSFORM_OT_clear_rotation_enhanced(Operator):
    """清除旋转（增强版：自动保存旋转快照后再归零）"""
    bl_idname = "transform.clear_rotation_enhanced"
    bl_label = "清除旋转（增强）"
    bl_description = "自动保存旋转快照后清除旋转，可通过 Alt+Shift+R 还原"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and len(context.selected_objects) > 0

    def execute(self, context):
        selected = list(context.selected_objects)

        # 1. 先保存快照
        for obj in selected:
            _save_rotation_to_obj(obj)

        # 2. 使用 context.temp_override 调用原生清除旋转
        with context.temp_override(selected_objects=selected):
            bpy.ops.object.rotation_clear()

        self.report({'INFO'},
                    f"已保存并清除 {len(selected)} 个对象的旋转"
                    f"（Alt+Shift+R 可还原）")
        return {'FINISHED'}


class TRANSFORM_OT_clear_saved_rotation(Operator):
    """清除选中对象上的旋转快照数据"""
    bl_idname = "transform.clear_saved_rotation"
    bl_label = "清除旋转快照"
    bl_description = "清除选中对象上保存的旋转快照数据"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and len(context.selected_objects) > 0

    def execute(self, context):
        selected = list(context.selected_objects)

        count = 0
        for obj in selected:
            if _has_saved_rotation(obj):
                _clear_saved_rotation(obj)
                count += 1

        if count == 0:
            self.report({'INFO'}, "选中的对象没有旋转快照")
        else:
            self.report({'INFO'}, f"已清除 {count} 个对象的旋转快照")
        return {'FINISHED'}


# ==================== 类注册列表 ====================

classes = (
    TRANSFORM_OT_copy_location,
    TRANSFORM_OT_copy_rotation,
    TRANSFORM_OT_copy_scale,
    TRANSFORM_OT_copy_dimensions,
    TRANSFORM_OT_save_rotation,
    TRANSFORM_OT_restore_rotation,
    TRANSFORM_OT_clear_rotation_enhanced,
    TRANSFORM_OT_clear_saved_rotation,
)
