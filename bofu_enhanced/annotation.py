# ==================== 标注系统模块 ====================
"""
bofu_enhanced/annotation.py

统一标注系统，包括：
- AnnotationKeyGenerator: 标注唯一性键生成器
- AnnotationManager: 标注管理器
- AnnotationCleaner: 标注清理器
- AnnotationStorage: 标注持久化存储
- 绘制回调函数
- 标注相关操作符
"""

import bpy
import bmesh
import math
import time
import json
from bpy.types import Operator
from mathutils import Vector
from bpy_extras.view3d_utils import location_3d_to_region_2d

from .config import Config, AnnotationType
from .render_utils import LabelRenderer, get_font_size, get_bg_color, ShaderCache
from .utils import get_vertex_world_coord_realtime, get_edge_world_coords_realtime


# ==================== 全局状态 ====================

# 统一的绘制处理器
_unified_draw_handler = None

# 标注注册表：存储所有标注数据
_annotation_registry = {}

# 标注显示开关
_annotations_visible = True


# ==================== 标注唯一性键生成器 ====================

class AnnotationKeyGenerator:
    """
    标注唯一性键生成器
    
    用于生成标注的唯一标识键，确保对相同元素的重复测量能够被正确识别和覆盖。
    """
    
    PRECISION = Config.COORDINATE_PRECISION
    
    @classmethod
    def round_coord(cls, value):
        return round(value, cls.PRECISION)
    
    @classmethod
    def vector_to_tuple(cls, vec):
        return (cls.round_coord(vec.x), cls.round_coord(vec.y), cls.round_coord(vec.z))
    
    @classmethod
    def normalize_vertex_refs(cls, vert_refs):
        if not vert_refs:
            return None
        sorted_refs = sorted(vert_refs, key=lambda x: (x[0], x[1]))
        return tuple(sorted_refs)
    
    @classmethod
    def normalize_edge_refs(cls, edge_refs):
        if not edge_refs:
            return None
        normalized = []
        for ref in edge_refs:
            obj_name, v1, v2 = ref
            v_min, v_max = min(v1, v2), max(v1, v2)
            normalized.append((obj_name, v_min, v_max))
        normalized.sort()
        return tuple(normalized)
    
    @classmethod
    def normalize_edge_data(cls, edge_data):
        if not edge_data:
            return None
        normalized = []
        for data in edge_data:
            obj_name, edge_idx, v1, v2 = data
            v_min, v_max = min(v1, v2), max(v1, v2)
            normalized.append((obj_name, v_min, v_max))
        normalized.sort()
        return tuple(normalized)
    
    @classmethod
    def normalize_points(cls, points):
        if not points:
            return None
        coords = [cls.vector_to_tuple(p) for p in points]
        coords.sort()
        return tuple(coords)
    
    @classmethod
    def normalize_edges_with_coords(cls, edges):
        if not edges:
            return None
        coords = []
        for e in edges:
            mid = e[0]
            coords.append(cls.vector_to_tuple(mid))
        coords.sort()
        return tuple(coords)
    
    @classmethod
    def generate_key(cls, annotation_type, data):
        """根据标注类型和数据生成唯一键"""
        key = None
        
        if annotation_type == AnnotationType.EDGE_LENGTH:
            if 'edge_data' in data:
                key = cls.normalize_edge_data(data['edge_data'])
            elif 'edges' in data:
                key = cls.normalize_edges_with_coords(data['edges'])
        
        elif annotation_type == AnnotationType.EDGE_ANGLE:
            if 'edge_refs' in data:
                key = cls.normalize_edge_refs(data['edge_refs'])
        
        elif annotation_type == AnnotationType.LINE_ANGLES:
            if 'vert_refs' in data:
                key = cls.normalize_vertex_refs(data['vert_refs'])
        
        elif annotation_type == AnnotationType.VERTEX_ANGLES:
            if 'vert_refs' in data:
                key = cls.normalize_vertex_refs(data['vert_refs'])
        
        elif annotation_type in (AnnotationType.ANGLE, AnnotationType.ANGLE_TEMP):
            if 'center' in data:
                key = cls.vector_to_tuple(data['center'])
            elif 'edge_indices' in data and 'angle' in data:
                key = ('angle', cls.round_coord(data['angle']))
        
        elif annotation_type in (AnnotationType.RADIUS, AnnotationType.RADIUS_TEMP):
            if 'center' in data:
                center = data['center']
                radius = data.get('radius', 0)
                key = (cls.vector_to_tuple(center), cls.round_coord(radius))
            elif 'center_vert_idx' in data:
                is_circle = data.get('is_circle', False)
                key = ('radius_bound', is_circle)
        
        elif annotation_type in (AnnotationType.DISTANCE, AnnotationType.DISTANCE_TEMP):
            if 'points' in data:
                key = cls.normalize_points(data['points'])
            elif 'measure_mode' in data and 'edge_indices' in data:
                key = ('distance_bound', data['measure_mode'], tuple(data['edge_indices']))
        
        if key is None:
            return None
        
        return (annotation_type, key)


