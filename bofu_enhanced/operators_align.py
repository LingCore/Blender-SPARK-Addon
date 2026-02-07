# ==================== 对齐工具操作符模块 ====================
"""
bofu_enhanced/operators_align.py

对齐相关操作符（对象模式和编辑模式）
"""

import bpy
import bmesh
from bpy.types import Operator
from bpy.props import EnumProperty, BoolProperty, FloatProperty
from mathutils import Vector

from .config import Config
from .utils import AlignmentHelper

# 轴名称到索引的映射常量
AXIS_INDEX = {'X': 0, 'Y': 1, 'Z': 2}


# ==================== 对象模式对齐操作符 ====================

class OBJECT_OT_align_objects(Operator):
    """智能对齐工具：将选中对象对齐到活动对象"""
    bl_idname = "object.align_objects_plus"
    bl_label = "对齐（增强）"
    bl_options = {'REGISTER', 'UNDO'}
    
    align_axis: EnumProperty(
        name="对齐轴",
        items=[
            ('X', "X轴 (左右)", "沿X轴对齐"),
            ('Y', "Y轴 (前后)", "沿Y轴对齐"),
            ('Z', "Z轴 (上下)", "沿Z轴对齐"),
        ],
        default='Z',
    )
    
    align_direction: EnumProperty(
        name="对齐方向",
        items=[
            ('MIN', "最小侧", "对齐到轴向的最小侧（左/后/下）"),
            ('CENTER', "中心", "对齐到中心"),
            ('MAX', "最大侧", "对齐到轴向的最大侧（右/前/上）"),
        ],
        default='MIN',
    )
    
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
        
        box = layout.box()
        box.label(text="快捷预设:", icon='PRESET')
        box.prop(self, "preset", text="")
        
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
        
        box = layout.box()
        box.label(text="对齐设置:", icon='ORIENTATION_GLOBAL')
        box.prop(self, "align_axis")
        
        if self.preset == 'CUSTOM':
            layout.separator()
            box = layout.box()
            box.label(text="自定义基准点:", icon='PIVOT_BOUNDBOX')
            box.prop(self, "source_ref", text="源对象")
            box.prop(self, "target_ref", text="目标对象")
        
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
        
        objects_to_align = [o for o in context.selected_objects if o != active]
        if not objects_to_align:
            self.report({'WARNING'}, "请选择要对齐的对象（除活动对象外）")
            return {'CANCELLED'}
        
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
        
        target_point = AlignmentHelper.get_reference_point(active, target_ref, self.align_axis)
        axis_idx = AXIS_INDEX.get(self.align_axis, 2)
        target_coord = target_point[axis_idx]
        
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
        
        target_point = AlignmentHelper.get_reference_point(active, 'BBOX_BOTTOM', self.align_axis)
        axis_idx = AXIS_INDEX.get(self.align_axis, 2)
        target_coord = target_point[axis_idx]
        
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
        
        axis_idx = AXIS_INDEX.get(self.distribute_axis, 0)
        
        def get_pos(obj):
            ref = AlignmentHelper.get_reference_point(obj, self.ref_point, self.distribute_axis)
            return ref[axis_idx]
        
        selected.sort(key=get_pos)
        
        if self.use_gap:
            for i, obj in enumerate(selected):
                if i == 0:
                    continue
                prev_obj = selected[i - 1]
                prev_bbox_min, prev_bbox_max = AlignmentHelper.get_world_bbox(prev_obj)
                curr_bbox_min, curr_bbox_max = AlignmentHelper.get_world_bbox(obj)
                
                target_min = prev_bbox_max[axis_idx] + self.gap_value
                current_min = curr_bbox_min[axis_idx]
                delta = target_min - current_min
                obj.location[axis_idx] += delta
        else:
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


# ==================== 方向对齐操作符 ====================

