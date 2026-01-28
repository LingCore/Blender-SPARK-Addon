bl_info = {
    "name": "Blender_增强_by.bofu",
    "author": "杨博夫",
    "version": (1, 5, 0),
    "blender": (3, 0, 0),
    "location": "View3D > ` 键或鼠标侧键呼出饼图菜单, Ctrl+M, Ctrl+F",
    "description": "批量导出OBJ文件，高精度变换显示，批量材质管理，增强镜像功能，名称批量替换，饼图快捷菜单",
    "warning": "",
    "doc_url": "",
    "category": "Import-Export",
}

import bpy
import bmesh
import os
import math
import re
import time
import gpu
import blf
from gpu_extras.batch import batch_for_shader
from bpy.app.handlers import persistent
from bpy.props import StringProperty, EnumProperty, FloatProperty, BoolProperty
from bpy.types import Operator, Panel, PropertyGroup
from mathutils import Vector, Matrix
from bpy_extras.view3d_utils import location_3d_to_region_2d

try:
    from bl_ui.space_view3d import VIEW3D_PT_transform
except ImportError:
    VIEW3D_PT_transform = None

# 存储被修改的面板原始 category，用于恢复
_original_panel_categories = {}

# ==================== 统一标注系统（模块化重构版）====================
# 
# 设计原则：
# 1. 连线是独立的模型，不和原对象绑定
# 2. 数据标注绑定到连线对象，跟随连线移动
# 3. 删除连线对象时自动清理标注
# 4. 三点角度等特殊模式可以不创建几何体，只显示数据
# 5. 【重要】对相同元素的重复测量会自动覆盖旧标注，避免数据叠加
#

# 统一的绘制处理器
_unified_draw_handler = None

# 标注注册表：存储所有标注数据
# key: 对象名称 或 特殊标识符（如 "__3point_temp__"）
# value: 标注数据字典
_annotation_registry = {}

# 标注显示开关
_annotations_visible = True

addon_keymaps = []


# ==================== 标注唯一性键生成器（模块化）====================

class AnnotationKeyGenerator:
    """
    标注唯一性键生成器
    
    用于生成标注的唯一标识键，确保对相同元素的重复测量能够被正确识别和覆盖。
    支持多种测量类型：边长、角度、半径、距离等。
    """
    
    # 精度：用于坐标四舍五入，避免浮点误差
    PRECISION = 4
    
    @classmethod
    def round_coord(cls, value):
        """四舍五入坐标值"""
        return round(value, cls.PRECISION)
    
    @classmethod
    def vector_to_tuple(cls, vec):
        """将 Vector 转换为可哈希的元组"""
        return (cls.round_coord(vec.x), cls.round_coord(vec.y), cls.round_coord(vec.z))
    
    @classmethod
    def normalize_vertex_refs(cls, vert_refs):
        """
        标准化顶点引用列表
        格式: [(obj_name, vert_idx), ...]
        返回排序后的元组，用于比较
        """
        if not vert_refs:
            return None
        # 排序以确保顺序无关
        sorted_refs = sorted(vert_refs, key=lambda x: (x[0], x[1]))
        return tuple(sorted_refs)
    
    @classmethod
    def normalize_edge_refs(cls, edge_refs):
        """
        标准化边引用列表
        格式: [(obj_name, v1_idx, v2_idx), ...]
        返回排序后的元组，用于比较
        """
        if not edge_refs:
            return None
        # 对每条边的顶点索引排序，然后对边列表排序
        normalized = []
        for ref in edge_refs:
            obj_name, v1, v2 = ref
            # 确保顶点索引有序
            v_min, v_max = min(v1, v2), max(v1, v2)
            normalized.append((obj_name, v_min, v_max))
        normalized.sort()
        return tuple(normalized)
    
    @classmethod
    def normalize_edge_data(cls, edge_data):
        """
        标准化边数据列表（边长测量专用）
        格式: [(obj_name, edge_index, v1_idx, v2_idx), ...]
        返回排序后的元组，用于比较
        """
        if not edge_data:
            return None
        # 对每条边的顶点索引排序，然后对边列表排序
        normalized = []
        for data in edge_data:
            obj_name, edge_idx, v1, v2 = data
            v_min, v_max = min(v1, v2), max(v1, v2)
            normalized.append((obj_name, v_min, v_max))
        normalized.sort()
        return tuple(normalized)
    
    @classmethod
    def normalize_points(cls, points):
        """
        标准化点列表
        格式: [Vector, ...]
        返回排序后的坐标元组
        """
        if not points:
            return None
        coords = [cls.vector_to_tuple(p) for p in points]
        coords.sort()
        return tuple(coords)
    
    @classmethod
    def normalize_edges_with_coords(cls, edges):
        """
        标准化带坐标的边列表
        格式: [(midpoint, length, p1, p2), ...]
        返回排序后的中点坐标元组
        """
        if not edges:
            return None
        coords = []
        for e in edges:
            mid = e[0]  # 边的中点
            coords.append(cls.vector_to_tuple(mid))
        coords.sort()
        return tuple(coords)
    
    @classmethod
    def generate_key(cls, annotation_type, data):
        """
        根据标注类型和数据生成唯一键
        
        返回: (annotation_type, unique_key) 元组，用于标识相同的测量
        """
        key = None
        
        # 边长测量（edge_length）
        if annotation_type == 'edge_length':
            if 'edge_data' in data:
                # 基于顶点索引的边长测量
                key = cls.normalize_edge_data(data['edge_data'])
            elif 'edges' in data:
                # 基于坐标的边长测量（已有边）
                key = cls.normalize_edges_with_coords(data['edges'])
        
        # 两边夹角（edge_angle）
        elif annotation_type == 'edge_angle':
            if 'edge_refs' in data:
                key = cls.normalize_edge_refs(data['edge_refs'])
        
        # 线段与轴夹角（line_angles）
        elif annotation_type == 'line_angles':
            if 'vert_refs' in data:
                key = cls.normalize_vertex_refs(data['vert_refs'])
        
        # 顶点角度（vertex_angles）
        elif annotation_type == 'vertex_angles':
            if 'vert_refs' in data:
                key = cls.normalize_vertex_refs(data['vert_refs'])
        
        # 两面夹角（angle / angle_temp）
        elif annotation_type in ('angle', 'angle_temp'):
            if 'center' in data:
                key = cls.vector_to_tuple(data['center'])
            elif 'edge_indices' in data and 'angle' in data:
                # 绑定对象的角度标注，使用角度值作为辅助键
                key = ('angle', cls.round_coord(data['angle']))
        
        # 半径/直径测量（radius / radius_temp）
        elif annotation_type in ('radius', 'radius_temp'):
            if 'center' in data:
                center = data['center']
                radius = data.get('radius', 0)
                key = (cls.vector_to_tuple(center), cls.round_coord(radius))
            elif 'center_vert_idx' in data:
                # 绑定对象的半径标注
                is_circle = data.get('is_circle', False)
                key = ('radius_bound', is_circle)
        
        # 距离测量（distance / distance_temp）
        elif annotation_type in ('distance', 'distance_temp'):
            if 'points' in data:
                key = cls.normalize_points(data['points'])
            elif 'measure_mode' in data and 'edge_indices' in data:
                # 绑定对象的距离标注
                key = ('distance_bound', data['measure_mode'], tuple(data['edge_indices']))
        
        # 如果无法生成键，返回 None
        if key is None:
            return None
        
        return (annotation_type, key)


# ==================== 标注管理器（模块化）====================

class AnnotationManager:
    """
    标注管理器
    
    提供标注的注册、注销、查询、去重等功能。
    确保对相同元素的重复测量不会产生叠加显示。
    """
    
    # ✅ 添加数量限制，防止内存泄漏
    MAX_ANNOTATIONS = 500  # 最大标注总数
    MAX_TEMP_ANNOTATIONS = 100  # 最大临时标注数
    
    @staticmethod
    def get_registry():
        """获取标注注册表"""
        global _annotation_registry
        return _annotation_registry
    
    @staticmethod
    def find_duplicate(annotation_type, data, exclude_name=None):
        """
        查找重复的标注
        
        参数:
            annotation_type: 标注类型
            data: 标注数据
            exclude_name: 排除的标注名称（用于更新时排除自身）
        
        返回:
            重复标注的名称列表
        """
        registry = AnnotationManager.get_registry()
        new_key = AnnotationKeyGenerator.generate_key(annotation_type, data)
        
        if new_key is None:
            return []
        
        duplicates = []
        for name, existing_data in registry.items():
            if exclude_name and name == exclude_name:
                continue
            
            existing_type = existing_data.get('type')
            # 检查类型是否兼容（同类型或相关类型）
            if not AnnotationManager._types_compatible(annotation_type, existing_type):
                continue
            
            existing_key = AnnotationKeyGenerator.generate_key(existing_type, existing_data)
            if existing_key == new_key:
                duplicates.append(name)
        
        return duplicates
    
    @staticmethod
    def _types_compatible(type1, type2):
        """检查两个标注类型是否兼容（可以互相覆盖）"""
        # 完全相同
        if type1 == type2:
            return True
        
        # 临时标注和绑定标注的对应关系
        compatible_pairs = [
            ('angle', 'angle_temp'),
            ('radius', 'radius_temp'),
            ('distance', 'distance_temp'),
        ]
        
        for pair in compatible_pairs:
            if (type1 in pair and type2 in pair):
                return True
        
        return False
    
    @staticmethod
    def remove_duplicates(annotation_type, data):
        """
        移除与新标注重复的旧标注
        
        返回:
            被移除的标注数量
        """
        global _annotation_registry
        duplicates = AnnotationManager.find_duplicate(annotation_type, data)
        
        for name in duplicates:
            del _annotation_registry[name]
            print(f"[标注系统] 已移除重复标注: {name}")
        
        return len(duplicates)
    
    @staticmethod
    def register(obj_name, annotation_type, data, auto_dedupe=True):
        """
        注册一个标注（带自动去重）
        
        参数:
            obj_name: 标注名称（临时标注以 __ 开头）
            annotation_type: 标注类型
            data: 标注数据
            auto_dedupe: 是否自动去重（默认 True）
        
        返回:
            实际使用的标注名称
        """
        global _annotation_registry
        
        # ✅ 检查数量限制，防止内存泄漏
        if obj_name.startswith("__"):
            # 临时标注数量检查
            temp_count = sum(1 for k in _annotation_registry if k.startswith("__"))
            if temp_count >= AnnotationManager.MAX_TEMP_ANNOTATIONS:
                print(f"⚠️ 临时标注数量已达上限 ({AnnotationManager.MAX_TEMP_ANNOTATIONS})，自动清理最旧的")
                # 清理最旧的临时标注（如果有时间戳）
                temp_annotations = [(k, v.get('created_time', 0)) for k, v in _annotation_registry.items() if k.startswith("__")]
                if temp_annotations:
                    oldest = min(temp_annotations, key=lambda x: x[1])[0]
                    del _annotation_registry[oldest]
        else:
            # 总标注数量检查
            if len(_annotation_registry) >= AnnotationManager.MAX_ANNOTATIONS:
                print(f"⚠️ 标注总数已达上限 ({AnnotationManager.MAX_ANNOTATIONS})，请清理部分标注")
                return None
        
        # 自动去重：移除相同元素的旧标注
        if auto_dedupe:
            removed_count = AnnotationManager.remove_duplicates(annotation_type, data)
            if removed_count > 0:
                print(f"[标注系统] 自动移除了 {removed_count} 个重复标注")
        
        # 如果是临时标注，生成唯一名称
        if obj_name.startswith("__"):
            base_name = obj_name.rstrip('_')
            index = 1
            unique_name = f"{base_name}_{index}__"
            while unique_name in _annotation_registry:
                index += 1
                unique_name = f"{base_name}_{index}__"
            obj_name = unique_name
        
        # ✅ 添加创建时间戳，用于过期清理
        data['created_time'] = time.time()
        
        # 注册标注
        _annotation_registry[obj_name] = {
            'type': annotation_type,
            'visible': True,
            **data
        }
        
        return obj_name
    
    @staticmethod
    def unregister(obj_name):
        """注销一个标注"""
        global _annotation_registry
        if obj_name in _annotation_registry:
            del _annotation_registry[obj_name]
            return True
        return False
    
    @staticmethod
    def clear_all():
        """清除所有标注"""
        global _annotation_registry
        count = len(_annotation_registry)
        _annotation_registry = {}
        return count
    
    @staticmethod
    def clear_temp():
        """清除所有临时标注（以 __ 开头的标注）"""
        global _annotation_registry
        to_remove = [name for name in _annotation_registry if name.startswith("__")]
        for name in to_remove:
            del _annotation_registry[name]
        return len(to_remove)
    
    @staticmethod
    def get_temp_count():
        """获取临时标注数量"""
        return sum(1 for name in _annotation_registry if name.startswith("__"))
    
    @staticmethod
    def get_bound_count():
        """获取绑定对象的标注数量"""
        return sum(1 for name in _annotation_registry if not name.startswith("__"))
    
    @staticmethod
    def cleanup_deleted_objects():
        """清理已删除对象的标注"""
        global _annotation_registry
        to_remove = []
        for obj_name in _annotation_registry:
            # 跳过特殊标注（以 __ 开头）
            if obj_name.startswith("__"):
                continue
            # 检查对象是否还存在
            if obj_name not in bpy.data.objects:
                to_remove.append(obj_name)
        
        for obj_name in to_remove:
            del _annotation_registry[obj_name]
            print(f"[标注系统] 已清理已删除对象的标注: {obj_name}")
        
        return len(to_remove)


# ==================== 兼容性包装函数 ====================
# 保持与原有代码的兼容性

def get_unique_measure_name(base_name):
    """生成唯一的测量对象名称"""
    index = 1
    while f"{base_name}_{index:03d}" in bpy.data.objects:
        index += 1
    return f"{base_name}_{index:03d}"


def get_annotation_position_key(data):
    """
    获取标注的位置键，用于判断是否是相同位置
    【已废弃】请使用 AnnotationKeyGenerator.generate_key()
    """
    # 保留原有逻辑以兼容旧代码
    if 'center' in data:
        c = data['center']
        return (round(c.x, 3), round(c.y, 3), round(c.z, 3))
    elif 'points' in data and len(data['points']) > 0:
        points = data['points']
        coords = []
        for p in points:
            coords.append((round(p.x, 3), round(p.y, 3), round(p.z, 3)))
        coords.sort()
        return tuple(coords)
    elif 'edges' in data and len(data['edges']) > 0:
        edges = data['edges']
        coords = []
        for e in edges:
            mid = e[0]
            coords.append((round(mid.x, 3), round(mid.y, 3), round(mid.z, 3)))
        coords.sort()
        return tuple(coords)
    return None


def register_annotation(obj_name, annotation_type, data):
    """
    注册一个标注（兼容性包装函数）
    
    根据用户设置决定是否自动去重：
    - 开启自动覆盖：对相同元素的重复测量会覆盖旧标注
    - 关闭自动覆盖：保留所有标注，允许叠加显示
    """
    # 获取用户设置
    auto_dedupe = True  # 默认值
    try:
        if hasattr(bpy.context, 'scene') and bpy.context.scene and hasattr(bpy.context.scene, 'annotation_settings'):
            auto_dedupe = bpy.context.scene.annotation_settings.auto_overwrite
    except Exception:
        pass  # 如果获取失败，使用默认值
    
    return AnnotationManager.register(obj_name, annotation_type, data, auto_dedupe=auto_dedupe)


def unregister_annotation(obj_name):
    """注销一个标注"""
    return AnnotationManager.unregister(obj_name)


def clear_all_annotations():
    """清除所有标注"""
    return AnnotationManager.clear_all()


def clear_temp_annotations():
    """清除所有临时标注（以 __ 开头的标注）"""
    return AnnotationManager.clear_temp()


def get_temp_annotation_count():
    """获取临时标注数量"""
    return AnnotationManager.get_temp_count()


def get_bound_annotation_count():
    """获取绑定对象的标注数量"""
    return AnnotationManager.get_bound_count()


def toggle_annotations_visibility():
    """切换标注显示/隐藏"""
    global _annotations_visible
    _annotations_visible = not _annotations_visible
    return _annotations_visible


def cleanup_deleted_objects():
    """清理已删除对象的标注"""
    return AnnotationManager.cleanup_deleted_objects()


# ==================== 实时数据获取辅助函数（编辑模式支持）====================

def get_vertex_world_coord_realtime(obj_name, vert_idx):
    """
    获取顶点的世界坐标（实时，支持编辑模式）
    
    在编辑模式下使用 BMesh 获取最新数据，确保标注实时刷新
    """
    obj = bpy.data.objects.get(obj_name)
    if not obj or obj.type != 'MESH':
        return None
    
    if obj.mode == 'EDIT':
        # 编辑模式：使用 BMesh 获取实时数据
        try:
            bm = bmesh.from_edit_mesh(obj.data)
            if not bm.is_valid:
                return None
            # 注意：from_edit_mesh 返回的是引用，不需要 free()
            # 但要确保索引有效，并在使用前检查
            if vert_idx < len(bm.verts):
                bm.verts.ensure_lookup_table()
                return obj.matrix_world @ bm.verts[vert_idx].co.copy()
        except (ReferenceError, IndexError):
            return None
    else:
        # 物体模式：直接从 mesh 获取
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
            # 先检查索引有效性，再调用 ensure_lookup_table
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


# ==================== 镜像增强工具函数 ====================

def axis_to_vec(axis: str) -> Vector:
    axis = axis.upper()
    if axis == "X": return Vector((1, 0, 0))
    if axis == "Y": return Vector((0, 1, 0))
    if axis == "Z": return Vector((0, 0, 1))
    return Vector((0, 1, 0))

def reflect_point_across_plane(p: Vector, plane_point: Vector, plane_normal_unit: Vector) -> Vector:
    d = (p - plane_point).dot(plane_normal_unit)
    return p - 2.0 * plane_normal_unit * d

def move_origin_keep_world_mesh(obj, new_origin_world: Vector):
    mw = obj.matrix_world.copy()
    delta_world = new_origin_world - mw.translation.copy()
    if delta_world.length < 1e-12:
        return
    inv3 = mw.inverted_safe().to_3x3()
    delta_local = inv3 @ delta_world
    obj.data.transform(Matrix.Translation(-delta_local))
    obj.matrix_world = Matrix.Translation(delta_world) @ mw

def bake_modifiers_to_mesh(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    try:
        new_mesh = bpy.data.meshes.new_from_object(eval_obj, preserve_all_data_layers=True, depsgraph=depsgraph)
    except TypeError:
        new_mesh = bpy.data.meshes.new_from_object(eval_obj)
    obj.data = new_mesh
    for m in list(obj.modifiers):
        obj.modifiers.remove(m)

def delete_side_by_plane_world(obj, plane_point: Vector, plane_normal_unit: Vector, side_sign_to_delete: float, eps: float):
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

# ==================== 镜像增强 Operator ====================

class OBJECT_OT_mirror_plus(Operator):
    """批量镜像复制选中对象（增强版）- 替代 Ctrl+M"""
    bl_idname = "object.mirror_plus"
    bl_label = "镜像（增强）"
    bl_options = {"REGISTER", "UNDO"}

    axis: EnumProperty(
        name="镜像轴",
        items=[("X", "X", ""), ("Y", "Y", ""), ("Z", "Z", "")],
        default="Y",
    )
    pivot_object_name: StringProperty(
        name="镜像物体",
        default="立方体",
    )
    mode: EnumProperty(
        name="模式",
        items=[
            ("MODIFIER", "仅添加修改器", "只添加 Mirror 修改器"),
            ("COPY_MIRROR", "复制并镜像", "复制对象并只保留镜像侧"),
        ],
        default="MODIFIER",
    )
    use_clip: BoolProperty(name="范围限制 (Clipping)", default=False)
    use_merge: BoolProperty(name="合并 (Merge)", default=False)
    new_suffix: StringProperty(name="后缀", default="_镜像")
    bake_modifiers: BoolProperty(name="烘焙所有修改器", default=True)
    keep_only_mirrored: BoolProperty(name="只保留镜像侧", default=True)
    move_origin: BoolProperty(name="移动原点到镜像位置", default=True)
    plane_eps: FloatProperty(name="平面容差", default=1e-6, min=0, precision=6)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "mode")
        layout.separator()
        layout.prop(self, "axis")
        layout.prop_search(self, "pivot_object_name", bpy.data, "objects", text="镜像物体")
        if self.mode == "MODIFIER":
            layout.separator()
            layout.label(text="修改器选项:")
            layout.prop(self, "use_clip")
            layout.prop(self, "use_merge")
        else:
            layout.separator()
            layout.label(text="复制镜像选项:")
            layout.prop(self, "new_suffix")
            layout.prop(self, "bake_modifiers")
            layout.prop(self, "keep_only_mirrored")
            layout.prop(self, "move_origin")

    def invoke(self, context, event):
        if self.pivot_object_name and self.pivot_object_name not in bpy.data.objects:
            self.pivot_object_name = ""
        return context.window_manager.invoke_props_dialog(self, width=320)

    def execute(self, context):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        pivot = bpy.data.objects.get(self.pivot_object_name) if self.pivot_object_name else None
        targets = [o for o in context.selected_objects if o.type == "MESH" and o.name != self.pivot_object_name]
        if not targets:
            self.report({"WARNING"}, "未选中任何 Mesh 对象")
            return {"CANCELLED"}
        if self.mode == "MODIFIER":
            return self._exec_modifier_mode(targets, pivot)
        else:
            return self._exec_copy_mirror_mode(context, targets, pivot)

    def _exec_modifier_mode(self, targets, pivot):
        for obj in targets:
            mod = obj.modifiers.new(name="镜像（增强）", type="MIRROR")
            mod.use_axis[0] = (self.axis == "X")
            mod.use_axis[1] = (self.axis == "Y")
            mod.use_axis[2] = (self.axis == "Z")
            mod.mirror_object = pivot
            if hasattr(mod, "use_clip"):
                mod.use_clip = self.use_clip
            if hasattr(mod, "use_mirror_merge"):
                mod.use_mirror_merge = self.use_merge
            elif hasattr(mod, "use_merge_vertices"):
                mod.use_merge_vertices = self.use_merge
        self.report({"INFO"}, f"已为 {len(targets)} 个对象添加 Mirror 修改器")
        return {"FINISHED"}

    def _exec_copy_mirror_mode(self, context, targets, pivot):
        if not pivot:
            self.report({"ERROR"}, "复制镜像模式需要指定镜像物体")
            return {"CANCELLED"}
        plane_point = pivot.matrix_world.translation.copy()
        n_world = (pivot.matrix_world.to_3x3() @ axis_to_vec(self.axis)).normalized()
        new_objs = []
        for src in targets:
            dst = src.copy()
            dst.data = src.data.copy()
            dst.name = src.name + self.new_suffix
            if src.users_collection:
                for col in src.users_collection:
                    col.objects.link(dst)
            else:
                context.scene.collection.objects.link(dst)
            for m in list(dst.modifiers):
                if m.type == 'MIRROR':
                    dst.modifiers.remove(m)
            mir = dst.modifiers.new(name="__Mirror__Temp__", type='MIRROR')
            mir.mirror_object = pivot
            mir.use_axis[0] = (self.axis == "X")
            mir.use_axis[1] = (self.axis == "Y")
            mir.use_axis[2] = (self.axis == "Z")
            if hasattr(mir, "use_clip"):
                mir.use_clip = False
            if hasattr(mir, "use_mirror_merge"):
                mir.use_mirror_merge = False
            if self.bake_modifiers:
                bake_modifiers_to_mesh(dst)
            if self.keep_only_mirrored:
                src_origin = src.matrix_world.translation.copy()
                d0 = (src_origin - plane_point).dot(n_world)
                if abs(d0) > 1e-9:
                    side_sign_to_delete = 1.0 if d0 > 0 else -1.0
                    delete_side_by_plane_world(dst, plane_point, n_world, side_sign_to_delete, self.plane_eps)
            if self.move_origin:
                src_origin = src.matrix_world.translation.copy()
                mirrored_origin = reflect_point_across_plane(src_origin, plane_point, n_world)
                move_origin_keep_world_mesh(dst, mirrored_origin)
            new_objs.append(dst)
        bpy.ops.object.select_all(action="DESELECT")
        for o in new_objs:
            o.select_set(True)
        context.view_layer.objects.active = new_objs[0] if new_objs else None
        self.report({"INFO"}, f"已生成 {len(new_objs)} 个镜像副本")
        return {"FINISHED"}

