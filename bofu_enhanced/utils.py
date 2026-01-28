# ==================== 共享工具函数模块 ====================
"""
bofu_enhanced/utils.py

提供全插件共用的工具函数，包括：
- 镜像工具函数
- 对齐辅助类
- 格式化函数
- 实时数据获取函数
"""

import bpy
import bmesh
import math
from mathutils import Vector, Matrix

from .config import Config


# ==================== 格式化函数 ====================

def format_value(value, is_angle=False):
    """格式化数值，移除末尾的零"""
    if is_angle:
        value = math.degrees(value)
        formatted = f"{value:.6f}".rstrip('0').rstrip('.')
        return f"{formatted}°"
    else:
        formatted = f"{value:.6f}".rstrip('0').rstrip('.')
        return formatted


# ==================== 镜像工具函数 ====================

def axis_to_vec(axis: str) -> Vector:
    """将轴向字符串转换为向量"""
    axis = axis.upper()
    if axis == "X":
        return Vector((1, 0, 0))
    if axis == "Y":
        return Vector((0, 1, 0))
    if axis == "Z":
        return Vector((0, 0, 1))
    return Vector((0, 1, 0))


def reflect_point_across_plane(p: Vector, plane_point: Vector, plane_normal_unit: Vector) -> Vector:
    """将点关于平面反射"""
    d = (p - plane_point).dot(plane_normal_unit)
    return p - 2.0 * plane_normal_unit * d


def move_origin_keep_world_mesh(obj, new_origin_world: Vector):
    """移动原点但保持网格世界位置不变"""
    mw = obj.matrix_world.copy()
    delta_world = new_origin_world - mw.translation.copy()
    if delta_world.length < Config.EPSILON:
        return
    inv3 = mw.inverted_safe().to_3x3()
    delta_local = inv3 @ delta_world
    obj.data.transform(Matrix.Translation(-delta_local))
    obj.matrix_world = Matrix.Translation(delta_world) @ mw


def bake_modifiers_to_mesh(obj):
    """将所有修改器烘焙到网格"""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    try:
        new_mesh = bpy.data.meshes.new_from_object(
            eval_obj, preserve_all_data_layers=True, depsgraph=depsgraph
        )
    except TypeError:
        new_mesh = bpy.data.meshes.new_from_object(eval_obj)
    obj.data = new_mesh
    for m in list(obj.modifiers):
        obj.modifiers.remove(m)


def delete_side_by_plane_world(obj, plane_point: Vector, plane_normal_unit: Vector, side_sign_to_delete: float, eps: float):
    """删除平面一侧的顶点"""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    mw = obj.matrix_world
    verts_to_delete = []
    for v in bm.verts:
        pw = mw @ v.co
        d = (pw - plane_point).dot(plane_normal_unit)
        if side_sign_to_delete > 0 and d > eps:
            verts_to_delete.append(v)
        elif side_sign_to_delete < 0 and d < -eps:
            verts_to_delete.append(v)
    if verts_to_delete:
        bmesh.ops.delete(bm, geom=verts_to_delete, context='VERTS')
    bm.to_mesh(me)
    bm.free()
    me.update()


# ==================== 实时数据获取函数（编辑模式支持）====================

def get_vertex_world_coord_realtime(obj_name, vert_idx):
    """
    获取顶点的世界坐标（实时，支持编辑模式）
    
    在编辑模式下使用 BMesh 获取最新数据，确保标注实时刷新
    """
    obj = bpy.data.objects.get(obj_name)
    if not obj or obj.type != 'MESH':
        return None
    
    if obj.mode == 'EDIT':
        try:
            bm = bmesh.from_edit_mesh(obj.data)
            if not bm.is_valid:
                return None
            if vert_idx < len(bm.verts):
                bm.verts.ensure_lookup_table()
                return obj.matrix_world @ bm.verts[vert_idx].co.copy()
        except (ReferenceError, IndexError):
            return None
    else:
        mesh = obj.data
        if vert_idx < len(mesh.vertices):
            return obj.matrix_world @ mesh.vertices[vert_idx].co
    
    return None


