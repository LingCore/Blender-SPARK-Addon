# ==================== 对象级操作符模块 ====================
"""
bofu_enhanced/operators_object.py

对象级操作符，包括：
- OBJECT_OT_mirror_plus: 镜像增强
- OBJECT_OT_batch_rename: 名称批量替换
"""

import bpy
import bmesh
import re
from bpy.types import Operator
from bpy.props import StringProperty, EnumProperty, FloatProperty, BoolProperty
from mathutils import Vector, Matrix

from .utils import (
    axis_to_vec, reflect_point_across_plane, move_origin_keep_world_mesh,
    bake_modifiers_to_mesh, delete_side_by_plane_world
)


# ==================== 镜像增强操作符 ====================

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
    """添加到修改器菜单的回调函数"""
    self.layout.operator(OBJECT_OT_mirror_plus.bl_idname, text="镜像（增强）", icon="MOD_MIRROR")


# ==================== 名称批量替换操作符 ====================

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

            if new_name == old_name:
                continue

            existing_obj = bpy.data.objects.get(new_name)
            if existing_obj and existing_obj != obj:
                if self.handle_conflict == "SKIP":
                    skipped_count += 1
                    continue
                elif self.handle_conflict == "DELETE_OLD":
                    bpy.data.objects.remove(existing_obj, do_unlink=True)
                    deleted_count += 1
                elif self.handle_conflict == "ADD_SUFFIX":
                    suffix = 1
                    base_name = new_name
                    while bpy.data.objects.get(new_name):
                        new_name = f"{base_name}.{suffix:03d}"
                        suffix += 1

            obj.name = new_name
            renamed_count += 1

        msg_parts = [f"已重命名 {renamed_count} 个对象"]
        if skipped_count > 0:
            msg_parts.append(f"跳过 {skipped_count} 个")
        if deleted_count > 0:
            msg_parts.append(f"删除旧对象 {deleted_count} 个")
        self.report({"INFO"}, "，".join(msg_parts))
        return {"FINISHED"}


# ==================== 类注册列表 ====================

classes = (
    OBJECT_OT_mirror_plus,
    OBJECT_OT_batch_rename,
)