def menu_func_mirror(self, context):
    self.layout.operator(OBJECT_OT_mirror_plus.bl_idname, text="镜像（增强）", icon="MOD_MIRROR")

# ==================== 标注清理模块（统一复用）====================

class AnnotationCleaner:
    """
    标注清理器（模块化）
    
    提供统一的标注清理功能，支持：
    1. 编辑模式：根据选中的点、边、面清理对应的标注
    2. 物体模式：清理选中对象的所有标注
    3. 无二次确认，直接执行
    """
    
    @staticmethod
    def refresh_view(context):
        """刷新3D视图"""
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
    
    @staticmethod
    def clear_by_vertex_refs(vert_refs_to_clear):
        """
        根据顶点引用清理标注
        
        参数:
            vert_refs_to_clear: set of (obj_name, vert_idx) 元组
        
        返回:
            清理的标注数量
        """
        global _annotation_registry
        to_remove = []
        
        for name, data in _annotation_registry.items():
            annotation_type = data.get('type', '')
            
            # 检查 vert_refs 类型的标注（顶点角度、线段角度等）
            if 'vert_refs' in data:
                for ref in data['vert_refs']:
                    if ref in vert_refs_to_clear:
                        to_remove.append(name)
                        break
            
            # 检查 edge_data 类型的标注（边长测量）
            if 'edge_data' in data:
                for obj_name, edge_idx, v1_idx, v2_idx in data['edge_data']:
                    if (obj_name, v1_idx) in vert_refs_to_clear or (obj_name, v2_idx) in vert_refs_to_clear:
                        to_remove.append(name)
                        break
            
            # 检查 edge_refs 类型的标注（两边夹角）
            if 'edge_refs' in data:
                for obj_name, v1_idx, v2_idx in data['edge_refs']:
                    if (obj_name, v1_idx) in vert_refs_to_clear or (obj_name, v2_idx) in vert_refs_to_clear:
                        to_remove.append(name)
                        break
        
        # 去重并删除
        to_remove = list(set(to_remove))
        for name in to_remove:
            if name in _annotation_registry:
                del _annotation_registry[name]
        
        return len(to_remove)
    
    @staticmethod
    def clear_by_edge_refs(edge_refs_to_clear):
        """
        根据边引用清理标注
        
        参数:
            edge_refs_to_clear: set of (obj_name, v1_idx, v2_idx) 元组（顶点索引已排序）
        
        返回:
            清理的标注数量
        """
        global _annotation_registry
        to_remove = []
        
        for name, data in _annotation_registry.items():
            # 检查 edge_data 类型的标注（边长测量）
            if 'edge_data' in data:
                for obj_name, edge_idx, v1_idx, v2_idx in data['edge_data']:
                    v_min, v_max = min(v1_idx, v2_idx), max(v1_idx, v2_idx)
                    if (obj_name, v_min, v_max) in edge_refs_to_clear:
                        to_remove.append(name)
                        break
            
            # 检查 edge_refs 类型的标注（两边夹角）
            if 'edge_refs' in data:
                for obj_name, v1_idx, v2_idx in data['edge_refs']:
                    v_min, v_max = min(v1_idx, v2_idx), max(v1_idx, v2_idx)
                    if (obj_name, v_min, v_max) in edge_refs_to_clear:
                        to_remove.append(name)
                        break
        
        # 去重并删除
        to_remove = list(set(to_remove))
        for name in to_remove:
            if name in _annotation_registry:
                del _annotation_registry[name]
        
        return len(to_remove)
    
    @staticmethod
    def clear_by_object_names(obj_names_to_clear):
        """
        根据对象名称清理标注
        
        参数:
            obj_names_to_clear: set of 对象名称
        
        返回:
            (清理的标注数量, 删除的测量对象列表)
        """
        global _annotation_registry
        to_remove = []
        measure_objects_to_delete = []
        
        for name, data in list(_annotation_registry.items()):
            # 直接绑定到对象的标注
            if name in obj_names_to_clear:
                to_remove.append(name)
                # 检查是否是测量对象
                obj = bpy.data.objects.get(name)
                if obj and name.startswith("测量_"):
                    measure_objects_to_delete.append(obj)
                continue
            
            # 检查标注数据中引用的对象
            should_remove = False
            
            # vert_refs 类型
            if 'vert_refs' in data:
                for ref in data['vert_refs']:
                    if ref[0] in obj_names_to_clear:
                        should_remove = True
                        break
            
            # edge_data 类型
            if not should_remove and 'edge_data' in data:
                for obj_name, edge_idx, v1_idx, v2_idx in data['edge_data']:
                    if obj_name in obj_names_to_clear:
                        should_remove = True
                        break
            
            # edge_refs 类型
            if not should_remove and 'edge_refs' in data:
                for obj_name, v1_idx, v2_idx in data['edge_refs']:
                    if obj_name in obj_names_to_clear:
                        should_remove = True
                        break
            
            if should_remove:
                to_remove.append(name)
        
        # 去重并删除标注
        to_remove = list(set(to_remove))
        for name in to_remove:
            if name in _annotation_registry:
                del _annotation_registry[name]
        
        return len(to_remove), measure_objects_to_delete
    
    @staticmethod
    def clear_selected_in_edit_mode(context):
        """
        编辑模式下清理选中元素的标注
        
        根据当前选择模式（顶点/边/面）清理对应的标注
        
        返回:
            清理的标注数量
        """
        edit_objects = [obj for obj in context.objects_in_mode if obj.type == 'MESH']
        if not edit_objects:
            return 0
        
        tool_settings = context.tool_settings
        select_mode = tool_settings.mesh_select_mode  # (vert, edge, face)
        
        cleared_count = 0
        
        if select_mode[2]:  # 面模式
            # 收集选中面的所有顶点
            vert_refs = set()
            for obj in edit_objects:
                bm = bmesh.from_edit_mesh(obj.data)
                bm.verts.ensure_lookup_table()
                bm.faces.ensure_lookup_table()
                for f in bm.faces:
                    if f.select:
                        for v in f.verts:
                            vert_refs.add((obj.name, v.index))
            cleared_count = AnnotationCleaner.clear_by_vertex_refs(vert_refs)
            
        elif select_mode[1]:  # 边模式
            # 收集选中的边
            edge_refs = set()
            for obj in edit_objects:
                bm = bmesh.from_edit_mesh(obj.data)
                bm.edges.ensure_lookup_table()
                for e in bm.edges:
                    if e.select:
                        v_min = min(e.verts[0].index, e.verts[1].index)
                        v_max = max(e.verts[0].index, e.verts[1].index)
                        edge_refs.add((obj.name, v_min, v_max))
            cleared_count = AnnotationCleaner.clear_by_edge_refs(edge_refs)
            
        else:  # 顶点模式
            # 收集选中的顶点
            vert_refs = set()
            for obj in edit_objects:
                bm = bmesh.from_edit_mesh(obj.data)
                bm.verts.ensure_lookup_table()
                for v in bm.verts:
                    if v.select:
                        vert_refs.add((obj.name, v.index))
            cleared_count = AnnotationCleaner.clear_by_vertex_refs(vert_refs)
        
        return cleared_count
    
    @staticmethod
    def clear_selected_in_object_mode(context):
        """
        物体模式下清理选中对象的所有标注
        
        返回:
            (清理的标注数量, 删除的测量对象数量)
        """
        selected_names = set(obj.name for obj in context.selected_objects)
        if not selected_names:
            return 0, 0
        
        cleared_count, measure_objects = AnnotationCleaner.clear_by_object_names(selected_names)
        
        # 删除测量对象
        deleted_count = 0
        for obj in measure_objects:
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
                deleted_count += 1
            except (ReferenceError, RuntimeError):
                pass
        
        return cleared_count, deleted_count


# ==================== 标注管理操作符 ====================

class BOFU_OT_clear_temp_annotations(Operator):
    """清除所有临时标注（边长测量、顶点角度等不创建几何体的标注）"""
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
    """智能清除标注：编辑模式下清除选中元素的标注，物体模式下清除选中对象的所有标注"""
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
            # 编辑模式：根据选中的点/边/面清理标注
            cleared_count = AnnotationCleaner.clear_selected_in_edit_mode(context)
            AnnotationCleaner.refresh_view(context)
            
            # 获取当前选择模式名称
            select_mode = context.tool_settings.mesh_select_mode
            mode_name = "面" if select_mode[2] else ("边" if select_mode[1] else "顶点")
            
            if cleared_count > 0:
                self.report({'INFO'}, f"已清除 {cleared_count} 个与选中{mode_name}相关的标注")
            else:
                self.report({'INFO'}, f"选中的{mode_name}没有关联的标注")
        else:
            # 物体模式：清除选中对象的所有标注
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
    """清除所有标注（包括绑定对象的标注和临时标注）"""
    bl_idname = "bofu.clear_all_annotations"
    bl_label = "清除所有标注"
    bl_options = {'REGISTER', 'UNDO'}
    
    # 移除二次确认，直接执行
    def execute(self, context):
        global _annotation_registry
        count = len(_annotation_registry)
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
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        visible = toggle_annotations_visibility()
        AnnotationCleaner.refresh_view(context)
        
        status = "显示" if visible else "隐藏"
        self.report({'INFO'}, f"标注已{status}")
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


# ==================== 饼图菜单 ====================

class VIEW3D_MT_PIE_bofu_tools(bpy.types.Menu):
    """🛠️ -小夫的增强工具- 🛠️饼图菜单"""
    bl_idname = "VIEW3D_MT_PIE_bofu_tools"
    bl_label = "🛠️ -小夫的增强工具- 🛠️"

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


class VIEW3D_MT_annotation_manage(bpy.types.Menu):
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


class BOFU_OT_call_pie_menu(Operator):
    """呼出🛠️ -小夫的增强工具- 🛠️饼图菜单"""
    bl_idname = "bofu.call_pie_menu"
    bl_label = "🛠️ -小夫的增强工具- 🛠️"
    bl_options = {'REGISTER'}

    def execute(self, context):
        bpy.ops.wm.call_menu_pie(name="VIEW3D_MT_PIE_bofu_tools")
        return {'FINISHED'}

# ==================== 名称批量替换功能 ====================

