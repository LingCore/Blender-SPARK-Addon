# ==================== 标注绘制模块 ====================
"""
bofu_enhanced/annotation_draw.py

标注系统的所有绘制函数和分派表。
"""

import bpy
import math
from mathutils import Vector
from bpy_extras.view3d_utils import location_3d_to_region_2d

from .config import Config, AnnotationType
from .render_utils import LabelRenderer, get_font_size, get_bg_color, invalidate_pref_cache
from .utils import get_vertex_world_coord_realtime, get_edge_world_coords_realtime, calc_arc_data


# ==================== 统一绘制回调 ====================

def unified_draw_callback():
    """统一的标注绘制回调函数（已优化）"""
    from .annotation_core import AnnotationManager, is_visible

    if not is_visible():
        return

    context = bpy.context
    region = context.region
    rv3d = context.region_data

    if not region or not rv3d:
        return

    # ★ 性能优化 3：每帧重置偏好缓存，确保每帧最多查询一次偏好设置
    invalidate_pref_cache()

    # ★ 性能优化 8：预建对象查找缓存，避免重复 bpy.data.objects.get()
    _obj_cache.clear()

    registry = AnnotationManager.get_registry()
    for obj_name, data in registry.items():
        if not data.get('visible', True):
            continue

        annotation_type = data.get('type', '')
        entry = _DRAW_DISPATCH.get(annotation_type)
        if entry:
            draw_fn, needs_name = entry
            if needs_name:
                draw_fn(obj_name, data, region, rv3d)
            else:
                draw_fn(data, region, rv3d)


# ==================== 对象查找缓存 ====================
# ★ 性能优化 8：避免同一帧内对同一对象名重复调用 bpy.data.objects.get()

_obj_cache = {}
_SENTINEL = object()  # 用于区分"未缓存"和"缓存了 None"


def _get_obj_cached(obj_name):
    """带帧缓存的对象查找（同一帧内缓存结果）"""
    result = _obj_cache.get(obj_name, _SENTINEL)
    if result is not _SENTINEL:
        return result
    obj = bpy.data.objects.get(obj_name)
    _obj_cache[obj_name] = obj  # 缓存，包括 None
    return obj


# ==================== 绘制辅助函数 ====================

def draw_distance_label(screen_pos, distance):
    text = Config.DISTANCE_FORMAT.format(distance)
    LabelRenderer.draw_single_line_label(
        screen_pos, text,
        text_color=Config.Colors.TEXT_PRIMARY,
        bg_color=get_bg_color('distance'),
        font_size=get_font_size()
    )


def draw_angle_label(screen_pos, angle_deg, bend_angle):
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
    obj = _get_obj_cached(obj_name)
    if not obj or obj.type != 'MESH':
        return

    mesh = obj.data
    edge_indices = data.get('edge_indices', [])
    measure_mode = data.get('measure_mode', 'CENTER_DISTANCE')

    if measure_mode == 'CENTER_DISTANCE':
        stored_distance = data.get('distance')
        if stored_distance is not None and len(mesh.edges) > 0:
            edge = mesh.edges[0]
            v1_world = obj.matrix_world @ mesh.vertices[edge.vertices[0]].co
            v2_world = obj.matrix_world @ mesh.vertices[edge.vertices[1]].co
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
        v1_world = obj.matrix_world @ mesh.vertices[v1_idx].co
        v2_world = obj.matrix_world @ mesh.vertices[v2_idx].co
        distance = (v2_world - v1_world).length
        mid_point = (v1_world + v2_world) / 2
        screen_pos = location_3d_to_region_2d(region, rv3d, mid_point)
        if screen_pos is not None:
            draw_distance_label(screen_pos, distance)