# ==================== 标注管理器 ====================

class AnnotationManager:
    """标注管理器"""
    
    MAX_ANNOTATIONS = Config.MAX_ANNOTATIONS
    MAX_TEMP_ANNOTATIONS = Config.MAX_TEMP_ANNOTATIONS
    
    @staticmethod
    def get_registry():
        global _annotation_registry
        return _annotation_registry
    
    @staticmethod
    def set_registry(registry):
        global _annotation_registry
        _annotation_registry = registry
    
    @staticmethod
    def find_duplicate(annotation_type, data, exclude_name=None):
        registry = AnnotationManager.get_registry()
        new_key = AnnotationKeyGenerator.generate_key(annotation_type, data)
        
        if new_key is None:
            return []
        
        duplicates = []
        for name, existing_data in registry.items():
            if exclude_name and name == exclude_name:
                continue
            
            existing_type = existing_data.get('type')
            if not AnnotationType.are_compatible(annotation_type, existing_type):
                continue
            
            existing_key = AnnotationKeyGenerator.generate_key(existing_type, existing_data)
            if existing_key == new_key:
                duplicates.append(name)
        
        return duplicates
    
    @staticmethod
    def remove_duplicates(annotation_type, data):
        global _annotation_registry
        duplicates = AnnotationManager.find_duplicate(annotation_type, data)
        
        for name in duplicates:
            del _annotation_registry[name]
            print(f"[标注系统] 已移除重复标注: {name}")
        
        return len(duplicates)
    
    @staticmethod
    def register(obj_name, annotation_type, data, auto_dedupe=True):
        global _annotation_registry
        
        if obj_name.startswith("__"):
            temp_count = sum(1 for k in _annotation_registry if k.startswith("__"))
            if temp_count >= AnnotationManager.MAX_TEMP_ANNOTATIONS:
                print(f"⚠️ 临时标注数量已达上限 ({AnnotationManager.MAX_TEMP_ANNOTATIONS})，自动清理最旧的")
                temp_annotations = [(k, v.get('created_time', 0)) for k, v in _annotation_registry.items() if k.startswith("__")]
                if temp_annotations:
                    oldest = min(temp_annotations, key=lambda x: x[1])[0]
                    del _annotation_registry[oldest]
        else:
            if len(_annotation_registry) >= AnnotationManager.MAX_ANNOTATIONS:
                print(f"⚠️ 标注总数已达上限 ({AnnotationManager.MAX_ANNOTATIONS})，请清理部分标注")
                return None
        
        if auto_dedupe:
            removed_count = AnnotationManager.remove_duplicates(annotation_type, data)
            if removed_count > 0:
                print(f"[标注系统] 自动移除了 {removed_count} 个重复标注")
        
        if obj_name.startswith("__"):
            base_name = obj_name.rstrip('_')
            index = 1
            unique_name = f"{base_name}_{index}__"
            while unique_name in _annotation_registry:
                index += 1
                unique_name = f"{base_name}_{index}__"
            obj_name = unique_name
        
        data['created_time'] = time.time()
        
        _annotation_registry[obj_name] = {
            'type': annotation_type,
            'visible': True,
            **data
        }
        
        return obj_name
    
    @staticmethod
    def unregister(obj_name):
        global _annotation_registry
        if obj_name in _annotation_registry:
            del _annotation_registry[obj_name]
            return True
        return False
    
    @staticmethod
    def clear_all():
        global _annotation_registry
        count = len(_annotation_registry)
        _annotation_registry = {}
        return count
    
    @staticmethod
    def clear_temp():
        global _annotation_registry
        to_remove = [name for name in _annotation_registry if name.startswith("__")]
        for name in to_remove:
            del _annotation_registry[name]
        return len(to_remove)
    
    @staticmethod
    def get_temp_count():
        return sum(1 for name in _annotation_registry if name.startswith("__"))
    
    @staticmethod
    def get_bound_count():
        return sum(1 for name in _annotation_registry if not name.startswith("__"))
    
    @staticmethod
    def cleanup_deleted_objects():
        global _annotation_registry
        to_remove = []
        for obj_name in _annotation_registry:
            if obj_name.startswith("__"):
                continue
            if obj_name not in bpy.data.objects:
                to_remove.append(obj_name)
        
        for obj_name in to_remove:
            del _annotation_registry[obj_name]
            print(f"[标注系统] 已清理已删除对象的标注: {obj_name}")
        
        return len(to_remove)