class OBJECT_OT_align_to_active_direction(Operator):
    """将选中对象的轴对齐到活动面的法线或活动对象的局部轴"""
    bl_idname = "object.align_to_active_direction"
    bl_label = "对齐到活动面/局部轴"
    bl_options = {'REGISTER', 'UNDO'}
    
    align_mode: EnumProperty(
        name="对齐目标",
        items=[
            ('FACE_NORMAL', "活动面法线", "对齐到活动面的法线方向（需要编辑模式与活动面）"),
            ('ACTIVE_AXIS', "活动对象局部轴", "对齐到活动对象的局部轴方向"),
        ],
        default='FACE_NORMAL',
    )
    
    target_axis: EnumProperty(
        name="目标对象轴",
        items=[
            ('Z', "Z", ""), ('Y', "Y", ""), ('X', "X", ""),
            ('-Z', "-Z", ""), ('-Y', "-Y", ""), ('-X', "-X", ""),
        ],
        default='Z',
    )
    
    active_axis: EnumProperty(
        name="活动对象轴",
        items=[
            ('Z', "Z", ""), ('Y', "Y", ""), ('X', "X", ""),
            ('-Z', "-Z", ""), ('-Y', "-Y", ""), ('-X', "-X", ""),
        ],
        default='Z',
    )
    
    @classmethod
    def poll(cls, context):
        return context.active_object is not None
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "align_mode")
        layout.prop(self, "target_axis")
        if self.align_mode == 'ACTIVE_AXIS':
            layout.prop(self, "active_axis")
        else:
            layout.label(text="需要在编辑模式选择活动面", icon='INFO')
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=320)
    
    def _axis_vector(self, axis_name):
        axis = axis_name.replace('-', '')
        if axis == 'X':
            vec = Vector((1, 0, 0))
        elif axis == 'Y':
            vec = Vector((0, 1, 0))
        else:
            vec = Vector((0, 0, 1))
        if axis_name.startswith('-'):
            vec = -vec
        return vec
    
    def _get_active_face_normal(self, active_obj):
        bm = bmesh.from_edit_mesh(active_obj.data)
        face = bm.faces.active
        if not face:
            for elem in reversed(bm.select_history):
                if isinstance(elem, bmesh.types.BMFace):
                    face = elem
                    break
        if not face:
            return None
        normal_world = (active_obj.matrix_world.to_3x3() @ face.normal).normalized()
        return normal_world
    
    def _apply_world_rotation(self, obj, rot_q):
        mw = obj.matrix_world.copy()
        loc = mw.to_translation()
        new_mw = rot_q.to_matrix().to_4x4() @ mw
        new_mw.translation = loc
        obj.matrix_world = new_mw
    
    def execute(self, context):
        active = context.active_object
        if not active:
            self.report({'ERROR'}, "未找到活动对象")
            return {'CANCELLED'}
        
        if self.align_mode == 'FACE_NORMAL':
            if context.mode != 'EDIT_MESH' or active.type != 'MESH':
                self.report({'ERROR'}, "活动面法线模式需要在网格编辑模式下使用")
                return {'CANCELLED'}
            target_dir = self._get_active_face_normal(active)
            if target_dir is None or target_dir.length < Config.VECTOR_LENGTH_EPSILON:
                self.report({'ERROR'}, "未找到活动面，请选中一个面")
                return {'CANCELLED'}
            
            # 编辑模式下获取目标对象：使用 objects_in_mode 以外的选中对象
            # 或者如果只有单对象编辑，则使用进入编辑模式前的选择（通过 view_layer）
            targets = []
            
            # 方法1：多对象编辑模式下，其他编辑对象
            if hasattr(context, 'objects_in_mode'):
                targets = [obj for obj in context.objects_in_mode if obj != active and obj.type == 'MESH']
            
            # 方法2：如果没有其他编辑对象，退出编辑模式后使用选中对象
            if not targets:
                # 保存法线方向，退出编辑模式
                saved_normal = target_dir.copy()
                bpy.ops.object.mode_set(mode='OBJECT')
                target_dir = saved_normal
                targets = [obj for obj in context.selected_objects if obj != active]
        else:
            target_dir = (active.matrix_world.to_quaternion() @ self._axis_vector(self.active_axis)).normalized()
            if target_dir.length < Config.VECTOR_LENGTH_EPSILON:
                self.report({'ERROR'}, "活动对象参考轴方向无效")
                return {'CANCELLED'}
            targets = [obj for obj in context.selected_objects if obj != active]
        
        if not targets:
            self.report({'WARNING'}, "没有需要对齐的对象（请先在对象模式选中多个对象，再进入编辑模式选择活动面）")
            return {'CANCELLED'}
        
        aligned_count = 0
        for obj in targets:
            source_dir = (obj.matrix_world.to_quaternion() @ self._axis_vector(self.target_axis)).normalized()
            if source_dir.length < Config.VECTOR_LENGTH_EPSILON:
                continue
            rot_q = source_dir.rotation_difference(target_dir)
            self._apply_world_rotation(obj, rot_q)
            aligned_count += 1
        
        if aligned_count == 0:
            self.report({'WARNING'}, "没有对象被对齐")
            return {'CANCELLED'}
        
        mode_text = "活动面法线" if self.align_mode == 'FACE_NORMAL' else "活动对象局部轴"
        self.report({'INFO'}, f"已对齐 {aligned_count} 个对象到{mode_text}")
        return {'FINISHED'}


