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

def _get_vert_world_coords(obj, vert_indices):
    """
    内部辅助：获取一个或多个顶点的世界坐标（自动处理编辑/物体模式）
    
    参数:
        obj: Blender 网格对象
        vert_indices: 顶点索引列表
    
    返回: 世界坐标列表（与 vert_indices 等长），失败的元素为 None
    """
    results = [None] * len(vert_indices)
    mat = obj.matrix_world
    
    if obj.mode == 'EDIT':
        try:
            bm = bmesh.from_edit_mesh(obj.data)
            if not bm.is_valid:
                return results
            bm.verts.ensure_lookup_table()
            n = len(bm.verts)
            for i, idx in enumerate(vert_indices):
                if idx < n:
                    results[i] = mat @ bm.verts[idx].co.copy()
        except (ReferenceError, IndexError):
            return results
    else:
        mesh = obj.data
        n = len(mesh.vertices)
        for i, idx in enumerate(vert_indices):
            if idx < n:
                results[i] = mat @ mesh.vertices[idx].co
    
    return results


def get_vertex_world_coord_realtime(obj_name, vert_idx):
    """
    获取顶点的世界坐标（实时，支持编辑模式）
    
    在编辑模式下使用 BMesh 获取最新数据，确保标注实时刷新
    """
    obj = bpy.data.objects.get(obj_name)
    if not obj or obj.type != 'MESH':
        return None
    return _get_vert_world_coords(obj, [vert_idx])[0]


def get_edge_world_coords_realtime(obj_name, v1_idx, v2_idx):
    """
    获取边的两个端点世界坐标（实时，支持编辑模式）
    
    返回: (v1_world, v2_world) 或 (None, None)
    """
    obj = bpy.data.objects.get(obj_name)
    if not obj or obj.type != 'MESH':
        return None, None
    coords = _get_vert_world_coords(obj, [v1_idx, v2_idx])
    return coords[0], coords[1]


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
        
        利用 Blender 已缓存的 bound_box（8 个角点）避免遍历全部顶点。
        返回: (min_point, max_point) 两个 Vector
        """
        if obj.type != 'MESH' or not obj.data.vertices:
            origin = obj.matrix_world.translation
            return origin.copy(), origin.copy()
        
        mw = obj.matrix_world
        world_corners = [mw @ Vector(corner) for corner in obj.bound_box]
        
        min_co = Vector((
            min(c.x for c in world_corners),
            min(c.y for c in world_corners),
            min(c.z for c in world_corners),
        ))
        max_co = Vector((
            max(c.x for c in world_corners),
            max(c.y for c in world_corners),
            max(c.z for c in world_corners),
        ))
        return min_co, max_co
    
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


# ==================== 弧长/扇形计算公共函数 ====================

def calc_arc_data(center, p_start, p_end, epsilon=1e-8):
    """
    计算弧长相关数据（供 operators_measure 和 annotation 共用）
    
    参数:
        center: 圆心世界坐标
        p_start: 弧起点世界坐标
        p_end: 弧终点世界坐标
        epsilon: 向量长度阈值
    
    返回: dict 包含弧长测量结果，或 None
    """
    vec_a = p_start - center
    vec_b = p_end - center
    radius_a = vec_a.length
    radius_b = vec_b.length
    avg_radius = (radius_a + radius_b) / 2
    radius_diff = abs(radius_a - radius_b)
    
    if vec_a.length < epsilon or vec_b.length < epsilon:
        return None
    
    dot = vec_a.normalized().dot(vec_b.normalized())
    dot = max(-1.0, min(1.0, dot))
    angle_rad = math.acos(dot)
    angle_deg = math.degrees(angle_rad)
    
    arc_length = avg_radius * angle_rad
    chord_length = (p_end - p_start).length
    sector_area = 0.5 * avg_radius ** 2 * angle_rad
    
    return {
        'radius_a': radius_a,
        'radius_b': radius_b,
        'avg_radius': avg_radius,
        'radius_diff': radius_diff,
        'angle_rad': angle_rad,
        'angle_deg': angle_deg,
        'arc_length': arc_length,
        'chord_length': chord_length,
        'sector_area': sector_area,
    }
