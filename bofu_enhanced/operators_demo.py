# ==================== 测量演示模块 ====================
"""
bofu_enhanced/operators_demo.py

为每种测量模式提供一键演示功能：
- OBJECT_OT_measure_demo: 创建演示场景并自动执行测量
- BOFU_OT_cleanup_demo: 清理所有 Demo_ 前缀的对象
"""

import bpy
import bmesh
import math
from bpy.types import Operator
from bpy.props import EnumProperty
from mathutils import Vector

from .config import MeasureMode


# ==================== 常量 ====================

DEMO_PREFIX = "Demo_"


# ==================== 辅助函数 ====================

def cleanup_demo_objects(context):
    """清理所有 Demo_ 前缀的对象及其数据"""
    # 先退出编辑模式
    if context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    bpy.ops.object.select_all(action='DESELECT')

    removed = 0
    for obj in list(bpy.data.objects):
        if obj.name.startswith(DEMO_PREFIX):
            bpy.data.objects.remove(obj, do_unlink=True)
            removed += 1

    # 清理孤立的网格数据
    for mesh in list(bpy.data.meshes):
        if mesh.name.startswith(DEMO_PREFIX) and mesh.users == 0:
            bpy.data.meshes.remove(mesh)

    return removed


def create_demo_mesh(context, name, verts, edges, faces, location=(0, 0, 0)):
    """
    创建演示用网格对象

    参数:
        name: 对象名称（会自动加 Demo_ 前缀）
        verts: 顶点坐标列表
        edges: 边定义列表
        faces: 面定义列表
        location: 对象位置

    返回: 创建的对象
    """
    full_name = f"{DEMO_PREFIX}{name}"
    mesh = bpy.data.meshes.new(full_name)
    mesh.from_pydata(verts, edges, faces)
    mesh.update()

    obj = bpy.data.objects.new(full_name, mesh)
    obj.location = location
    context.collection.objects.link(obj)
    return obj


def create_demo_cube(context, name, location=(0, 0, 0), size=0.3):
    """创建演示用小立方体"""
    half = size / 2
    verts = [
        (-half, -half, -half), (half, -half, -half),
        (half, half, -half), (-half, half, -half),
        (-half, -half, half), (half, -half, half),
        (half, half, half), (-half, half, half),
    ]
    faces = [
        (0, 1, 2, 3), (4, 5, 6, 7),
        (0, 1, 5, 4), (2, 3, 7, 6),
        (0, 3, 7, 4), (1, 2, 6, 5),
    ]
    return create_demo_mesh(context, name, verts, [], faces, location)


def enter_edit_select_all(context, obj, select_mode='VERT'):
    """进入编辑模式并全选"""
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    context.view_layer.objects.active = obj

    bpy.ops.object.mode_set(mode='EDIT')

    if select_mode == 'VERT':
        bpy.context.tool_settings.mesh_select_mode = (True, False, False)
    elif select_mode == 'EDGE':
        bpy.context.tool_settings.mesh_select_mode = (False, True, False)
    elif select_mode == 'FACE':
        bpy.context.tool_settings.mesh_select_mode = (False, False, True)

    bpy.ops.mesh.select_all(action='SELECT')


# ==================== 演示创建操作符 ====================