def draw_distance_temp_annotation(data, region, rv3d):
    points = data.get('points', [])
    if len(points) < 2:
        return

    stored_distance = data.get('distance')
    if stored_distance is not None:
        mid_point = (points[0] + points[1]) / 2
        screen_pos = location_3d_to_region_2d(region, rv3d, mid_point)
        if screen_pos:
            draw_distance_label(screen_pos, stored_distance)
        return

    for i in range(len(points) - 1):
        p1, p2 = points[i], points[i + 1]
        distance = (p2 - p1).length
        mid_point = (p1 + p2) / 2
        screen_pos = location_3d_to_region_2d(region, rv3d, mid_point)
        if screen_pos:
            draw_distance_label(screen_pos, distance)


def draw_angle_annotation(obj_name, data, region, rv3d):
    obj = _get_obj_cached(obj_name)
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
    center = data.get('center')
    if center is None:
        return
    screen_pos = location_3d_to_region_2d(region, rv3d, center)
    if screen_pos:
        draw_angle_label(screen_pos, data.get('angle', 0), data.get('bend', 0))


def draw_edge_angle_annotation(data, region, rv3d):
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
        dot_product = max(-1.0, min(1.0, dir1.dot(dir2)))
        angle_rad = math.acos(abs(dot_product))
        angle_deg = math.degrees(angle_rad)
        supplement = 180.0 - angle_deg
        center = ((v1_1 + v2_1) / 2 + (v1_2 + v2_2) / 2) / 2
    else:
        center = data.get('center')
        angle_deg = data.get('angle', 0)
        supplement = data.get('supplement', 0)
        if center is None:
            return

    screen_pos = location_3d_to_region_2d(region, rv3d, center)
    if screen_pos is not None:
        draw_edge_angle_label(screen_pos, angle_deg, supplement)


def draw_edge_length_annotation(data, region, rv3d):
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
    vert_refs = data.get('vert_refs', [])
    if len(vert_refs) < 3:
        return

    vertices_world = [get_vertex_world_coord_realtime(name, idx) for name, idx in vert_refs]
    vertices_world = [v for v in vertices_world if v is not None]
    if len(vertices_world) < 3:
        return

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
                for j in range(i + 1, len(points)):
                    for k in range(j + 1, len(points)):
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
        up = Vector((0, 0, 1)) if abs(normal.z) < 0.9 else Vector((1, 0, 0))
        local_x = up.cross(normal).normalized()
        local_y = normal.cross(local_x).normalized()

        def get_angle(p):
            rel = p - center
            return math.atan2(rel.dot(local_y), rel.dot(local_x))

        indexed = [(get_angle(p), i) for i, p in enumerate(points)]
        indexed.sort(key=lambda x: x[0])
        return [points[i] for _, i in indexed], [i for _, i in indexed]

    vertices_world, sort_order = sort_points_convex_draw(vertices_world)

    def calc_angle_at_vertex(p1, vertex, p2):
        va = (p1 - vertex).normalized()
        vb = (p2 - vertex).normalized()
        dot = max(-1.0, min(1.0, va.dot(vb)))
        return math.degrees(math.acos(dot))

    n = len(vertices_world)
    angles = []
    for i in range(n):
        angle = calc_angle_at_vertex(
            vertices_world[(i - 1) % n],
            vertices_world[i],
            vertices_world[(i + 1) % n],
        )
        angles.append(angle)

    for i, (point, angle) in enumerate(zip(vertices_world, angles)):
        if angle is None:
            continue
        screen_pos = location_3d_to_region_2d(region, rv3d, point)
        if screen_pos is None:
            continue
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
    vert_refs = data.get('vert_refs', [])

    if len(vert_refs) == 2:
        p1 = get_vertex_world_coord_realtime(*vert_refs[0])
        p2 = get_vertex_world_coord_realtime(*vert_refs[1])
        if p1 is None or p2 is None:
            return

        direction = (p2 - p1).normalized()
        center = (p1 + p2) / 2

        def angle_with_axis(dir_vec, axis):
            dot = max(-1.0, min(1.0, abs(dir_vec.dot(axis))))
            return math.degrees(math.acos(dot))

        angle_x = angle_with_axis(direction, Vector((1, 0, 0)))
        angle_y = angle_with_axis(direction, Vector((0, 1, 0)))
        angle_z = angle_with_axis(direction, Vector((0, 0, 1)))

        horizontal = Vector((direction.x, direction.y, 0))
        if horizontal.length > Config.COORDINATE_EPSILON:
            horizontal = horizontal.normalized()
            dot = max(-1.0, min(1.0, direction.dot(horizontal)))
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

    lines = [f"X轴: {angle_x:.2f}°", f"Y轴: {angle_y:.2f}°", f"Z轴: {angle_z:.2f}°", f"水平: {angle_horizontal:.2f}°"]
    colors = [Config.Colors.AXIS_X, Config.Colors.AXIS_Y, Config.Colors.AXIS_Z, Config.Colors.AXIS_HORIZONTAL]
    LabelRenderer.draw_multi_line_label(
        screen_pos, lines, colors,
        bg_color=get_bg_color('line_angle'),
        font_size=Config.MINI_FONT_SIZE,
        padding=12,
        line_height=Config.LINE_HEIGHT_MINI,
        line_spacing=Config.LINE_SPACING_SMALL
    )