class OBJECT_OT_connect_origins(Operator):
    """智能测量工具：支持距离、角度、半径等多种测量模式"""
    bl_idname = "object.connect_origins"
    bl_label = "智能测量"
    bl_options = {"REGISTER", "UNDO"}
    
    measure_mode: EnumProperty(
        name="测量模式",
        items=[
            ('CENTER_DISTANCE', '通用距离', '测量点/线/面之间的距离，支持灵活的轴锁定（可锁定0/1/2个轴）'),
            ('EDGE_LENGTH', '边长测量', '测量选中边的长度（不创建几何体）'),
            ('XYZ_SPLIT', '分轴测量（XYZ）', '同时显示X、Y、Z三个方向的距离（自动跳过无差异的轴）'),
            ('ANGLE_EDGES', '两边夹角', '选择2条边，计算两条边的夹角'),
            ('ANGLE_FACES', '两面夹角', '选择2个面，计算法线夹角（适用于弯管、弯头等）'),
            ('ANGLE_VERTS', '顶点角度', '2点:线段与轴夹角; 3+点:每个顶点的角度（不创建几何体）'),
            ('RADIUS', '半距/全距（半径/直径）', '选择2个点/边/面，计算距离的一半和全长；或选择1个圆形面/3+个点拟合圆'),
        ],
        default='CENTER_DISTANCE',
    )
    
    create_geometry: BoolProperty(
        name="创建辅助几何体",
        description="是否创建连线/标记点（关闭则只显示数据标注）",
        default=True,
    )
    
    # 圆心距离模式的偏移量
    center_offset_x: FloatProperty(
        name="X偏移",
        description="圆心X轴偏移量",
        default=0.0,
        unit='LENGTH',
    )
    center_offset_y: FloatProperty(
        name="Y偏移",
        description="圆心Y轴偏移量",
        default=0.0,
        unit='LENGTH',
    )
    center_offset_z: FloatProperty(
        name="Z偏移",
        description="圆心Z轴偏移量（用于对齐到同一平面）",
        default=0.0,
        unit='LENGTH',
    )
    
    # 增强的轴锁定选项（支持同时锁定多个轴）
    lock_x: BoolProperty(
        name="锁定X轴",
        description="忽略X轴差异",
        default=False,
    )
    lock_y: BoolProperty(
        name="锁定Y轴",
        description="忽略Y轴差异",
        default=False,
    )
    lock_z: BoolProperty(
        name="锁定Z轴",
        description="忽略Z轴差异",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        return context.mode in {'OBJECT', 'EDIT_MESH'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=320)
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "measure_mode")
        
        # 根据模式显示不同选项
        if self.measure_mode == 'ANGLE_VERTS':
            layout.separator()
            box = layout.box()
            box.label(text="💡 顶点角度模式不创建新几何体", icon='INFO')
            box.label(text="   2点: 计算线段与坐标轴的夹角")
            box.label(text="   3+点: 计算每个顶点的角度")
        elif self.measure_mode == 'ANGLE_EDGES':
            layout.separator()
            box = layout.box()
            box.label(text="💡 选择2条边，计算夹角", icon='INFO')
            box.label(text="   支持不相交的边")
        elif self.measure_mode == 'EDGE_LENGTH':
            layout.separator()
            box = layout.box()
            box.label(text="💡 边长测量模式不创建新几何体", icon='INFO')
            box.label(text="   直接显示选中边的长度")
        elif self.measure_mode == 'CENTER_DISTANCE':
            layout.separator()
            box = layout.box()
            box.label(text="💡 通用距离测量（增强版）", icon='INFO')
            box.label(text="   支持点/线/面，自动计算中心点")
            box.label(text="   可灵活锁定0/1/2个轴")
            layout.separator()
            
            # 轴锁定选项（支持多选）
            box2 = layout.box()
            box2.label(text="轴锁定设置:", icon='LOCKED')
            row = box2.row(align=True)
            row.prop(self, "lock_x", toggle=True)
            row.prop(self, "lock_y", toggle=True)
            row.prop(self, "lock_z", toggle=True)
            
            # 显示当前锁定状态的说明
            locked_axes = []
            if self.lock_x:
                locked_axes.append('X')
            if self.lock_y:
                locked_axes.append('Y')
            if self.lock_z:
                locked_axes.append('Z')
            
            if not locked_axes:
                box2.label(text="   当前: 3D空间距离", icon='EMPTY_AXIS')
            elif len(locked_axes) == 1:
                free_axes = [a for a in ['X', 'Y', 'Z'] if a not in locked_axes]
                box2.label(text=f"   当前: {free_axes[0]}{free_axes[1]}平面距离", icon='MESH_PLANE')
            elif len(locked_axes) == 2:
                free_axis = [a for a in ['X', 'Y', 'Z'] if a not in locked_axes][0]
                box2.label(text=f"   当前: 仅{free_axis}轴方向距离", icon='EMPTY_SINGLE_ARROW')
            else:
                box2.label(text="   ⚠️ 不能锁定全部3个轴", icon='ERROR')
            
            layout.separator()
            box3 = layout.box()
            box3.label(text="偏移量设置:", icon='ORIENTATION_GLOBAL')
            row = box3.row()
            row.prop(self, "center_offset_x", text="X")
            row.prop(self, "center_offset_y", text="Y")
            row.prop(self, "center_offset_z", text="Z")
            layout.prop(self, "create_geometry")
        else:
            layout.separator()
            layout.prop(self, "create_geometry")

    def execute(self, context):
        if context.mode == 'EDIT_MESH':
            return self.execute_edit_mode(context)
        else:
            return self.execute_object_mode(context)
    
    def calc_distance(self, p1, p2):
        """
        根据轴锁定设置计算距离
        
        支持：
        - 锁定0个轴：3D空间距离
        - 锁定1个轴：平面距离（如锁定Z = XY平面距离）
        - 锁定2个轴：单轴距离（如锁定Y和Z = 只测X轴距离）
        """
        # 计算各轴的差值
        dx = 0 if self.lock_x else (p2.x - p1.x)
        dy = 0 if self.lock_y else (p2.y - p1.y)
        dz = 0 if self.lock_z else (p2.z - p1.z)
        
        # 计算距离
        return math.sqrt(dx**2 + dy**2 + dz**2)
    
    def get_axis_lock_info(self):
        """获取轴锁定状态的描述信息"""
        locked_axes = []
        if self.lock_x:
            locked_axes.append('X')
        if self.lock_y:
            locked_axes.append('Y')
        if self.lock_z:
            locked_axes.append('Z')
        
        if not locked_axes:
            return "3D距离"
        elif len(locked_axes) == 1:
            free_axes = [a for a in ['X', 'Y', 'Z'] if a not in locked_axes]
            return f"{free_axes[0]}{free_axes[1]}平面距离（锁定{locked_axes[0]}）"
        elif len(locked_axes) == 2:
            free_axis = [a for a in ['X', 'Y', 'Z'] if a not in locked_axes][0]
            return f"{free_axis}轴方向距离（锁定{','.join(locked_axes)}）"
        else:
            return "错误：不能锁定全部3个轴"
    
    def get_display_points(self, p1, p2):
        """
        根据轴锁定设置获取用于显示的两个点
        
        返回: (display_p1, display_p2)
        """
        # 根据锁定的轴调整第二个点的坐标
        x = p1.x if self.lock_x else p2.x
        y = p1.y if self.lock_y else p2.y
        z = p1.z if self.lock_z else p2.z
        
        return p1.copy(), Vector((x, y, z))
    
    def fit_circle_3d(self, points):
        """
        在3D空间中拟合圆
        
        原理：
        1. 首先用PCA找到点集的最佳拟合平面
        2. 将点投影到该平面上
        3. 在2D平面上用最小二乘法拟合圆
        4. 将圆心转换回3D坐标
        
        返回: (圆心Vector, 半径float, 拟合误差float) 或 (None, None, None)
        """
        import numpy as np
        
        if len(points) < 3:
            return None, None, None
        
        # 转换为numpy数组
        pts = np.array([[p.x, p.y, p.z] for p in points])
        
        # 计算质心
        centroid = pts.mean(axis=0)
        
        # 中心化
        pts_centered = pts - centroid
        
        # PCA找到最佳拟合平面
        # 协方差矩阵的特征向量
        cov = np.cov(pts_centered.T)
        eigenvalues, eigenvectors = np.linalg.eigh(cov)
        
        # 最小特征值对应的特征向量是平面法线
        normal = eigenvectors[:, 0]  # 最小特征值对应的向量
        
        # 构建局部坐标系（平面上的两个正交轴）
        # u: 第二大特征值对应的向量
        # v: 最大特征值对应的向量
        u = eigenvectors[:, 1]
        v = eigenvectors[:, 2]
        
        # 将点投影到2D平面
        pts_2d = np.column_stack([
            pts_centered.dot(u),
            pts_centered.dot(v)
        ])
        
        # 在2D平面上拟合圆（最小二乘法）
        # 圆方程: (x-a)^2 + (y-b)^2 = r^2
        # 展开: x^2 + y^2 = 2ax + 2by + (r^2 - a^2 - b^2)
        # 令 c = r^2 - a^2 - b^2
        # 线性方程: 2ax + 2by + c = x^2 + y^2
        
        A = np.column_stack([2 * pts_2d[:, 0], 2 * pts_2d[:, 1], np.ones(len(pts_2d))])
        b = pts_2d[:, 0]**2 + pts_2d[:, 1]**2
        
        try:
            # 最小二乘解
            result, residuals, rank, s = np.linalg.lstsq(A, b, rcond=None)
            a, b_val, c = result
            
            # 计算半径
            r_squared = c + a**2 + b_val**2
            if r_squared <= 0:
                return None, None, None
            radius = np.sqrt(r_squared)
            
            # 2D圆心
            center_2d = np.array([a, b_val])
            
            # 转换回3D
            center_3d = centroid + a * u + b_val * v
            
            # 计算拟合误差（各点到圆的平均距离）
            distances_to_center = np.sqrt(np.sum((pts_2d - center_2d)**2, axis=1))
            fit_error = np.mean(np.abs(distances_to_center - radius))
            
            return Vector(center_3d), float(radius), float(fit_error)
            
        except (np.linalg.LinAlgError, ValueError, RuntimeError):
            return None, None, None
    
    def execute_edit_mode(self, context):
        """编辑模式：根据选择模式（顶点/边/面）连接对应的中心点"""
        # 获取所有编辑中的对象
        edit_objects = [obj for obj in context.objects_in_mode if obj.type == 'MESH']
        
        if not edit_objects:
            self.report({'WARNING'}, "没有处于编辑模式的网格对象")
            return {'CANCELLED'}
        
        # 获取当前选择模式
        tool_settings = context.tool_settings
        select_mode = tool_settings.mesh_select_mode  # (vert, edge, face)
        
        # 收集选中元素的世界坐标点
        points_world = []  # 存储要连接的世界坐标点
        
        for obj in edit_objects:
            bm = bmesh.from_edit_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            
            if select_mode[2]:  # 面模式
                for f in bm.faces:
                    if f.select:
                        # 计算面的中心点（世界坐标）
                        center_local = f.calc_center_median()
                        center_world = obj.matrix_world @ center_local
                        points_world.append(center_world)
            elif select_mode[1]:  # 边模式
                for e in bm.edges:
                    if e.select:
                        # 计算边的中点（世界坐标）
                        v1_world = obj.matrix_world @ e.verts[0].co
                        v2_world = obj.matrix_world @ e.verts[1].co
                        mid_world = (v1_world + v2_world) / 2
                        points_world.append(mid_world)
            else:  # 顶点模式
                for v in bm.verts:
                    if v.select:
                        world_co = obj.matrix_world @ v.co
                        points_world.append(world_co)
        
        # ========== 边长测量模式特殊处理 ==========
        if self.measure_mode == 'EDGE_LENGTH':
            # 收集选中的边及其顶点索引（用于实时跟随）
            edge_data_list = []  # [(obj_name, edge_index, v1_idx, v2_idx), ...]
            
            for obj in edit_objects:
                bm_read = bmesh.from_edit_mesh(obj.data)
                bm_read.edges.ensure_lookup_table()
                for edge_idx, e in enumerate(bm_read.edges):
                    if e.select:
                        edge_data_list.append((obj.name, edge_idx, e.verts[0].index, e.verts[1].index))
            
            if len(edge_data_list) == 0:
                self.report({'WARNING'}, "边长测量模式需要在边选择模式下选择至少1条边")
                return {'CANCELLED'}
            
            # 注册标注（存储对象名和顶点索引，绘制时实时计算）
            register_annotation("__edge_length__", "edge_length", {
                'edge_data': edge_data_list,
            })
            
            # 确保绘制处理器已启用
            ensure_draw_handler_enabled()
            
            # 刷新视图
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
            
            # 计算并输出长度信息
            total_length = 0.0
            edge_count = len(edge_data_list)
            print(f"\n========== 边长测量 ==========")
            for i, (obj_name, edge_idx, v1_idx, v2_idx) in enumerate(edge_data_list):
                obj = bpy.data.objects.get(obj_name)
                if obj and obj.type == 'MESH':
                    mesh = obj.data
                    if v1_idx < len(mesh.vertices) and v2_idx < len(mesh.vertices):
                        v1_world = obj.matrix_world @ mesh.vertices[v1_idx].co
                        v2_world = obj.matrix_world @ mesh.vertices[v2_idx].co
                        length = (v2_world - v1_world).length
                        total_length += length
                        print(f"  边 {i+1}: {length:.6f} m")
            print(f"  ─────────────────────")
            print(f"  总长度: {total_length:.6f} m")
            print(f"  边数: {edge_count}")
            print("  💡 未创建几何体，标注跟随物体移动")
            print("==============================\n")
            
            if edge_count == 1:
                self.report({'INFO'}, f"边长: {total_length:.6f} m（标注跟随物体）")
            else:
                self.report({'INFO'}, f"选中 {edge_count} 条边，总长度: {total_length:.6f} m（标注跟随物体）")
            return {'FINISHED'}
        
        # ========== 通用距离模式特殊处理 ==========
        if self.measure_mode == 'CENTER_DISTANCE':
            # 支持点/线/面的距离测量
            # 策略：
            # 1. 面模式：每个选中的面计算中心点
            # 2. 边模式：每条选中的边计算中点，或通过连通性分组
            # 3. 顶点模式：每个选中的顶点，或通过连通性分组
            
            centers = []  # 存储各组的中心点
            
            if select_mode[2]:  # 面模式
                # 每个选中的面计算中心点
                for obj in edit_objects:
                    bm_read = bmesh.from_edit_mesh(obj.data)
                    bm_read.faces.ensure_lookup_table()
                    for f in bm_read.faces:
                        if f.select:
                            # 计算面的中心点（世界坐标）
                            face_center = f.calc_center_median()
                            world_center = obj.matrix_world @ face_center
                            centers.append(world_center.copy())
                
            elif select_mode[1]:  # 边模式
                # 每条选中的边计算中点
                for obj in edit_objects:
                    bm_read = bmesh.from_edit_mesh(obj.data)
                    bm_read.edges.ensure_lookup_table()
                    for e in bm_read.edges:
                        if e.select:
                            # 计算边的中点（世界坐标）
                            v1_world = obj.matrix_world @ e.verts[0].co
                            v2_world = obj.matrix_world @ e.verts[1].co
                            edge_center = (v1_world + v2_world) / 2
                            centers.append(edge_center.copy())
                            
            else:  # 顶点模式
                # 每个选中的顶点
                for obj in edit_objects:
                    bm_read = bmesh.from_edit_mesh(obj.data)
                    bm_read.verts.ensure_lookup_table()
                    for v in bm_read.verts:
                        if v.select:
                            world_co = obj.matrix_world @ v.co
                            centers.append(world_co.copy())
            
            # 检查是否有至少2个中心点
            if len(centers) < 2:
                mode_name = "面" if select_mode[2] else ("边" if select_mode[1] else "顶点")
                self.report({'WARNING'}, f"通用距离模式需要选择至少2个{mode_name}")
                return {'CANCELLED'}
            
            # 如果正好2个点，直接计算距离
            if len(centers) == 2:
                center1, center2 = centers[0], centers[1]
            else:
                # 多于2个点时，取前两个（或可以改为计算所有点的质心）
                center1, center2 = centers[0], centers[1]
                self.report({'INFO'}, f"选中了{len(centers)}个元素，使用前两个计算距离")
            
            # 应用偏移量
            offset = Vector((self.center_offset_x, self.center_offset_y, self.center_offset_z))
            center2_offset = center2 + offset
            
            # 检查是否锁定了全部3个轴
            if self.lock_x and self.lock_y and self.lock_z:
                self.report({'ERROR'}, "不能同时锁定全部3个轴")
                return {'CANCELLED'}
            
            # 根据轴锁定设置计算距离和显示点
            display_p1, display_p2 = self.get_display_points(center1, center2_offset)
            distance = self.calc_distance(center1, center2_offset)
            axis_info = self.get_axis_lock_info()
            
            # 创建几何体或临时标注
            if self.create_geometry:
                bpy.ops.object.mode_set(mode='OBJECT')
                
                obj_name = get_unique_measure_name("测量_通用距离")
                mesh = bpy.data.meshes.new(obj_name)
                measure_obj = bpy.data.objects.new(obj_name, mesh)
                context.collection.objects.link(measure_obj)
                
                # 创建连线
                bm = bmesh.new()
                v1 = bm.verts.new(display_p1)
                v2 = bm.verts.new(display_p2)
                bm.verts.ensure_lookup_table()
                bm.edges.new((v1, v2))
                bm.to_mesh(mesh)
                bm.free()
                
                # 注册标注（存储计算好的距离值）
                register_annotation(obj_name, "distance", {
                    'measure_mode': 'CENTER_DISTANCE',
                    'edge_indices': [0],
                    'distance': distance,
                })
                
                # 选中新创建的对象
                bpy.ops.object.select_all(action='DESELECT')
                measure_obj.select_set(True)
                context.view_layer.objects.active = measure_obj
            else:
                # 不创建几何体，使用临时标注（存储计算好的距离值）
                register_annotation("__center_distance_temp__", "distance_temp", {
                    'points': [display_p1.copy(), display_p2.copy()],
                    'measure_mode': 'CENTER_DISTANCE',
                    'distance': distance,
                })
            
            # 确保绘制处理器已启用
            ensure_draw_handler_enabled()
            
            # 刷新视图
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
            
            # 输出信息
            mode_name = "面" if select_mode[2] else ("边" if select_mode[1] else "顶点")
            print(f"\n========== 通用距离测量（{mode_name}模式）==========")
            print(f"  距离: {distance:.6f} m（{axis_info}）")
            if offset.length > 0.0001:
                print(f"  偏移量: X={self.center_offset_x:.4f}, Y={self.center_offset_y:.4f}, Z={self.center_offset_z:.4f}")
            print(f"  点1: ({center1.x:.4f}, {center1.y:.4f}, {center1.z:.4f})")
            print(f"  点2: ({center2.x:.4f}, {center2.y:.4f}, {center2.z:.4f})")
            print("==============================\n")
            
            self.report({'INFO'}, f"距离: {distance:.6f} m（{axis_info}）")
            return {'FINISHED'}
        
        # ========== 两边夹角模式特殊处理 ==========
        if self.measure_mode == 'ANGLE_EDGES':
            # 收集选中的边（存储对象名和顶点索引）
            edge_refs = []  # [(obj_name, v1_idx, v2_idx), ...]
            
            for obj in edit_objects:
                bm_read = bmesh.from_edit_mesh(obj.data)
                bm_read.edges.ensure_lookup_table()
                for e in bm_read.edges:
                    if e.select:
                        edge_refs.append((obj.name, e.verts[0].index, e.verts[1].index))
            
            if len(edge_refs) != 2:
                self.report({'WARNING'}, f"两边夹角模式需要选择恰好2条边，当前选中了{len(edge_refs)}条")
                return {'CANCELLED'}
            
            # 注册标注（存储对象引用，绘制时实时计算）
            register_annotation("__edge_angle__", "edge_angle", {
                'edge_refs': edge_refs,
            })
            
            # 确保绘制处理器已启用
            ensure_draw_handler_enabled()
            
            # 刷新视图
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
            
            # 计算并输出角度信息（用于控制台）
            def get_edge_direction(obj_name, v1_idx, v2_idx):
                obj = bpy.data.objects.get(obj_name)
                if obj and obj.type == 'MESH':
                    mesh = obj.data
                    if v1_idx < len(mesh.vertices) and v2_idx < len(mesh.vertices):
                        v1_world = obj.matrix_world @ mesh.vertices[v1_idx].co
                        v2_world = obj.matrix_world @ mesh.vertices[v2_idx].co
                        return (v2_world - v1_world).normalized(), (v1_world + v2_world) / 2
                return None, None
            
            dir1, mid1 = get_edge_direction(*edge_refs[0])
            dir2, mid2 = get_edge_direction(*edge_refs[1])
            
            if dir1 and dir2:
                dot_product = dir1.dot(dir2)
                dot_product = max(-1.0, min(1.0, dot_product))
                angle_rad = math.acos(abs(dot_product))
                angle_deg = math.degrees(angle_rad)
                supplement_angle = 180.0 - angle_deg
                
                print(f"\n========== 角度测量（两边夹角）==========")
                print(f"  夹角: {angle_deg:.6f}°")
                print(f"  补角: {supplement_angle:.6f}°")
                print("  💡 标注跟随物体移动")
                print("==============================\n")
                
                self.report({'INFO'}, f"两边夹角: {angle_deg:.2f}°（补角: {supplement_angle:.2f}°）")
            
            return {'FINISHED'}
        
        # ========== 两面夹角模式特殊处理 ==========
        if self.measure_mode == 'ANGLE_FACES':
            # 必须在面模式下选择恰好2个面
            if not select_mode[2]:
                self.report({'WARNING'}, "两面夹角模式需要在面选择模式下使用")
                return {'CANCELLED'}
            
            # 收集选中面的法线（世界坐标）
            face_normals = []
            face_centers = []
            for obj in edit_objects:
                bm_read = bmesh.from_edit_mesh(obj.data)
                bm_read.faces.ensure_lookup_table()
                for f in bm_read.faces:
                    if f.select:
                        # 计算面中心点（世界坐标）
                        center_local = f.calc_center_median()
                        center_world = obj.matrix_world @ center_local
                        # 将法线从局部坐标转换到世界坐标（使用3x3矩阵，不含位移）
                        normal_world = (obj.matrix_world.to_3x3() @ f.normal).normalized()
                        face_normals.append(normal_world.copy())
                        face_centers.append(center_world.copy())
            
            if len(face_normals) != 2:
                self.report({'WARNING'}, f"两面夹角模式需要选择恰好2个面，当前选中了{len(face_normals)}个")
                return {'CANCELLED'}
            
            # 计算两个法线的夹角
            n1 = face_normals[0]
            n2 = face_normals[1]
            
            # 使用点积计算夹角：cos(θ) = n1 · n2
            dot_product = n1.dot(n2)
            # 限制在[-1, 1]范围内，避免浮点误差导致的 acos 错误
            dot_product = max(-1.0, min(1.0, dot_product))
            angle_rad = math.acos(dot_product)
            angle_deg = math.degrees(angle_rad)
            
            # 计算补角（弯曲角度）
            # 对于弯管：如果两个端面法线相对（指向相反方向），夹角接近180°，弯曲角度接近0°
            # 如果法线垂直，夹角90°，弯曲角度也是90°
            bend_angle = 180.0 - angle_deg
            
            # 【重要改进】创建独立的连线对象
            if self.create_geometry:
                # 退出编辑模式
                bpy.ops.object.mode_set(mode='OBJECT')
                
                # 创建独立的测量对象
                obj_name = get_unique_measure_name("测量_夹角")
                mesh = bpy.data.meshes.new(obj_name)
                measure_obj = bpy.data.objects.new(obj_name, mesh)
                context.collection.objects.link(measure_obj)
                
                # 创建连线
                bm = bmesh.new()
                v1 = bm.verts.new(face_centers[0])
                v2 = bm.verts.new(face_centers[1])
                bm.verts.ensure_lookup_table()
                bm.edges.new((v1, v2))
                bm.to_mesh(mesh)
                bm.free()
                
                # 注册标注（绑定到独立对象）
                register_annotation(obj_name, "angle", {
                    'edge_indices': [0],
                    'angle': angle_deg,
                    'bend': bend_angle,
                })
                
                # 选中新创建的对象
                bpy.ops.object.select_all(action='DESELECT')
                measure_obj.select_set(True)
                context.view_layer.objects.active = measure_obj
            else:
                # 不创建几何体，使用临时标注
                register_annotation("__angle_temp__", "angle_temp", {
                    'center': (face_centers[0] + face_centers[1]) / 2,
                    'angle': angle_deg,
                    'bend': bend_angle,
                })
            
            # 确保绘制处理器已启用
            ensure_draw_handler_enabled()
            
            # 刷新视图
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
            
            # 输出角度信息
            print(f"\n========== 角度测量（两面夹角）==========")
            print(f"  法线夹角: {angle_deg:.6f}°")
            print(f"  弯曲角度: {bend_angle:.6f}°")
            print(f"  面1法线: ({n1.x:.4f}, {n1.y:.4f}, {n1.z:.4f})")
            print(f"  面2法线: ({n2.x:.4f}, {n2.y:.4f}, {n2.z:.4f})")
            if self.create_geometry:
                print(f"  已创建独立对象: {obj_name}")
            print("==============================\n")
            
            self.report({'INFO'}, f"法线夹角: {angle_deg:.2f}°，弯曲角度: {bend_angle:.2f}°")
            return {'FINISHED'}
        
        # ========== 顶点角度模式特殊处理 ==========
        if self.measure_mode == 'ANGLE_VERTS':
            # 收集选中的顶点（存储对象名和顶点索引）
            vert_refs = []  # [(obj_name, vert_idx), ...]
            
            for obj in edit_objects:
                bm_read = bmesh.from_edit_mesh(obj.data)
                bm_read.verts.ensure_lookup_table()
                for v in bm_read.verts:
                    if v.select:
                        vert_refs.append((obj.name, v.index))
            
            if len(vert_refs) < 2:
                self.report({'WARNING'}, f"顶点角度模式需要至少选择2个顶点，当前选中了{len(vert_refs)}个")
                return {'CANCELLED'}
            
            # 获取世界坐标（用于计算和输出）
            def get_vert_world(obj_name, vert_idx):
                obj = bpy.data.objects.get(obj_name)
                if obj and obj.type == 'MESH':
                    mesh = obj.data
                    if vert_idx < len(mesh.vertices):
                        return obj.matrix_world @ mesh.vertices[vert_idx].co
                return None
            
            vertices_world = [get_vert_world(name, idx) for name, idx in vert_refs]
            vertices_world = [v for v in vertices_world if v is not None]
            
            # ========== 对3+个点进行凸包排序（解决顶点索引顺序问题）==========
            def sort_points_convex(points, vert_refs_list):
                """
                对共面的点按凸包顺序排序（逆时针）
                同时返回排序后的 vert_refs
                """
                if len(points) < 3:
                    return points, vert_refs_list
                
                # 计算中心点
                center = Vector((0, 0, 0))
                for p in points:
                    center += p
                center /= len(points)
                
                # 计算平面法线（用前3个点）
                v1 = points[1] - points[0]
                v2 = points[2] - points[0]
                normal = v1.cross(v2)
                if normal.length < 0.0001:
                    # 点共线，尝试其他组合
                    for i in range(len(points)):
                        for j in range(i+1, len(points)):
                            for k in range(j+1, len(points)):
                                v1 = points[j] - points[i]
                                v2 = points[k] - points[i]
                                normal = v1.cross(v2)
                                if normal.length > 0.0001:
                                    break
                            if normal.length > 0.0001:
                                break
                        if normal.length > 0.0001:
                            break
                
                if normal.length < 0.0001:
                    # 所有点共线，按距离排序
                    return points, vert_refs_list
                
                normal = normal.normalized()
                
                # 建立局部坐标系
                # 选择一个不平行于法线的向量
                if abs(normal.z) < 0.9:
                    up = Vector((0, 0, 1))
                else:
                    up = Vector((1, 0, 0))
                
                local_x = up.cross(normal).normalized()
                local_y = normal.cross(local_x).normalized()
                
                # 计算每个点相对于中心的角度
                def get_angle(p):
                    rel = p - center
                    x = rel.dot(local_x)
                    y = rel.dot(local_y)
                    return math.atan2(y, x)
                
                # 创建 (角度, 索引) 列表并排序
                indexed = [(get_angle(p), i) for i, p in enumerate(points)]
                indexed.sort(key=lambda x: x[0])
                
                # 按排序后的顺序重建列表
                sorted_points = [points[i] for _, i in indexed]
                sorted_refs = [vert_refs_list[i] for _, i in indexed]
                
                return sorted_points, sorted_refs
            
            # 对3+个点进行排序
            if len(vertices_world) >= 3:
                vertices_world, vert_refs = sort_points_convex(vertices_world, vert_refs)
            
            # ========== 2个点：计算线段与坐标轴的夹角 ==========
            if len(vert_refs) == 2:
                # 注册标注（存储对象引用）
                register_annotation("__line_angles__", "line_angles", {
                    'vert_refs': vert_refs,
                })
                
                # 确保绘制处理器已启用
                ensure_draw_handler_enabled()
                
                # 刷新视图
                for area in bpy.context.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()
                
                # 计算并输出角度信息
                if len(vertices_world) == 2:
                    p1, p2 = vertices_world[0], vertices_world[1]
                    direction = (p2 - p1).normalized()
                    
                    x_axis = Vector((1, 0, 0))
                    y_axis = Vector((0, 1, 0))
                    z_axis = Vector((0, 0, 1))
                    
                    def angle_with_axis(dir_vec, axis):
                        dot = abs(dir_vec.dot(axis))
                        dot = max(-1.0, min(1.0, dot))
                        return math.degrees(math.acos(dot))
                    
                    angle_x = angle_with_axis(direction, x_axis)
                    angle_y = angle_with_axis(direction, y_axis)
                    angle_z = angle_with_axis(direction, z_axis)
                    
                    horizontal = Vector((direction.x, direction.y, 0))
                    if horizontal.length > 0.0001:
                        horizontal = horizontal.normalized()
                        dot = direction.dot(horizontal)
                        dot = max(-1.0, min(1.0, dot))
                        angle_horizontal = math.degrees(math.acos(dot))
                    else:
                        angle_horizontal = 90.0
                    
                    print(f"\n========== 角度测量（线段与轴夹角）==========")
                    print(f"  与X轴夹角: {angle_x:.6f}°")
                    print(f"  与Y轴夹角: {angle_y:.6f}°")
                    print(f"  与Z轴夹角: {angle_z:.6f}°")
                    print(f"  与水平面夹角: {angle_horizontal:.6f}°")
                    print("  💡 标注跟随物体移动")
                    print("==============================\n")
                    
                    self.report({'INFO'}, f"线段角度: X={angle_x:.1f}°, Y={angle_y:.1f}°, Z={angle_z:.1f}°, 水平={angle_horizontal:.1f}°")
                
                return {'FINISHED'}
            
            # ========== 3+个点：计算每个顶点处的角度 ==========
            # 注册标注（存储对象引用）
            register_annotation("__vertex_angles__", "vertex_angles", {
                'vert_refs': vert_refs,
            })
            
            # 确保绘制处理器已启用
            ensure_draw_handler_enabled()
            
            # 刷新视图
            for area in bpy.context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
            
            # 计算并输出角度信息
            def calc_angle_at_vertex(p1, vertex, p2):
                v1 = (p1 - vertex).normalized()
                v2 = (p2 - vertex).normalized()
                dot = max(-1.0, min(1.0, v1.dot(v2)))
                return math.degrees(math.acos(dot))
            
            n = len(vertices_world)
            angles = []
            # 对于3+个点，始终当作闭合多边形处理（凸包排序后形成闭环）
            is_closed = True
            
            for i in range(n):
                p_prev = vertices_world[(i - 1) % n]
                p_curr = vertices_world[i]
                p_next = vertices_world[(i + 1) % n]
                angle = calc_angle_at_vertex(p_prev, p_curr, p_next)
                angles.append(angle)
            
            valid_angles = angles  # 所有角度都有效
            print(f"\n========== 角度测量（顶点角度）==========")
            for i, angle in enumerate(angles):
                print(f"  顶点 {i+1}: {angle:.6f}°")
            print(f"  ─────────────────────")
            print(f"  角度总和: {sum(valid_angles):.6f}°")
            print(f"  顶点数: {n}，闭合多边形")
            print("  💡 标注跟随物体移动")
            print("==============================\n")
            
            angle_str = ", ".join([f"{a:.1f}°" for a in valid_angles])
            self.report({'INFO'}, f"顶点角度: {angle_str}（共{len(valid_angles)}个角）")
            return {'FINISHED'}
        
        # ========== 半径/直径模式特殊处理 ==========
        if self.measure_mode == 'RADIUS':
            # 收集选中元素的中心点（世界坐标）
            # 顶点模式：直接用顶点坐标
            # 边模式：用边的中点
            # 面模式：用面的中心点，或单个面的顶点拟合圆
            center_points = []
            all_points = []  # 用于3+点拟合圆
            single_face_mode = False  # 标记是否是单个面模式
            
            for obj in edit_objects:
                bm_read = bmesh.from_edit_mesh(obj.data)
                bm_read.verts.ensure_lookup_table()
                bm_read.edges.ensure_lookup_table()
                bm_read.faces.ensure_lookup_table()
                
                if select_mode[2]:  # 面模式：用面的中心点
                    for f in bm_read.faces:
                        if f.select:
                            center_local = f.calc_center_median()
                            center_world = obj.matrix_world @ center_local
                            center_points.append(center_world.copy())
                            # 同时收集所有顶点用于拟合
                            for v in f.verts:
                                world_co = obj.matrix_world @ v.co
                                all_points.append(world_co.copy())
                elif select_mode[1]:  # 边模式：用边的中点
                    for e in bm_read.edges:
                        if e.select:
                            v1_world = obj.matrix_world @ e.verts[0].co
                            v2_world = obj.matrix_world @ e.verts[1].co
                            mid_world = (v1_world + v2_world) / 2
                            center_points.append(mid_world.copy())
                            all_points.append(v1_world.copy())
                            all_points.append(v2_world.copy())
                else:  # 顶点模式：直接用顶点
                    for v in bm_read.verts:
                        if v.select:
                            world_co = obj.matrix_world @ v.co
                            center_points.append(world_co.copy())
                            all_points.append(world_co.copy())
            
            # 【新增】单个面模式：如果只选中了1个面，且该面有3个以上顶点，直接用顶点拟合圆
            if len(center_points) == 1 and select_mode[2] and len(all_points) >= 3:
                single_face_mode = True
                # 去重
                unique_points = []
                for p in all_points:
                    is_duplicate = False
                    for up in unique_points:
                        if (p - up).length < 0.0001:
                            is_duplicate = True
                            break
                    if not is_duplicate:
                        unique_points.append(p)
                
                if len(unique_points) >= 3:
                    # 拟合圆
                    center, radius, fit_error = self.fit_circle_3d(unique_points)
                    
                    if center is None:
                        self.report({'WARNING'}, "无法拟合圆，点可能共线")
                        return {'CANCELLED'}
                    
                    diameter = radius * 2
                    
                    # 创建独立的测量对象
                    if self.create_geometry:
                        bpy.ops.object.mode_set(mode='OBJECT')
                        
                        obj_name = get_unique_measure_name("测量_半径")
                        mesh = bpy.data.meshes.new(obj_name)
                        measure_obj = bpy.data.objects.new(obj_name, mesh)
                        context.collection.objects.link(measure_obj)
                        
                        # 创建圆心和半径线
                        bm = bmesh.new()
                        v_center = bm.verts.new(center)
                        # 找到距离圆心最近的点作为半径线终点
                        nearest_point = min(unique_points, key=lambda p: abs((p - center).length - radius))
                        v_nearest = bm.verts.new(nearest_point)
                        bm.verts.ensure_lookup_table()
                        bm.edges.new((v_center, v_nearest))
                        bm.to_mesh(mesh)
                        bm.free()
                        
                        # 注册标注
                        register_annotation(obj_name, "radius", {
                            'is_circle': True,
                            'center_vert_idx': 0,
                            'fit_error': fit_error,
                        })
                        
                        # 选中新创建的对象
                        bpy.ops.object.select_all(action='DESELECT')
                        measure_obj.select_set(True)
                        context.view_layer.objects.active = measure_obj
                    else:
                        # 不创建几何体，使用临时标注
                        register_annotation("__radius_temp__", "radius_temp", {
                            'center': center.copy(),
                            'radius': radius,
                            'diameter': diameter,
                            'is_circle': True,
                            'fit_error': fit_error,
                        })
                    
                    # 确保绘制处理器已启用
                    ensure_draw_handler_enabled()
                    
                    # 刷新视图
                    for area in context.screen.areas:
                        if area.type == 'VIEW_3D':
                            area.tag_redraw()
                    
                    # 输出信息
                    print(f"\n========== 半径/直径测量（单面拟合）==========")
                    print(f"  半径: {radius:.6f} m")
                    print(f"  直径: {diameter:.6f} m")
                    print(f"  圆心: ({center.x:.4f}, {center.y:.4f}, {center.z:.4f})")
                    print(f"  面顶点数: {len(unique_points)}")
                    print(f"  拟合误差: {fit_error:.6f}")
                    print("==============================\n")
                    
                    self.report({'INFO'}, f"半径: {radius:.6f} m，直径: {diameter:.6f} m（拟合误差: {fit_error:.4f}）")
                    return {'FINISHED'}
                else:
                    self.report({'WARNING'}, f"选中的面顶点数不足，需要至少3个不同的顶点")
                    return {'CANCELLED'}
            
            # 原有逻辑：需要至少2个元素
            if len(center_points) < 2:
                mode_name = "面" if select_mode[2] else ("边" if select_mode[1] else "顶点")
                self.report({'WARNING'}, f"半径/直径模式需要至少选中2个{mode_name}，或选中1个圆形面")
                return {'CANCELLED'}
            
            if len(center_points) == 2:
                # ========== 2个元素：计算距离的一半 ==========
                p1, p2 = center_points[0], center_points[1]
                diameter = (p2 - p1).length
                radius = diameter / 2
                center = (p1 + p2) / 2  # 中点
                
                # 【重要改进】创建独立的测量对象
                if self.create_geometry:
                    # 退出编辑模式
                    bpy.ops.object.mode_set(mode='OBJECT')
                    
                    obj_name = get_unique_measure_name("测量_半距")
                    mesh = bpy.data.meshes.new(obj_name)
                    measure_obj = bpy.data.objects.new(obj_name, mesh)
                    context.collection.objects.link(measure_obj)
                    
                    # 创建连线和中点标记
                    bm = bmesh.new()
                    v1 = bm.verts.new(p1)
                    v2 = bm.verts.new(p2)
                    v_center = bm.verts.new(center)
                    bm.verts.ensure_lookup_table()
                    bm.edges.new((v_center, v1))
                    bm.edges.new((v_center, v2))
                    bm.to_mesh(mesh)
                    bm.free()
                    
                    # 注册标注
                    register_annotation(obj_name, "radius", {
                        'is_circle': False,
                        'center_vert_idx': 2,  # 中点顶点索引
                    })
                    
                    # 选中新创建的对象
                    bpy.ops.object.select_all(action='DESELECT')
                    measure_obj.select_set(True)
                    context.view_layer.objects.active = measure_obj
                else:
                    # 不创建几何体，使用临时标注
                    register_annotation("__radius_temp__", "radius_temp", {
                        'center': center.copy(),
                        'radius': radius,
                        'diameter': diameter,
                        'is_circle': False,
                    })
                
                # 确保绘制处理器已启用
                ensure_draw_handler_enabled()
                
                # 刷新视图
                for area in context.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()
                
                # 输出信息
                mode_name = "面中心" if select_mode[2] else ("边中点" if select_mode[1] else "顶点")
                print(f"\n========== 半距/全距测量（{mode_name}）==========")
                print(f"  半距: {radius:.6f} m")
                print(f"  全距: {diameter:.6f} m")
                print(f"  中点: ({center.x:.4f}, {center.y:.4f}, {center.z:.4f})")
                print("==============================\n")
                
                self.report({'INFO'}, f"半距: {radius:.6f} m，全距: {diameter:.6f} m")
                return {'FINISHED'}
            
            else:
                # ========== 3+个元素：拟合圆 ==========
                # 去重
                unique_points = []
                for p in all_points:
                    is_duplicate = False
                    for up in unique_points:
                        if (p - up).length < 0.0001:
                            is_duplicate = True
                            break
                    if not is_duplicate:
                        unique_points.append(p)
                
                if len(unique_points) < 3:
                    self.report({'WARNING'}, f"拟合圆需要至少3个不同的点，当前只有{len(unique_points)}个")
                    return {'CANCELLED'}
                
                # 拟合圆
                center, radius, fit_error = self.fit_circle_3d(unique_points)
                
                if center is None:
                    self.report({'WARNING'}, "无法拟合圆，点可能共线")
                    return {'CANCELLED'}
                
                diameter = radius * 2
                
                # 【重要改进】创建独立的测量对象
                if self.create_geometry:
                    # 退出编辑模式
                    bpy.ops.object.mode_set(mode='OBJECT')
                    
                    obj_name = get_unique_measure_name("测量_半径")
                    mesh = bpy.data.meshes.new(obj_name)
                    measure_obj = bpy.data.objects.new(obj_name, mesh)
                    context.collection.objects.link(measure_obj)
                    
                    # 创建圆心和半径线
                    bm = bmesh.new()
                    v_center = bm.verts.new(center)
                    nearest_point = min(unique_points, key=lambda p: (p - center).length)
                    v_nearest = bm.verts.new(nearest_point)
                    bm.verts.ensure_lookup_table()
                    bm.edges.new((v_center, v_nearest))
                    bm.to_mesh(mesh)
                    bm.free()
                    
                    # 注册标注
                    register_annotation(obj_name, "radius", {
                        'is_circle': True,
                        'center_vert_idx': 0,
                        'fit_error': fit_error,
                    })
                    
                    # 选中新创建的对象
                    bpy.ops.object.select_all(action='DESELECT')
                    measure_obj.select_set(True)
                    context.view_layer.objects.active = measure_obj
                else:
                    # 不创建几何体，使用临时标注
                    register_annotation("__radius_temp__", "radius_temp", {
                        'center': center.copy(),
                        'radius': radius,
                        'diameter': diameter,
                        'is_circle': True,
                        'fit_error': fit_error,
                    })
                
                # 确保绘制处理器已启用
                ensure_draw_handler_enabled()
                
                # 刷新视图
                for area in context.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()
                
                # 输出信息
                print(f"\n========== 半径/直径测量（圆拟合）==========")
                print(f"  半径: {radius:.6f} m")
                print(f"  直径: {diameter:.6f} m")
                print(f"  圆心: ({center.x:.4f}, {center.y:.4f}, {center.z:.4f})")
                print(f"  拟合点数: {len(unique_points)}")
                print(f"  拟合误差: {fit_error:.6f}")
                print("==============================\n")
                
                self.report({'INFO'}, f"半径: {radius:.6f} m，直径: {diameter:.6f} m（拟合误差: {fit_error:.4f}）")
                return {'FINISHED'}
        
        if len(points_world) < 2:
            mode_name = "面" if select_mode[2] else ("边" if select_mode[1] else "顶点")
            self.report({'WARNING'}, f"请至少选中2个{mode_name}")
            return {'CANCELLED'}
        
        # ========== 智能检测：通用距离模式下检查2个顶点是否已连成边 ==========
        if self.measure_mode == 'CENTER_DISTANCE' and len(points_world) == 2 and not select_mode[2] and not select_mode[1]:
            # 只在顶点模式下检查
            # 检查这2个顶点是否已经被一条边连接
            existing_edge_found = False
            edge_length = 0.0
            edge_midpoint = None
            
            for obj in edit_objects:
                bm_check = bmesh.from_edit_mesh(obj.data)
                bm_check.verts.ensure_lookup_table()
                bm_check.edges.ensure_lookup_table()
                
                # 收集选中的顶点
                selected_verts = [v for v in bm_check.verts if v.select]
                
                if len(selected_verts) == 2:
                    v1, v2 = selected_verts
                    # 检查这两个顶点之间是否有边
                    for e in bm_check.edges:
                        if (e.verts[0] == v1 and e.verts[1] == v2) or (e.verts[0] == v2 and e.verts[1] == v1):
                            existing_edge_found = True
                            # 计算边长
                            v1_world = obj.matrix_world @ v1.co
                            v2_world = obj.matrix_world @ v2.co
                            edge_length = (v2_world - v1_world).length
                            edge_midpoint = (v1_world + v2_world) / 2
                            break
                
                if existing_edge_found:
                    break
            
            if existing_edge_found:
                # 两个顶点已经连成边，不创建新几何体，只显示标注
                register_annotation("__existing_edge__", "edge_length", {
                    'edges': [(edge_midpoint.copy(), edge_length, points_world[0].copy(), points_world[1].copy())],
                })
                
                # 确保绘制处理器已启用
                ensure_draw_handler_enabled()
                
                # 刷新视图
                for area in context.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()
                
                print(f"\n========== 距离测量（已有边）==========")
                print(f"  💡 检测到2个顶点已连成边，不创建新线")
                print(f"  边长: {edge_length:.6f} m")
                print("==============================\n")
                
                self.report({'INFO'}, f"边长: {edge_length:.6f} m（已有边，未创建新线）")
                return {'FINISHED'}
        
        # ========== 计算测量点的世界坐标（根据测量模式调整）==========
        # 注意：不再在原对象上创建几何体，直接计算世界坐标点
        
        final_points_world = []  # 最终用于创建独立对象的世界坐标点
        
        if self.measure_mode == 'XYZ_SPLIT' and len(points_world) == 2:
            # 分轴测量模式
            p1, p2 = points_world[0], points_world[1]
            dx, dy, dz = abs(p2.x - p1.x), abs(p2.y - p1.y), abs(p2.z - p1.z)
            threshold = 0.0001
            
            if dx < threshold and dy < threshold and dz < threshold:
                self.report({'WARNING'}, "两点的XYZ坐标完全相等，无法测量距离")
                return {'CANCELLED'}
            
            # 构建路径点
            final_points_world = [p1.copy()]
            current = p1.copy()
            if dx > threshold:
                current = Vector((p2.x, current.y, current.z))
                final_points_world.append(current.copy())
            if dy > threshold:
                current = Vector((current.x, p2.y, current.z))
                final_points_world.append(current.copy())
            if dz > threshold:
                current = Vector((current.x, current.y, p2.z))
                final_points_world.append(current.copy())
        else:
            # 直线距离模式或其他：使用原始坐标
            final_points_world = [p.copy() for p in points_world]
        
        # 计算距离
        distances = []
        total_distance = 0.0
        for i in range(len(final_points_world) - 1):
            dist = (final_points_world[i + 1] - final_points_world[i]).length
            distances.append(dist)
            total_distance += dist
        
        edge_count = len(final_points_world) - 1
        
        # ========== 创建独立的测量对象（不在原对象上创建任何几何体）==========
        if self.create_geometry:
            # 退出编辑模式
            bpy.ops.object.mode_set(mode='OBJECT')
            
            # 创建独立的测量对象
            measure_types_name = {'X_AXIS': 'X轴', 'Y_AXIS': 'Y轴', 'Z_AXIS': 'Z轴', 'XYZ_SPLIT': '分轴', 'CENTER_DISTANCE': '距离'}
            base_name = f"测量_{measure_types_name.get(self.measure_mode, '距离')}"
            obj_name = get_unique_measure_name(base_name)
            
            mesh = bpy.data.meshes.new(obj_name)
            measure_obj = bpy.data.objects.new(obj_name, mesh)
            context.collection.objects.link(measure_obj)
            
            # 创建顶点和边
            bm_new = bmesh.new()
            new_verts_list = []
            for pt in final_points_world:
                v = bm_new.verts.new(pt)
                new_verts_list.append(v)
            bm_new.verts.ensure_lookup_table()
            
            for i in range(len(new_verts_list) - 1):
                bm_new.edges.new((new_verts_list[i], new_verts_list[i + 1]))
            
            bm_new.to_mesh(mesh)
            bm_new.free()
            
            # 注册标注
            register_annotation(obj_name, "distance", {
                'measure_mode': self.measure_mode,
                'edge_indices': list(range(edge_count)),
            })
            
            # 选中新创建的对象
            bpy.ops.object.select_all(action='DESELECT')
            measure_obj.select_set(True)
            context.view_layer.objects.active = measure_obj
        else:
            # 不创建独立对象，使用临时标注
            register_annotation("__distance_temp__", "distance_temp", {
                'points': [p.copy() for p in final_points_world],
                'measure_mode': self.measure_mode,
            })
        
        # 确保绘制处理器已启用
        ensure_draw_handler_enabled()
        
        # 刷新视图
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        # 输出距离信息
        mode_name = "面中心" if select_mode[2] else ("边中点" if select_mode[1] else "顶点")
        measure_types = {'X_AXIS': 'X轴', 'Y_AXIS': 'Y轴', 'Z_AXIS': 'Z轴（垂直）', 'XYZ_SPLIT': '分轴XYZ', 'CENTER_DISTANCE': '通用'}
        measure_type = measure_types.get(self.measure_mode, '通用')
        self.report_distances(distances, total_distance, len(final_points_world), f"{mode_name}（{measure_type}）")
        return {'FINISHED'}
    
    def report_distances(self, distances, total_distance, point_count, mode_name="顶点"):
        """输出距离测量结果"""
        # 打印详细信息到控制台
        print(f"\n========== 距离测量（{mode_name}）==========")
        for i, dist in enumerate(distances):
            print(f"  线段 {i+1}: {dist:.6f} m")
        print(f"  ─────────────────────")
        print(f"  总长度: {total_distance:.6f} m")
        print(f"  {mode_name}数: {point_count}")
        print("==============================\n")
        
        # 在状态栏显示简要信息
        if len(distances) == 1:
            self.report({'INFO'}, f"已连接 {point_count} 个{mode_name}，距离: {total_distance:.6f} m")
        else:
            self.report({'INFO'}, f"已连接 {point_count} 个{mode_name}，总长度: {total_distance:.6f} m（{len(distances)} 段）")
    
    def execute_object_mode(self, context):
        """物体模式：在选中对象的原点位置创建新网格并连接"""
        selected = [obj for obj in context.selected_objects]
        if len(selected) < 2:
            self.report({'WARNING'}, "请至少选中2个对象")
            return {'CANCELLED'}
        
        # 获取所有选中对象的世界坐标原点
        origins = []
        for obj in selected:
            origins.append(obj.matrix_world.translation.copy())
        
        # 创建新的网格和对象
        mesh = bpy.data.meshes.new("原点连线")
        obj = bpy.data.objects.new("原点连线", mesh)
        
        # 链接到当前集合
        context.collection.objects.link(obj)
        
        # 使用 bmesh 创建顶点和边
        bm = bmesh.new()
        
        # 根据测量模式创建顶点
        verts = []
        if self.measure_mode == 'XYZ_SPLIT':
            # ========== 分轴测量模式（XYZ）==========
            #
            # 功能说明：
            #   同时测量X、Y、Z三个方向的距离，自动跳过无差异的轴
            #   创建一个"阶梯形"的路径，分别显示各轴的分量
            #
            # 线段特点：
            #   - 最多创建3条线段（X、Y、Z各一条）
            #   - 如果某轴的差值接近0（小于0.0001），则跳过该轴
            #   - 线段按 X → Y → Z 的顺序连接
            #   - 如果所有轴都相等，提示用户并取消操作
            
            if len(origins) == 2:
                p1 = origins[0]
                p2 = origins[1]
                
                # 计算各轴的差值
                dx = abs(p2.x - p1.x)
                dy = abs(p2.y - p1.y)
                dz = abs(p2.z - p1.z)
                
                # 阈值：小于此值认为无差异
                threshold = 0.0001
                
                # 检查是否所有轴都相等
                if dx < threshold and dy < threshold and dz < threshold:
                    # 清理已创建的对象
                    bpy.data.objects.remove(obj, do_unlink=True)
                    bpy.data.meshes.remove(mesh)
                    self.report({'WARNING'}, "两点的XYZ坐标完全相等，无法测量距离")
                    return {'CANCELLED'}
                
                # 构建路径点：从p1出发，依次沿X、Y、Z方向移动到p2
                path_points = [p1.copy()]
                current = p1.copy()
                
                # X轴移动
                if dx > threshold:
                    current = Vector((p2.x, current.y, current.z))
                    path_points.append(current.copy())
                
                # Y轴移动
                if dy > threshold:
                    current = Vector((current.x, p2.y, current.z))
                    path_points.append(current.copy())
                
                # Z轴移动
                if dz > threshold:
                    current = Vector((current.x, current.y, p2.z))
                    path_points.append(current.copy())
                
                # 创建顶点
                for pt in path_points:
                    v = bm.verts.new(pt)
                    verts.append(v)
                
                # 更新origins用于后续距离计算
                origins = path_points
            else:
                # 多个点：使用直线距离模式
                for origin in origins:
                    v = bm.verts.new(origin)
                    verts.append(v)
        elif self.measure_mode == 'CENTER_DISTANCE':
            # ========== 通用距离模式（物体模式）==========
            # 使用物体原点作为圆心，根据轴锁定设置计算距离
            if len(origins) != 2:
                bpy.data.objects.remove(obj, do_unlink=True)
                bpy.data.meshes.remove(mesh)
                self.report({'WARNING'}, "通用距离模式需要选中2个对象")
                return {'CANCELLED'}
            
            # 检查是否锁定了全部3个轴
            if self.lock_x and self.lock_y and self.lock_z:
                bpy.data.objects.remove(obj, do_unlink=True)
                bpy.data.meshes.remove(mesh)
                self.report({'ERROR'}, "不能同时锁定全部3个轴")
                return {'CANCELLED'}
            
            p1, p2 = origins[0], origins[1]
            
            # 应用偏移量
            offset = Vector((self.center_offset_x, self.center_offset_y, self.center_offset_z))
            p2_offset = p2 + offset
            
            # 根据轴锁定设置计算距离和显示点
            display_p1, display_p2 = self.get_display_points(p1, p2_offset)
            distance = self.calc_distance(p1, p2_offset)
            axis_info = self.get_axis_lock_info()
            
            # 创建连线
            v1 = bm.verts.new(display_p1)
            v2 = bm.verts.new(display_p2)
            verts = [v1, v2]
            bm.verts.ensure_lookup_table()
            bm.edges.new((v1, v2))
            bm.to_mesh(mesh)
            bm.free()
            
            # 使用唯一名称
            base_name = "测量_通用距离"
            obj.name = get_unique_measure_name(base_name)
            mesh.name = obj.name
            
            # 取消选中所有对象，选中新创建的对象
            for o in selected:
                o.select_set(False)
            obj.select_set(True)
            context.view_layer.objects.active = obj
            
            # 注册标注（存储计算好的距离值）
            register_annotation(obj.name, "distance", {
                'measure_mode': 'CENTER_DISTANCE',
                'edge_indices': [0],
                'distance': distance,
            })
            
            # 确保绘制处理器已启用
            ensure_draw_handler_enabled()
            
            # 刷新视图
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
            
            # 输出信息
            print(f"\n========== 通用距离测量（物体模式）==========")
            print(f"  距离: {distance:.6f} m（{axis_info}）")
            if offset.length > 0.0001:
                print(f"  偏移量: X={self.center_offset_x:.4f}, Y={self.center_offset_y:.4f}, Z={self.center_offset_z:.4f}")
            
            self.report({'INFO'}, f"距离: {distance:.6f} m（{axis_info}）")
            return {'FINISHED'}
        else:
            # 其他模式：使用原始坐标
            for origin in origins:
                v = bm.verts.new(origin)
                verts.append(v)
        
        # 按顺序连接相邻顶点，并计算距离
        distances = []
        total_distance = 0.0
        edge_count = len(verts) - 1
        for i in range(edge_count):
            bm.edges.new((verts[i], verts[i + 1]))
            dist = self.calc_distance(origins[i], origins[i + 1])
            distances.append(dist)
            total_distance += dist
        
        # 将 bmesh 写入网格
        bm.to_mesh(mesh)
        bm.free()
        
        # 【重要改进】使用唯一名称
        measure_types_name = {'XYZ_SPLIT': '分轴', 'CENTER_DISTANCE': '距离'}
        base_name = f"测量_{measure_types_name.get(self.measure_mode, '距离')}"
        obj.name = get_unique_measure_name(base_name)
        mesh.name = obj.name
        
        # 取消选中所有对象，选中新创建的对象
        for o in selected:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        
        # 注册标注到统一系统
        register_annotation(obj.name, "distance", {
            'measure_mode': self.measure_mode,
            'edge_indices': list(range(edge_count)),
        })
        
        # 确保绘制处理器已启用
        ensure_draw_handler_enabled()
        
        # 刷新视图
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        # 输出距离信息
        measure_types = {'XYZ_SPLIT': '分轴XYZ', 'CENTER_DISTANCE': '通用'}
        measure_type = measure_types.get(self.measure_mode, '通用')
        self.report_distances(distances, total_distance, len(origins), f"原点（{measure_type}）")
        return {'FINISHED'}


