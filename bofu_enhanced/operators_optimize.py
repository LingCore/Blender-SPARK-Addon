# ==================== 模型优化操作符模块 ====================
"""
bofu_enhanced/operators_optimize.py

模型优化操作符，包括：
- MESH_OT_optimize_mesh: 一键优化模型（集成多种网格清理与减面操作）
"""

import math
import bpy
from bpy.types import Operator
from bpy.props import BoolProperty, FloatProperty


class MESH_OT_optimize_mesh(Operator):
    """一键优化选中的模型：合并重叠顶点、删除孤立/内部面、溶解退化几何体、清理数据层、减面等"""
    bl_idname = "mesh.optimize_mesh_plus"
    bl_label = "一键优化模型"
    bl_options = {'REGISTER', 'UNDO'}

    # ---- 阶段一：无损清理 ----

    use_delete_loose: BoolProperty(
        name="删除孤立元素",
        description="移除不与任何面相连的游离顶点和边",
        default=True,
    )
    use_delete_interior: BoolProperty(
        name="删除内部面",
        description="移除完全被包裹在网格内部、不可见的面",
        default=True,
    )
    use_dissolve_degenerate: BoolProperty(
        name="溶解退化几何体",
        description="移除零面积面和零长度边",
        default=True,
    )
    use_merge_by_distance: BoolProperty(
        name="按距离合并顶点",
        description="合并位置重叠或距离极近的顶点",
        default=True,
    )
    merge_threshold: FloatProperty(
        name="合并阈值",
        description="小于此距离的顶点将被合并",
        default=0.0001,
        min=0.0,
        max=1.0,
        precision=6,
        unit='LENGTH',
    )
    use_cleanup_materials: BoolProperty(
        name="清理材质槽",
        description="移除对象上未被任何面引用的空材质槽",
        default=True,
    )
    use_cleanup_uv_layers: BoolProperty(
        name="清理多余UV层",
        description="只保留活动UV层，移除其余所有UV层",
        default=False,
    )
    use_cleanup_vertex_colors: BoolProperty(
        name="清理顶点色",
        description="移除所有颜色属性数据（Vertex Color / Color Attribute）",
        default=False,
    )

    # ---- 阶段二：轻量优化 ----

    use_limited_dissolve: BoolProperty(
        name="有限溶解",
        description="移除平面区域上多余的顶点和边（可能导致极小形变）",
        default=False,
    )
    dissolve_angle: FloatProperty(
        name="溶解角度",
        description="低于此角度的共面顶点将被溶解",
        default=math.radians(5),
        min=0.0,
        max=math.pi,
        subtype='ANGLE',
    )
    use_tris_to_quads: BoolProperty(
        name="三角面转四边面",
        description="将相邻三角面合并为四边面，减少面数",
        default=False,
    )
    use_recalc_normals: BoolProperty(
        name="重新计算法线",
        description="统一所有面的法线方向",
        default=True,
    )

    # ---- 阶段三：激进减面 ----

    use_decimate: BoolProperty(
        name="精简几何体",
        description="按比例减少面数（会改变模型形状）",
        default=False,
    )
    decimate_ratio: FloatProperty(
        name="保留比例",
        description="保留原始面数的百分比（0.5 = 保留 50%）",
        default=0.5,
        min=0.0,
        max=1.0,
        precision=3,
    )

    # ---- 全局清理 ----

    use_purge_orphans: BoolProperty(
        name="清理孤立数据块",
        description="清理场景中未被引用的材质、纹理等数据",
        default=True,
    )

    def draw(self, context):
        layout = self.layout

        targets = [o for o in context.selected_objects if o.type == 'MESH']
        box = layout.box()
        box.label(text=f"当前选中 {len(targets)} 个 Mesh 对象", icon='INFO')

        layout.separator()

        # 阶段一
        layout.label(text="阶段一：无损清理", icon='BRUSH_DATA')
        col = layout.column(align=True)
        col.prop(self, "use_delete_loose")
        col.prop(self, "use_delete_interior")
        col.prop(self, "use_dissolve_degenerate")
        row = col.row(align=True)
        row.prop(self, "use_merge_by_distance")
        sub = row.row(align=True)
        sub.enabled = self.use_merge_by_distance
        sub.prop(self, "merge_threshold", text="")
        col.prop(self, "use_cleanup_materials")
        col.prop(self, "use_cleanup_uv_layers")
        col.prop(self, "use_cleanup_vertex_colors")

        layout.separator()

        # 阶段二
        layout.label(text="阶段二：轻量优化", icon='MOD_SMOOTH')
        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(self, "use_limited_dissolve")
        sub = row.row(align=True)
        sub.enabled = self.use_limited_dissolve
        sub.prop(self, "dissolve_angle", text="")
        col.prop(self, "use_tris_to_quads")
        col.prop(self, "use_recalc_normals")

        layout.separator()

        # 阶段三
        layout.label(text="阶段三：激进减面", icon='MOD_DECIM')
        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(self, "use_decimate")
        sub = row.row(align=True)
        sub.enabled = self.use_decimate
        sub.prop(self, "decimate_ratio", text="")

        layout.separator()

        # 全局清理
        layout.label(text="全局清理", icon='TRASH')
        layout.prop(self, "use_purge_orphans")

    def invoke(self, context, event):
        targets = [o for o in context.selected_objects if o.type == 'MESH']
        if not targets:
            self.report({'WARNING'}, "未选中任何 Mesh 对象")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=380)

    def execute(self, context):
        original_active = context.view_layer.objects.active
        original_mode = context.mode
        if original_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        targets = [o for o in context.selected_objects if o.type == 'MESH']
        if not targets:
            self.report({'WARNING'}, "未选中任何 Mesh 对象")
            return {'CANCELLED'}

        total_verts_removed = 0
        total_edges_removed = 0
        total_faces_removed = 0

        for obj in targets:
            before_v = len(obj.data.vertices)
            before_e = len(obj.data.edges)
            before_f = len(obj.data.polygons)

            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj

            # ---- 编辑模式操作 ----
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')

            # 阶段一（编辑模式部分）
            if self.use_delete_interior:
                bpy.ops.mesh.select_all(action='DESELECT')
                bpy.ops.mesh.select_interior_faces()
                bpy.ops.mesh.delete(type='FACE')
                bpy.ops.mesh.select_all(action='SELECT')

            if self.use_delete_loose:
                bpy.ops.mesh.delete_loose(
                    use_verts=True, use_edges=True, use_faces=False,
                )
            if self.use_dissolve_degenerate:
                bpy.ops.mesh.dissolve_degenerate(threshold=0.0001)
            if self.use_merge_by_distance:
                bpy.ops.mesh.remove_doubles(threshold=self.merge_threshold)

            # 阶段二
            if self.use_limited_dissolve:
                bpy.ops.mesh.dissolve_limited(
                    angle_limit=self.dissolve_angle,
                )
            if self.use_tris_to_quads:
                bpy.ops.mesh.tris_convert_to_quads()
            if self.use_recalc_normals:
                bpy.ops.mesh.normals_make_consistent(inside=False)

            # 阶段三
            if self.use_decimate:
                bpy.ops.mesh.decimate(ratio=self.decimate_ratio)

            bpy.ops.object.mode_set(mode='OBJECT')

            # ---- 对象模式操作 ----
            if self.use_cleanup_materials:
                self._cleanup_material_slots(obj)
            if self.use_cleanup_uv_layers:
                self._cleanup_uv_layers(obj.data)
            if self.use_cleanup_vertex_colors:
                self._cleanup_vertex_colors(obj.data)

            after_v = len(obj.data.vertices)
            after_e = len(obj.data.edges)
            after_f = len(obj.data.polygons)

            total_verts_removed += max(0, before_v - after_v)
            total_edges_removed += max(0, before_e - after_e)
            total_faces_removed += max(0, before_f - after_f)

        # 恢复选择
        bpy.ops.object.select_all(action='DESELECT')
        for obj in targets:
            if obj.name in bpy.data.objects:
                obj.select_set(True)
        if original_active and original_active.name in bpy.data.objects:
            context.view_layer.objects.active = original_active

        # 全局清理
        if self.use_purge_orphans:
            bpy.ops.outliner.orphans_purge(
                do_local_ids=True, do_linked_ids=True, do_recursive=True,
            )

        self.report(
            {'INFO'},
            f"优化完成（{len(targets)} 个对象）："
            f"减少 {total_verts_removed} 顶点 / "
            f"{total_edges_removed} 边 / "
            f"{total_faces_removed} 面",
        )
        return {'FINISHED'}

    @staticmethod
    def _cleanup_material_slots(obj):
        """移除未被任何面引用的材质槽"""
        if not obj.data.polygons:
            return
        used_indices = set()
        for poly in obj.data.polygons:
            used_indices.add(poly.material_index)
        for i in reversed(range(len(obj.material_slots))):
            if i not in used_indices:
                obj.active_material_index = i
                bpy.ops.object.material_slot_remove()

    @staticmethod
    def _cleanup_uv_layers(mesh):
        """只保留活动UV层，移除其余UV层"""
        if not mesh.uv_layers:
            return
        active_uv = mesh.uv_layers.active
        for uv in reversed(list(mesh.uv_layers)):
            if uv != active_uv:
                mesh.uv_layers.remove(uv)

    @staticmethod
    def _cleanup_vertex_colors(mesh):
        """移除所有颜色属性"""
        if hasattr(mesh, 'color_attributes'):
            for attr in reversed(list(mesh.color_attributes)):
                mesh.color_attributes.remove(attr)
        if hasattr(mesh, 'vertex_colors'):
            for vc in reversed(list(mesh.vertex_colors)):
                mesh.vertex_colors.remove(vc)


# ==================== 类注册列表 ====================

classes = (
    MESH_OT_optimize_mesh,
)