# ==================== 编辑模式对齐操作符 ====================

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
        
        layout.separator()
        obj = context.edit_object
        if obj:
            layout.label(text=f"选中 {obj.data.total_vert_sel} 个顶点", icon='INFO')
    
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
        
        axis_idx = AXIS_INDEX.get(self.align_axis, 2)
        mw = obj.matrix_world
        mw_inv = mw.inverted()
        
        target_coord = None
        
        if self.align_target == 'ACTIVE':
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
                target_coord = (mw_inv @ Vector((0, 0, 0)))[axis_idx]
            else:
                target_coord = 0.0
        
        if target_coord is None:
            self.report({'ERROR'}, "无法确定对齐目标")
            return {'CANCELLED'}
        
        aligned_count = 0
        for v in selected_verts:
            if self.use_local:
                v.co[axis_idx] = target_coord
            else:
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
        
        axis_idx = AXIS_INDEX.get(self.axis, 2)
        
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
            axis_idx = AXIS_INDEX.get(self.axis, 2)
            
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
            avg_normal = Vector((0, 0, 0))
            for v in selected_verts:
                avg_normal += v.normal
            avg_normal.normalize()
            
            center = Vector((0, 0, 0))
            for v in selected_verts:
                center += v.co
            center /= len(selected_verts)
            
            for v in selected_verts:
                offset = v.co - center
                dist = offset.dot(avg_normal)
                v.co = v.co - avg_normal * dist
        
        elif self.flatten_mode == 'VIEW':
            region = context.region
            rv3d = context.region_data
            if rv3d:
                view_normal = rv3d.view_rotation @ Vector((0, 0, 1))
                view_normal = obj.matrix_world.inverted().to_3x3() @ view_normal
                view_normal.normalize()
                
                center = Vector((0, 0, 0))
                for v in selected_verts:
                    center += v.co
                center /= len(selected_verts)
                
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
        
        active_edge = None
        if bm.select_history:
            for elem in reversed(bm.select_history):
                if isinstance(elem, bmesh.types.BMEdge):
                    active_edge = elem
                    break
        
        if not active_edge:
            selected_edges = [e for e in bm.edges if e.select]
            if selected_edges:
                active_edge = selected_edges[0]
        
        if not active_edge:
            self.report({'WARNING'}, "请先选择一条边作为参考")
            return {'CANCELLED'}
        
        edge_vec = (active_edge.verts[1].co - active_edge.verts[0].co).normalized()
        edge_start = active_edge.verts[0].co
        
        edge_vert_indices = {active_edge.verts[0].index, active_edge.verts[1].index}
        verts_to_align = [v for v in bm.verts if v.select and v.index not in edge_vert_indices]
        
        if not verts_to_align:
            self.report({'WARNING'}, "请选择要对齐的顶点（除参考边外）")
            return {'CANCELLED'}
        
        for v in verts_to_align:
            offset = v.co - edge_start
            proj_length = offset.dot(edge_vec)
            v.co = edge_start + edge_vec * proj_length
        
        bmesh.update_edit_mesh(obj.data)
        self.report({'INFO'}, f"已将 {len(verts_to_align)} 个顶点对齐到边")
        return {'FINISHED'}


# ==================== 类注册列表 ====================

classes = (
    OBJECT_OT_align_objects,
    OBJECT_OT_quick_align,
    OBJECT_OT_distribute_objects,
    OBJECT_OT_align_to_active_direction,
    MESH_OT_align_vertices,
    MESH_OT_quick_align_axis,
    MESH_OT_flatten_selection,
    MESH_OT_align_to_edge,
)