# ==================== 统一绘制系统 ====================

def ensure_draw_handler_enabled():
    """确保统一绘制处理器已启用"""
    global _unified_draw_handler
    
    if _unified_draw_handler is None:
        _unified_draw_handler = bpy.types.SpaceView3D.draw_handler_add(
            unified_draw_callback, (), 'WINDOW', 'POST_PIXEL'
        )


def disable_draw_handler():
    """禁用统一绘制处理器"""
    global _unified_draw_handler
    
    if _unified_draw_handler is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_unified_draw_handler, 'WINDOW')
            print("[标注系统] 绘制处理器已移除")
        except Exception as e:
            # ✅ 记录错误而不是吞掉，便于调试
            print(f"⚠️ 移除绘制处理器失败: {e}")
        finally:
            # ✅ 无论成功失败都重置变量
            _unified_draw_handler = None


def unified_draw_callback():
    """统一的标注绘制回调函数"""
    global _annotation_registry, _annotations_visible
    
    if not _annotations_visible:
        return
    
    # ✅ 节流：每 5 秒清理一次，而不是每帧清理
    if not hasattr(unified_draw_callback, '_last_cleanup_time'):
        unified_draw_callback._last_cleanup_time = 0
    
    current_time = time.time()
    if current_time - unified_draw_callback._last_cleanup_time > 5.0:
        cleanup_deleted_objects()
        unified_draw_callback._last_cleanup_time = current_time
    
    context = bpy.context
    region = context.region
    rv3d = context.region_data
    
    if not region or not rv3d:
        return
    
    # ✅ 创建副本遍历，因为 cleanup_deleted_objects() 可能修改字典
    # 遍历所有注册的标注
    for obj_name, data in list(_annotation_registry.items()):
        if not data.get('visible', True):
            continue
        
        annotation_type = data.get('type', '')
        
        # 根据标注类型调用不同的绘制函数
        if annotation_type == 'distance':
            draw_distance_annotation(obj_name, data, region, rv3d)
        elif annotation_type == 'distance_temp':
            draw_distance_temp_annotation(data, region, rv3d)
        elif annotation_type == 'angle':
            draw_angle_annotation(obj_name, data, region, rv3d)
        elif annotation_type == 'angle_temp':
            draw_angle_temp_annotation(data, region, rv3d)
        elif annotation_type == 'edge_angle':
            draw_edge_angle_annotation(data, region, rv3d)
        elif annotation_type == 'edge_length':
            draw_edge_length_annotation(data, region, rv3d)
        elif annotation_type == 'vertex_angles':
            draw_vertex_angles_annotation(data, region, rv3d)
        elif annotation_type == 'line_angles':
            draw_line_angles_annotation(data, region, rv3d)
        elif annotation_type == 'radius':
            draw_radius_annotation(obj_name, data, region, rv3d)
        elif annotation_type == 'radius_temp':
            draw_radius_temp_annotation(data, region, rv3d)


