# ==================== 测量操作符模块 ====================
"""
bofu_enhanced/operators_measure.py

智能测量相关操作符

重构后的结构：
- OBJECT_OT_connect_origins: 主操作符类
- 各测量模式的执行逻辑拆分为独立方法
- numpy 导入优雅处理
"""

import bpy
import bmesh
import math
from bpy.types import Operator
from bpy.props import EnumProperty, BoolProperty, FloatProperty
from mathutils import Vector

from .config import Config, MeasureMode, AnnotationType
from .utils import get_unique_measure_name, calc_arc_data
from .annotation import register_annotation, ensure_draw_handler_enabled


# ==================== numpy 检测 ====================

_numpy_available = None

def check_numpy():
    """检查 numpy 是否可用"""
    global _numpy_available
    if _numpy_available is None:
        try:
            import numpy
            _numpy_available = True
        except ImportError:
            _numpy_available = False
    return _numpy_available


# ==================== 辅助函数 ====================

def refresh_3d_views(context):
    """刷新所有3D视图"""
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


def get_selected_centers(edit_objects, select_mode):
    """
    获取编辑模式下选中元素的中心点
    
    返回: 世界坐标中心点列表
    """
    centers = []
    
    if select_mode[2]:  # 面模式
        for obj in edit_objects:
            bm_read = bmesh.from_edit_mesh(obj.data)
            bm_read.faces.ensure_lookup_table()
            for f in bm_read.faces:
                if f.select:
                    face_center = f.calc_center_median()
                    world_center = obj.matrix_world @ face_center
                    centers.append(world_center.copy())
    elif select_mode[1]:  # 边模式
        for obj in edit_objects:
            bm_read = bmesh.from_edit_mesh(obj.data)
            bm_read.edges.ensure_lookup_table()
            for e in bm_read.edges:
                if e.select:
                    v1_world = obj.matrix_world @ e.verts[0].co
                    v2_world = obj.matrix_world @ e.verts[1].co
                    edge_center = (v1_world + v2_world) / 2
                    centers.append(edge_center.copy())
    else:  # 顶点模式
        for obj in edit_objects:
            bm_read = bmesh.from_edit_mesh(obj.data)
            bm_read.verts.ensure_lookup_table()
            for v in bm_read.verts:
                if v.select:
                    world_co = obj.matrix_world @ v.co
                    centers.append(world_co.copy())
    
    return centers


def get_mode_name(select_mode):
    """获取当前选择模式名称"""
    if select_mode[2]:
        return "面"
    elif select_mode[1]:
        return "边"
    return "顶点"


def create_measure_object(context, name, points, edges_definition):
    """
    创建测量辅助几何体
    
    参数:
        context: Blender context
        name: 对象名称
        points: 顶点坐标列表
        edges_definition: 边定义，如 [(0, 1), (1, 2)]
    
    返回: 创建的对象
    """
    obj_name = get_unique_measure_name(name)
    mesh = bpy.data.meshes.new(obj_name)
    measure_obj = bpy.data.objects.new(obj_name, mesh)
    context.collection.objects.link(measure_obj)
    
    bm = bmesh.new()
    verts = [bm.verts.new(p) for p in points]
    bm.verts.ensure_lookup_table()
    
    for v1_idx, v2_idx in edges_definition:
        bm.edges.new((verts[v1_idx], verts[v2_idx]))
    
    bm.to_mesh(mesh)
    bm.free()
    
    return measure_obj


# ==================== 主操作符类 ====================