# ==================== 标注持久化存储 ====================

class AnnotationStorage:
    """标注数据持久化存储"""
    
    STORAGE_KEY = "bofu_annotations_data"
    
    @staticmethod
    def serialize_vector(vec):
        """将 Vector 序列化为列表"""
        if vec is None:
            return None
        return [vec.x, vec.y, vec.z]
    
    @staticmethod
    def deserialize_vector(data):
        """将列表反序列化为 Vector"""
        if data is None:
            return None
        return Vector(data)
    
    @staticmethod
    def serialize_annotation(data):
        """序列化单个标注数据"""
        result = {}
        for key, value in data.items():
            if isinstance(value, Vector):
                result[key] = {'__vector__': True, 'data': AnnotationStorage.serialize_vector(value)}
            elif key == 'points' and isinstance(value, list):
                result[key] = [{'__vector__': True, 'data': AnnotationStorage.serialize_vector(v)} for v in value]
            else:
                result[key] = value
        return result
    
    @staticmethod
    def deserialize_annotation(data):
        """反序列化单个标注数据"""
        result = {}
        for key, value in data.items():
            if isinstance(value, dict) and value.get('__vector__'):
                result[key] = AnnotationStorage.deserialize_vector(value['data'])
            elif key == 'points' and isinstance(value, list):
                result[key] = [
                    AnnotationStorage.deserialize_vector(v['data']) if isinstance(v, dict) and v.get('__vector__') else v
                    for v in value
                ]
            else:
                result[key] = value
        return result
    
    @staticmethod
    def save_to_scene(scene):
        """保存标注数据到场景"""
        global _annotation_registry
        
        try:
            # 只保存绑定对象的标注（非临时标注）
            data_to_save = {}
            for name, data in _annotation_registry.items():
                if not name.startswith("__"):
                    data_to_save[name] = AnnotationStorage.serialize_annotation(data)
            
            scene[AnnotationStorage.STORAGE_KEY] = json.dumps(data_to_save)
            print(f"[标注系统] 已保存 {len(data_to_save)} 个标注到场景")
            return True
        except Exception as e:
            print(f"⚠️ 保存标注数据失败: {e}")
            return False
    
    @staticmethod
    def load_from_scene(scene):
        """从场景加载标注数据"""
        global _annotation_registry
        
        try:
            if AnnotationStorage.STORAGE_KEY not in scene:
                return 0
            
            raw_data = scene[AnnotationStorage.STORAGE_KEY]
            loaded_data = json.loads(raw_data)
            
            loaded_count = 0
            for name, data in loaded_data.items():
                # 只加载对象仍存在的标注
                if name in bpy.data.objects or name.startswith("测量_"):
                    deserialized = AnnotationStorage.deserialize_annotation(data)
                    _annotation_registry[name] = deserialized
                    loaded_count += 1
            
            print(f"[标注系统] 已从场景加载 {loaded_count} 个标注")
            return loaded_count
        except Exception as e:
            print(f"⚠️ 加载标注数据失败: {e}")
            return 0
    
    @staticmethod
    def clear_from_scene(scene):
        """清除场景中的标注数据"""
        if AnnotationStorage.STORAGE_KEY in scene:
            del scene[AnnotationStorage.STORAGE_KEY]
            print("[标注系统] 已清除场景中的标注数据")