def draw_distance_annotation(obj_name, data, region, rv3d):
    """绘制距离标注（绑定到对象，实时跟随）"""
    obj = bpy.data.objects.get(obj_name)
    if not obj or obj.type != 'MESH':
        return
    
    mesh = obj.data
    edge_indices = data.get('edge_indices', [])
    measure_mode = data.get('measure_mode', 'CENTER_DISTANCE')
    
    font_id = 0
    blf.size(font_id, 28)
    
    # 圆心距离模式：使用存储的距离值
    if measure_mode == 'CENTER_DISTANCE':
        stored_distance = data.get('distance')
        if stored_distance is not None and len(mesh.edges) > 0:
            # 获取第一条边的中点位置用于显示标注
            edge = mesh.edges[0]
            v1_local = mesh.vertices[edge.vertices[0]].co
            v2_local = mesh.vertices[edge.vertices[1]].co
            v1_world = obj.matrix_world @ v1_local
            v2_world = obj.matrix_world @ v2_local
            mid_point = (v1_world + v2_world) / 2
            
            screen_pos = location_3d_to_region_2d(region, rv3d, mid_point)
            if screen_pos:
                draw_distance_label(font_id, screen_pos, stored_distance)
        return
    
    # 普通距离模式
    for edge_idx in edge_indices:
        if not isinstance(edge_idx, int) or edge_idx >= len(mesh.edges):
            continue
        
        edge = mesh.edges[edge_idx]
        v1_idx, v2_idx = edge.vertices
        
        # 获取顶点的世界坐标（实时计算）
        v1_local = mesh.vertices[v1_idx].co
        v2_local = mesh.vertices[v2_idx].co
        v1_world = obj.matrix_world @ v1_local
        v2_world = obj.matrix_world @ v2_local
        
        # 计算距离
        distance = (v2_world - v1_world).length
        
        # 计算线段中点的世界坐标
        mid_point = (v1_world + v2_world) / 2
        
        # 将3D坐标转换为2D屏幕坐标
        screen_pos = location_3d_to_region_2d(region, rv3d, mid_point)
        
        if screen_pos is None:
            continue
        
        draw_distance_label(font_id, screen_pos, distance)


def draw_distance_temp_annotation(data, region, rv3d):
    """绘制临时距离标注（不绑定对象）"""
    points = data.get('points', [])
    if len(points) < 2:
        return
    
    font_id = 0
    blf.size(font_id, 28)
    
    # 如果有存储的距离值（圆心距离模式），使用存储的值
    stored_distance = data.get('distance')
    if stored_distance is not None:
        p1 = points[0]
        p2 = points[1]
        mid_point = (p1 + p2) / 2
        screen_pos = location_3d_to_region_2d(region, rv3d, mid_point)
        if screen_pos:
            draw_distance_label(font_id, screen_pos, stored_distance)
        return
    
    # 普通模式：计算实际距离
    for i in range(len(points) - 1):
        p1 = points[i]
        p2 = points[i + 1]
        distance = (p2 - p1).length
        mid_point = (p1 + p2) / 2
        
        screen_pos = location_3d_to_region_2d(region, rv3d, mid_point)
        if screen_pos:
            draw_distance_label(font_id, screen_pos, distance)


def draw_angle_annotation(obj_name, data, region, rv3d):
    """绘制角度标注（绑定到对象）"""
    obj = bpy.data.objects.get(obj_name)
    if not obj or obj.type != 'MESH':
        return
    
    mesh = obj.data
    edge_indices = data.get('edge_indices', [0])
    angle_deg = data.get('angle', 0)
    bend_angle = data.get('bend', 0)
    
    if len(edge_indices) == 0 or edge_indices[0] >= len(mesh.edges):
        return
    
    edge = mesh.edges[edge_indices[0]]
    v1_world = obj.matrix_world @ mesh.vertices[edge.vertices[0]].co
    v2_world = obj.matrix_world @ mesh.vertices[edge.vertices[1]].co
    
    mid_point = (v1_world + v2_world) / 2
    screen_pos = location_3d_to_region_2d(region, rv3d, mid_point)
    
    if screen_pos:
        draw_angle_label(screen_pos, angle_deg, bend_angle)


def draw_angle_temp_annotation(data, region, rv3d):
    """绘制临时角度标注"""
    center = data.get('center')
    angle_deg = data.get('angle', 0)
    bend_angle = data.get('bend', 0)
    
    if center is None:
        return
    
    screen_pos = location_3d_to_region_2d(region, rv3d, center)
    if screen_pos:
        draw_angle_label(screen_pos, angle_deg, bend_angle)


def draw_edge_angle_annotation(data, region, rv3d):
    """绘制两边夹角标注（实时刷新版，支持编辑模式）"""
    edge_refs = data.get('edge_refs', [])
    
    # 优先使用实时计算（从存储的边引用获取最新坐标）
    if len(edge_refs) == 2:
        obj_name1, v1_idx1, v2_idx1 = edge_refs[0]
        obj_name2, v1_idx2, v2_idx2 = edge_refs[1]
        
        v1_1, v2_1 = get_edge_world_coords_realtime(obj_name1, v1_idx1, v2_idx1)
        v1_2, v2_2 = get_edge_world_coords_realtime(obj_name2, v1_idx2, v2_idx2)
        
        if v1_1 is None or v2_1 is None or v1_2 is None or v2_2 is None:
            return
        
        # 实时计算方向和中点
        dir1 = (v2_1 - v1_1).normalized()
        dir2 = (v2_2 - v1_2).normalized()
        mid1 = (v1_1 + v2_1) / 2
        mid2 = (v1_2 + v2_2) / 2
        
        # 实时计算夹角
        dot_product = dir1.dot(dir2)
        dot_product = max(-1.0, min(1.0, dot_product))
        angle_rad = math.acos(abs(dot_product))
        angle_deg = math.degrees(angle_rad)
        supplement = 180.0 - angle_deg
        
        # 中心点取两边中点的中点
        center = (mid1 + mid2) / 2
    else:
        # 回退到静态数据（兼容旧标注）
        center = data.get('center')
        angle_deg = data.get('angle', 0)
        supplement = data.get('supplement', 0)
        
        if center is None:
            return
    
    screen_pos = location_3d_to_region_2d(region, rv3d, center)
    if screen_pos is None:
        return
    
    font_id = 0
    blf.size(font_id, 28)
    
    # 格式化文本（两行：夹角和补角）
    text1 = f"夹角: {angle_deg:.2f}°"
    text2 = f"补角: {supplement:.2f}°"
    
    # 获取文本尺寸
    text1_width, _ = blf.dimensions(font_id, text1)
    text2_width, _ = blf.dimensions(font_id, text2)
    
    # 使用固定行高
    line_height = 35
    line_spacing = 15
    max_width = max(text1_width, text2_width)
    total_height = line_height * 2 + line_spacing
    
    # 绘制背景
    padding = 15
    bg_x = screen_pos[0] - max_width / 2 - padding
    bg_y = screen_pos[1] - total_height / 2 - padding
    bg_width = max_width + padding * 2
    bg_height = total_height + padding * 2
    
    vertices = (
        (bg_x, bg_y),
        (bg_x + bg_width, bg_y),
        (bg_x + bg_width, bg_y + bg_height),
        (bg_x, bg_y + bg_height),
    )
    indices = ((0, 1, 2), (2, 3, 0))
    
    gpu.state.blend_set('ALPHA')
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
    shader.bind()
    shader.uniform_float("color", (0.5, 0.3, 0.1, 0.5))  # 橙色背景（半透明）
    batch.draw(shader)
    gpu.state.blend_set('NONE')
    
    # 绘制第一行文本（夹角）- 上方
    y1 = screen_pos[1] + line_spacing / 2 + line_height / 2
    blf.position(font_id, screen_pos[0] - text1_width / 2, y1, 0)
    blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
    blf.draw(font_id, text1)
    
    # 绘制第二行文本（补角）- 下方，用黄色高亮
    y2 = screen_pos[1] - line_spacing / 2 - line_height / 2
    blf.position(font_id, screen_pos[0] - text2_width / 2, y2, 0)
    blf.color(font_id, 1.0, 0.9, 0.3, 1.0)  # 黄色
    blf.draw(font_id, text2)


def draw_edge_length_annotation(data, region, rv3d):
    """绘制边长标注（实时刷新版，支持编辑模式）"""
    edge_data = data.get('edge_data', [])
    
    if not edge_data:
        return
    
    font_id = 0
    blf.size(font_id, 26)
    
    for obj_name, edge_idx, v1_idx, v2_idx in edge_data:
        # 使用实时数据获取函数（支持编辑模式）
        v1_world, v2_world = get_edge_world_coords_realtime(obj_name, v1_idx, v2_idx)
        if v1_world is None or v2_world is None:
            continue
        
        mid_point = (v1_world + v2_world) / 2
        length = (v2_world - v1_world).length
        
        screen_pos = location_3d_to_region_2d(region, rv3d, mid_point)
        if screen_pos is None:
            continue
        
        # 格式化文本
        text = f"{length:.4f} m"
        text_width, _ = blf.dimensions(font_id, text)
        
        # 绘制背景（青色半透明）
        padding = 10
        line_height = 30
        bg_x = screen_pos[0] - text_width / 2 - padding
        bg_y = screen_pos[1] - line_height / 2 - padding
        bg_width = text_width + padding * 2
        bg_height = line_height + padding * 2
        
        vertices = (
            (bg_x, bg_y),
            (bg_x + bg_width, bg_y),
            (bg_x + bg_width, bg_y + bg_height),
            (bg_x, bg_y + bg_height),
        )
        indices = ((0, 1, 2), (2, 3, 0))
        
        gpu.state.blend_set('ALPHA')
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
        shader.bind()
        shader.uniform_float("color", (0.1, 0.4, 0.5, 0.5))  # 青色背景（半透明）
        batch.draw(shader)
        gpu.state.blend_set('NONE')
        
        # 绘制文本
        blf.position(font_id, screen_pos[0] - text_width / 2, screen_pos[1] - line_height / 4, 0)
        blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
        blf.draw(font_id, text)


def draw_vertex_angles_annotation(data, region, rv3d):
    """绘制顶点角度标注（实时刷新版，支持编辑模式）"""
    vert_refs = data.get('vert_refs', [])
    
    if len(vert_refs) < 3:
        return
    
    # 使用实时数据获取函数（支持编辑模式）
    vertices_world = [get_vertex_world_coord_realtime(name, idx) for name, idx in vert_refs]
    vertices_world = [v for v in vertices_world if v is not None]
    
    if len(vertices_world) < 3:
        return
    
    # ========== 对点进行凸包排序 ==========
    def sort_points_convex_draw(points):
        """对共面的点按凸包顺序排序（逆时针）"""
        if len(points) < 3:
            return points, list(range(len(points)))
        
        # 计算中心点
        center = Vector((0, 0, 0))
        for p in points:
            center += p
        center /= len(points)
        
        # 计算平面法线
        v1 = points[1] - points[0]
        v2 = points[2] - points[0]
        normal = v1.cross(v2)
        if normal.length < 0.0001:
            for i in range(len(points)):
                for j in range(i+1, len(points)):
                    for k in range(j+1, len(points)):
                        v1 = points[j] - points[i]
                        v2 = points[k] - points[i]
                        normal = v1.cross(v2)
                        if normal.length > 0.0001:
                            break
                    if normal.length > 0.0001:
                        break
                if normal.length > 0.0001:
                    break
        
        if normal.length < 0.0001:
            return points, list(range(len(points)))
        
        normal = normal.normalized()
        
        if abs(normal.z) < 0.9:
            up = Vector((0, 0, 1))
        else:
            up = Vector((1, 0, 0))
        
        local_x = up.cross(normal).normalized()
        local_y = normal.cross(local_x).normalized()
        
        def get_angle(p):
            rel = p - center
            x = rel.dot(local_x)
            y = rel.dot(local_y)
            return math.atan2(y, x)
        
        indexed = [(get_angle(p), i) for i, p in enumerate(points)]
        indexed.sort(key=lambda x: x[0])
        
        sorted_points = [points[i] for _, i in indexed]
        sorted_indices = [i for _, i in indexed]
        
        return sorted_points, sorted_indices
    
    # 排序顶点
    vertices_world, sort_order = sort_points_convex_draw(vertices_world)
    
    # 计算角度
    def calc_angle_at_vertex(p1, vertex, p2):
        v1 = (p1 - vertex).normalized()
        v2 = (p2 - vertex).normalized()
        dot = max(-1.0, min(1.0, v1.dot(v2)))
        return math.degrees(math.acos(dot))
    
    n = len(vertices_world)
    # 对于3+个点，始终当作闭合多边形处理（凸包排序后形成闭环）
    is_closed = True  # 强制闪环，因为我们已经做了凸包排序
    
    angles = []
    for i in range(n):
        p_prev = vertices_world[(i - 1) % n]
        p_curr = vertices_world[i]
        p_next = vertices_world[(i + 1) % n]
        angle = calc_angle_at_vertex(p_prev, p_curr, p_next)
        angles.append(angle)
    
    font_id = 0
    blf.size(font_id, 24)
    
    for i, (point, angle) in enumerate(zip(vertices_world, angles)):
        if angle is None:
            continue
            
        screen_pos = location_3d_to_region_2d(region, rv3d, point)
        if screen_pos is None:
            continue
        
        screen_pos = (screen_pos[0] + 20, screen_pos[1] + 20)
        
        text = f"{i+1}: {angle:.2f}°"
        text_width, _ = blf.dimensions(font_id, text)
        
        padding = 8
        line_height = 28
        bg_x = screen_pos[0] - padding
        bg_y = screen_pos[1] - padding
        bg_width = text_width + padding * 2
        bg_height = line_height + padding * 2
        
        vertices = (
            (bg_x, bg_y),
            (bg_x + bg_width, bg_y),
            (bg_x + bg_width, bg_y + bg_height),
            (bg_x, bg_y + bg_height),
        )
        indices = ((0, 1, 2), (2, 3, 0))
        
        gpu.state.blend_set('ALPHA')
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
        shader.bind()
        shader.uniform_float("color", (0.4, 0.2, 0.5, 0.5))
        batch.draw(shader)
        gpu.state.blend_set('NONE')
        
        blf.position(font_id, screen_pos[0], screen_pos[1], 0)
        blf.color(font_id, 1.0, 1.0, 0.5, 1.0)
        blf.draw(font_id, text)