class OBJECT_OT_measure_demo(Operator):
    """创建测量模式的演示场景并自动执行测量"""
    bl_idname = "object.measure_demo"
    bl_label = "测量演示"
    bl_options = {"REGISTER", "UNDO"}

    demo_mode: EnumProperty(
        name="演示模式",
        items=[
            (MeasureMode.CENTER_DISTANCE, '通用距离', ''),
            (MeasureMode.EDGE_LENGTH, '边长测量', ''),
            (MeasureMode.XYZ_SPLIT, '分轴测量', ''),
            (MeasureMode.ANGLE_EDGES, '两边夹角', ''),
            (MeasureMode.ANGLE_FACES, '两面夹角', ''),
            (MeasureMode.ANGLE_VERTS, '顶点角度', ''),
            (MeasureMode.RADIUS, '半径/直径', ''),
            (MeasureMode.FACE_AREA, '面积测量', ''),
            (MeasureMode.PERIMETER, '周长测量', ''),
            (MeasureMode.ARC_LENGTH, '弧长/扇形', ''),
        ],
        default=MeasureMode.CENTER_DISTANCE,
    )

    def execute(self, context):
        # 1. 确保在物体模式
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # 2. 清理旧的 Demo 对象
        removed = cleanup_demo_objects(context)
        if removed > 0:
            print(f"[演示] 已清理 {removed} 个旧演示对象")

        # 3. 根据模式创建演示
        dispatch = {
            MeasureMode.CENTER_DISTANCE: self._demo_center_distance,
            MeasureMode.EDGE_LENGTH: self._demo_edge_length,
            MeasureMode.XYZ_SPLIT: self._demo_xyz_split,
            MeasureMode.ANGLE_EDGES: self._demo_angle_edges,
            MeasureMode.ANGLE_FACES: self._demo_angle_faces,
            MeasureMode.ANGLE_VERTS: self._demo_angle_verts,
            MeasureMode.RADIUS: self._demo_radius,
            MeasureMode.FACE_AREA: self._demo_face_area,
            MeasureMode.PERIMETER: self._demo_perimeter,
            MeasureMode.ARC_LENGTH: self._demo_arc_length,
        }

        handler = dispatch.get(self.demo_mode)
        if handler:
            return handler(context)

        self.report({'WARNING'}, "未知的演示模式")
        return {'CANCELLED'}

    # ==================== 各模式演示方法 ====================

    def _demo_center_distance(self, context):
        """通用距离演示：2个立方体，间距2m"""
        cube1 = create_demo_cube(context, "距离A", location=(0, 0, 0))
        cube2 = create_demo_cube(context, "距离B", location=(2, 0, 0))

        bpy.ops.object.select_all(action='DESELECT')
        cube1.select_set(True)
        cube2.select_set(True)
        context.view_layer.objects.active = cube1

        bpy.ops.object.connect_origins(
            measure_mode=MeasureMode.CENTER_DISTANCE,
            create_geometry=True,
        )

        self.report({'INFO'}, "演示: 通用距离 — 测量两个物体原点之间的距离")
        return {'FINISHED'}

    def _demo_edge_length(self, context):
        """边长测量演示：1个立方体，选中一条边"""
        cube = create_demo_cube(context, "边长", location=(0, 0, 0), size=1.0)

        enter_edit_select_all(context, cube, 'EDGE')

        # 只选中第一条边
        bpy.ops.mesh.select_all(action='DESELECT')
        bm = bmesh.from_edit_mesh(cube.data)
        bm.edges.ensure_lookup_table()
        if len(bm.edges) > 0:
            bm.edges[0].select = True
        bmesh.update_edit_mesh(cube.data)

        bpy.ops.object.connect_origins(measure_mode=MeasureMode.EDGE_LENGTH)

        self.report({'INFO'}, "演示: 边长测量 — 测量选中边的长度")
        return {'FINISHED'}

    def _demo_xyz_split(self, context):
        """分轴测量演示：2个立方体，XYZ各偏移不同"""
        cube1 = create_demo_cube(context, "分轴A", location=(0, 0, 0))
        cube2 = create_demo_cube(context, "分轴B", location=(1.5, 1.0, 0.8))

        bpy.ops.object.select_all(action='DESELECT')
        cube1.select_set(True)
        cube2.select_set(True)
        context.view_layer.objects.active = cube1

        bpy.ops.object.connect_origins(measure_mode=MeasureMode.XYZ_SPLIT)

        self.report({'INFO'}, "演示: 分轴测量 — 分别显示X/Y/Z方向的距离")
        return {'FINISHED'}

    def _demo_angle_edges(self, context):
        """两边夹角演示：V形网格，2条边约60度"""
        angle = math.radians(60)
        length = 1.5
        verts = [
            (0, 0, 0),                                        # 顶点（交叉点）
            (length, 0, 0),                                    # 边1终点
            (length * math.cos(angle), length * math.sin(angle), 0),  # 边2终点
        ]
        edges = [(0, 1), (0, 2)]
        obj = create_demo_mesh(context, "夹角", verts, edges, [], location=(0, 0, 0))

        enter_edit_select_all(context, obj, 'EDGE')

        bpy.ops.object.connect_origins(measure_mode=MeasureMode.ANGLE_EDGES)

        self.report({'INFO'}, "演示: 两边夹角 — 选2条边计算它们之间的角度")
        return {'FINISHED'}

    def _demo_angle_faces(self, context):
        """两面夹角演示：弯折平面，2个面约120度"""
        angle = math.radians(120)
        # 共享边沿Y轴，两个面分别向两侧展开
        verts = [
            (0, -0.5, 0),   # 共享边顶点1
            (0, 0.5, 0),    # 共享边顶点2
            (-1, -0.5, 0),  # 面1外顶点
            (-1, 0.5, 0),   # 面1外顶点
            # 面2外顶点：绕共享边旋转angle度
            (math.cos(math.pi - angle), -0.5, math.sin(math.pi - angle)),
            (math.cos(math.pi - angle), 0.5, math.sin(math.pi - angle)),
        ]
        faces = [(0, 1, 3, 2), (0, 1, 5, 4)]
        obj = create_demo_mesh(context, "面夹角", verts, [], faces, location=(0, 0, 0))

        enter_edit_select_all(context, obj, 'FACE')

        bpy.ops.object.connect_origins(
            measure_mode=MeasureMode.ANGLE_FACES,
            create_geometry=True,
        )

        self.report({'INFO'}, "演示: 两面夹角 — 选2个面计算法线之间的角度")
        return {'FINISHED'}

    def _demo_angle_verts(self, context):
        """顶点角度演示：等边三角形"""
        side = 1.5
        h = side * math.sqrt(3) / 2
        verts = [
            (0, 0, 0),
            (side, 0, 0),
            (side / 2, h, 0),
        ]
        edges = [(0, 1), (1, 2), (2, 0)]
        obj = create_demo_mesh(context, "顶点角度", verts, edges, [], location=(0, 0, 0))

        enter_edit_select_all(context, obj, 'VERT')

        bpy.ops.object.connect_origins(measure_mode=MeasureMode.ANGLE_VERTS)

        self.report({'INFO'}, "演示: 顶点角度 — 3+个顶点计算每个顶点处的角度")
        return {'FINISHED'}

    def _demo_radius(self, context):
        """半径测量演示：圆形面(8顶点)"""
        n = 8
        radius = 1.0
        verts = []
        for i in range(n):
            angle = 2 * math.pi * i / n
            verts.append((radius * math.cos(angle), radius * math.sin(angle), 0))
        faces = [tuple(range(n))]
        obj = create_demo_mesh(context, "半径", verts, [], faces, location=(0, 0, 0))

        enter_edit_select_all(context, obj, 'FACE')

        bpy.ops.object.connect_origins(
            measure_mode=MeasureMode.RADIUS,
            create_geometry=True,
        )

        self.report({'INFO'}, "演示: 半径/直径 — 选1个圆形面拟合圆，或选2个元素计算半距/全距")
        return {'FINISHED'}

    def _demo_face_area(self, context):
        """面积测量演示：1m x 1m 正方形"""
        verts = [
            (0, 0, 0), (1, 0, 0),
            (1, 1, 0), (0, 1, 0),
        ]
        faces = [(0, 1, 2, 3)]
        obj = create_demo_mesh(context, "面积", verts, [], faces, location=(0, 0, 0))

        enter_edit_select_all(context, obj, 'FACE')

        bpy.ops.object.connect_origins(measure_mode=MeasureMode.FACE_AREA)

        self.report({'INFO'}, "演示: 面积测量 — 选中面计算面积（此面 = 1.0 m²）")
        return {'FINISHED'}

    def _demo_perimeter(self, context):
        """周长测量演示：正六边形"""
        n = 6
        radius = 1.0
        verts = []
        for i in range(n):
            angle = 2 * math.pi * i / n
            verts.append((radius * math.cos(angle), radius * math.sin(angle), 0))
        faces = [tuple(range(n))]
        obj = create_demo_mesh(context, "周长", verts, [], faces, location=(0, 0, 0))

        enter_edit_select_all(context, obj, 'FACE')

        bpy.ops.object.connect_origins(measure_mode=MeasureMode.PERIMETER)

        self.report({'INFO'}, "演示: 周长测量 — 选中面计算边界周长")
        return {'FINISHED'}

    def _demo_arc_length(self, context):
        """弧长测量演示：圆心 + 2个弧端点(45度角)"""
        radius = 1.5
        angle = math.radians(45)
        verts = [
            (0, 0, 0),                                             # 圆心
            (radius, 0, 0),                                        # 弧起点
            (radius * math.cos(angle), radius * math.sin(angle), 0),  # 弧终点
        ]
        edges = [(0, 1), (0, 2), (1, 2)]
        obj = create_demo_mesh(context, "弧长", verts, edges, [], location=(0, 0, 0))

        enter_edit_select_all(context, obj, 'VERT')

        bpy.ops.object.connect_origins(
            measure_mode=MeasureMode.ARC_LENGTH,
            create_geometry=False,
        )

        self.report({'INFO'}, "演示: 弧长/扇形 — 选3个点(圆心+起点+终点)计算弧长、弧角等")
        return {'FINISHED'}


# ==================== 清理操作符 ====================

class BOFU_OT_cleanup_demo(Operator):
    """清理所有演示对象（Demo_前缀）"""
    bl_idname = "bofu.cleanup_demo"
    bl_label = "清理演示对象"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # 确保在物体模式
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        removed = cleanup_demo_objects(context)

        if removed > 0:
            self.report({'INFO'}, f"已清理 {removed} 个演示对象")
        else:
            self.report({'INFO'}, "没有演示对象需要清理")
        return {'FINISHED'}


# ==================== 类注册列表 ====================

classes = (
    OBJECT_OT_measure_demo,
    BOFU_OT_cleanup_demo,
)
