# ==================== 测量操作符模块 ====================
"""
bofu_enhanced/operators_measure.py

智能测量相关操作符
"""

import bpy
import bmesh
import math
from bpy.types import Operator
from bpy.props import EnumProperty, BoolProperty, FloatProperty
from mathutils import Vector

from .utils import get_unique_measure_name
from .annotation import (
    register_annotation, ensure_draw_handler_enabled
)


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
        
        if self.measure_mode == 'ANGLE_VERTS':
            layout.separator()
            box = layout.box()
            box.label(text="顶点角度模式不创建新几何体", icon='INFO')
            box.label(text="   2点: 计算线段与坐标轴的夹角")
            box.label(text="   3+点: 计算每个顶点的角度")
        elif self.measure_mode == 'ANGLE_EDGES':
            layout.separator()
            box = layout.box()
            box.label(text="选择2条边，计算夹角", icon='INFO')
        elif self.measure_mode == 'EDGE_LENGTH':
            layout.separator()
            box = layout.box()
            box.label(text="边长测量模式不创建新几何体", icon='INFO')
        elif self.measure_mode == 'CENTER_DISTANCE':
            layout.separator()
            box = layout.box()
            box.label(text="通用距离测量（增强版）", icon='INFO')
            layout.separator()
            
            box2 = layout.box()
            box2.label(text="轴锁定设置:", icon='LOCKED')
            row = box2.row(align=True)
            row.prop(self, "lock_x", toggle=True)
            row.prop(self, "lock_y", toggle=True)
            row.prop(self, "lock_z", toggle=True)
            
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
                box2.label(text="   不能锁定全部3个轴", icon='ERROR')
            
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

    def calc_distance(self, p1, p2):
        dx = 0 if self.lock_x else (p2.x - p1.x)
        dy = 0 if self.lock_y else (p2.y - p1.y)
        dz = 0 if self.lock_z else (p2.z - p1.z)
        return math.sqrt(dx**2 + dy**2 + dz**2)
    
    def get_axis_lock_info(self):
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
        x = p1.x if self.lock_x else p2.x
        y = p1.y if self.lock_y else p2.y
        z = p1.z if self.lock_z else p2.z
        return p1.copy(), Vector((x, y, z))
    
    def fit_circle_3d(self, points):
        """在3D空间中拟合圆"""
        import numpy as np
        
        if len(points) < 3:
            return None, None, None
        
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
        
        try:
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

    def execute(self, context):
        if context.mode == 'EDIT_MESH':
            return self.execute_edit_mode(context)
        else:
            return self.execute_object_mode(context)
    
    def execute_edit_mode(self, context):
        """编辑模式执行"""
        edit_objects = [obj for obj in context.objects_in_mode if obj.type == 'MESH']
        
        if not edit_objects:
            self.report({'WARNING'}, "没有处于编辑模式的网格对象")
            return {'CANCELLED'}
        
        tool_settings = context.tool_settings
        select_mode = tool_settings.mesh_select_mode
        
        points_world = []
        
        for obj in edit_objects:
            bm = bmesh.from_edit_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            
            if select_mode[2]:
                for f in bm.faces:
                    if f.select:
                        center_local = f.calc_center_median()
                        center_world = obj.matrix_world @ center_local
                        points_world.append(center_world)
            elif select_mode[1]:
                for e in bm.edges:
                    if e.select:
                        v1_world = obj.matrix_world @ e.verts[0].co
                        v2_world = obj.matrix_world @ e.verts[1].co
                        mid_world = (v1_world + v2_world) / 2
                        points_world.append(mid_world)
            else:
                for v in bm.verts:
                    if v.select:
                        world_co = obj.matrix_world @ v.co
                        points_world.append(world_co)
        
        # 边长测量模式
        if self.measure_mode == 'EDGE_LENGTH':
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
            
            register_annotation("__edge_length__", "edge_length", {
                'edge_data': edge_data_list,
            })
            
            ensure_draw_handler_enabled()
            
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
            
            total_length = 0.0
            edge_count = len(edge_data_list)
            for i, (obj_name, edge_idx, v1_idx, v2_idx) in enumerate(edge_data_list):
                obj = bpy.data.objects.get(obj_name)
                if obj and obj.type == 'MESH':
                    mesh = obj.data
                    if v1_idx < len(mesh.vertices) and v2_idx < len(mesh.vertices):
                        v1_world = obj.matrix_world @ mesh.vertices[v1_idx].co
                        v2_world = obj.matrix_world @ mesh.vertices[v2_idx].co
                        length = (v2_world - v1_world).length
                        total_length += length
            
            if edge_count == 1:
                self.report({'INFO'}, f"边长: {total_length:.6f} m（标注跟随物体）")
            else:
                self.report({'INFO'}, f"选中 {edge_count} 条边，总长度: {total_length:.6f} m（标注跟随物体）")
            return {'FINISHED'}
        
        # 通用距离模式
        if self.measure_mode == 'CENTER_DISTANCE':
            centers = []
            
            if select_mode[2]:
                for obj in edit_objects:
                    bm_read = bmesh.from_edit_mesh(obj.data)
                    bm_read.faces.ensure_lookup_table()
                    for f in bm_read.faces:
                        if f.select:
                            face_center = f.calc_center_median()
                            world_center = obj.matrix_world @ face_center
                            centers.append(world_center.copy())
            elif select_mode[1]:
                for obj in edit_objects:
                    bm_read = bmesh.from_edit_mesh(obj.data)
                    bm_read.edges.ensure_lookup_table()
                    for e in bm_read.edges:
                        if e.select:
                            v1_world = obj.matrix_world @ e.verts[0].co
                            v2_world = obj.matrix_world @ e.verts[1].co
                            edge_center = (v1_world + v2_world) / 2
                            centers.append(edge_center.copy())
            else:
                for obj in edit_objects:
                    bm_read = bmesh.from_edit_mesh(obj.data)
                    bm_read.verts.ensure_lookup_table()
                    for v in bm_read.verts:
                        if v.select:
                            world_co = obj.matrix_world @ v.co
                            centers.append(world_co.copy())
            
            if len(centers) < 2:
                mode_name = "面" if select_mode[2] else ("边" if select_mode[1] else "顶点")
                self.report({'WARNING'}, f"通用距离模式需要选择至少2个{mode_name}")
                return {'CANCELLED'}
            
            center1, center2 = centers[0], centers[1]
            
            offset = Vector((self.center_offset_x, self.center_offset_y, self.center_offset_z))
            center2_offset = center2 + offset
            
            if self.lock_x and self.lock_y and self.lock_z:
                self.report({'ERROR'}, "不能同时锁定全部3个轴")
                return {'CANCELLED'}
            
            display_p1, display_p2 = self.get_display_points(center1, center2_offset)
            distance = self.calc_distance(center1, center2_offset)
            axis_info = self.get_axis_lock_info()
            
            if self.create_geometry:
                bpy.ops.object.mode_set(mode='OBJECT')
                
                obj_name = get_unique_measure_name("测量_通用距离")
                mesh = bpy.data.meshes.new(obj_name)
                measure_obj = bpy.data.objects.new(obj_name, mesh)
                context.collection.objects.link(measure_obj)
                
                bm = bmesh.new()
                v1 = bm.verts.new(display_p1)
                v2 = bm.verts.new(display_p2)
                bm.verts.ensure_lookup_table()
                bm.edges.new((v1, v2))
                bm.to_mesh(mesh)
                bm.free()
                
                register_annotation(obj_name, "distance", {
                    'measure_mode': 'CENTER_DISTANCE',
                    'edge_indices': [0],
                    'distance': distance,
                })
                
                bpy.ops.object.select_all(action='DESELECT')
                measure_obj.select_set(True)
                context.view_layer.objects.active = measure_obj
            else:
                register_annotation("__center_distance_temp__", "distance_temp", {
                    'points': [display_p1.copy(), display_p2.copy()],
                    'measure_mode': 'CENTER_DISTANCE',
                    'distance': distance,
                })
            
            ensure_draw_handler_enabled()
            
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
            
            self.report({'INFO'}, f"距离: {distance:.6f} m（{axis_info}）")
            return {'FINISHED'}
        
        # 两边夹角模式
        if self.measure_mode == 'ANGLE_EDGES':
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
            
            register_annotation("__edge_angle__", "edge_angle", {
                'edge_refs': edge_refs,
            })
            
            ensure_draw_handler_enabled()
            
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
            
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
                
                self.report({'INFO'}, f"两边夹角: {angle_deg:.2f}°（补角: {supplement_angle:.2f}°）")
            
            return {'FINISHED'}
        
        # 两面夹角模式
        if self.measure_mode == 'ANGLE_FACES':
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
            
            n1 = face_normals[0]
            n2 = face_normals[1]
            
            dot_product = n1.dot(n2)
            dot_product = max(-1.0, min(1.0, dot_product))
            angle_rad = math.acos(dot_product)
            angle_deg = math.degrees(angle_rad)
            bend_angle = 180.0 - angle_deg
            
            if self.create_geometry:
                bpy.ops.object.mode_set(mode='OBJECT')
                
                obj_name = get_unique_measure_name("测量_夹角")
                mesh = bpy.data.meshes.new(obj_name)
                measure_obj = bpy.data.objects.new(obj_name, mesh)
                context.collection.objects.link(measure_obj)
                
                bm = bmesh.new()
                v1 = bm.verts.new(face_centers[0])
                v2 = bm.verts.new(face_centers[1])
                bm.verts.ensure_lookup_table()
                bm.edges.new((v1, v2))
                bm.to_mesh(mesh)
                bm.free()
                
                register_annotation(obj_name, "angle", {
                    'edge_indices': [0],
                    'angle': angle_deg,
                    'bend': bend_angle,
                })
                
                bpy.ops.object.select_all(action='DESELECT')
                measure_obj.select_set(True)
                context.view_layer.objects.active = measure_obj
            else:
                register_annotation("__angle_temp__", "angle_temp", {
                    'center': (face_centers[0] + face_centers[1]) / 2,
                    'angle': angle_deg,
                    'bend': bend_angle,
                })
            
            ensure_draw_handler_enabled()
            
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
            
            self.report({'INFO'}, f"法线夹角: {angle_deg:.2f}°，弯曲角度: {bend_angle:.2f}°")
            return {'FINISHED'}
        
        # 顶点角度模式
        if self.measure_mode == 'ANGLE_VERTS':
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
                register_annotation("__line_angles__", "line_angles", {
                    'vert_refs': vert_refs,
                })
            else:
                register_annotation("__vertex_angles__", "vertex_angles", {
                    'vert_refs': vert_refs,
                })
            
            ensure_draw_handler_enabled()
            
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
            
            self.report({'INFO'}, f"已创建顶点角度标注（{len(vert_refs)}个顶点）")
            return {'FINISHED'}
        
        # 半径模式
        if self.measure_mode == 'RADIUS':
            center_points = []
            all_points = []
            
            for obj in edit_objects:
                bm_read = bmesh.from_edit_mesh(obj.data)
                bm_read.verts.ensure_lookup_table()
                bm_read.edges.ensure_lookup_table()
                bm_read.faces.ensure_lookup_table()
                
                if select_mode[2]:
                    for f in bm_read.faces:
                        if f.select:
                            center_local = f.calc_center_median()
                            center_world = obj.matrix_world @ center_local
                            center_points.append(center_world.copy())
                            for v in f.verts:
                                world_co = obj.matrix_world @ v.co
                                all_points.append(world_co.copy())
                elif select_mode[1]:
                    for e in bm_read.edges:
                        if e.select:
                            v1_world = obj.matrix_world @ e.verts[0].co
                            v2_world = obj.matrix_world @ e.verts[1].co
                            mid_world = (v1_world + v2_world) / 2
                            center_points.append(mid_world.copy())
                            all_points.append(v1_world.copy())
                            all_points.append(v2_world.copy())
                else:
                    for v in bm_read.verts:
                        if v.select:
                            world_co = obj.matrix_world @ v.co
                            center_points.append(world_co.copy())
                            all_points.append(world_co.copy())
            
            if len(center_points) == 1 and select_mode[2] and len(all_points) >= 3:
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
                    center, radius, fit_error = self.fit_circle_3d(unique_points)
                    
                    if center is None:
                        self.report({'WARNING'}, "无法拟合圆，点可能共线")
                        return {'CANCELLED'}
                    
                    diameter = radius * 2
                    
                    if self.create_geometry:
                        bpy.ops.object.mode_set(mode='OBJECT')
                        
                        obj_name = get_unique_measure_name("测量_半径")
                        mesh = bpy.data.meshes.new(obj_name)
                        measure_obj = bpy.data.objects.new(obj_name, mesh)
                        context.collection.objects.link(measure_obj)
                        
                        bm = bmesh.new()
                        v_center = bm.verts.new(center)
                        nearest_point = min(unique_points, key=lambda p: abs((p - center).length - radius))
                        v_nearest = bm.verts.new(nearest_point)
                        bm.verts.ensure_lookup_table()
                        bm.edges.new((v_center, v_nearest))
                        bm.to_mesh(mesh)
                        bm.free()
                        
                        register_annotation(obj_name, "radius", {
                            'is_circle': True,
                            'center_vert_idx': 0,
                            'fit_error': fit_error,
                        })
                        
                        bpy.ops.object.select_all(action='DESELECT')
                        measure_obj.select_set(True)
                        context.view_layer.objects.active = measure_obj
                    else:
                        register_annotation("__radius_temp__", "radius_temp", {
                            'center': center.copy(),
                            'radius': radius,
                            'diameter': diameter,
                            'is_circle': True,
                            'fit_error': fit_error,
                        })
                    
                    ensure_draw_handler_enabled()
                    
                    for area in context.screen.areas:
                        if area.type == 'VIEW_3D':
                            area.tag_redraw()
                    
                    self.report({'INFO'}, f"半径: {radius:.6f} m，直径: {diameter:.6f} m（拟合误差: {fit_error:.4f}）")
                    return {'FINISHED'}
            
            if len(center_points) < 2:
                mode_name = "面" if select_mode[2] else ("边" if select_mode[1] else "顶点")
                self.report({'WARNING'}, f"半径/直径模式需要至少选中2个{mode_name}，或选中1个圆形面")
                return {'CANCELLED'}
            
            p1, p2 = center_points[0], center_points[1]
            diameter = (p2 - p1).length
            radius = diameter / 2
            center = (p1 + p2) / 2
            
            if self.create_geometry:
                bpy.ops.object.mode_set(mode='OBJECT')
                
                obj_name = get_unique_measure_name("测量_半距")
                mesh = bpy.data.meshes.new(obj_name)
                measure_obj = bpy.data.objects.new(obj_name, mesh)
                context.collection.objects.link(measure_obj)
                
                bm = bmesh.new()
                v1 = bm.verts.new(p1)
                v2 = bm.verts.new(p2)
                v_center = bm.verts.new(center)
                bm.verts.ensure_lookup_table()
                bm.edges.new((v_center, v1))
                bm.edges.new((v_center, v2))
                bm.to_mesh(mesh)
                bm.free()
                
                register_annotation(obj_name, "radius", {
                    'is_circle': False,
                    'center_vert_idx': 2,
                })
                
                bpy.ops.object.select_all(action='DESELECT')
                measure_obj.select_set(True)
                context.view_layer.objects.active = measure_obj
            else:
                register_annotation("__radius_temp__", "radius_temp", {
                    'center': center.copy(),
                    'radius': radius,
                    'diameter': diameter,
                    'is_circle': False,
                })
            
            ensure_draw_handler_enabled()
            
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
            
            self.report({'INFO'}, f"半距: {radius:.6f} m，全距: {diameter:.6f} m")
            return {'FINISHED'}
        
        if len(points_world) < 2:
            mode_name = "面" if select_mode[2] else ("边" if select_mode[1] else "顶点")
            self.report({'WARNING'}, f"请至少选中2个{mode_name}")
            return {'CANCELLED'}
        
        return {'FINISHED'}
    
    def execute_object_mode(self, context):
        """物体模式执行"""
        selected = [obj for obj in context.selected_objects]
        if len(selected) < 2:
            self.report({'WARNING'}, "请至少选中2个对象")
            return {'CANCELLED'}
        
        origins = []
        for obj in selected:
            origins.append(obj.matrix_world.translation.copy())
        
        mesh = bpy.data.meshes.new("原点连线")
        obj = bpy.data.objects.new("原点连线", mesh)
        context.collection.objects.link(obj)
        
        bm = bmesh.new()
        verts = []
        
        if self.measure_mode == 'XYZ_SPLIT' and len(origins) == 2:
            p1 = origins[0]
            p2 = origins[1]
            
            dx = abs(p2.x - p1.x)
            dy = abs(p2.y - p1.y)
            dz = abs(p2.z - p1.z)
            threshold = 0.0001
            
            if dx < threshold and dy < threshold and dz < threshold:
                bpy.data.objects.remove(obj, do_unlink=True)
                bpy.data.meshes.remove(mesh)
                self.report({'WARNING'}, "两点的XYZ坐标完全相等，无法测量距离")
                return {'CANCELLED'}
            
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
            
            for pt in path_points:
                v = bm.verts.new(pt)
                verts.append(v)
            
            origins = path_points
        elif self.measure_mode == 'CENTER_DISTANCE':
            if len(origins) != 2:
                bpy.data.objects.remove(obj, do_unlink=True)
                bpy.data.meshes.remove(mesh)
                self.report({'WARNING'}, "通用距离模式需要选中2个对象")
                return {'CANCELLED'}
            
            if self.lock_x and self.lock_y and self.lock_z:
                bpy.data.objects.remove(obj, do_unlink=True)
                bpy.data.meshes.remove(mesh)
                self.report({'ERROR'}, "不能同时锁定全部3个轴")
                return {'CANCELLED'}
            
            p1, p2 = origins[0], origins[1]
            offset = Vector((self.center_offset_x, self.center_offset_y, self.center_offset_z))
            p2_offset = p2 + offset
            
            display_p1, display_p2 = self.get_display_points(p1, p2_offset)
            distance = self.calc_distance(p1, p2_offset)
            axis_info = self.get_axis_lock_info()
            
            v1 = bm.verts.new(display_p1)
            v2 = bm.verts.new(display_p2)
            verts = [v1, v2]
            bm.verts.ensure_lookup_table()
            bm.edges.new((v1, v2))
            bm.to_mesh(mesh)
            bm.free()
            
            base_name = "测量_通用距离"
            obj.name = get_unique_measure_name(base_name)
            mesh.name = obj.name
            
            for o in selected:
                o.select_set(False)
            obj.select_set(True)
            context.view_layer.objects.active = obj
            
            register_annotation(obj.name, "distance", {
                'measure_mode': 'CENTER_DISTANCE',
                'edge_indices': [0],
                'distance': distance,
            })
            
            ensure_draw_handler_enabled()
            
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
            
            self.report({'INFO'}, f"距离: {distance:.6f} m（{axis_info}）")
            return {'FINISHED'}
        else:
            for origin in origins:
                v = bm.verts.new(origin)
                verts.append(v)
        
        distances = []
        total_distance = 0.0
        edge_count = len(verts) - 1
        for i in range(edge_count):
            bm.edges.new((verts[i], verts[i + 1]))
            dist = self.calc_distance(origins[i], origins[i + 1])
            distances.append(dist)
            total_distance += dist
        
        bm.to_mesh(mesh)
        bm.free()
        
        measure_types_name = {'XYZ_SPLIT': '分轴', 'CENTER_DISTANCE': '距离'}
        base_name = f"测量_{measure_types_name.get(self.measure_mode, '距离')}"
        obj.name = get_unique_measure_name(base_name)
        mesh.name = obj.name
        
        for o in selected:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        
        register_annotation(obj.name, "distance", {
            'measure_mode': self.measure_mode,
            'edge_indices': list(range(edge_count)),
        })
        
        ensure_draw_handler_enabled()
        
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        if len(distances) == 1:
            self.report({'INFO'}, f"已连接 {len(origins)} 个原点，距离: {total_distance:.6f} m")
        else:
            self.report({'INFO'}, f"已连接 {len(origins)} 个原点，总长度: {total_distance:.6f} m（{len(distances)} 段）")
        return {'FINISHED'}


# ==================== 类注册列表 ====================

classes = (
    OBJECT_OT_connect_origins,
)