def draw_line_angles_annotation(data, region, rv3d):
    """绘制线段与坐标轴夹角标注（实时刷新版，支持编辑模式）"""
    vert_refs = data.get('vert_refs', [])
    
    # 优先使用实时计算（从存储的顶点引用获取最新坐标）
    if len(vert_refs) == 2:
        p1 = get_vertex_world_coord_realtime(*vert_refs[0])
        p2 = get_vertex_world_coord_realtime(*vert_refs[1])
        
        if p1 is None or p2 is None:
            return
        
        # 实时计算方向和中心点
        direction = (p2 - p1).normalized()
        center = (p1 + p2) / 2
        
        x_axis = Vector((1, 0, 0))
        y_axis = Vector((0, 1, 0))
        z_axis = Vector((0, 0, 1))
        
        def angle_with_axis(dir_vec, axis):
            dot = abs(dir_vec.dot(axis))
            dot = max(-1.0, min(1.0, dot))
            return math.degrees(math.acos(dot))
        
        angle_x = angle_with_axis(direction, x_axis)
        angle_y = angle_with_axis(direction, y_axis)
        angle_z = angle_with_axis(direction, z_axis)
        
        # 与水平面夹角
        horizontal = Vector((direction.x, direction.y, 0))
        if horizontal.length > 0.0001:
            horizontal = horizontal.normalized()
            dot = direction.dot(horizontal)
            dot = max(-1.0, min(1.0, dot))
            angle_horizontal = math.degrees(math.acos(dot))
        else:
            angle_horizontal = 90.0
    else:
        # 回退到静态数据（兼容旧标注）
        center = data.get('center')
        angle_x = data.get('angle_x', 0)
        angle_y = data.get('angle_y', 0)
        angle_z = data.get('angle_z', 0)
        angle_horizontal = data.get('angle_horizontal', 0)
        
        if center is None:
            return
    
    screen_pos = location_3d_to_region_2d(region, rv3d, center)
    if screen_pos is None:
        return
    
    font_id = 0
    blf.size(font_id, 24)
    
    # 格式化文本（4行）
    lines = [
        f"X轴: {angle_x:.2f}°",
        f"Y轴: {angle_y:.2f}°",
        f"Z轴: {angle_z:.2f}°",
        f"水平: {angle_horizontal:.2f}°",
    ]
    
    # 计算最大宽度
    max_width = 0
    for line in lines:
        w, _ = blf.dimensions(font_id, line)
        max_width = max(max_width, w)
    
    line_height = 28
    line_spacing = 5
    total_height = line_height * len(lines) + line_spacing * (len(lines) - 1)
    
    # 绘制背景
    padding = 12
    bg_x = screen_pos[0] - max_width / 2 - padding
    bg_y = screen_pos[1] - total_height / 2 - padding
    bg_width = max_width + padding * 2
    bg_height = total_height + padding * 2
    
    vertices = (
        (bg_x, bg_y),
        (bg_x + bg_width, bg_y),
        (bg_x + bg_width, bg_y + bg_height),
        (bg_x, bg_y + bg_height),
    )
    indices = ((0, 1, 2), (2, 3, 0))
    
    gpu.state.blend_set('ALPHA')
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
    shader.bind()
    shader.uniform_float("color", (0.4, 0.2, 0.5, 0.5))  # 紫色背景（半透明）
    batch.draw(shader)
    gpu.state.blend_set('NONE')
    
    # 绘制文本（从上到下）
    y_start = screen_pos[1] + total_height / 2 - line_height / 2
    colors = [
        (1.0, 0.5, 0.5, 1.0),  # X轴 - 红色
        (0.5, 1.0, 0.5, 1.0),  # Y轴 - 绿色
        (0.5, 0.5, 1.0, 1.0),  # Z轴 - 蓝色
        (1.0, 1.0, 0.5, 1.0),  # 水平 - 黄色
    ]
    
    for i, (line, color) in enumerate(zip(lines, colors)):
        y = y_start - i * (line_height + line_spacing)
        w, _ = blf.dimensions(font_id, line)
        blf.position(font_id, screen_pos[0] - w / 2, y, 0)
        blf.color(font_id, *color)
        blf.draw(font_id, line)


def draw_radius_annotation(obj_name, data, region, rv3d):
    """绘制半径/直径标注（绑定到对象）"""
    obj = bpy.data.objects.get(obj_name)
    if not obj or obj.type != 'MESH':
        return
    
    mesh = obj.data
    center_vert_idx = data.get('center_vert_idx', 0)
    is_circle = data.get('is_circle', True)
    
    if center_vert_idx >= len(mesh.vertices):
        return
    
    # 获取中心点的世界坐标
    center_local = mesh.vertices[center_vert_idx].co
    center_world = obj.matrix_world @ center_local
    
    # 计算半径（从中心点到第一条边的另一端）
    if len(mesh.edges) > 0:
        edge = mesh.edges[0]
        other_vert_idx = edge.vertices[1] if edge.vertices[0] == center_vert_idx else edge.vertices[0]
        other_local = mesh.vertices[other_vert_idx].co
        other_world = obj.matrix_world @ other_local
        radius = (other_world - center_world).length
        diameter = radius * 2
    else:
        radius = 0
        diameter = 0
    
    screen_pos = location_3d_to_region_2d(region, rv3d, center_world)
    if screen_pos:
        draw_radius_label(screen_pos, radius, diameter, is_circle)


def draw_radius_temp_annotation(data, region, rv3d):
    """绘制临时半径/直径标注"""
    center = data.get('center')
    radius = data.get('radius', 0)
    diameter = data.get('diameter', 0)
    is_circle = data.get('is_circle', True)
    
    if center is None:
        return
    
    screen_pos = location_3d_to_region_2d(region, rv3d, center)
    if screen_pos:
        draw_radius_label(screen_pos, radius, diameter, is_circle)


def draw_distance_label(font_id, screen_pos, distance):
    """绘制单个距离标签"""
    # 格式化距离文本（6位小数）
    text = f"{distance:.6f} m"
    
    # 获取文本尺寸
    text_width, text_height = blf.dimensions(font_id, text)
    
    # 绘制背景（更大的padding）
    padding = 10
    bg_x = screen_pos[0] - text_width / 2 - padding
    bg_y = screen_pos[1] - text_height / 2 - padding
    bg_width = text_width + padding * 2
    bg_height = text_height + padding * 2
    
    # 使用GPU绘制背景矩形
    vertices = (
        (bg_x, bg_y),
        (bg_x + bg_width, bg_y),
        (bg_x + bg_width, bg_y + bg_height),
        (bg_x, bg_y + bg_height),
    )
    indices = ((0, 1, 2), (2, 3, 0))
    
    gpu.state.blend_set('ALPHA')
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
    shader.bind()
    shader.uniform_float("color", (0.2, 0.2, 0.2, 0.5))  # 深灰背景（半透明）
    batch.draw(shader)
    gpu.state.blend_set('NONE')
    
    # 绘制文本
    blf.position(font_id, screen_pos[0] - text_width / 2, screen_pos[1] - text_height / 2, 0)
    blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
    blf.draw(font_id, text)


def draw_angle_label(screen_pos, angle_deg, bend_angle):
    """绘制角度标签（显示法线夹角和弯曲角度）"""
    font_id = 0
    blf.size(font_id, 28)
    
    # 格式化文本（两行：法线夹角和弯曲角度）
    text1 = f"法线夹角: {angle_deg:.2f}°"
    text2 = f"弯曲角度: {bend_angle:.2f}°"
    
    # 获取文本尺寸
    text1_width, _ = blf.dimensions(font_id, text1)
    text2_width, _ = blf.dimensions(font_id, text2)
    
    # 使用固定行高（中文字体高度不准确）
    line_height = 35
    line_spacing = 15
    max_width = max(text1_width, text2_width)
    total_height = line_height * 2 + line_spacing
    
    # 绘制背景
    padding = 15
    bg_x = screen_pos[0] - max_width / 2 - padding
    bg_y = screen_pos[1] - total_height / 2 - padding
    bg_width = max_width + padding * 2
    bg_height = total_height + padding * 2
    
    vertices = (
        (bg_x, bg_y),
        (bg_x + bg_width, bg_y),
        (bg_x + bg_width, bg_y + bg_height),
        (bg_x, bg_y + bg_height),
    )
    indices = ((0, 1, 2), (2, 3, 0))
    
    gpu.state.blend_set('ALPHA')
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
    shader.bind()
    shader.uniform_float("color", (0.1, 0.3, 0.5, 0.5))  # 蓝色背景（半透明）
    batch.draw(shader)
    gpu.state.blend_set('NONE')
    
    # 绘制第一行文本（法线夹角）- 上方
    y1 = screen_pos[1] + line_spacing / 2 + line_height / 2
    blf.position(font_id, screen_pos[0] - text1_width / 2, y1, 0)
    blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
    blf.draw(font_id, text1)
    
    # 绘制第二行文本（弯曲角度）- 下方，用黄色高亮
    y2 = screen_pos[1] - line_spacing / 2 - line_height / 2
    blf.position(font_id, screen_pos[0] - text2_width / 2, y2, 0)
    blf.color(font_id, 1.0, 0.9, 0.3, 1.0)  # 黄色
    blf.draw(font_id, text2)


def draw_radius_label(screen_pos, radius, diameter, is_circle):
    """绘制半径/直径或半距/全距标签"""
    font_id = 0
    blf.size(font_id, 28)
    
    # 根据模式选择标签文字
    if is_circle:
        text1 = f"半径: {radius:.6f} m"
        text2 = f"直径: {diameter:.6f} m"
    else:
        text1 = f"半距: {radius:.6f} m"
        text2 = f"全距: {diameter:.6f} m"
    
    # 获取文本尺寸
    text1_width, _ = blf.dimensions(font_id, text1)
    text2_width, _ = blf.dimensions(font_id, text2)
    
    # 使用固定行高
    line_height = 35
    line_spacing = 15
    max_width = max(text1_width, text2_width)
    total_height = line_height * 2 + line_spacing
    
    # 绘制背景
    padding = 15
    bg_x = screen_pos[0] - max_width / 2 - padding
    bg_y = screen_pos[1] - total_height / 2 - padding
    bg_width = max_width + padding * 2
    bg_height = total_height + padding * 2
    
    vertices = (
        (bg_x, bg_y),
        (bg_x + bg_width, bg_y),
        (bg_x + bg_width, bg_y + bg_height),
        (bg_x, bg_y + bg_height),
    )
    indices = ((0, 1, 2), (2, 3, 0))
    
    gpu.state.blend_set('ALPHA')
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
    shader.bind()
    shader.uniform_float("color", (0.2, 0.5, 0.3, 0.5))  # 绿色背景（半透明）
    batch.draw(shader)
    gpu.state.blend_set('NONE')
    
    # 绘制第一行文本
    y1 = screen_pos[1] + line_spacing / 2 + line_height / 2
    blf.position(font_id, screen_pos[0] - text1_width / 2, y1, 0)
    blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
    blf.draw(font_id, text1)
    
    # 绘制第二行文本 - 用黄色高亮
    y2 = screen_pos[1] - line_spacing / 2 - line_height / 2
    blf.position(font_id, screen_pos[0] - text2_width / 2, y2, 0)
    blf.color(font_id, 1.0, 0.9, 0.3, 1.0)  # 黄色
    blf.draw(font_id, text2)


# ==================== 标注操作 Operators ====================

class OBJECT_OT_clear_distance_display(Operator):
    """清除3D视图中的所有标注"""
    bl_idname = "object.clear_distance_display"
    bl_label = "清除标注"
    bl_options = {"REGISTER"}

    def execute(self, context):
        # 使用新的统一标注系统清除所有标注
        clear_all_annotations()
        
        # 刷新视图
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        self.report({'INFO'}, "已清除所有标注")
        return {'FINISHED'}


class OBJECT_OT_toggle_annotations(Operator):
    """切换标注显示/隐藏"""
    bl_idname = "object.toggle_annotations"
    bl_label = "切换标注显示"
    bl_options = {"REGISTER"}

    def execute(self, context):
        visible = toggle_annotations_visibility()
        
        # 刷新视图
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        status = "显示" if visible else "隐藏"
        self.report({'INFO'}, f"标注已{status}")
        return {'FINISHED'}


class OBJECT_OT_batch_rename(Operator):
    """批量搜索替换选中对象的名称（支持正则表达式）- Ctrl+F"""
    bl_idname = "object.batch_rename_plus"
    bl_label = "名称批量替换"
    bl_options = {"REGISTER", "UNDO"}

    search_pattern: StringProperty(
        name="搜索",
        description="要搜索的文本或正则表达式",
        default="_镜像",
    )
    replace_text: StringProperty(
        name="替换为",
        description="替换后的文本（留空则删除匹配内容）",
        default="",
    )
    use_regex: BoolProperty(
        name="使用正则表达式",
        description="启用正则表达式匹配",
        default=False,
    )
    case_sensitive: BoolProperty(
        name="区分大小写",
        description="搜索时区分大小写",
        default=True,
    )
    handle_conflict: EnumProperty(
        name="名称冲突处理",
        description="当替换后的名称已存在时如何处理",
        items=[
            ("SKIP", "跳过", "跳过该对象，保持原名"),
            ("DELETE_OLD", "删除旧对象", "删除同名的旧对象"),
            ("ADD_SUFFIX", "添加后缀", "自动添加数字后缀"),
        ],
        default="DELETE_OLD",
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "search_pattern")
        layout.prop(self, "replace_text")
        layout.separator()
        layout.prop(self, "use_regex")
        layout.prop(self, "case_sensitive")
        layout.separator()
        layout.prop(self, "handle_conflict")
        layout.separator()
        # 预览
        selected = [o for o in context.selected_objects]
        if selected:
            box = layout.box()
            box.label(text=f"预览 (共 {len(selected)} 个对象):", icon='INFO')
            preview_count = min(5, len(selected))
            for i in range(preview_count):
                obj = selected[i]
                new_name = self._get_new_name(obj.name)
                if new_name != obj.name:
                    box.label(text=f"  {obj.name} → {new_name}")
                else:
                    box.label(text=f"  {obj.name} (无变化)")
            if len(selected) > 5:
                box.label(text=f"  ... 还有 {len(selected) - 5} 个对象")

    def _get_new_name(self, name):
        """根据设置计算新名称"""
        try:
            if self.use_regex:
                flags = 0 if self.case_sensitive else re.IGNORECASE
                return re.sub(self.search_pattern, self.replace_text, name, flags=flags)
            else:
                if self.case_sensitive:
                    return name.replace(self.search_pattern, self.replace_text)
                else:
                    # 不区分大小写的替换
                    pattern = re.escape(self.search_pattern)
                    return re.sub(pattern, self.replace_text, name, flags=re.IGNORECASE)
        except re.error:
            return name

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=400)

    def execute(self, context):
        selected = [o for o in context.selected_objects]
        if not selected:
            self.report({"WARNING"}, "未选中任何对象")
            return {"CANCELLED"}

        # 验证正则表达式
        if self.use_regex:
            try:
                re.compile(self.search_pattern)
            except re.error as e:
                self.report({"ERROR"}, f"正则表达式错误: {str(e)}")
                return {"CANCELLED"}

        renamed_count = 0
        skipped_count = 0
        deleted_count = 0

        for obj in selected:
            old_name = obj.name
            new_name = self._get_new_name(old_name)

            # 名称没有变化，跳过
            if new_name == old_name:
                continue

            # 检查是否存在同名对象
            existing_obj = bpy.data.objects.get(new_name)
            if existing_obj and existing_obj != obj:
                if self.handle_conflict == "SKIP":
                    skipped_count += 1
                    continue
                elif self.handle_conflict == "DELETE_OLD":
                    # 删除旧对象
                    bpy.data.objects.remove(existing_obj, do_unlink=True)
                    deleted_count += 1
                elif self.handle_conflict == "ADD_SUFFIX":
                    # 添加数字后缀
                    suffix = 1
                    base_name = new_name
                    while bpy.data.objects.get(new_name):
                        new_name = f"{base_name}.{suffix:03d}"
                        suffix += 1

            obj.name = new_name
            renamed_count += 1

        # 报告结果
        msg_parts = [f"已重命名 {renamed_count} 个对象"]
        if skipped_count > 0:
            msg_parts.append(f"跳过 {skipped_count} 个")
        if deleted_count > 0:
            msg_parts.append(f"删除旧对象 {deleted_count} 个")
        self.report({"INFO"}, "，".join(msg_parts))
        return {"FINISHED"}

# ==================== 批量材质管理功能 ====================

class MATERIAL_OT_apply_to_selected(Operator):
    """将选中的材质应用到所有选中的网格对象"""
    bl_idname = "material.apply_to_selected"
    bl_label = "批量应用材质"
    bl_options = {'REGISTER', 'UNDO'}

    new_material: StringProperty(
        name="新材质",
        description="要应用的新材质",
        default=""
    )
    replace_mode: EnumProperty(
        name="替换模式",
        items=[
            ("REPLACE_ALL", "全部替换", "清空对象所有材质，只保留新材质"),
            ("ADD", "追加材质", "保留现有材质，在末尾添加新材质"),
            ("REPLACE_SPECIFIC", "替换指定材质", "将指定的旧材质替换为新材质"),
        ],
        default="REPLACE_ALL"
    )
    old_material: StringProperty(
        name="旧材质",
        description="要被替换的旧材质（仅在'替换指定材质'模式下使用）",
        default=""
    )

    def draw(self, context):
        layout = self.layout
        
        # 替换模式
        layout.prop(self, "replace_mode")
        
        # 模式说明
        box = layout.box()
        if self.replace_mode == "REPLACE_ALL":
            box.label(text="说明: 删除对象上所有材质，只应用新材质", icon='INFO')
        elif self.replace_mode == "ADD":
            box.label(text="说明: 保留现有材质，在材质列表末尾添加新材质", icon='INFO')
        elif self.replace_mode == "REPLACE_SPECIFIC":
            box.label(text="说明: 找到旧材质并替换为新材质，其他材质不变", icon='INFO')
        
        layout.separator()
        
        # 如果是替换指定材质模式，显示旧材质选择
        if self.replace_mode == "REPLACE_SPECIFIC":
            # 收集选中对象的所有材质
            layout.label(text="选择要替换的旧材质:")
            layout.prop_search(self, "old_material", bpy.data, "materials", text="旧材质", icon='MATERIAL')
        
        # 新材质选择
        layout.label(text="选择新材质:")
        layout.prop_search(self, "new_material", bpy.data, "materials", text="新材质", icon='MATERIAL')
        
        layout.separator()
        selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        layout.label(text=f"将应用到 {len(selected_meshes)} 个网格对象", icon='OBJECT_DATA')
        
        # 显示选中对象的材质列表
        if selected_meshes and self.replace_mode == "REPLACE_SPECIFIC":
            box = layout.box()
            box.label(text="选中对象的材质:", icon='MATERIAL')
            materials_found = set()
            for obj in selected_meshes:
                for slot in obj.material_slots:
                    if slot.material:
                        materials_found.add(slot.material.name)
            if materials_found:
                for mat_name in sorted(materials_found):
                    box.label(text=f"  • {mat_name}")
            else:
                box.label(text="  (无材质)")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=400)

    def execute(self, context):
        selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not selected_meshes:
            self.report({'ERROR'}, "未选中任何网格对象")
            return {'CANCELLED'}
        if not self.new_material:
            self.report({'ERROR'}, "请选择新材质")
            return {'CANCELLED'}
        new_material = bpy.data.materials.get(self.new_material)
        if new_material is None:
            self.report({'ERROR'}, f"未找到新材质: {self.new_material}")
            return {'CANCELLED'}
        
        if self.replace_mode == "REPLACE_SPECIFIC" and not self.old_material:
            self.report({'ERROR'}, "请选择要替换的旧材质")
            return {'CANCELLED'}
        
        old_material = None
        if self.replace_mode == "REPLACE_SPECIFIC":
            old_material = bpy.data.materials.get(self.old_material)
            if old_material is None:
                self.report({'ERROR'}, f"未找到旧材质: {self.old_material}")
                return {'CANCELLED'}
        
        success_count = 0
        replaced_count = 0
        
        for obj in selected_meshes:
            try:
                if self.replace_mode == "REPLACE_ALL":
                    # 全部替换：清空所有材质，只保留新材质
                    obj.data.materials.clear()
                    obj.data.materials.append(new_material)
                    success_count += 1
                    
                elif self.replace_mode == "ADD":
                    # 追加材质：在末尾添加新材质
                    obj.data.materials.append(new_material)
                    success_count += 1
                    
                elif self.replace_mode == "REPLACE_SPECIFIC":
                    # 替换指定材质：找到旧材质并替换
                    found = False
                    for i, slot in enumerate(obj.material_slots):
                        if slot.material == old_material:
                            obj.data.materials[i] = new_material
                            found = True
                            replaced_count += 1
                    if found:
                        success_count += 1
                        
            except Exception as e:
                self.report({'WARNING'}, f"处理 {obj.name} 时发生错误: {str(e)}")
                continue
        
        if success_count > 0:
            if self.replace_mode == "REPLACE_SPECIFIC":
                self.report({'INFO'}, f"成功处理 {success_count} 个对象，替换了 {replaced_count} 处材质")
            else:
                self.report({'INFO'}, f"成功将材质 '{self.new_material}' 应用到 {success_count} 个对象")
            return {'FINISHED'}
        else:
            if self.replace_mode == "REPLACE_SPECIFIC":
                self.report({'WARNING'}, f"未找到材质 '{self.old_material}'")
            else:
                self.report({'ERROR'}, "未能成功应用材质到任何对象")
            return {'CANCELLED'}