# ==================== 标注清理器 ====================

class AnnotationCleaner:
    """标注清理器"""
    
    @staticmethod
    def refresh_view(context):
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
    
    @staticmethod
    def clear_by_vertex_refs(vert_refs_to_clear):
        global _annotation_registry
        to_remove = []
        
        for name, data in _annotation_registry.items():
            if 'vert_refs' in data:
                for ref in data['vert_refs']:
                    if ref in vert_refs_to_clear:
                        to_remove.append(name)
                        break
            
            if 'edge_data' in data:
                for obj_name, edge_idx, v1_idx, v2_idx in data['edge_data']:
                    if (obj_name, v1_idx) in vert_refs_to_clear or (obj_name, v2_idx) in vert_refs_to_clear:
                        to_remove.append(name)
                        break
            
            if 'edge_refs' in data:
                for obj_name, v1_idx, v2_idx in data['edge_refs']:
                    if (obj_name, v1_idx) in vert_refs_to_clear or (obj_name, v2_idx) in vert_refs_to_clear:
                        to_remove.append(name)
                        break
        
        to_remove = list(set(to_remove))
        for name in to_remove:
            if name in _annotation_registry:
                del _annotation_registry[name]
        
        return len(to_remove)
    
    @staticmethod
    def clear_by_edge_refs(edge_refs_to_clear):
        global _annotation_registry
        to_remove = []
        
        for name, data in _annotation_registry.items():
            if 'edge_data' in data:
                for obj_name, edge_idx, v1_idx, v2_idx in data['edge_data']:
                    v_min, v_max = min(v1_idx, v2_idx), max(v1_idx, v2_idx)
                    if (obj_name, v_min, v_max) in edge_refs_to_clear:
                        to_remove.append(name)
                        break
            
            if 'edge_refs' in data:
                for obj_name, v1_idx, v2_idx in data['edge_refs']:
                    v_min, v_max = min(v1_idx, v2_idx), max(v1_idx, v2_idx)
                    if (obj_name, v_min, v_max) in edge_refs_to_clear:
                        to_remove.append(name)
                        break
        
        to_remove = list(set(to_remove))
        for name in to_remove:
            if name in _annotation_registry:
                del _annotation_registry[name]
        
        return len(to_remove)
    
    @staticmethod
    def clear_by_object_names(obj_names_to_clear):
        global _annotation_registry
        to_remove = []
        measure_objects_to_delete = []
        
        for name, data in list(_annotation_registry.items()):
            if name in obj_names_to_clear:
                to_remove.append(name)
                obj = bpy.data.objects.get(name)
                if obj and name.startswith(Config.MEASURE_OBJECT_PREFIX):
                    measure_objects_to_delete.append(obj)
                continue
            
            should_remove = False
            
            if 'vert_refs' in data:
                for ref in data['vert_refs']:
                    if ref[0] in obj_names_to_clear:
                        should_remove = True
                        break
            
            if not should_remove and 'edge_data' in data:
                for obj_name, edge_idx, v1_idx, v2_idx in data['edge_data']:
                    if obj_name in obj_names_to_clear:
                        should_remove = True
                        break
            
            if not should_remove and 'edge_refs' in data:
                for obj_name, v1_idx, v2_idx in data['edge_refs']:
                    if obj_name in obj_names_to_clear:
                        should_remove = True
                        break
            
            if should_remove:
                to_remove.append(name)
        
        to_remove = list(set(to_remove))
        for name in to_remove:
            if name in _annotation_registry:
                del _annotation_registry[name]
        
        return len(to_remove), measure_objects_to_delete
    
    @staticmethod
    def clear_selected_in_edit_mode(context):
        edit_objects = [obj for obj in context.objects_in_mode if obj.type == 'MESH']
        if not edit_objects:
            return 0
        
        tool_settings = context.tool_settings
        select_mode = tool_settings.mesh_select_mode
        
        cleared_count = 0
        
        if select_mode[2]:  # 面模式
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
        selected_names = set(obj.name for obj in context.selected_objects)
        if not selected_names:
            return 0, 0
        
        cleared_count, measure_objects = AnnotationCleaner.clear_by_object_names(selected_names)
        
        deleted_count = 0
        for obj in measure_objects:
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
                deleted_count += 1
            except (ReferenceError, RuntimeError):
                pass
        
        return cleared_count, deleted_count