def get_edge_world_coords_realtime(obj_name, v1_idx, v2_idx):
    """
    获取边的两个端点世界坐标（实时，支持编辑模式）
    
    返回: (v1_world, v2_world) 或 (None, None)
    """
    obj = bpy.data.objects.get(obj_name)
    if not obj or obj.type != 'MESH':
        return None, None
    
    if obj.mode == 'EDIT':
        try:
            bm = bmesh.from_edit_mesh(obj.data)
            if not bm.is_valid:
                return None, None
            if v1_idx < len(bm.verts) and v2_idx < len(bm.verts):
                bm.verts.ensure_lookup_table()
                v1 = obj.matrix_world @ bm.verts[v1_idx].co.copy()
                v2 = obj.matrix_world @ bm.verts[v2_idx].co.copy()
                return v1, v2
        except (ReferenceError, IndexError):
            return None, None
    else:
        mesh = obj.data
        if v1_idx < len(mesh.vertices) and v2_idx < len(mesh.vertices):
            v1 = obj.matrix_world @ mesh.vertices[v1_idx].co
            v2 = obj.matrix_world @ mesh.vertices[v2_idx].co
            return v1, v2
    
    return None, None


# ==================== 对齐辅助类 ====================

class AlignmentHelper:
    """
    对齐辅助工具类
    
    提供获取对象边界框各点坐标的功能
    """
    
    # 基准点类型
    REFERENCE_POINTS = [
        ('ORIGIN', "原点", "使用对象原点作为对齐基准"),
        ('BBOX_MIN', "边界框最小点", "使用边界框的最小坐标点（左下后）"),
        ('BBOX_MAX', "边界框最大点", "使用边界框的最大坐标点（右上前）"),
        ('BBOX_CENTER', "边界框中心", "使用边界框的几何中心"),
        ('BBOX_BOTTOM', "底部中心", "使用边界框底面的中心点"),
        ('BBOX_TOP', "顶部中心", "使用边界框顶面的中心点"),
    ]
    
    # 对齐轴向
    ALIGN_AXES = [
        ('X', "X轴 (左右)", "沿X轴对齐"),
        ('Y', "Y轴 (前后)", "沿Y轴对齐"),
        ('Z', "Z轴 (上下)", "沿Z轴对齐"),
    ]
    
    @staticmethod
    def get_world_bbox(obj):
        """
        获取对象在世界坐标系中的边界框
        
        返回: (min_point, max_point) 两个 Vector
        """
        if obj.type != 'MESH' or not obj.data.vertices:
            origin = obj.matrix_world.translation
            return origin.copy(), origin.copy()
        
        world_verts = [obj.matrix_world @ v.co for v in obj.data.vertices]
        
        min_x = min(v.x for v in world_verts)
        min_y = min(v.y for v in world_verts)
        min_z = min(v.z for v in world_verts)
        max_x = max(v.x for v in world_verts)
        max_y = max(v.y for v in world_verts)
        max_z = max(v.z for v in world_verts)
        
        return Vector((min_x, min_y, min_z)), Vector((max_x, max_y, max_z))
    
    @staticmethod
    def get_reference_point(obj, ref_type, axis='Z'):
        """
        获取对象的参考点坐标
        
        参数:
            obj: Blender 对象
            ref_type: 参考点类型
            axis: 对齐轴向，用于确定"底部"和"顶部"的方向
        
        返回: Vector 世界坐标
        """
        if ref_type == 'ORIGIN':
            return obj.matrix_world.translation.copy()
        
        bbox_min, bbox_max = AlignmentHelper.get_world_bbox(obj)
        bbox_center = (bbox_min + bbox_max) / 2
        
        if ref_type == 'BBOX_MIN':
            return bbox_min
        elif ref_type == 'BBOX_MAX':
            return bbox_max
        elif ref_type == 'BBOX_CENTER':
            return bbox_center
        elif ref_type == 'BBOX_BOTTOM':
            result = bbox_center.copy()
            axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)
            result[axis_idx] = bbox_min[axis_idx]
            return result
        elif ref_type == 'BBOX_TOP':
            result = bbox_center.copy()
            axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)
            result[axis_idx] = bbox_max[axis_idx]
            return result
        
        return obj.matrix_world.translation.copy()
    
    @staticmethod
    def align_object(obj, target_coord, ref_type, axis):
        """
        将对象对齐到目标坐标
        
        参数:
            obj: 要移动的对象
            target_coord: 目标坐标值（单轴）
            ref_type: 参考点类型
            axis: 对齐轴向 ('X', 'Y', 'Z')
        """
        axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)
        current_ref = AlignmentHelper.get_reference_point(obj, ref_type, axis)
        delta = target_coord - current_ref[axis_idx]
        obj.location[axis_idx] += delta


def get_unique_measure_name(base_name):
    """
    生成唯一的测量对象名称
    
    参数:
        base_name: 基础名称
    
    返回:
        唯一名称，格式为 base_name_001, base_name_002, ...
    """
    index = 1
    while f"{base_name}_{index:03d}" in bpy.data.objects:
        index += 1
    return f"{base_name}_{index:03d}"