# ==================== 批量OBJ导出功能 ====================

class EXPORT_OT_batch_obj_with_origin(Operator):
    """批量导出OBJ文件并生成原点信息"""
    bl_idname = "export.batch_obj_with_origin"
    bl_label = "批量导出OBJ"
    bl_options = {'REGISTER', 'UNDO'}

    export_path: StringProperty(
        name="导出路径",
        description="指定导出目录",
        subtype='DIR_PATH',
        default=""
    )
    forward_axis: EnumProperty(
        name="前向轴",
        items=[
            ('X', 'X Forward', ''), ('Y', 'Y Forward', ''), ('Z', 'Z Forward', ''),
            ('NEGATIVE_X', '-X Forward', ''), ('NEGATIVE_Y', '-Y Forward', ''), ('NEGATIVE_Z', '-Z Forward', ''),
        ],
        default='NEGATIVE_Z'
    )
    up_axis: EnumProperty(
        name="向上轴",
        items=[('X', 'X Up', ''), ('Y', 'Y Up', ''), ('Z', 'Z Up', '')],
        default='Y'
    )
    scale_factor: FloatProperty(name="缩放系数", default=1.0, min=0.01, max=1000.0)
    export_materials: BoolProperty(name="导出材质", default=True)
    export_origin_info: BoolProperty(name="导出原点信息", default=True)
    only_export_origin: BoolProperty(name="只导出原点信息", default=False)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "export_path")
        layout.separator()
        box = layout.box()
        box.label(text="导出设置:", icon='SETTINGS')
        box.prop(self, "forward_axis")
        box.prop(self, "up_axis")
        box.prop(self, "scale_factor")
        box.prop(self, "export_materials")
        layout.separator()
        box = layout.box()
        box.label(text="原点信息:", icon='EMPTY_AXIS')
        box.prop(self, "export_origin_info")
        box.prop(self, "only_export_origin")
        layout.separator()
        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        layout.label(text=f"将导出 {len(meshes)} 个网格对象", icon='INFO')

    def invoke(self, context, event):
        # 默认路径设为 Blender 工程所在目录
        if not self.export_path and bpy.data.filepath:
            self.export_path = os.path.dirname(bpy.data.filepath)
        return context.window_manager.invoke_props_dialog(self, width=400)

    def execute(self, context):
        if self.export_path:
            export_dir = bpy.path.abspath(self.export_path)
        else:
            if not bpy.data.filepath:
                self.report({'ERROR'}, "请先保存Blender文件或手动指定导出路径")
                return {'CANCELLED'}
            export_dir = os.path.dirname(bpy.data.filepath)
        try:
            os.makedirs(export_dir, exist_ok=True)
        except Exception as e:
            self.report({'ERROR'}, f"无法创建导出目录: {str(e)}")
            return {'CANCELLED'}
        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        if not meshes:
            self.report({'ERROR'}, "未检测到选中的网格对象")
            return {'CANCELLED'}

        origin_info_file = os.path.join(export_dir, "origin_info.txt")
        origin_data = []
        exported_count = 0
        for ob in meshes:
            try:
                world_location = ob.matrix_world.translation
                origin_data.append({
                    'name': ob.name,
                    'x': round(world_location.x, 6),
                    'y': round(world_location.y, 6),
                    'z': round(world_location.z, 6)
                })
                if not self.only_export_origin:
                    bpy.ops.object.select_all(action='DESELECT')
                    ob.select_set(True)
                    context.view_layer.objects.active = ob
                    filepath = os.path.join(export_dir, f"{ob.name}.obj")
                    bpy.ops.wm.obj_export(
                        filepath=filepath,
                        export_selected_objects=True,
                        forward_axis=self.forward_axis,
                        up_axis=self.up_axis,
                        global_scale=self.scale_factor,
                        path_mode='STRIP',
                        export_materials=self.export_materials
                    )
                    exported_count += 1
                    print(f"已导出: {ob.name}.obj")
            except Exception as e:
                self.report({'WARNING'}, f"导出 {ob.name} 时发生错误: {str(e)}")
                continue
        if self.export_origin_info or self.only_export_origin:
            try:
                with open(origin_info_file, 'w', encoding='utf-8') as f:
                    for data in origin_data:
                        x = format_value(data['x'])
                        y = format_value(data['y'])
                        z = format_value(data['z'])
                        f.write(f"{data['name']}({x}, {y}, {z})\n")
                self.report({'INFO'}, f"原点信息已写入: {origin_info_file}")
            except Exception as e:
                self.report({'WARNING'}, f"写入原点信息时发生错误: {str(e)}")
        if self.only_export_origin:
            self.report({'INFO'}, f"完成！已导出 {len(origin_data)} 个物体的原点信息 -> {export_dir}")
        else:
            self.report({'INFO'}, f"完成！共导出 {exported_count} 个 OBJ -> {export_dir}")
        return {'FINISHED'}

# ==================== 变换复制功能 ====================

def format_value(value, is_angle=False):
    if is_angle:
        value = math.degrees(value)
        formatted = f"{value:.6f}".rstrip('0').rstrip('.')
        return f"{formatted}°"
    else:
        formatted = f"{value:.6f}".rstrip('0').rstrip('.')
        return formatted

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


# ==================== 对齐工具模块 ====================
# 
# 设计原则：
# 1. 支持多种对齐基准点：原点、边界框各点（最低点、最高点、中心点）
# 2. 支持6个方向对齐：左、右、前、后、上、下
# 3. 子对象对齐到父对象（活动对象作为目标）
# 4. 批量对齐多个选中对象
# 5. 支持世界坐标和局部坐标
#

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
            # 非网格对象或空网格，返回原点位置
            origin = obj.matrix_world.translation
            return origin.copy(), origin.copy()
        
        # 获取所有顶点的世界坐标
        world_verts = [obj.matrix_world @ v.co for v in obj.data.vertices]
        
        # 计算边界框
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
            ref_type: 参考点类型 (ORIGIN, BBOX_MIN, BBOX_MAX, BBOX_CENTER, BBOX_BOTTOM, BBOX_TOP)
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
            # 底部中心：在指定轴向上取最小值，其他轴取中心
            result = bbox_center.copy()
            axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 2)
            result[axis_idx] = bbox_min[axis_idx]
            return result
        elif ref_type == 'BBOX_TOP':
            # 顶部中心：在指定轴向上取最大值，其他轴取中心
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
        
        # 获取对象当前参考点
        current_ref = AlignmentHelper.get_reference_point(obj, ref_type, axis)
        
        # 计算需要移动的距离
        delta = target_coord - current_ref[axis_idx]
        
        # 移动对象
        obj.location[axis_idx] += delta


class OBJECT_OT_align_objects(Operator):
    """智能对齐工具：将选中对象对齐到活动对象"""
    bl_idname = "object.align_objects_plus"
    bl_label = "对齐（增强）"
    bl_options = {'REGISTER', 'UNDO'}
    
    # 对齐轴向
    align_axis: EnumProperty(
        name="对齐轴",
        items=[
            ('X', "X轴 (左右)", "沿X轴对齐"),
            ('Y', "Y轴 (前后)", "沿Y轴对齐"),
            ('Z', "Z轴 (上下)", "沿Z轴对齐"),
        ],
        default='Z',
    )
    
    # 对齐方向
    align_direction: EnumProperty(
        name="对齐方向",
        items=[
            ('MIN', "最小侧", "对齐到轴向的最小侧（左/后/下）"),
            ('CENTER', "中心", "对齐到中心"),
            ('MAX', "最大侧", "对齐到轴向的最大侧（右/前/上）"),
        ],
        default='MIN',
    )
    
    # 源对象（被移动的对象）的参考点
    source_ref: EnumProperty(
        name="源对象基准",
        description="被移动对象使用的对齐基准点",
        items=[
            ('ORIGIN', "原点", "使用对象原点"),
            ('BBOX_MIN', "边界框最小点", "边界框的最小坐标点"),
            ('BBOX_MAX', "边界框最大点", "边界框的最大坐标点"),
            ('BBOX_CENTER', "边界框中心", "边界框的几何中心"),
            ('BBOX_BOTTOM', "底部中心", "边界框底面中心（沿对齐轴的最小侧）"),
            ('BBOX_TOP', "顶部中心", "边界框顶面中心（沿对齐轴的最大侧）"),
        ],
        default='BBOX_BOTTOM',
    )
    
    # 目标对象（对齐目标）的参考点
    target_ref: EnumProperty(
        name="目标对象基准",
        description="目标对象（活动对象）使用的对齐基准点",
        items=[
            ('ORIGIN', "原点", "使用对象原点"),
            ('BBOX_MIN', "边界框最小点", "边界框的最小坐标点"),
            ('BBOX_MAX', "边界框最大点", "边界框的最大坐标点"),
            ('BBOX_CENTER', "边界框中心", "边界框的几何中心"),
            ('BBOX_BOTTOM', "底部中心", "边界框底面中心（沿对齐轴的最小侧）"),
            ('BBOX_TOP', "顶部中心", "边界框顶面中心（沿对齐轴的最大侧）"),
        ],
        default='BBOX_BOTTOM',
    )
    
    # 快捷预设
    preset: EnumProperty(
        name="快捷预设",
        description="常用对齐场景的快捷设置",
        items=[
            ('CUSTOM', "自定义", "使用下方的自定义设置"),
            ('BOTTOM_ALIGN', "底部对齐", "让对象底部对齐（常用于放置物体）"),
            ('TOP_ALIGN', "顶部对齐", "让对象顶部对齐"),
            ('CENTER_ALIGN', "中心对齐", "让对象中心对齐"),
            ('ORIGIN_ALIGN', "原点对齐", "让对象原点对齐"),
            ('STACK_ON_TOP', "堆叠在上方", "将对象堆叠在目标上方"),
        ],
        default='BOTTOM_ALIGN',
    )
    
    def draw(self, context):
        layout = self.layout
        
        # 快捷预设
        box = layout.box()
        box.label(text="快捷预设:", icon='PRESET')
        box.prop(self, "preset", text="")
        
        # 预设说明
        preset_desc = {
            'CUSTOM': "使用下方的自定义设置",
            'BOTTOM_ALIGN': "源和目标都使用底部中心，实现底部对齐",
            'TOP_ALIGN': "源和目标都使用顶部中心，实现顶部对齐",
            'CENTER_ALIGN': "源和目标都使用边界框中心，实现中心对齐",
            'ORIGIN_ALIGN': "源和目标都使用原点，实现原点对齐",
            'STACK_ON_TOP': "源底部对齐到目标顶部，实现堆叠效果",
        }
        box.label(text=preset_desc.get(self.preset, ""), icon='INFO')
        
        layout.separator()
        
        # 对齐轴向
        box = layout.box()
        box.label(text="对齐设置:", icon='ORIENTATION_GLOBAL')
        box.prop(self, "align_axis")
        
        # 自定义设置（仅在自定义模式下显示）
        if self.preset == 'CUSTOM':
            layout.separator()
            box = layout.box()
            box.label(text="自定义基准点:", icon='PIVOT_BOUNDBOX')
            box.prop(self, "source_ref", text="源对象")
            box.prop(self, "target_ref", text="目标对象")
        
        # 显示选中信息
        layout.separator()
        selected = [o for o in context.selected_objects if o != context.active_object]
        active = context.active_object
        if active:
            layout.label(text=f"目标对象: {active.name}", icon='OBJECT_DATA')
        layout.label(text=f"将对齐 {len(selected)} 个对象", icon='INFO')
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=350)
    
    def execute(self, context):
        active = context.active_object
        if not active:
            self.report({'ERROR'}, "请先选择一个活动对象作为对齐目标")
            return {'CANCELLED'}
        
        # 获取要对齐的对象（排除活动对象）
        objects_to_align = [o for o in context.selected_objects if o != active]
        if not objects_to_align:
            self.report({'WARNING'}, "请选择要对齐的对象（除活动对象外）")
            return {'CANCELLED'}
        
        # 应用预设
        source_ref = self.source_ref
        target_ref = self.target_ref
        
        if self.preset == 'BOTTOM_ALIGN':
            source_ref = 'BBOX_BOTTOM'
            target_ref = 'BBOX_BOTTOM'
        elif self.preset == 'TOP_ALIGN':
            source_ref = 'BBOX_TOP'
            target_ref = 'BBOX_TOP'
        elif self.preset == 'CENTER_ALIGN':
            source_ref = 'BBOX_CENTER'
            target_ref = 'BBOX_CENTER'
        elif self.preset == 'ORIGIN_ALIGN':
            source_ref = 'ORIGIN'
            target_ref = 'ORIGIN'
        elif self.preset == 'STACK_ON_TOP':
            source_ref = 'BBOX_BOTTOM'
            target_ref = 'BBOX_TOP'
        
        # 获取目标参考点坐标
        target_point = AlignmentHelper.get_reference_point(active, target_ref, self.align_axis)
        axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(self.align_axis, 2)
        target_coord = target_point[axis_idx]
        
        # 对齐所有选中对象
        aligned_count = 0
        for obj in objects_to_align:
            try:
                AlignmentHelper.align_object(obj, target_coord, source_ref, self.align_axis)
                aligned_count += 1
            except Exception as e:
                self.report({'WARNING'}, f"对齐 {obj.name} 时出错: {str(e)}")
        
        axis_names = {'X': 'X轴', 'Y': 'Y轴', 'Z': 'Z轴'}
        self.report({'INFO'}, f"已沿{axis_names[self.align_axis]}对齐 {aligned_count} 个对象到 {active.name}")
        return {'FINISHED'}


class OBJECT_OT_quick_align(Operator):
    """快速对齐：一键底部对齐"""
    bl_idname = "object.quick_align"
    bl_label = "快速底部对齐"
    bl_options = {'REGISTER', 'UNDO'}
    
    align_axis: EnumProperty(
        name="轴向",
        items=[('X', "X", ""), ('Y', "Y", ""), ('Z', "Z", "")],
        default='Z',
    )
    
    def execute(self, context):
        active = context.active_object
        if not active:
            self.report({'ERROR'}, "请先选择一个活动对象作为对齐目标")
            return {'CANCELLED'}
        
        objects_to_align = [o for o in context.selected_objects if o != active]
        if not objects_to_align:
            self.report({'WARNING'}, "请选择要对齐的对象")
            return {'CANCELLED'}
        
        # 获取目标底部坐标
        target_point = AlignmentHelper.get_reference_point(active, 'BBOX_BOTTOM', self.align_axis)
        axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(self.align_axis, 2)
        target_coord = target_point[axis_idx]
        
        # 对齐
        for obj in objects_to_align:
            AlignmentHelper.align_object(obj, target_coord, 'BBOX_BOTTOM', self.align_axis)
        
        self.report({'INFO'}, f"已底部对齐 {len(objects_to_align)} 个对象")
        return {'FINISHED'}


class OBJECT_OT_distribute_objects(Operator):
    """均匀分布选中对象"""
    bl_idname = "object.distribute_objects"
    bl_label = "均匀分布"
    bl_options = {'REGISTER', 'UNDO'}
    
    distribute_axis: EnumProperty(
        name="分布轴",
        items=[
            ('X', "X轴", "沿X轴分布"),
            ('Y', "Y轴", "沿Y轴分布"),
            ('Z', "Z轴", "沿Z轴分布"),
        ],
        default='X',
    )
    
    ref_point: EnumProperty(
        name="参考点",
        items=[
            ('ORIGIN', "原点", "使用对象原点"),
            ('BBOX_CENTER', "边界框中心", "使用边界框中心"),
        ],
        default='BBOX_CENTER',
    )
    
    use_gap: BoolProperty(
        name="使用间距",
        description="使用固定间距而非均匀分布",
        default=False,
    )
    
    gap_value: FloatProperty(
        name="间距",
        description="对象之间的间距",
        default=1.0,
        min=0.0,
        unit='LENGTH',
    )
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "distribute_axis")
        layout.prop(self, "ref_point")
        layout.separator()
        layout.prop(self, "use_gap")
        if self.use_gap:
            layout.prop(self, "gap_value")
        
        selected = context.selected_objects
        layout.separator()
        layout.label(text=f"将分布 {len(selected)} 个对象", icon='INFO')
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=300)
    
    def execute(self, context):
        selected = list(context.selected_objects)
        if len(selected) < 2:
            self.report({'WARNING'}, "请至少选择2个对象")
            return {'CANCELLED'}
        
        axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(self.distribute_axis, 0)
        
        # 按当前位置排序
        def get_pos(obj):
            ref = AlignmentHelper.get_reference_point(obj, self.ref_point, self.distribute_axis)
            return ref[axis_idx]
        
        selected.sort(key=get_pos)
        
        if self.use_gap:
            # 使用固定间距
            start_pos = get_pos(selected[0])
            for i, obj in enumerate(selected):
                if i == 0:
                    continue
                # 计算目标位置
                prev_obj = selected[i - 1]
                prev_bbox_min, prev_bbox_max = AlignmentHelper.get_world_bbox(prev_obj)
                curr_bbox_min, curr_bbox_max = AlignmentHelper.get_world_bbox(obj)
                
                # 前一个对象的最大边界 + 间距 = 当前对象的最小边界
                target_min = prev_bbox_max[axis_idx] + self.gap_value
                current_min = curr_bbox_min[axis_idx]
                delta = target_min - current_min
                obj.location[axis_idx] += delta
        else:
            # 均匀分布
            first_pos = get_pos(selected[0])
            last_pos = get_pos(selected[-1])
            
            if len(selected) > 2:
                step = (last_pos - first_pos) / (len(selected) - 1)
                for i, obj in enumerate(selected[1:-1], 1):
                    target_pos = first_pos + step * i
                    current_pos = get_pos(obj)
                    delta = target_pos - current_pos
                    obj.location[axis_idx] += delta
        
        self.report({'INFO'}, f"已沿{self.distribute_axis}轴分布 {len(selected)} 个对象")
        return {'FINISHED'}


# ==================== 编辑模式对齐功能 ====================

class MESH_OT_align_vertices(Operator):
    """编辑模式下对齐选中的顶点/边/面"""
    bl_idname = "mesh.align_vertices_plus"
    bl_label = "对齐顶点（增强）"
    bl_options = {'REGISTER', 'UNDO'}
    
    align_axis: EnumProperty(
        name="对齐轴",
        items=[
            ('X', "X轴", "沿X轴对齐"),
            ('Y', "Y轴", "沿Y轴对齐"),
            ('Z', "Z轴", "沿Z轴对齐"),
        ],
        default='Z',
    )
    
    align_target: EnumProperty(
        name="对齐目标",
        items=[
            ('ACTIVE', "活动元素", "对齐到活动顶点/边/面"),
            ('CURSOR', "3D游标", "对齐到3D游标位置"),
            ('MIN', "最小值", "对齐到选中元素的最小坐标"),
            ('MAX', "最大值", "对齐到选中元素的最大坐标"),
            ('CENTER', "中心", "对齐到选中元素的中心"),
            ('ZERO', "世界原点", "对齐到世界坐标0"),
        ],
        default='ACTIVE',
    )
    
    use_local: BoolProperty(
        name="局部坐标",
        description="使用对象的局部坐标系",
        default=False,
    )
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "align_axis")
        layout.prop(self, "align_target")
        layout.prop(self, "use_local")
        
        # 显示当前选择信息
        layout.separator()
        obj = context.edit_object
        if obj:
            bm = bmesh.from_edit_mesh(obj.data)
            selected_verts = [v for v in bm.verts if v.select]
            layout.label(text=f"选中 {len(selected_verts)} 个顶点", icon='INFO')
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=280)
    
    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.edit_object is not None
    
    def execute(self, context):
        obj = context.edit_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "请在编辑模式下选择网格对象")
            return {'CANCELLED'}
        
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        
        selected_verts = [v for v in bm.verts if v.select]
        if not selected_verts:
            self.report({'WARNING'}, "请先选择顶点")
            return {'CANCELLED'}
        
        axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(self.align_axis, 2)
        mw = obj.matrix_world
        mw_inv = mw.inverted()
        
        # 确定目标坐标
        target_coord = None
        
        if self.align_target == 'ACTIVE':
            # 获取活动元素
            if bm.select_history:
                active_elem = bm.select_history.active
                if active_elem:
                    if isinstance(active_elem, bmesh.types.BMVert):
                        if self.use_local:
                            target_coord = active_elem.co[axis_idx]
                        else:
                            target_coord = (mw @ active_elem.co)[axis_idx]
                    elif isinstance(active_elem, bmesh.types.BMEdge):
                        center = (active_elem.verts[0].co + active_elem.verts[1].co) / 2
                        if self.use_local:
                            target_coord = center[axis_idx]
                        else:
                            target_coord = (mw @ center)[axis_idx]
                    elif isinstance(active_elem, bmesh.types.BMFace):
                        center = active_elem.calc_center_median()
                        if self.use_local:
                            target_coord = center[axis_idx]
                        else:
                            target_coord = (mw @ center)[axis_idx]
            
            if target_coord is None:
                # 没有活动元素，使用第一个选中的顶点
                if self.use_local:
                    target_coord = selected_verts[0].co[axis_idx]
                else:
                    target_coord = (mw @ selected_verts[0].co)[axis_idx]
        
        elif self.align_target == 'CURSOR':
            cursor_world = context.scene.cursor.location
            if self.use_local:
                cursor_local = mw_inv @ cursor_world
                target_coord = cursor_local[axis_idx]
            else:
                target_coord = cursor_world[axis_idx]
        
        elif self.align_target == 'MIN':
            if self.use_local:
                target_coord = min(v.co[axis_idx] for v in selected_verts)
            else:
                target_coord = min((mw @ v.co)[axis_idx] for v in selected_verts)
        
        elif self.align_target == 'MAX':
            if self.use_local:
                target_coord = max(v.co[axis_idx] for v in selected_verts)
            else:
                target_coord = max((mw @ v.co)[axis_idx] for v in selected_verts)
        
        elif self.align_target == 'CENTER':
            if self.use_local:
                coords = [v.co[axis_idx] for v in selected_verts]
            else:
                coords = [(mw @ v.co)[axis_idx] for v in selected_verts]
            target_coord = (min(coords) + max(coords)) / 2
        
        elif self.align_target == 'ZERO':
            if self.use_local:
                # 世界原点在局部坐标中的位置
                target_coord = (mw_inv @ Vector((0, 0, 0)))[axis_idx]
            else:
                target_coord = 0.0
        
        if target_coord is None:
            self.report({'ERROR'}, "无法确定对齐目标")
            return {'CANCELLED'}
        
        # 执行对齐
        aligned_count = 0
        for v in selected_verts:
            if self.use_local:
                v.co[axis_idx] = target_coord
            else:
                # 世界坐标对齐
                world_pos = mw @ v.co
                world_pos[axis_idx] = target_coord
                v.co = mw_inv @ world_pos
            aligned_count += 1
        
        bmesh.update_edit_mesh(obj.data)
        
        target_names = {
            'ACTIVE': '活动元素',
            'CURSOR': '3D游标',
            'MIN': '最小值',
            'MAX': '最大值',
            'CENTER': '中心',
            'ZERO': '世界原点',
        }
        self.report({'INFO'}, f"已将 {aligned_count} 个顶点沿{self.align_axis}轴对齐到{target_names[self.align_target]}")
        return {'FINISHED'}