# ==================== 兼容性包装函数 ====================

def get_annotation_position_key(data):
    """获取标注的位置键（兼容旧代码）"""
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
    """注册一个标注（兼容性包装函数）"""
    auto_dedupe = True
    try:
        if hasattr(bpy.context, 'scene') and bpy.context.scene and hasattr(bpy.context.scene, 'annotation_settings'):
            auto_dedupe = bpy.context.scene.annotation_settings.auto_overwrite
    except Exception:
        pass
    
    return AnnotationManager.register(obj_name, annotation_type, data, auto_dedupe=auto_dedupe)


def unregister_annotation(obj_name):
    """注销一个标注"""
    return AnnotationManager.unregister(obj_name)


def clear_all_annotations():
    """清除所有标注"""
    return AnnotationManager.clear_all()


def clear_temp_annotations():
    """清除所有临时标注"""
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


# ==================== 绘制处理器管理 ====================

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
            print(f"⚠️ 移除绘制处理器失败: {e}")
        finally:
            _unified_draw_handler = None
    
    # 清除 Shader 缓存
    ShaderCache.clear()


# ==================== 统一绘制回调 ====================

def unified_draw_callback():
    """统一的标注绘制回调函数"""
    global _annotation_registry, _annotations_visible
    
    if not _annotations_visible:
        return
    
    if not hasattr(unified_draw_callback, '_last_cleanup_time'):
        unified_draw_callback._last_cleanup_time = 0
    
    current_time = time.time()
    if current_time - unified_draw_callback._last_cleanup_time > Config.CLEANUP_INTERVAL:
        cleanup_deleted_objects()
        unified_draw_callback._last_cleanup_time = current_time
    
    context = bpy.context
    region = context.region
    rv3d = context.region_data
    
    if not region or not rv3d:
        return
    
    for obj_name, data in list(_annotation_registry.items()):
        if not data.get('visible', True):
            continue
        
        annotation_type = data.get('type', '')
        
        if annotation_type == AnnotationType.DISTANCE:
            draw_distance_annotation(obj_name, data, region, rv3d)
        elif annotation_type == AnnotationType.DISTANCE_TEMP:
            draw_distance_temp_annotation(data, region, rv3d)
        elif annotation_type == AnnotationType.ANGLE:
            draw_angle_annotation(obj_name, data, region, rv3d)
        elif annotation_type == AnnotationType.ANGLE_TEMP:
            draw_angle_temp_annotation(data, region, rv3d)
        elif annotation_type == AnnotationType.EDGE_ANGLE:
            draw_edge_angle_annotation(data, region, rv3d)
        elif annotation_type == AnnotationType.EDGE_LENGTH:
            draw_edge_length_annotation(data, region, rv3d)
        elif annotation_type == AnnotationType.VERTEX_ANGLES:
            draw_vertex_angles_annotation(data, region, rv3d)
        elif annotation_type == AnnotationType.LINE_ANGLES:
            draw_line_angles_annotation(data, region, rv3d)
        elif annotation_type == AnnotationType.RADIUS:
            draw_radius_annotation(obj_name, data, region, rv3d)
        elif annotation_type == AnnotationType.RADIUS_TEMP:
            draw_radius_temp_annotation(data, region, rv3d)


# ==================== 绘制辅助函数（使用 LabelRenderer）====================

def draw_distance_label(screen_pos, distance):
    """绘制单个距离标签"""
    text = Config.DISTANCE_FORMAT.format(distance)
    LabelRenderer.draw_single_line_label(
        screen_pos, text,
        text_color=Config.Colors.TEXT_PRIMARY,
        bg_color=get_bg_color('distance'),
        font_size=get_font_size()
    )