def draw_radius_annotation(obj_name, data, region, rv3d):
    obj = _get_obj_cached(obj_name)
    if not obj or obj.type != 'MESH':
        return

    mesh = obj.data
    center_vert_idx = data.get('center_vert_idx', 0)
    is_circle = data.get('is_circle', True)

    if center_vert_idx >= len(mesh.vertices):
        return

    center_world = obj.matrix_world @ mesh.vertices[center_vert_idx].co

    if len(mesh.edges) > 0:
        edge = mesh.edges[0]
        other_idx = edge.vertices[1] if edge.vertices[0] == center_vert_idx else edge.vertices[0]
        other_world = obj.matrix_world @ mesh.vertices[other_idx].co
        radius = (other_world - center_world).length
        diameter = radius * 2
    else:
        radius = 0
        diameter = 0

    screen_pos = location_3d_to_region_2d(region, rv3d, center_world)
    if screen_pos:
        draw_radius_label(screen_pos, radius, diameter, is_circle)


def draw_radius_temp_annotation(data, region, rv3d):
    center = data.get('center')
    if center is None:
        return
    screen_pos = location_3d_to_region_2d(region, rv3d, center)
    if screen_pos:
        draw_radius_label(screen_pos, data.get('radius', 0), data.get('diameter', 0), data.get('is_circle', True))


def draw_face_area_label(screen_pos, area, is_total=False):
    if is_total:
        text = f"总面积: {Config.AREA_FORMAT.format(area)}"
    else:
        text = Config.AREA_FORMAT.format(area)
    LabelRenderer.draw_single_line_label(
        screen_pos, text,
        text_color=Config.Colors.TEXT_PRIMARY if not is_total else Config.Colors.TEXT_HIGHLIGHT,
        bg_color=get_bg_color('face_area'),
        font_size=get_font_size() if not is_total else Config.DEFAULT_FONT_SIZE
    )


def draw_face_area_annotation(data, region, rv3d):
    face_data = data.get('face_data', [])
    if not face_data:
        return

    all_centers = []
    all_areas = []

    for face_info in face_data:
        obj_name = face_info.get('obj_name')
        vert_indices = face_info.get('vert_indices', [])
        verts_world = [v for v in (get_vertex_world_coord_realtime(obj_name, idx) for idx in vert_indices) if v is not None]
        if len(verts_world) < 3:
            continue

        center = sum(verts_world, Vector((0, 0, 0))) / len(verts_world)
        all_centers.append(center)

        area = 0.0
        n = len(verts_world)
        for i in range(n):
            v1 = verts_world[i] - center
            v2 = verts_world[(i + 1) % n] - center
            area += v1.cross(v2).length / 2
        all_areas.append(area)

        screen_pos = location_3d_to_region_2d(region, rv3d, center)
        if screen_pos:
            draw_face_area_label(screen_pos, area, is_total=False)

    if len(all_areas) > 1 and all_centers:
        overall_center = sum(all_centers, Vector((0, 0, 0))) / len(all_centers)
        screen_pos = location_3d_to_region_2d(region, rv3d, overall_center)
        if screen_pos:
            draw_face_area_label((screen_pos[0], screen_pos[1] - 40), sum(all_areas), is_total=True)


