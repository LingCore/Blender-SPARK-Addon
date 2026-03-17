# ==================== 标注系统核心模块 ====================
"""
bofu_enhanced/annotation_core.py

标注系统核心逻辑，包括：
- 全局状态管理
- AnnotationKeyGenerator: 标注唯一性键生成器
- AnnotationManager: 标注管理器
- AnnotationStorage: 标注持久化存储
- AnnotationCleaner: 标注清理器
- 兼容性包装函数
- 绘制处理器 / 定时器管理
"""

import bpy
import bmesh
import logging
import time
import json
from mathutils import Vector

from .config import Config, AnnotationType
from .render_utils import ShaderCache

logger = logging.getLogger(__name__)


# ==================== 全局状态 ====================

_unified_draw_handler = None
_annotation_registry = {}
_annotations_visible = True
_cleanup_timer_running = False


def is_visible():
    return _annotations_visible


# ==================== 标注唯一性键生成器 ====================

class AnnotationKeyGenerator:
    """标注唯一性键生成器"""

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

        elif annotation_type == AnnotationType.ARC_LENGTH:
            if 'vert_refs' in data:
                key = ('arc_length', tuple(data['vert_refs']))
            elif 'center_vert_idx' in data:
                key = ('arc_length_bound', data.get('is_bound', False))

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
            logger.debug("已移除重复标注: %s", name)

        return len(duplicates)

    @staticmethod
    def register(obj_name, annotation_type, data, auto_dedupe=True):
        global _annotation_registry

        if obj_name.startswith("__"):
            temp_count = sum(1 for k in _annotation_registry if k.startswith("__"))
            if temp_count >= AnnotationManager.MAX_TEMP_ANNOTATIONS:
                logger.debug("临时标注数量已达上限 (%d)，自动清理最旧的", AnnotationManager.MAX_TEMP_ANNOTATIONS)
                temp_annotations = [(k, v.get('created_time', 0)) for k, v in _annotation_registry.items() if k.startswith("__")]
                if temp_annotations:
                    oldest = min(temp_annotations, key=lambda x: x[1])[0]
                    del _annotation_registry[oldest]
        else:
            if len(_annotation_registry) >= AnnotationManager.MAX_ANNOTATIONS:
                logger.warning("标注总数已达上限 (%d)，请清理部分标注", AnnotationManager.MAX_ANNOTATIONS)
                return None

        if auto_dedupe:
            removed_count = AnnotationManager.remove_duplicates(annotation_type, data)
            if removed_count > 0:
                logger.debug("自动移除了 %d 个重复标注", removed_count)

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
            logger.debug("已清理已删除对象的标注: %s", obj_name)

        return len(to_remove)


# ==================== 标注持久化存储 ====================

class AnnotationStorage:
    """标注数据持久化存储"""

    STORAGE_KEY = "bofu_annotations_data"

    @staticmethod
    def serialize_vector(vec):
        if vec is None:
            return None
        return [vec.x, vec.y, vec.z]

    @staticmethod
    def deserialize_vector(data):
        if data is None:
            return None
        return Vector(data)

    @staticmethod
    def serialize_annotation(data):
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
        global _annotation_registry
        try:
            data_to_save = {}
            for name, data in _annotation_registry.items():
                if not name.startswith("__"):
                    data_to_save[name] = AnnotationStorage.serialize_annotation(data)

            scene[AnnotationStorage.STORAGE_KEY] = json.dumps(data_to_save)
            logger.info("已保存 %d 个标注到场景", len(data_to_save))
            return True
        except Exception as e:
            logger.warning("保存标注数据失败: %s", e)
            return False

    @staticmethod
    def load_from_scene(scene):
        global _annotation_registry
        try:
            if AnnotationStorage.STORAGE_KEY not in scene:
                return 0

            raw_data = scene[AnnotationStorage.STORAGE_KEY]
            loaded_data = json.loads(raw_data)

            loaded_count = 0
            for name, data in loaded_data.items():
                if name in bpy.data.objects or name.startswith("测量_"):
                    deserialized = AnnotationStorage.deserialize_annotation(data)
                    _annotation_registry[name] = deserialized
                    loaded_count += 1

            logger.info("已从场景加载 %d 个标注", loaded_count)
            return loaded_count
        except Exception as e:
            logger.warning("加载标注数据失败: %s", e)
            return 0

    @staticmethod
    def clear_from_scene(scene):
        if AnnotationStorage.STORAGE_KEY in scene:
            del scene[AnnotationStorage.STORAGE_KEY]
            logger.debug("已清除场景中的标注数据")


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

        if select_mode[2]:
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

        elif select_mode[1]:
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

        else:
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
    return AnnotationManager.unregister(obj_name)


def clear_all_annotations():
    return AnnotationManager.clear_all()


def clear_temp_annotations():
    return AnnotationManager.clear_temp()


def get_temp_annotation_count():
    return AnnotationManager.get_temp_count()


def get_bound_annotation_count():
    return AnnotationManager.get_bound_count()


def toggle_annotations_visibility():
    global _annotations_visible
    _annotations_visible = not _annotations_visible
    return _annotations_visible


def cleanup_deleted_objects():
    return AnnotationManager.cleanup_deleted_objects()


# ==================== 绘制处理器 / 定时器管理 ====================

def _cleanup_timer_callback():
    cleanup_deleted_objects()
    return Config.CLEANUP_INTERVAL


def ensure_cleanup_timer():
    global _cleanup_timer_running
    if not _cleanup_timer_running:
        if not bpy.app.timers.is_registered(_cleanup_timer_callback):
            bpy.app.timers.register(_cleanup_timer_callback, first_interval=Config.CLEANUP_INTERVAL, persistent=True)
        _cleanup_timer_running = True


def stop_cleanup_timer():
    global _cleanup_timer_running
    if bpy.app.timers.is_registered(_cleanup_timer_callback):
        bpy.app.timers.unregister(_cleanup_timer_callback)
    _cleanup_timer_running = False


def ensure_draw_handler_enabled():
    global _unified_draw_handler
    if _unified_draw_handler is None:
        from .annotation_draw import unified_draw_callback
        _unified_draw_handler = bpy.types.SpaceView3D.draw_handler_add(
            unified_draw_callback, (), 'WINDOW', 'POST_PIXEL'
        )
    ensure_cleanup_timer()


def disable_draw_handler():
    global _unified_draw_handler

    stop_cleanup_timer()

    if _unified_draw_handler is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_unified_draw_handler, 'WINDOW')
            logger.debug("绘制处理器已移除")
        except Exception as e:
            logger.warning("移除绘制处理器失败: %s", e)
        finally:
            _unified_draw_handler = None

    ShaderCache.clear()