def draw_angle_label(screen_pos, angle_deg, bend_angle):
    """绘制角度标签（两行）"""
    lines = [
        f"法线夹角: {angle_deg:.2f}°",
        f"弯曲角度: {bend_angle:.2f}°"
    ]
    colors = [Config.Colors.TEXT_PRIMARY, Config.Colors.TEXT_HIGHLIGHT]
    LabelRenderer.draw_multi_line_label(
        screen_pos, lines, colors,
        bg_color=get_bg_color('angle'),
        font_size=get_font_size()
    )


def draw_radius_label(screen_pos, radius, diameter, is_circle):
    """绘制半径/直径标签"""
    if is_circle:
        text1 = f"半径: {radius:.6f} m"
        text2 = f"直径: {diameter:.6f} m"
    else:
        text1 = f"半距: {radius:.6f} m"
        text2 = f"全距: {diameter:.6f} m"
    
    lines = [text1, text2]
    colors = [Config.Colors.TEXT_PRIMARY, Config.Colors.TEXT_HIGHLIGHT]
    LabelRenderer.draw_multi_line_label(
        screen_pos, lines, colors,
        bg_color=get_bg_color('radius'),
        font_size=get_font_size()
    )


def draw_edge_angle_label(screen_pos, angle_deg, supplement):
    """绘制边夹角标签"""
    lines = [
        f"夹角: {angle_deg:.2f}°",
        f"补角: {supplement:.2f}°"
    ]
    colors = [Config.Colors.TEXT_PRIMARY, Config.Colors.TEXT_HIGHLIGHT]
    LabelRenderer.draw_multi_line_label(
        screen_pos, lines, colors,
        bg_color=get_bg_color('edge_angle'),
        font_size=get_font_size()
    )


# ==================== 具体绘制函数 ====================

def draw_distance_annotation(obj_name, data, region, rv3d):
    """绘制距离标注"""
    obj = bpy.data.objects.get(obj_name)
    if not obj or obj.type != 'MESH':
        return
    
    mesh = obj.data
    edge_indices = data.get('edge_indices', [])
    measure_mode = data.get('measure_mode', 'CENTER_DISTANCE')
    
    if measure_mode == 'CENTER_DISTANCE':
        stored_distance = data.get('distance')
        if stored_distance is not None and len(mesh.edges) > 0:
            edge = mesh.edges[0]
            v1_local = mesh.vertices[edge.vertices[0]].co
            v2_local = mesh.vertices[edge.vertices[1]].co
            v1_world = obj.matrix_world @ v1_local
            v2_world = obj.matrix_world @ v2_local
            mid_point = (v1_world + v2_world) / 2
            
            screen_pos = location_3d_to_region_2d(region, rv3d, mid_point)
            if screen_pos:
                draw_distance_label(screen_pos, stored_distance)
        return
    
    for edge_idx in edge_indices:
        if not isinstance(edge_idx, int) or edge_idx >= len(mesh.edges):
            continue
        
        edge = mesh.edges[edge_idx]
        v1_idx, v2_idx = edge.vertices
        
        v1_local = mesh.vertices[v1_idx].co
        v2_local = mesh.vertices[v2_idx].co
        v1_world = obj.matrix_world @ v1_local
        v2_world = obj.matrix_world @ v2_local
        
        distance = (v2_world - v1_world).length
        mid_point = (v1_world + v2_world) / 2
        
        screen_pos = location_3d_to_region_2d(region, rv3d, mid_point)
        if screen_pos is None:
            continue
        
        draw_distance_label(screen_pos, distance)


def draw_distance_temp_annotation(data, region, rv3d):
    """绘制临时距离标注"""
    points = data.get('points', [])
    if len(points) < 2:
        return
    
    stored_distance = data.get('distance')
    if stored_distance is not None:
        p1 = points[0]
        p2 = points[1]
        mid_point = (p1 + p2) / 2
        screen_pos = location_3d_to_region_2d(region, rv3d, mid_point)
        if screen_pos:
            draw_distance_label(screen_pos, stored_distance)
        return
    
    for i in range(len(points) - 1):
        p1 = points[i]
        p2 = points[i + 1]
        distance = (p2 - p1).length
        mid_point = (p1 + p2) / 2
        
        screen_pos = location_3d_to_region_2d(region, rv3d, mid_point)
        if screen_pos:
            draw_distance_label(screen_pos, distance)