def draw_perimeter_label(screen_pos, perimeter, is_total=False, mode='face'):
    if mode == 'face':
        text = f"总周长: {Config.DISTANCE_FORMAT.format(perimeter)}" if is_total else f"周长: {Config.DISTANCE_FORMAT_SHORT.format(perimeter)}"
    else:
        text = f"总长度: {Config.DISTANCE_FORMAT.format(perimeter)}" if is_total else Config.DISTANCE_FORMAT_SHORT.format(perimeter)
    LabelRenderer.draw_single_line_label(
        screen_pos, text,
        text_color=Config.Colors.TEXT_PRIMARY if not is_total else Config.Colors.TEXT_HIGHLIGHT,
        bg_color=get_bg_color('perimeter'),
        font_size=get_font_size() if not is_total else Config.DEFAULT_FONT_SIZE
    )


def draw_perimeter_annotation(data, region, rv3d):
    mode = data.get('mode', 'face')
    all_centers = []

    if mode == 'face':
        perimeter_data = data.get('perimeter_data', [])
        if not perimeter_data:
            return

        all_perimeters = []
        for peri_info in perimeter_data:
            obj_name = peri_info.get('obj_name')
            vert_indices = peri_info.get('vert_indices', [])
            verts_world = [v for v in (get_vertex_world_coord_realtime(obj_name, idx) for idx in vert_indices) if v is not None]
            if len(verts_world) < 3:
                continue

            center = sum(verts_world, Vector((0, 0, 0))) / len(verts_world)
            all_centers.append(center)

            perimeter = sum((verts_world[(i + 1) % len(verts_world)] - verts_world[i]).length for i in range(len(verts_world)))
            all_perimeters.append(perimeter)

            screen_pos = location_3d_to_region_2d(region, rv3d, center)
            if screen_pos:
                draw_perimeter_label(screen_pos, perimeter, is_total=False, mode='face')

        if len(all_perimeters) > 1 and all_centers:
            overall_center = sum(all_centers, Vector((0, 0, 0))) / len(all_centers)
            screen_pos = location_3d_to_region_2d(region, rv3d, overall_center)
            if screen_pos:
                draw_perimeter_label((screen_pos[0], screen_pos[1] - 40), sum(all_perimeters), is_total=True, mode='face')
    else:
        edge_data = data.get('edge_data', [])
        if not edge_data:
            return

        all_lengths = []
        for edge_info in edge_data:
            v1_world, v2_world = get_edge_world_coords_realtime(edge_info.get('obj_name'), edge_info.get('v1_idx'), edge_info.get('v2_idx'))
            if v1_world is None or v2_world is None:
                continue
            mid_point = (v1_world + v2_world) / 2
            all_centers.append(mid_point)
            length = (v2_world - v1_world).length
            all_lengths.append(length)
            screen_pos = location_3d_to_region_2d(region, rv3d, mid_point)
            if screen_pos:
                draw_perimeter_label(screen_pos, length, is_total=False, mode='edge')

        if len(all_lengths) > 1 and all_centers:
            overall_center = sum(all_centers, Vector((0, 0, 0))) / len(all_centers)
            screen_pos = location_3d_to_region_2d(region, rv3d, overall_center)
            if screen_pos:
                draw_perimeter_label((screen_pos[0], screen_pos[1] - 40), sum(all_lengths), is_total=True, mode='edge')


# ==================== 弧长/扇形标注绘制 ====================