class OBJECT_OT_connect_origins(Operator):
    """智能测量工具：支持距离、角度、半径等多种测量模式"""
    bl_idname = "object.connect_origins"
    bl_label = "智能测量"
    bl_options = {"REGISTER", "UNDO"}
    
    measure_mode: EnumProperty(
        name="测量模式",
        items=[
            (MeasureMode.CENTER_DISTANCE, '通用距离', '测量点/线/面之间的距离，支持灵活的轴锁定（可锁定0/1/2个轴）'),
            (MeasureMode.EDGE_LENGTH, '边长测量', '测量选中边的长度（不创建几何体）'),
            (MeasureMode.XYZ_SPLIT, '分轴测量（XYZ）', '同时显示X、Y、Z三个方向的距离（自动跳过无差异的轴）'),
            (MeasureMode.ANGLE_EDGES, '两边夹角', '选择2条边，计算两条边的夹角'),
            (MeasureMode.ANGLE_FACES, '两面夹角', '选择2个面，计算法线夹角（适用于弯管、弯头等）'),
            (MeasureMode.ANGLE_VERTS, '顶点角度', '2点:线段与轴夹角; 3+点:每个顶点的角度（不创建几何体）'),
            (MeasureMode.RADIUS, '半距/全距（半径/直径）', '选择2个点/边/面，计算距离的一半和全长；或选择1个圆形面/3+个点拟合圆'),
            (MeasureMode.FACE_AREA, '面积测量', '测量选中面的面积，支持单面和多面总计（不创建几何体）'),
            (MeasureMode.PERIMETER, '周长测量', '测量选中面的周长或选中边的总长度（不创建几何体）'),
            (MeasureMode.ARC_LENGTH, '弧长/扇形（运动学）', '选3个点(圆心+起点+终点)，计算弧长、弧角、弦长、扇形面积（适用于凸轮、齿轮、曲柄等）'),
        ],
        default=MeasureMode.CENTER_DISTANCE,
    )
    
    create_geometry: BoolProperty(
        name="创建辅助几何体",
        description="是否创建连线/标记点（关闭则只显示数据标注）",
        default=True,
    )
    
    center_offset_x: FloatProperty(name="X偏移", default=0.0, unit='LENGTH')
    center_offset_y: FloatProperty(name="Y偏移", default=0.0, unit='LENGTH')
    center_offset_z: FloatProperty(name="Z偏移", default=0.0, unit='LENGTH')
    
    lock_x: BoolProperty(name="锁定X轴", default=False)
    lock_y: BoolProperty(name="锁定Y轴", default=False)
    lock_z: BoolProperty(name="锁定Z轴", default=False)

    @classmethod
    def poll(cls, context):
        return context.mode in {'OBJECT', 'EDIT_MESH'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=320)
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "measure_mode")
        
        if self.measure_mode == MeasureMode.ANGLE_VERTS:
            layout.separator()
            box = layout.box()
            box.label(text="顶点角度模式不创建新几何体", icon='INFO')
            box.label(text="   2点: 计算线段与坐标轴的夹角")
            box.label(text="   3+点: 计算每个顶点的角度")
            self._draw_demo_button(box, MeasureMode.ANGLE_VERTS)
        elif self.measure_mode == MeasureMode.ANGLE_EDGES:
            layout.separator()
            box = layout.box()
            box.label(text="选择2条边，计算夹角", icon='INFO')
            self._draw_demo_button(box, MeasureMode.ANGLE_EDGES)
        elif self.measure_mode == MeasureMode.EDGE_LENGTH:
            layout.separator()
            box = layout.box()
            box.label(text="边长测量模式不创建新几何体", icon='INFO')
            self._draw_demo_button(box, MeasureMode.EDGE_LENGTH)
        elif self.measure_mode == MeasureMode.FACE_AREA:
            layout.separator()
            box = layout.box()
            box.label(text="面积测量模式（需要面选择模式）", icon='INFO')
            box.label(text="   单面: 显示该面面积")
            box.label(text="   多面: 每面面积 + 总面积")
            self._draw_demo_button(box, MeasureMode.FACE_AREA)
        elif self.measure_mode == MeasureMode.PERIMETER:
            layout.separator()
            box = layout.box()
            box.label(text="周长测量模式", icon='INFO')
            box.label(text="   面模式: 计算面的边界周长")
            box.label(text="   边模式: 计算选中边总长度")
            self._draw_demo_button(box, MeasureMode.PERIMETER)
        elif self.measure_mode == MeasureMode.ARC_LENGTH:
            layout.separator()
            box = layout.box()
            box.label(text="弧长/扇形测量（运动学）", icon='CURVE_BEZCURVE')
            box.label(text="   选择3个点: 圆心 + 弧起点 + 弧终点")
            box.label(text="   编辑模式: 顶点模式选3个顶点")
            box.label(text="   物体模式: 活动对象=圆心, 另2个=弧端")
            box.separator()
            box.label(text="计算: 半径/弧角/弧长/弦长/扇形面积", icon='KEYTYPE_KEYFRAME_VEC')
            self._draw_demo_button(box, MeasureMode.ARC_LENGTH)
            layout.separator()
            layout.prop(self, "create_geometry")
        elif self.measure_mode == MeasureMode.CENTER_DISTANCE:
            self._draw_center_distance_options(layout)
        else:
            # XYZ_SPLIT, RADIUS 等其他模式
            layout.separator()
            box = layout.box()
            box.label(text="提示: 点击下方按钮查看演示", icon='INFO')
            self._draw_demo_button(box, self.measure_mode)
            layout.separator()
            layout.prop(self, "create_geometry")
    
    def _draw_center_distance_options(self, layout):
        """绘制通用距离模式的选项"""
        layout.separator()
        box = layout.box()
        box.label(text="通用距离测量（增强版）", icon='INFO')
        layout.separator()
        
        # 轴锁定设置
        box2 = layout.box()
        box2.label(text="轴锁定设置:", icon='LOCKED')
        row = box2.row(align=True)
        row.prop(self, "lock_x", toggle=True)
        row.prop(self, "lock_y", toggle=True)
        row.prop(self, "lock_z", toggle=True)
        
        locked_axes = self._get_locked_axes()
        
        if not locked_axes:
            box2.label(text="   当前: 3D空间距离", icon='EMPTY_AXIS')
        elif len(locked_axes) == 1:
            free_axes = [a for a in ['X', 'Y', 'Z'] if a not in locked_axes]
            box2.label(text=f"   当前: {free_axes[0]}{free_axes[1]}平面距离", icon='MESH_PLANE')
        elif len(locked_axes) == 2:
            free_axis = [a for a in ['X', 'Y', 'Z'] if a not in locked_axes][0]
            box2.label(text=f"   当前: 仅{free_axis}轴方向距离", icon='EMPTY_SINGLE_ARROW')
        else:
            box2.label(text="   不能锁定全部3个轴", icon='ERROR')
        
        # 偏移量设置
        layout.separator()
        box3 = layout.box()
        box3.label(text="偏移量设置:", icon='ORIENTATION_GLOBAL')
        row = box3.row()
        row.prop(self, "center_offset_x", text="X")
        row.prop(self, "center_offset_y", text="Y")
        row.prop(self, "center_offset_z", text="Z")
        layout.prop(self, "create_geometry")
        
        # 演示按钮
        layout.separator()
        self._draw_demo_button(layout, MeasureMode.CENTER_DISTANCE)
    
    # ==================== 演示按钮 ====================
    
    @staticmethod
    def _draw_demo_button(parent_layout, mode):
        """在指定布局中绘制演示按钮"""
        parent_layout.separator()
        row = parent_layout.row()
        row.scale_y = 1.2
        op = row.operator("object.measure_demo", text="演示此模式", icon='PLAY')
        op.demo_mode = mode
    
    # ==================== 计算辅助方法 ====================
    
    def _get_locked_axes(self):
        """获取锁定的轴列表"""
        locked = []
        if self.lock_x:
            locked.append('X')
        if self.lock_y:
            locked.append('Y')
        if self.lock_z:
            locked.append('Z')
        return locked

    def calc_distance(self, p1, p2):
        """计算考虑轴锁定的距离"""
        dx = 0 if self.lock_x else (p2.x - p1.x)
        dy = 0 if self.lock_y else (p2.y - p1.y)
        dz = 0 if self.lock_z else (p2.z - p1.z)
        return math.sqrt(dx**2 + dy**2 + dz**2)
    
    def get_axis_lock_info(self):
        """获取轴锁定信息描述"""
        locked_axes = self._get_locked_axes()
        
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
        """获取用于显示的点（考虑轴锁定）"""
        x = p1.x if self.lock_x else p2.x
        y = p1.y if self.lock_y else p2.y
        z = p1.z if self.lock_z else p2.z
        return p1.copy(), Vector((x, y, z))
    
    def get_offset_vector(self):
        """获取偏移向量"""
        return Vector((self.center_offset_x, self.center_offset_y, self.center_offset_z))
    
    # ==================== 圆拟合方法 ====================
    
    def fit_circle_3d(self, points):
        """
        在3D空间中拟合圆
        
        返回: (center, radius, fit_error) 或 (None, None, None)
        """
        if not check_numpy():
            return None, None, "numpy 未安装"
        
        try:
            import numpy as np
        except ImportError:
            return None, None, "numpy 导入失败"
        
        if len(points) < 3:
            return None, None, None
        
        try:
            pts = np.array([[p.x, p.y, p.z] for p in points])
            centroid = pts.mean(axis=0)
            pts_centered = pts - centroid
            
            cov = np.cov(pts_centered.T)
            eigenvalues, eigenvectors = np.linalg.eigh(cov)
            
            normal = eigenvectors[:, 0]
            u = eigenvectors[:, 1]
            v = eigenvectors[:, 2]
            
            pts_2d = np.column_stack([
                pts_centered.dot(u),
                pts_centered.dot(v)
            ])
            
            A = np.column_stack([2 * pts_2d[:, 0], 2 * pts_2d[:, 1], np.ones(len(pts_2d))])
            b = pts_2d[:, 0]**2 + pts_2d[:, 1]**2
            
            result, residuals, rank, s = np.linalg.lstsq(A, b, rcond=None)
            a, b_val, c = result
            
            r_squared = c + a**2 + b_val**2
            if r_squared <= 0:
                return None, None, None
            radius = np.sqrt(r_squared)
            
            center_3d = centroid + a * u + b_val * v
            
            center_2d = np.array([a, b_val])
            distances_to_center = np.sqrt(np.sum((pts_2d - center_2d)**2, axis=1))
            fit_error = np.mean(np.abs(distances_to_center - radius))
            
            return Vector(center_3d), float(radius), float(fit_error)
            
        except (np.linalg.LinAlgError, ValueError, RuntimeError):
            return None, None, None

    # ==================== 主执行入口 ====================

    def execute(self, context):
        if context.mode == 'EDIT_MESH':
            return self.execute_edit_mode(context)
        else:
            return self.execute_object_mode(context)
    
    # ==================== 编辑模式执行 ====================
    
    def execute_edit_mode(self, context):
        """编辑模式执行入口"""
        edit_objects = [obj for obj in context.objects_in_mode if obj.type == 'MESH']
        
        if not edit_objects:
            self.report({'WARNING'}, "没有处于编辑模式的网格对象")
            return {'CANCELLED'}
        
        select_mode = context.tool_settings.mesh_select_mode
        
        # 根据测量模式分发到不同的方法
        if self.measure_mode == MeasureMode.EDGE_LENGTH:
            return self._measure_edge_length(context, edit_objects)
        
        elif self.measure_mode == MeasureMode.CENTER_DISTANCE:
            return self._measure_center_distance(context, edit_objects, select_mode)
        
        elif self.measure_mode == MeasureMode.ANGLE_EDGES:
            return self._measure_angle_edges(context, edit_objects)
        
        elif self.measure_mode == MeasureMode.ANGLE_FACES:
            return self._measure_angle_faces(context, edit_objects, select_mode)
        
        elif self.measure_mode == MeasureMode.ANGLE_VERTS:
            return self._measure_angle_verts(context, edit_objects)
        
        elif self.measure_mode == MeasureMode.RADIUS:
            return self._measure_radius(context, edit_objects, select_mode)
        
        elif self.measure_mode == MeasureMode.FACE_AREA:
            return self._measure_face_area(context, edit_objects, select_mode)
        
        elif self.measure_mode == MeasureMode.PERIMETER:
            return self._measure_perimeter(context, edit_objects, select_mode)
        
        elif self.measure_mode == MeasureMode.ARC_LENGTH:
            return self._measure_arc_length(context, edit_objects)
        
        # 默认情况
        self.report({'WARNING'}, "不支持的测量模式")
        return {'CANCELLED'}
    
    def _measure_edge_length(self, context, edit_objects):
        """边长测量"""
        edge_data_list = []
        
        for obj in edit_objects:
            bm_read = bmesh.from_edit_mesh(obj.data)
            bm_read.edges.ensure_lookup_table()
            for edge_idx, e in enumerate(bm_read.edges):
                if e.select:
                    edge_data_list.append((obj.name, edge_idx, e.verts[0].index, e.verts[1].index))
        
        if len(edge_data_list) == 0:
            self.report({'WARNING'}, "边长测量模式需要在边选择模式下选择至少1条边")
            return {'CANCELLED'}
        
        register_annotation("__edge_length__", AnnotationType.EDGE_LENGTH, {
            'edge_data': edge_data_list,
        })
        
        ensure_draw_handler_enabled()
        refresh_3d_views(context)
        
        # 计算总长度
        total_length = 0.0
        for obj_name, edge_idx, v1_idx, v2_idx in edge_data_list:
            obj = bpy.data.objects.get(obj_name)
            if obj and obj.type == 'MESH':
                mesh = obj.data
                if v1_idx < len(mesh.vertices) and v2_idx < len(mesh.vertices):
                    v1_world = obj.matrix_world @ mesh.vertices[v1_idx].co
                    v2_world = obj.matrix_world @ mesh.vertices[v2_idx].co
                    total_length += (v2_world - v1_world).length
        
        edge_count = len(edge_data_list)
        if edge_count == 1:
            self.report({'INFO'}, f"边长: {total_length:.6f} m（标注跟随物体）")
        else:
            self.report({'INFO'}, f"选中 {edge_count} 条边，总长度: {total_length:.6f} m（标注跟随物体）")
        
        return {'FINISHED'}
    
    def _measure_center_distance(self, context, edit_objects, select_mode):
        """通用距离测量"""
        centers = get_selected_centers(edit_objects, select_mode)
        
        if len(centers) < 2:
            mode_name = get_mode_name(select_mode)
            self.report({'WARNING'}, f"通用距离模式需要选择至少2个{mode_name}")
            return {'CANCELLED'}
        
        center1, center2 = centers[0], centers[1]
        center2_offset = center2 + self.get_offset_vector()
        
        if self.lock_x and self.lock_y and self.lock_z:
            self.report({'ERROR'}, "不能同时锁定全部3个轴")
            return {'CANCELLED'}
        
        display_p1, display_p2 = self.get_display_points(center1, center2_offset)
        distance = self.calc_distance(center1, center2_offset)
        axis_info = self.get_axis_lock_info()
        
        if self.create_geometry:
            bpy.ops.object.mode_set(mode='OBJECT')
            
            measure_obj = create_measure_object(
                context,
                f"{Config.MEASURE_OBJECT_PREFIX}通用距离",
                [display_p1, display_p2],
                [(0, 1)]
            )
            
            register_annotation(measure_obj.name, AnnotationType.DISTANCE, {
                'measure_mode': MeasureMode.CENTER_DISTANCE,
                'edge_indices': [0],
                'distance': distance,
            })
            
            bpy.ops.object.select_all(action='DESELECT')
            measure_obj.select_set(True)
            context.view_layer.objects.active = measure_obj
        else:
            register_annotation("__center_distance_temp__", AnnotationType.DISTANCE_TEMP, {
                'points': [display_p1.copy(), display_p2.copy()],
                'measure_mode': MeasureMode.CENTER_DISTANCE,
                'distance': distance,
            })
        
        ensure_draw_handler_enabled()
        refresh_3d_views(context)
        
        self.report({'INFO'}, f"距离: {distance:.6f} m（{axis_info}）")
        return {'FINISHED'}
    
    def _measure_angle_edges(self, context, edit_objects):
        """两边夹角测量"""
        edge_refs = []
        
        for obj in edit_objects:
            bm_read = bmesh.from_edit_mesh(obj.data)
            bm_read.edges.ensure_lookup_table()
            for e in bm_read.edges:
                if e.select:
                    edge_refs.append((obj.name, e.verts[0].index, e.verts[1].index))
        
        if len(edge_refs) != 2:
            self.report({'WARNING'}, f"两边夹角模式需要选择恰好2条边，当前选中了{len(edge_refs)}条")
            return {'CANCELLED'}
        
        register_annotation("__edge_angle__", AnnotationType.EDGE_ANGLE, {
            'edge_refs': edge_refs,
        })
        
        ensure_draw_handler_enabled()
        refresh_3d_views(context)
        
        # 计算并显示角度
        def get_edge_direction(obj_name, v1_idx, v2_idx):
            obj = bpy.data.objects.get(obj_name)
            if obj and obj.type == 'MESH':
                mesh = obj.data
                if v1_idx < len(mesh.vertices) and v2_idx < len(mesh.vertices):
                    v1_world = obj.matrix_world @ mesh.vertices[v1_idx].co
                    v2_world = obj.matrix_world @ mesh.vertices[v2_idx].co
                    return (v2_world - v1_world).normalized()
            return None
        
        dir1 = get_edge_direction(*edge_refs[0])
        dir2 = get_edge_direction(*edge_refs[1])
        
        if dir1 and dir2:
            dot_product = max(-1.0, min(1.0, dir1.dot(dir2)))
            angle_rad = math.acos(abs(dot_product))
            angle_deg = math.degrees(angle_rad)
            supplement_angle = 180.0 - angle_deg
            
            self.report({'INFO'}, f"两边夹角: {angle_deg:.2f}°（补角: {supplement_angle:.2f}°）")
        
        return {'FINISHED'}
    
    def _measure_angle_faces(self, context, edit_objects, select_mode):
        """两面夹角测量"""
        if not select_mode[2]:
            self.report({'WARNING'}, "两面夹角模式需要在面选择模式下使用")
            return {'CANCELLED'}
        
        face_normals = []
        face_centers = []
        
        for obj in edit_objects:
            bm_read = bmesh.from_edit_mesh(obj.data)
            bm_read.faces.ensure_lookup_table()
            for f in bm_read.faces:
                if f.select:
                    center_local = f.calc_center_median()
                    center_world = obj.matrix_world @ center_local
                    normal_world = (obj.matrix_world.to_3x3() @ f.normal).normalized()
                    face_normals.append(normal_world.copy())
                    face_centers.append(center_world.copy())
        
        if len(face_normals) != 2:
            self.report({'WARNING'}, f"两面夹角模式需要选择恰好2个面，当前选中了{len(face_normals)}个")
            return {'CANCELLED'}
        
        n1, n2 = face_normals[0], face_normals[1]
        
        dot_product = max(-1.0, min(1.0, n1.dot(n2)))
        angle_rad = math.acos(dot_product)
        angle_deg = math.degrees(angle_rad)
        bend_angle = 180.0 - angle_deg
        
        if self.create_geometry:
            bpy.ops.object.mode_set(mode='OBJECT')
            
            measure_obj = create_measure_object(
                context,
                f"{Config.MEASURE_OBJECT_PREFIX}夹角",
                [face_centers[0], face_centers[1]],
                [(0, 1)]
            )
            
            register_annotation(measure_obj.name, AnnotationType.ANGLE, {
                'edge_indices': [0],
                'angle': angle_deg,
                'bend': bend_angle,
            })
            
            bpy.ops.object.select_all(action='DESELECT')
            measure_obj.select_set(True)
            context.view_layer.objects.active = measure_obj
        else:
            register_annotation("__angle_temp__", AnnotationType.ANGLE_TEMP, {
                'center': (face_centers[0] + face_centers[1]) / 2,
                'angle': angle_deg,
                'bend': bend_angle,
            })
        
        ensure_draw_handler_enabled()
        refresh_3d_views(context)
        
        self.report({'INFO'}, f"法线夹角: {angle_deg:.2f}°，弯曲角度: {bend_angle:.2f}°")
        return {'FINISHED'}
    
    def _measure_angle_verts(self, context, edit_objects):
        """顶点角度测量"""
        vert_refs = []
        
        for obj in edit_objects:
            bm_read = bmesh.from_edit_mesh(obj.data)
            bm_read.verts.ensure_lookup_table()
            for v in bm_read.verts:
                if v.select:
                    vert_refs.append((obj.name, v.index))
        
        if len(vert_refs) < 2:
            self.report({'WARNING'}, f"顶点角度模式需要至少选择2个顶点，当前选中了{len(vert_refs)}个")
            return {'CANCELLED'}
        
        if len(vert_refs) == 2:
            register_annotation("__line_angles__", AnnotationType.LINE_ANGLES, {
                'vert_refs': vert_refs,
            })
        else:
            register_annotation("__vertex_angles__", AnnotationType.VERTEX_ANGLES, {
                'vert_refs': vert_refs,
            })
        
        ensure_draw_handler_enabled()
        refresh_3d_views(context)
        
        self.report({'INFO'}, f"已创建顶点角度标注（{len(vert_refs)}个顶点）")
        return {'FINISHED'}
    
    def _measure_radius(self, context, edit_objects, select_mode):
        """半径/直径测量"""
        center_points = []
        all_points = []
        
        for obj in edit_objects:
            bm_read = bmesh.from_edit_mesh(obj.data)
            bm_read.verts.ensure_lookup_table()
            bm_read.edges.ensure_lookup_table()
            bm_read.faces.ensure_lookup_table()
            
            if select_mode[2]:  # 面模式
                for f in bm_read.faces:
                    if f.select:
                        center_local = f.calc_center_median()
                        center_world = obj.matrix_world @ center_local
                        center_points.append(center_world.copy())
                        for v in f.verts:
                            world_co = obj.matrix_world @ v.co
                            all_points.append(world_co.copy())
            elif select_mode[1]:  # 边模式
                for e in bm_read.edges:
                    if e.select:
                        v1_world = obj.matrix_world @ e.verts[0].co
                        v2_world = obj.matrix_world @ e.verts[1].co
                        mid_world = (v1_world + v2_world) / 2
                        center_points.append(mid_world.copy())
                        all_points.append(v1_world.copy())
                        all_points.append(v2_world.copy())
            else:  # 顶点模式
                for v in bm_read.verts:
                    if v.select:
                        world_co = obj.matrix_world @ v.co
                        center_points.append(world_co.copy())
                        all_points.append(world_co.copy())
        
        # 尝试圆拟合（单个面且有足够顶点）
        if len(center_points) == 1 and select_mode[2] and len(all_points) >= 3:
            return self._measure_radius_circle_fit(context, all_points)
        
        # 两点距离的半距/全距
        if len(center_points) < 2:
            mode_name = get_mode_name(select_mode)
            self.report({'WARNING'}, f"半径/直径模式需要至少选中2个{mode_name}，或选中1个圆形面")
            return {'CANCELLED'}
        
        return self._measure_radius_two_points(context, center_points[0], center_points[1])
    
    def _measure_radius_circle_fit(self, context, all_points):
        """圆拟合测量半径"""
        # 去重
        unique_points = []
        for p in all_points:
            is_duplicate = False
            for up in unique_points:
                if (p - up).length < Config.COORDINATE_EPSILON:
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique_points.append(p)
        
        if len(unique_points) < 3:
            self.report({'WARNING'}, "去重后点数不足3个，无法拟合圆")
            return {'CANCELLED'}
        
        center, radius, fit_error = self.fit_circle_3d(unique_points)
        
        if center is None:
            if isinstance(fit_error, str):
                self.report({'ERROR'}, f"圆拟合失败: {fit_error}。请安装 numpy: pip install numpy")
            else:
                self.report({'WARNING'}, "无法拟合圆，点可能共线")
            return {'CANCELLED'}
        
        diameter = radius * 2
        
        if self.create_geometry:
            bpy.ops.object.mode_set(mode='OBJECT')
            
            nearest_point = min(unique_points, key=lambda p: abs((p - center).length - radius))
            
            measure_obj = create_measure_object(
                context,
                f"{Config.MEASURE_OBJECT_PREFIX}半径",
                [center, nearest_point],
                [(0, 1)]
            )
            
            register_annotation(measure_obj.name, AnnotationType.RADIUS, {
                'is_circle': True,
                'center_vert_idx': 0,
                'fit_error': fit_error,
            })
            
            bpy.ops.object.select_all(action='DESELECT')
            measure_obj.select_set(True)
            context.view_layer.objects.active = measure_obj
        else:
            register_annotation("__radius_temp__", AnnotationType.RADIUS_TEMP, {
                'center': center.copy(),
                'radius': radius,
                'diameter': diameter,
                'is_circle': True,
                'fit_error': fit_error,
            })
        
        ensure_draw_handler_enabled()
        refresh_3d_views(context)
        
        self.report({'INFO'}, f"半径: {radius:.6f} m，直径: {diameter:.6f} m（拟合误差: {fit_error:.4f}）")
        return {'FINISHED'}
    
    def _measure_radius_two_points(self, context, p1, p2):
        """两点半距/全距测量"""
        diameter = (p2 - p1).length
        radius = diameter / 2
        center = (p1 + p2) / 2
        
        if self.create_geometry:
            bpy.ops.object.mode_set(mode='OBJECT')
            
            measure_obj = create_measure_object(
                context,
                f"{Config.MEASURE_OBJECT_PREFIX}半距",
                [p1, p2, center],
                [(2, 0), (2, 1)]  # center -> p1, center -> p2
            )
            
            register_annotation(measure_obj.name, AnnotationType.RADIUS, {
                'is_circle': False,
                'center_vert_idx': 2,
            })
            
            bpy.ops.object.select_all(action='DESELECT')
            measure_obj.select_set(True)
            context.view_layer.objects.active = measure_obj
        else:
            register_annotation("__radius_temp__", AnnotationType.RADIUS_TEMP, {
                'center': center.copy(),
                'radius': radius,
                'diameter': diameter,
                'is_circle': False,
            })
        
        ensure_draw_handler_enabled()
        refresh_3d_views(context)
        
        self.report({'INFO'}, f"半距: {radius:.6f} m，全距: {diameter:.6f} m")
        return {'FINISHED'}
    
    def _measure_face_area(self, context, edit_objects, select_mode):
        """面积测量"""
        if not select_mode[2]:  # 不是面选择模式
            self.report({'WARNING'}, "面积测量需要在面选择模式下使用")
            return {'CANCELLED'}
        
        face_data_list = []
        total_area = 0.0
        
        for obj in edit_objects:
            bm_read = bmesh.from_edit_mesh(obj.data)
            bm_read.faces.ensure_lookup_table()
            
            # 获取物体的缩放因子用于计算世界坐标面积
            scale = obj.matrix_world.to_scale()
            # 面积缩放因子（对于非均匀缩放，这是近似值）
            # 精确计算需要对每个面的顶点进行世界坐标变换
            
            for face_idx, f in enumerate(bm_read.faces):
                if f.select:
                    # 计算世界坐标面积
                    # 将面的顶点转换到世界坐标计算面积
                    verts_world = [obj.matrix_world @ v.co for v in f.verts]
                    
                    # 使用向量叉积计算多边形面积
                    area = 0.0
                    n = len(verts_world)
                    if n >= 3:
                        # 计算多边形面积（适用于任意多边形）
                        center = sum(verts_world, Vector((0, 0, 0))) / n
                        for i in range(n):
                            v1 = verts_world[i] - center
                            v2 = verts_world[(i + 1) % n] - center
                            area += v1.cross(v2).length / 2
                    
                    face_data_list.append({
                        'obj_name': obj.name,
                        'face_idx': face_idx,
                        'vert_indices': [v.index for v in f.verts],
                        'area': area,
                    })
                    total_area += area
        
        if len(face_data_list) == 0:
            self.report({'WARNING'}, "请至少选择1个面")
            return {'CANCELLED'}
        
        # 注册标注
        register_annotation("__face_area__", AnnotationType.FACE_AREA, {
            'face_data': face_data_list,
            'total_area': total_area,
        })
        
        ensure_draw_handler_enabled()
        refresh_3d_views(context)
        
        face_count = len(face_data_list)
        if face_count == 1:
            self.report({'INFO'}, f"面积: {total_area:.6f} m²")
        else:
            self.report({'INFO'}, f"选中 {face_count} 个面，总面积: {total_area:.6f} m²")
        
        return {'FINISHED'}
    
    def _measure_perimeter(self, context, edit_objects, select_mode):
        """周长测量"""
        if select_mode[0]:  # 顶点选择模式
            self.report({'WARNING'}, "周长测量需要在边或面选择模式下使用")
            return {'CANCELLED'}
        
        perimeter_data_list = []
        total_perimeter = 0.0
        
        if select_mode[2]:  # 面选择模式
            # 计算选中面的边界周长
            for obj in edit_objects:
                bm_read = bmesh.from_edit_mesh(obj.data)
                bm_read.faces.ensure_lookup_table()
                
                for face_idx, f in enumerate(bm_read.faces):
                    if f.select:
                        # 计算面的周长（所有边的世界坐标长度之和）
                        perimeter = 0.0
                        edge_data = []
                        
                        for e in f.edges:
                            v1_world = obj.matrix_world @ e.verts[0].co
                            v2_world = obj.matrix_world @ e.verts[1].co
                            edge_length = (v2_world - v1_world).length
                            perimeter += edge_length
                            edge_data.append({
                                'v1_idx': e.verts[0].index,
                                'v2_idx': e.verts[1].index,
                                'length': edge_length,
                            })
                        
                        perimeter_data_list.append({
                            'obj_name': obj.name,
                            'face_idx': face_idx,
                            'vert_indices': [v.index for v in f.verts],
                            'perimeter': perimeter,
                            'edge_count': len(f.edges),
                            'edges': edge_data,
                        })
                        total_perimeter += perimeter
            
            if len(perimeter_data_list) == 0:
                self.report({'WARNING'}, "请至少选择1个面")
                return {'CANCELLED'}
            
            # 注册标注
            register_annotation("__perimeter__", AnnotationType.PERIMETER, {
                'mode': 'face',
                'perimeter_data': perimeter_data_list,
                'total_perimeter': total_perimeter,
            })
            
            ensure_draw_handler_enabled()
            refresh_3d_views(context)
            
            face_count = len(perimeter_data_list)
            if face_count == 1:
                self.report({'INFO'}, f"周长: {total_perimeter:.6f} m")
            else:
                self.report({'INFO'}, f"选中 {face_count} 个面，总周长: {total_perimeter:.6f} m")
        
        else:  # 边选择模式
            # 计算选中边的总长度
            edge_data_list = []
            
            for obj in edit_objects:
                bm_read = bmesh.from_edit_mesh(obj.data)
                bm_read.edges.ensure_lookup_table()
                
                for edge_idx, e in enumerate(bm_read.edges):
                    if e.select:
                        v1_world = obj.matrix_world @ e.verts[0].co
                        v2_world = obj.matrix_world @ e.verts[1].co
                        edge_length = (v2_world - v1_world).length
                        
                        edge_data_list.append({
                            'obj_name': obj.name,
                            'edge_idx': edge_idx,
                            'v1_idx': e.verts[0].index,
                            'v2_idx': e.verts[1].index,
                            'length': edge_length,
                        })
                        total_perimeter += edge_length
            
            if len(edge_data_list) == 0:
                self.report({'WARNING'}, "请至少选择1条边")
                return {'CANCELLED'}
            
            # 注册标注
            register_annotation("__perimeter__", AnnotationType.PERIMETER, {
                'mode': 'edge',
                'edge_data': edge_data_list,
                'total_perimeter': total_perimeter,
            })
            
            ensure_draw_handler_enabled()
            refresh_3d_views(context)
            
            edge_count = len(edge_data_list)
            if edge_count == 1:
                self.report({'INFO'}, f"边长: {total_perimeter:.6f} m")
            else:
                self.report({'INFO'}, f"选中 {edge_count} 条边，总长度: {total_perimeter:.6f} m")
        
        return {'FINISHED'}
    
    # ==================== 弧长/扇形测量 ====================
    
    def _calc_arc_data(self, center, p_start, p_end):
        """计算弧长相关数据（委托给共享函数）"""
        return calc_arc_data(center, p_start, p_end, epsilon=Config.VECTOR_LENGTH_EPSILON)
    
    def _measure_arc_length(self, context, edit_objects):
        """编辑模式 - 弧长/扇形测量"""
        # 收集选中的顶点（固定使用顶点模式逻辑）
        vert_refs = []
        
        for obj in edit_objects:
            bm_read = bmesh.from_edit_mesh(obj.data)
            bm_read.verts.ensure_lookup_table()
            for v in bm_read.verts:
                if v.select:
                    vert_refs.append((obj.name, v.index))
        
        if len(vert_refs) != 3:
            self.report({'WARNING'}, f"弧长测量需要选择恰好3个顶点（圆心+起点+终点），当前选中了{len(vert_refs)}个")
            return {'CANCELLED'}
        
        # 获取世界坐标
        points = []
        for obj_name, v_idx in vert_refs:
            obj = bpy.data.objects.get(obj_name)
            if obj and obj.type == 'MESH':
                mesh = obj.data
                if v_idx < len(mesh.vertices):
                    world_co = obj.matrix_world @ mesh.vertices[v_idx].co
                    points.append(world_co.copy())
        
        if len(points) != 3:
            self.report({'WARNING'}, "无法获取顶点坐标")
            return {'CANCELLED'}
        
        center, p_start, p_end = points[0], points[1], points[2]
        
        # 计算弧长数据
        arc_data = self._calc_arc_data(center, p_start, p_end)
        if arc_data is None:
            self.report({'WARNING'}, "圆心与端点重合，无法计算弧长")
            return {'CANCELLED'}
        
        if self.create_geometry:
            bpy.ops.object.mode_set(mode='OBJECT')
            
            measure_obj = create_measure_object(
                context,
                f"{Config.MEASURE_OBJECT_PREFIX}弧长",
                [center, p_start, p_end],
                [(0, 1), (0, 2), (1, 2)]  # 圆心到起点、圆心到终点、弦线
            )
            
            register_annotation(measure_obj.name, AnnotationType.ARC_LENGTH, {
                'center_vert_idx': 0,
                'is_bound': True,
            })
            
            bpy.ops.object.select_all(action='DESELECT')
            measure_obj.select_set(True)
            context.view_layer.objects.active = measure_obj
        else:
            # 注册临时标注（实时跟随顶点）
            register_annotation("__arc_length__", AnnotationType.ARC_LENGTH, {
                'vert_refs': vert_refs,
            })
        
        ensure_draw_handler_enabled()
        refresh_3d_views(context)
        
        # 构建报告信息
        r = arc_data
        report_msg = (
            f"弧长: {r['arc_length']:.6f} m | "
            f"弧角: {r['angle_deg']:.2f}° | "
            f"半径: {r['avg_radius']:.6f} m | "
            f"弦长: {r['chord_length']:.6f} m"
        )
        if r['radius_diff'] > Config.COORDINATE_EPSILON:
            report_msg += f" | ⚠半径偏差: {r['radius_diff']:.6f} m"
        
        self.report({'INFO'}, report_msg)
        return {'FINISHED'}
    
    # ==================== 物体模式执行 ====================
    
    def execute_object_mode(self, context):
        """物体模式执行"""
        selected = list(context.selected_objects)
        if len(selected) < 2:
            self.report({'WARNING'}, "请至少选中2个对象")
            return {'CANCELLED'}
        
        origins = [obj.matrix_world.translation.copy() for obj in selected]
        
        # 弧长/扇形模式
        if self.measure_mode == MeasureMode.ARC_LENGTH:
            return self._object_mode_arc_length(context, selected, origins)
        
        # 通用距离模式
        if self.measure_mode == MeasureMode.CENTER_DISTANCE:
            return self._object_mode_center_distance(context, selected, origins)
        
        # XYZ 分轴测量
        if self.measure_mode == MeasureMode.XYZ_SPLIT and len(origins) == 2:
            return self._object_mode_xyz_split(context, selected, origins)
        
        # 默认：连接所有原点
        return self._object_mode_connect_origins(context, selected, origins)
    
    def _object_mode_center_distance(self, context, selected, origins):
        """物体模式 - 通用距离测量"""
        if len(origins) != 2:
            self.report({'WARNING'}, "通用距离模式需要选中2个对象")
            return {'CANCELLED'}
        
        if self.lock_x and self.lock_y and self.lock_z:
            self.report({'ERROR'}, "不能同时锁定全部3个轴")
            return {'CANCELLED'}
        
        p1, p2 = origins[0], origins[1]
        p2_offset = p2 + self.get_offset_vector()
        
        display_p1, display_p2 = self.get_display_points(p1, p2_offset)
        distance = self.calc_distance(p1, p2_offset)
        axis_info = self.get_axis_lock_info()
        
        measure_obj = create_measure_object(
            context,
            f"{Config.MEASURE_OBJECT_PREFIX}通用距离",
            [display_p1, display_p2],
            [(0, 1)]
        )
        
        for o in selected:
            o.select_set(False)
        measure_obj.select_set(True)
        context.view_layer.objects.active = measure_obj
        
        register_annotation(measure_obj.name, AnnotationType.DISTANCE, {
            'measure_mode': MeasureMode.CENTER_DISTANCE,
            'edge_indices': [0],
            'distance': distance,
        })
        
        ensure_draw_handler_enabled()
        refresh_3d_views(context)
        
        self.report({'INFO'}, f"距离: {distance:.6f} m（{axis_info}）")
        return {'FINISHED'}
    
    def _object_mode_xyz_split(self, context, selected, origins):
        """物体模式 - XYZ分轴测量"""
        p1, p2 = origins[0], origins[1]
        
        dx = abs(p2.x - p1.x)
        dy = abs(p2.y - p1.y)
        dz = abs(p2.z - p1.z)
        threshold = Config.COORDINATE_EPSILON
        
        if dx < threshold and dy < threshold and dz < threshold:
            self.report({'WARNING'}, "两点的XYZ坐标完全相等，无法测量距离")
            return {'CANCELLED'}
        
        # 构建路径点
        path_points = [p1.copy()]
        current = p1.copy()
        
        if dx > threshold:
            current = Vector((p2.x, current.y, current.z))
            path_points.append(current.copy())
        
        if dy > threshold:
            current = Vector((current.x, p2.y, current.z))
            path_points.append(current.copy())
        
        if dz > threshold:
            current = Vector((current.x, current.y, p2.z))
            path_points.append(current.copy())
        
        # 构建边
        edges = [(i, i + 1) for i in range(len(path_points) - 1)]
        
        measure_obj = create_measure_object(
            context,
            f"{Config.MEASURE_OBJECT_PREFIX}分轴",
            path_points,
            edges
        )
        
        for o in selected:
            o.select_set(False)
        measure_obj.select_set(True)
        context.view_layer.objects.active = measure_obj
        
        # 计算总距离
        total_distance = 0.0
        for i in range(len(path_points) - 1):
            total_distance += self.calc_distance(path_points[i], path_points[i + 1])
        
        register_annotation(measure_obj.name, AnnotationType.DISTANCE, {
            'measure_mode': MeasureMode.XYZ_SPLIT,
            'edge_indices': list(range(len(edges))),
        })
        
        ensure_draw_handler_enabled()
        refresh_3d_views(context)
        
        self.report({'INFO'}, f"已连接 {len(path_points)} 个原点，总长度: {total_distance:.6f} m（{len(edges)} 段）")
        return {'FINISHED'}
    
    def _object_mode_connect_origins(self, context, selected, origins):
        """物体模式 - 连接所有原点"""
        edges = [(i, i + 1) for i in range(len(origins) - 1)]
        
        measure_obj = create_measure_object(
            context,
            f"{Config.MEASURE_OBJECT_PREFIX}距离",
            origins,
            edges
        )
        
        for o in selected:
            o.select_set(False)
        measure_obj.select_set(True)
        context.view_layer.objects.active = measure_obj
        
        # 计算距离
        distances = []
        total_distance = 0.0
        for i in range(len(origins) - 1):
            dist = self.calc_distance(origins[i], origins[i + 1])
            distances.append(dist)
            total_distance += dist
        
        register_annotation(measure_obj.name, AnnotationType.DISTANCE, {
            'measure_mode': self.measure_mode,
            'edge_indices': list(range(len(edges))),
        })
        
        ensure_draw_handler_enabled()
        refresh_3d_views(context)
        
        if len(distances) == 1:
            self.report({'INFO'}, f"已连接 {len(origins)} 个原点，距离: {total_distance:.6f} m")
        else:
            self.report({'INFO'}, f"已连接 {len(origins)} 个原点，总长度: {total_distance:.6f} m（{len(distances)} 段）")
        
        return {'FINISHED'}

    def _object_mode_arc_length(self, context, selected, origins):
        """物体模式 - 弧长/扇形测量"""
        if len(selected) != 3:
            self.report({'WARNING'}, "弧长测量需要选中恰好3个对象（活动对象=圆心，另2个=弧端点）")
            return {'CANCELLED'}
        
        # 活动对象为圆心
        active = context.active_object
        if active not in selected:
            self.report({'WARNING'}, "活动对象必须在选中对象中（作为圆心）")
            return {'CANCELLED'}
        
        center = active.matrix_world.translation.copy()
        endpoints = [obj.matrix_world.translation.copy() for obj in selected if obj != active]
        
        if len(endpoints) != 2:
            self.report({'WARNING'}, "需要恰好2个非活动对象作为弧端点")
            return {'CANCELLED'}
        
        p_start, p_end = endpoints[0], endpoints[1]
        
        # 计算弧长数据
        arc_data = self._calc_arc_data(center, p_start, p_end)
        if arc_data is None:
            self.report({'WARNING'}, "圆心与端点重合，无法计算弧长")
            return {'CANCELLED'}
        
        # 创建辅助几何体
        measure_obj = create_measure_object(
            context,
            f"{Config.MEASURE_OBJECT_PREFIX}弧长",
            [center, p_start, p_end],
            [(0, 1), (0, 2), (1, 2)]
        )
        
        for o in selected:
            o.select_set(False)
        measure_obj.select_set(True)
        context.view_layer.objects.active = measure_obj
        
        register_annotation(measure_obj.name, AnnotationType.ARC_LENGTH, {
            'center_vert_idx': 0,
            'is_bound': True,
        })
        
        ensure_draw_handler_enabled()
        refresh_3d_views(context)
        
        # 构建报告信息
        r = arc_data
        report_msg = (
            f"弧长: {r['arc_length']:.6f} m | "
            f"弧角: {r['angle_deg']:.2f}° | "
            f"半径: {r['avg_radius']:.6f} m | "
            f"弦长: {r['chord_length']:.6f} m"
        )
        if r['radius_diff'] > Config.COORDINATE_EPSILON:
            report_msg += f" | ⚠半径偏差: {r['radius_diff']:.6f} m"
        
        self.report({'INFO'}, report_msg)
        return {'FINISHED'}


# ==================== 类注册列表 ====================

classes = (
    OBJECT_OT_connect_origins,
)