def draw_angle_annotation(obj_name, data, region, rv3d):
    """绘制角度标注"""
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
    """绘制两边夹角标注"""
    edge_refs = data.get('edge_refs', [])
    
    if len(edge_refs) == 2:
        obj_name1, v1_idx1, v2_idx1 = edge_refs[0]
        obj_name2, v1_idx2, v2_idx2 = edge_refs[1]
        
        v1_1, v2_1 = get_edge_world_coords_realtime(obj_name1, v1_idx1, v2_idx1)
        v1_2, v2_2 = get_edge_world_coords_realtime(obj_name2, v1_idx2, v2_idx2)
        
        if v1_1 is None or v2_1 is None or v1_2 is None or v2_2 is None:
            return
        
        dir1 = (v2_1 - v1_1).normalized()
        dir2 = (v2_2 - v1_2).normalized()
        mid1 = (v1_1 + v2_1) / 2
        mid2 = (v1_2 + v2_2) / 2
        
        dot_product = dir1.dot(dir2)
        dot_product = max(-1.0, min(1.0, dot_product))
        angle_rad = math.acos(abs(dot_product))
        angle_deg = math.degrees(angle_rad)
        supplement = 180.0 - angle_deg
        
        center = (mid1 + mid2) / 2
    else:
        center = data.get('center')
        angle_deg = data.get('angle', 0)
        supplement = data.get('supplement', 0)
        
        if center is None:
            return
    
    screen_pos = location_3d_to_region_2d(region, rv3d, center)
    if screen_pos is None:
        return
    
    draw_edge_angle_label(screen_pos, angle_deg, supplement)


def draw_edge_length_annotation(data, region, rv3d):
    """绘制边长标注"""
    edge_data = data.get('edge_data', [])
    
    if not edge_data:
        return
    
    for obj_name, edge_idx, v1_idx, v2_idx in edge_data:
        v1_world, v2_world = get_edge_world_coords_realtime(obj_name, v1_idx, v2_idx)
        if v1_world is None or v2_world is None:
            continue
        
        mid_point = (v1_world + v2_world) / 2
        length = (v2_world - v1_world).length
        
        screen_pos = location_3d_to_region_2d(region, rv3d, mid_point)
        if screen_pos is None:
            continue
        
        text = Config.DISTANCE_FORMAT_SHORT.format(length)
        LabelRenderer.draw_single_line_label(
            screen_pos, text,
            text_color=Config.Colors.TEXT_PRIMARY,
            bg_color=get_bg_color('edge_length'),
            font_size=Config.SMALL_FONT_SIZE
        )