def draw_arc_length_label(screen_pos, arc_data):
    lines = [
        f"半径: {arc_data['avg_radius']:.6f} m",
        f"弧角: {arc_data['angle_deg']:.2f}°",
        f"弧长: {arc_data['arc_length']:.6f} m",
        f"弦长: {arc_data['chord_length']:.6f} m",
        f"扇形面积: {arc_data['sector_area']:.6f} m²",
    ]
    colors = [
        Config.Colors.TEXT_PRIMARY,
        Config.Colors.TEXT_HIGHLIGHT,
        Config.Colors.TEXT_PRIMARY,
        Config.Colors.TEXT_PRIMARY,
        Config.Colors.TEXT_PRIMARY,
    ]
    if arc_data.get('radius_diff', 0) > 0.0001:
        lines.append(f"⚠半径偏差: {arc_data['radius_diff']:.6f} m")
        colors.append((1.0, 0.5, 0.3, 1.0))

    LabelRenderer.draw_multi_line_label(
        screen_pos, lines, colors,
        bg_color=get_bg_color('arc_length'),
        font_size=get_font_size(),
        padding=12,
        line_height=Config.LINE_HEIGHT_SMALL,
        line_spacing=Config.LINE_SPACING_SMALL
    )


def draw_arc_length_annotation(obj_name, data, region, rv3d):
    vert_refs = data.get('vert_refs')
    is_bound = data.get('is_bound', False)

    if vert_refs and len(vert_refs) == 3:
        center = get_vertex_world_coord_realtime(*vert_refs[0])
        p_start = get_vertex_world_coord_realtime(*vert_refs[1])
        p_end = get_vertex_world_coord_realtime(*vert_refs[2])
        if center is None or p_start is None or p_end is None:
            return

        arc_data = calc_arc_data(center, p_start, p_end)
        if arc_data is None:
            return

        mid_dir = ((p_start - center).normalized() + (p_end - center).normalized())
        label_pos = center + mid_dir.normalized() * arc_data['avg_radius'] * 0.5 if mid_dir.length > 1e-8 else (p_start + p_end) / 2

        screen_pos = location_3d_to_region_2d(region, rv3d, label_pos)
        if screen_pos:
            draw_arc_length_label(screen_pos, arc_data)

    elif is_bound:
        obj = _get_obj_cached(obj_name)
        if not obj or obj.type != 'MESH':
            return
        mesh = obj.data
        if len(mesh.vertices) < 3:
            return

        center = obj.matrix_world @ mesh.vertices[0].co
        p_start = obj.matrix_world @ mesh.vertices[1].co
        p_end = obj.matrix_world @ mesh.vertices[2].co

        arc_data = calc_arc_data(center, p_start, p_end)
        if arc_data is None:
            return

        mid_dir = ((p_start - center).normalized() + (p_end - center).normalized())
        label_pos = center + mid_dir.normalized() * arc_data['avg_radius'] * 0.5 if mid_dir.length > 1e-8 else (p_start + p_end) / 2

        screen_pos = location_3d_to_region_2d(region, rv3d, label_pos)
        if screen_pos:
            draw_arc_length_label(screen_pos, arc_data)


# ==================== 绘制分派表 ====================

_DRAW_DISPATCH = {
    AnnotationType.DISTANCE:      (draw_distance_annotation, True),
    AnnotationType.DISTANCE_TEMP: (draw_distance_temp_annotation, False),
    AnnotationType.ANGLE:         (draw_angle_annotation, True),
    AnnotationType.ANGLE_TEMP:    (draw_angle_temp_annotation, False),
    AnnotationType.EDGE_ANGLE:    (draw_edge_angle_annotation, False),
    AnnotationType.EDGE_LENGTH:   (draw_edge_length_annotation, False),
    AnnotationType.VERTEX_ANGLES: (draw_vertex_angles_annotation, False),
    AnnotationType.LINE_ANGLES:   (draw_line_angles_annotation, False),
    AnnotationType.RADIUS:        (draw_radius_annotation, True),
    AnnotationType.RADIUS_TEMP:   (draw_radius_temp_annotation, False),
    AnnotationType.FACE_AREA:     (draw_face_area_annotation, False),
    AnnotationType.PERIMETER:     (draw_perimeter_annotation, False),
    AnnotationType.ARC_LENGTH:    (draw_arc_length_annotation, True),
}