class MESH_OT_quick_align_axis(Operator):
    """快速轴向对齐（一键操作）"""
    bl_idname = "mesh.quick_align_axis"
    bl_label = "快速轴向对齐"
    bl_options = {'REGISTER', 'UNDO'}
    
    axis: EnumProperty(
        name="轴",
        items=[('X', "X", ""), ('Y', "Y", ""), ('Z', "Z", "")],
        default='Z',
    )
    
    target: EnumProperty(
        name="目标",
        items=[
            ('ACTIVE', "活动", ""),
            ('MIN', "最小", ""),
            ('MAX', "最大", ""),
            ('CENTER', "中心", ""),
        ],
        default='ACTIVE',
    )
    
    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.edit_object is not None
    
    def execute(self, context):
        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        selected_verts = [v for v in bm.verts if v.select]
        
        if not selected_verts:
            self.report({'WARNING'}, "请先选择顶点")
            return {'CANCELLED'}
        
        axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(self.axis, 2)
        
        # 确定目标坐标（局部坐标）
        if self.target == 'ACTIVE':
            if bm.select_history and bm.select_history.active:
                active = bm.select_history.active
                if isinstance(active, bmesh.types.BMVert):
                    target_coord = active.co[axis_idx]
                elif isinstance(active, bmesh.types.BMEdge):
                    target_coord = ((active.verts[0].co + active.verts[1].co) / 2)[axis_idx]
                elif isinstance(active, bmesh.types.BMFace):
                    target_coord = active.calc_center_median()[axis_idx]
                else:
                    target_coord = selected_verts[0].co[axis_idx]
            else:
                target_coord = selected_verts[0].co[axis_idx]
        elif self.target == 'MIN':
            target_coord = min(v.co[axis_idx] for v in selected_verts)
        elif self.target == 'MAX':
            target_coord = max(v.co[axis_idx] for v in selected_verts)
        elif self.target == 'CENTER':
            coords = [v.co[axis_idx] for v in selected_verts]
            target_coord = (min(coords) + max(coords)) / 2
        
        # 对齐
        for v in selected_verts:
            v.co[axis_idx] = target_coord
        
        bmesh.update_edit_mesh(obj.data)
        self.report({'INFO'}, f"已对齐 {len(selected_verts)} 个顶点")
        return {'FINISHED'}


class MESH_OT_flatten_selection(Operator):
    """将选中的顶点展平到一个平面"""
    bl_idname = "mesh.flatten_selection"
    bl_label = "展平选区"
    bl_options = {'REGISTER', 'UNDO'}
    
    flatten_mode: EnumProperty(
        name="展平模式",
        items=[
            ('AXIS', "轴向平面", "展平到与轴垂直的平面"),
            ('NORMAL', "法线平面", "展平到选区的平均法线平面"),
            ('VIEW', "视图平面", "展平到当前视图平面"),
        ],
        default='AXIS',
    )
    
    axis: EnumProperty(
        name="轴向",
        description="展平到与此轴垂直的平面",
        items=[
            ('X', "X轴 (YZ平面)", "展平到YZ平面"),
            ('Y', "Y轴 (XZ平面)", "展平到XZ平面"),
            ('Z', "Z轴 (XY平面)", "展平到XY平面"),
        ],
        default='Z',
    )
    
    use_center: BoolProperty(
        name="使用中心",
        description="展平到选区中心，否则展平到活动元素",
        default=True,
    )
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "flatten_mode")
        if self.flatten_mode == 'AXIS':
            layout.prop(self, "axis")
        layout.prop(self, "use_center")
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=280)
    
    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.edit_object is not None
    
    def execute(self, context):
        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        selected_verts = [v for v in bm.verts if v.select]
        
        if len(selected_verts) < 2:
            self.report({'WARNING'}, "请至少选择2个顶点")
            return {'CANCELLED'}
        
        if self.flatten_mode == 'AXIS':
            axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(self.axis, 2)
            
            # 确定展平位置
            if self.use_center:
                coords = [v.co[axis_idx] for v in selected_verts]
                target = (min(coords) + max(coords)) / 2
            else:
                if bm.select_history and bm.select_history.active:
                    active = bm.select_history.active
                    if isinstance(active, bmesh.types.BMVert):
                        target = active.co[axis_idx]
                    else:
                        target = selected_verts[0].co[axis_idx]
                else:
                    target = selected_verts[0].co[axis_idx]
            
            for v in selected_verts:
                v.co[axis_idx] = target
        
        elif self.flatten_mode == 'NORMAL':
            # 计算平均法线
            avg_normal = Vector((0, 0, 0))
            for v in selected_verts:
                avg_normal += v.normal
            avg_normal.normalize()
            
            # 计算中心点
            center = Vector((0, 0, 0))
            for v in selected_verts:
                center += v.co
            center /= len(selected_verts)
            
            # 投影到平面
            for v in selected_verts:
                offset = v.co - center
                dist = offset.dot(avg_normal)
                v.co = v.co - avg_normal * dist
        
        elif self.flatten_mode == 'VIEW':
            # 获取视图方向
            region = context.region
            rv3d = context.region_data
            if rv3d:
                view_normal = rv3d.view_rotation @ Vector((0, 0, 1))
                # 转换到局部坐标
                view_normal = obj.matrix_world.inverted().to_3x3() @ view_normal
                view_normal.normalize()
                
                # 计算中心点
                center = Vector((0, 0, 0))
                for v in selected_verts:
                    center += v.co
                center /= len(selected_verts)
                
                # 投影到平面
                for v in selected_verts:
                    offset = v.co - center
                    dist = offset.dot(view_normal)
                    v.co = v.co - view_normal * dist
            else:
                self.report({'WARNING'}, "无法获取视图方向")
                return {'CANCELLED'}
        
        bmesh.update_edit_mesh(obj.data)
        self.report({'INFO'}, f"已展平 {len(selected_verts)} 个顶点")
        return {'FINISHED'}


class MESH_OT_align_to_edge(Operator):
    """将选中顶点对齐到边的延长线上"""
    bl_idname = "mesh.align_to_edge"
    bl_label = "对齐到边"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.edit_object is not None
    
    def execute(self, context):
        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        
        # 获取活动边
        active_edge = None
        if bm.select_history:
            for elem in reversed(bm.select_history):
                if isinstance(elem, bmesh.types.BMEdge):
                    active_edge = elem
                    break
        
        if not active_edge:
            # 尝试从选中的边中获取
            selected_edges = [e for e in bm.edges if e.select]
            if selected_edges:
                active_edge = selected_edges[0]
        
        if not active_edge:
            self.report({'WARNING'}, "请先选择一条边作为参考")
            return {'CANCELLED'}
        
        # 获取边的方向
        edge_vec = (active_edge.verts[1].co - active_edge.verts[0].co).normalized()
        edge_start = active_edge.verts[0].co
        
        # 获取要对齐的顶点（排除边的顶点）
        edge_vert_indices = {active_edge.verts[0].index, active_edge.verts[1].index}
        verts_to_align = [v for v in bm.verts if v.select and v.index not in edge_vert_indices]
        
        if not verts_to_align:
            self.report({'WARNING'}, "请选择要对齐的顶点（除参考边外）")
            return {'CANCELLED'}
        
        # 将顶点投影到边的延长线上
        for v in verts_to_align:
            offset = v.co - edge_start
            proj_length = offset.dot(edge_vec)
            v.co = edge_start + edge_vec * proj_length
        
        bmesh.update_edit_mesh(obj.data)
        self.report({'INFO'}, f"已将 {len(verts_to_align)} 个顶点对齐到边")
        return {'FINISHED'}


# 对齐工具子菜单
class VIEW3D_MT_align_tools(bpy.types.Menu):
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
            layout.operator("object.quick_align", text="快速底部对齐 Z", icon='ALIGN_BOTTOM').align_axis = 'Z'
            layout.separator()
            layout.operator("object.distribute_objects", text="均匀分布", icon='ALIGN_JUSTIFY')


# ==================== 面板定义 ====================

class TRANSFORM_PT_precise_panel(Panel):
    """高精度变换面板（增强版）"""
    bl_label = "变换（增强）"
    bl_idname = "TRANSFORM_PT_precise_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Item"  # 放在默认的 Item 标签页
    bl_order = 0  # 排在最前面

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
        row = col.row(align=True)
        row.operator("transform.copy_location", text="📋 位置 (点击复制)", icon='ORIENTATION_GLOBAL', emboss=True)
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
        row = col.row(align=True)
        row.operator("transform.copy_rotation", text="📋 旋转 (点击复制)", icon='ORIENTATION_GIMBAL', emboss=True)
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
        row = col.row(align=True)
        row.operator("transform.copy_scale", text="📋 缩放 (点击复制)", icon='FULLSCREEN_EXIT', emboss=True)
        sub = col.column(align=True)
        for i in range(3):
            axis = ['X', 'Y', 'Z'][i]
            value = [obj.scale.x, obj.scale.y, obj.scale.z][i]
            row = sub.row(align=True)
            row.prop(obj, "scale", index=i, text=f"{axis}  {format_value(value)}")
            row.prop(obj, "lock_scale", index=i, text="", icon_only=True, emboss=False)
        if obj.type == 'MESH':
            col.separator()
            row = col.row(align=True)
            row.operator("transform.copy_dimensions", text="📋 尺寸 (点击复制)", icon='ARROW_LEFTRIGHT', emboss=True)
            sub = col.column(align=True)
            for i in range(3):
                axis = ['X', 'Y', 'Z'][i]
                value = [obj.dimensions.x, obj.dimensions.y, obj.dimensions.z][i]
                sub.prop(obj, "dimensions", index=i, text=f"{axis}  {format_value(value)} m")



# ==================== 属性组定义 ====================

class BatchObjExportProperties(PropertyGroup):
    export_path: StringProperty(
        name="导出路径",
        description="指定导出目录",
        subtype='DIR_PATH',
        default=""
    )
    forward_axis: EnumProperty(
        name="前向轴",
        items=[
            ('X', 'X Forward', ''), ('Y', 'Y Forward', ''), ('Z', 'Z Forward', ''),
            ('NEGATIVE_X', '-X Forward', ''), ('NEGATIVE_Y', '-Y Forward', ''), ('NEGATIVE_Z', '-Z Forward', ''),
        ],
        default='NEGATIVE_Z'
    )
    up_axis: EnumProperty(
        name="向上轴",
        items=[('X', 'X Up', ''), ('Y', 'Y Up', ''), ('Z', 'Z Up', '')],
        default='Y'
    )
    scale_factor: FloatProperty(name="缩放系数", default=1.0, min=0.01, max=1000.0)
    export_materials: BoolProperty(name="导出材质", default=True)
    export_origin_info: BoolProperty(name="导出原点信息", default=True)
    only_export_origin: BoolProperty(name="只导出原点信息", default=False)

class BatchMaterialProperties(PropertyGroup):
    selected_material: StringProperty(name="选择材质", default="")

class AnnotationSettings(PropertyGroup):
    """标注系统设置"""
    auto_overwrite: BoolProperty(
        name="自动覆盖标注",
        description="对相同元素重复测量时，自动覆盖旧标注。关闭后会保留所有标注，允许叠加显示",
        default=True
    )

def update_origin_location(self, context):
    obj = context.active_object
    if not obj or obj.type != 'MESH':
        return
    current_location = obj.location.copy()
    target_location = self.origin_location.copy()
    delta_vec = target_location - current_location
    if delta_vec.length < 0.000001:
        return
    mesh = obj.data
    vert_count = len(mesh.vertices)
    if vert_count == 0:
        return
    coords = [0.0] * (vert_count * 3)
    mesh.vertices.foreach_get("co", coords)
    try:
        basis_matrix = obj.matrix_basis.to_3x3()
        local_delta = basis_matrix.inverted_safe() @ delta_vec
    except Exception:
        local_delta = delta_vec.copy()
    for i in range(0, len(coords), 3):
        coords[i] -= local_delta.x
        coords[i + 1] -= local_delta.y
        coords[i + 2] -= local_delta.z
    mesh.vertices.foreach_set("co", coords)
    obj.location = target_location
    mesh.update_tag()
    if context.view_layer.objects.active:
        context.view_layer.update()

def update_only_modify_origin(self, context):
    obj = context.active_object
    if self.only_modify_origin and obj and obj.type == 'MESH':
        self.origin_location = obj.location
        self.last_origin_object = obj.name
    else:
        self.last_origin_object = ""

class TransformPlusProperties(PropertyGroup):
    only_modify_origin: BoolProperty(
        name="只修改原点位置",
        default=False,
        update=update_only_modify_origin
    )
    origin_location: bpy.props.FloatVectorProperty(
        name="原点位置",
        size=3,
        default=(0.0, 0.0, 0.0),
        update=update_origin_location,
        precision=6,
        subtype='TRANSLATION'
    )
    last_origin_object: StringProperty(name="原点同步对象", default="")

# ==================== 处理器 ====================

@persistent
def transform_plus_origin_sync(scene, depsgraph):
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

# ==================== 注册/注销 ====================

classes = (
    BatchMaterialProperties,
    BatchObjExportProperties,
    TransformPlusProperties,
    AnnotationSettings,
    MATERIAL_OT_apply_to_selected,
    EXPORT_OT_batch_obj_with_origin,
    TRANSFORM_OT_copy_location,
    TRANSFORM_OT_copy_rotation,
    TRANSFORM_OT_copy_scale,
    TRANSFORM_OT_copy_dimensions,
    OBJECT_OT_align_objects,
    OBJECT_OT_quick_align,
    OBJECT_OT_distribute_objects,
    MESH_OT_align_vertices,
    MESH_OT_quick_align_axis,
    MESH_OT_flatten_selection,
    MESH_OT_align_to_edge,
    VIEW3D_MT_align_tools,
    OBJECT_OT_mirror_plus,
    OBJECT_OT_batch_rename,
    OBJECT_OT_connect_origins,
    OBJECT_OT_clear_distance_display,
    OBJECT_OT_toggle_annotations,
    BOFU_OT_clear_temp_annotations,
    BOFU_OT_clear_selected_annotations,
    BOFU_OT_clear_all_annotations,
    BOFU_OT_toggle_annotations,
    BOFU_OT_annotation_info,
    VIEW3D_MT_annotation_manage,
    VIEW3D_MT_PIE_bofu_tools,
    BOFU_OT_call_pie_menu,
    TRANSFORM_PT_precise_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.batch_material_props = bpy.props.PointerProperty(type=BatchMaterialProperties)
    bpy.types.Scene.batch_obj_export_props = bpy.props.PointerProperty(type=BatchObjExportProperties)
    bpy.types.Scene.transform_plus_props = bpy.props.PointerProperty(type=TransformPlusProperties)
    bpy.types.Scene.annotation_settings = bpy.props.PointerProperty(type=AnnotationSettings)
    
    if transform_plus_origin_sync not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(transform_plus_origin_sync)
    
    # 启用统一绘制处理器
    ensure_draw_handler_enabled()
    
    # 添加到修改器菜单
    if hasattr(bpy.types, "OBJECT_MT_modifier_add_generate"):
        bpy.types.OBJECT_MT_modifier_add_generate.append(menu_func_mirror)
    else:
        bpy.types.OBJECT_MT_modifier_add.append(menu_func_mirror)
    
    # 覆盖 Ctrl+M 快捷键
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name="Object Mode", space_type="EMPTY")
        kmi = km.keymap_items.new(OBJECT_OT_mirror_plus.bl_idname, type="M", value="PRESS", ctrl=True)
        addon_keymaps.append((km, kmi))
        km = kc.keymaps.new(name="3D View", space_type="VIEW_3D")
        kmi = km.keymap_items.new(OBJECT_OT_mirror_plus.bl_idname, type="M", value="PRESS", ctrl=True)
        addon_keymaps.append((km, kmi))
        
        # 注册 Ctrl+F 快捷键（名称批量替换）
        km = kc.keymaps.new(name="Object Mode", space_type="EMPTY")
        kmi = km.keymap_items.new(OBJECT_OT_batch_rename.bl_idname, type="F", value="PRESS", ctrl=True)
        addon_keymaps.append((km, kmi))
        km = kc.keymaps.new(name="3D View", space_type="VIEW_3D")
        kmi = km.keymap_items.new(OBJECT_OT_batch_rename.bl_idname, type="F", value="PRESS", ctrl=True)
        addon_keymaps.append((km, kmi))
        
        # 注册饼图菜单快捷键
        # 波浪键 (`)
        km = kc.keymaps.new(name="3D View", space_type="VIEW_3D")
        kmi = km.keymap_items.new(BOFU_OT_call_pie_menu.bl_idname, type="ACCENT_GRAVE", value="PRESS")
        addon_keymaps.append((km, kmi))
        km = kc.keymaps.new(name="Object Mode", space_type="EMPTY")
        kmi = km.keymap_items.new(BOFU_OT_call_pie_menu.bl_idname, type="ACCENT_GRAVE", value="PRESS")
        addon_keymaps.append((km, kmi))
        
        # 鼠标侧键（靠近掌心的 BUTTON4）
        km = kc.keymaps.new(name="3D View", space_type="VIEW_3D")
        kmi = km.keymap_items.new(BOFU_OT_call_pie_menu.bl_idname, type="BUTTON4MOUSE", value="PRESS")
        addon_keymaps.append((km, kmi))
        km = kc.keymaps.new(name="Object Mode", space_type="EMPTY")
        kmi = km.keymap_items.new(BOFU_OT_call_pie_menu.bl_idname, type="BUTTON4MOUSE", value="PRESS")
        addon_keymaps.append((km, kmi))
    
    # 把默认的变换面板移到隐藏的标签页，让我们的面板显示在 Item 标签页
    try:
        # 只移动默认的变换面板
        panel = getattr(bpy.types, 'VIEW3D_PT_transform', None)
        if panel and hasattr(panel, 'bl_category'):
            _original_panel_categories['VIEW3D_PT_transform'] = panel.bl_category
            panel.bl_category = "Item (旧版)"
    except Exception:
        pass

def unregister():
    global _unified_draw_handler, _annotation_registry
    
    # 移除统一绘制处理器
    disable_draw_handler()
    
    # 清除标注数据
    clear_all_annotations()
    
    # ✅ 清理函数属性（节流计时器）
    if hasattr(unified_draw_callback, '_last_cleanup_time'):
        delattr(unified_draw_callback, '_last_cleanup_time')
    
    # 移除快捷键
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    
    # 移除菜单
    if hasattr(bpy.types, "OBJECT_MT_modifier_add_generate"):
        try:
            bpy.types.OBJECT_MT_modifier_add_generate.remove(menu_func_mirror)
        except Exception:
            pass
    else:
        try:
            bpy.types.OBJECT_MT_modifier_add.remove(menu_func_mirror)
        except Exception:
            pass
    
    # 移除处理器
    if transform_plus_origin_sync in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(transform_plus_origin_sync)
    
    # 删除属性
    del bpy.types.Scene.batch_obj_export_props
    del bpy.types.Scene.batch_material_props
    del bpy.types.Scene.transform_plus_props
    del bpy.types.Scene.annotation_settings
    
    # 注销类
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    # 恢复被移动的面板到原始标签页
    for name, original_category in _original_panel_categories.items():
        try:
            panel = getattr(bpy.types, name, None)
            if panel:
                panel.bl_category = original_category
        except Exception:
            pass
    _original_panel_categories.clear()
    
    # ✅ 强制垃圾回收，确保内存释放
    import gc
    gc.collect()
    print("[标注系统] 插件已卸载，内存已清理")

if __name__ == "__main__":
    register()