def draw_vertex_angles_annotation(data, region, rv3d):
    """绘制顶点角度标注"""
    vert_refs = data.get('vert_refs', [])
    
    if len(vert_refs) < 3:
        return
    
    vertices_world = [get_vertex_world_coord_realtime(name, idx) for name, idx in vert_refs]
    vertices_world = [v for v in vertices_world if v is not None]
    
    if len(vertices_world) < 3:
        return
    
    # 对点进行凸包排序
    def sort_points_convex_draw(points):
        if len(points) < 3:
            return points, list(range(len(points)))
        
        center = Vector((0, 0, 0))
        for p in points:
            center += p
        center /= len(points)
        
        v1 = points[1] - points[0]
        v2 = points[2] - points[0]
        normal = v1.cross(v2)
        
        if normal.length < Config.COORDINATE_EPSILON:
            for i in range(len(points)):
                for j in range(i+1, len(points)):
                    for k in range(j+1, len(points)):
                        v1 = points[j] - points[i]
                        v2 = points[k] - points[i]
                        normal = v1.cross(v2)
                        if normal.length > Config.COORDINATE_EPSILON:
                            break
                    if normal.length > Config.COORDINATE_EPSILON:
                        break
                if normal.length > Config.COORDINATE_EPSILON:
                    break
        
        if normal.length < Config.COORDINATE_EPSILON:
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
    
    vertices_world, sort_order = sort_points_convex_draw(vertices_world)
    
    def calc_angle_at_vertex(p1, vertex, p2):
        v1 = (p1 - vertex).normalized()
        v2 = (p2 - vertex).normalized()
        dot = max(-1.0, min(1.0, v1.dot(v2)))
        return math.degrees(math.acos(dot))
    
    n = len(vertices_world)
    
    angles = []
    for i in range(n):
        p_prev = vertices_world[(i - 1) % n]
        p_curr = vertices_world[i]
        p_next = vertices_world[(i + 1) % n]
        angle = calc_angle_at_vertex(p_prev, p_curr, p_next)
        angles.append(angle)
    
    for i, (point, angle) in enumerate(zip(vertices_world, angles)):
        if angle is None:
            continue
            
        screen_pos = location_3d_to_region_2d(region, rv3d, point)
        if screen_pos is None:
            continue
        
        # 偏移显示，避免遮挡顶点
        offset_pos = (screen_pos[0] + 20, screen_pos[1] + 20)
        
        text = f"{i+1}: {angle:.2f}°"
        LabelRenderer.draw_single_line_label(
            offset_pos, text,
            text_color=Config.Colors.TEXT_ANGLE_YELLOW,
            bg_color=get_bg_color('vertex_angle'),
            font_size=Config.MINI_FONT_SIZE,
            padding=Config.LABEL_PADDING_SMALL
        )


def draw_line_angles_annotation(data, region, rv3d):
    """绘制线段与坐标轴夹角标注"""
    vert_refs = data.get('vert_refs', [])
    
    if len(vert_refs) == 2:
        p1 = get_vertex_world_coord_realtime(*vert_refs[0])
        p2 = get_vertex_world_coord_realtime(*vert_refs[1])
        
        if p1 is None or p2 is None:
            return
        
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
        
        horizontal = Vector((direction.x, direction.y, 0))
        if horizontal.length > Config.COORDINATE_EPSILON:
            horizontal = horizontal.normalized()
            dot = direction.dot(horizontal)
            dot = max(-1.0, min(1.0, dot))
            angle_horizontal = math.degrees(math.acos(dot))
        else:
            angle_horizontal = 90.0
    else:
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
    
    lines = [
        f"X轴: {angle_x:.2f}°",
        f"Y轴: {angle_y:.2f}°",
        f"Z轴: {angle_z:.2f}°",
        f"水平: {angle_horizontal:.2f}°",
    ]
    colors = [
        Config.Colors.AXIS_X,
        Config.Colors.AXIS_Y,
        Config.Colors.AXIS_Z,
        Config.Colors.AXIS_HORIZONTAL,
    ]
    
    LabelRenderer.draw_multi_line_label(
        screen_pos, lines, colors,
        bg_color=get_bg_color('line_angle'),
        font_size=Config.MINI_FONT_SIZE,
        padding=12,
        line_height=Config.LINE_HEIGHT_MINI,
        line_spacing=Config.LINE_SPACING_SMALL
    )


def draw_radius_annotation(obj_name, data, region, rv3d):
    """绘制半径/直径标注"""
    obj = bpy.data.objects.get(obj_name)
    if not obj or obj.type != 'MESH':
        return
    
    mesh = obj.data
    center_vert_idx = data.get('center_vert_idx', 0)
    is_circle = data.get('is_circle', True)
    
    if center_vert_idx >= len(mesh.vertices):
        return
    
    center_local = mesh.vertices[center_vert_idx].co
    center_world = obj.matrix_world @ center_local
    
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
    bl_options = {'REGISTER', 'UNDO'}
    
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


class OBJECT_OT_clear_distance_display(Operator):
    """清除3D视图中的所有标注"""
    bl_idname = "object.clear_distance_display"
    bl_label = "清除标注"
    bl_options = {"REGISTER"}

    def execute(self, context):
        clear_all_annotations()
        
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
        
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        status = "显示" if visible else "隐藏"
        self.report({'INFO'}, f"标注已{status}")
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
    OBJECT_OT_clear_distance_display,
    OBJECT_OT_toggle_annotations,
)
