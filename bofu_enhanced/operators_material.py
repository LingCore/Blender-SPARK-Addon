# ==================== 批量材质操作符模块 ====================
"""
bofu_enhanced/operators_material.py

批量材质管理相关操作符，包括：
- MATERIAL_OT_apply_to_selected: 批量应用材质
- MATERIAL_OT_cleanup_unused: 清理未使用材质
- MATERIAL_OT_cleanup_slots: 材质槽整理
- 材质自动同步系统
"""

import bpy
from bpy.types import Operator
from bpy.props import StringProperty, EnumProperty, BoolProperty


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
        
        layout.prop(self, "replace_mode")
        
        box = layout.box()
        if self.replace_mode == "REPLACE_ALL":
            box.label(text="说明: 删除对象上所有材质，只应用新材质", icon='INFO')
        elif self.replace_mode == "ADD":
            box.label(text="说明: 保留现有材质，在材质列表末尾添加新材质", icon='INFO')
        elif self.replace_mode == "REPLACE_SPECIFIC":
            box.label(text="说明: 找到旧材质并替换为新材质，其他材质不变", icon='INFO')
        
        layout.separator()
        
        if self.replace_mode == "REPLACE_SPECIFIC":
            layout.label(text="选择要替换的旧材质:")
            layout.prop_search(self, "old_material", bpy.data, "materials", text="旧材质", icon='MATERIAL')
        
        layout.label(text="选择新材质:")
        layout.prop_search(self, "new_material", bpy.data, "materials", text="新材质", icon='MATERIAL')
        
        layout.separator()
        selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        layout.label(text=f"将应用到 {len(selected_meshes)} 个网格对象", icon='OBJECT_DATA')
        
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
                    obj.data.materials.clear()
                    obj.data.materials.append(new_material)
                    success_count += 1
                    
                elif self.replace_mode == "ADD":
                    obj.data.materials.append(new_material)
                    success_count += 1
                    
                elif self.replace_mode == "REPLACE_SPECIFIC":
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


# ==================== 清理未使用材质 ====================

class MATERIAL_OT_cleanup_unused(Operator):
    """清理场景中未使用的材质"""
    bl_idname = "material.cleanup_unused"
    bl_label = "清理未使用材质"
    bl_options = {'REGISTER', 'UNDO'}
    
    include_fake_user: BoolProperty(
        name="包含假用户材质",
        description="同时删除设置了假用户（F标记）的未使用材质",
        default=False
    )
    
    def draw(self, context):
        layout = self.layout
        
        # 获取实际使用的材质
        used_materials = self._get_actually_used_materials()
        
        # 统计未使用材质
        unused_materials = self._get_unused_materials(used_materials)
        fake_user_unused = [m for m in unused_materials if m.use_fake_user]
        no_fake_user_unused = [m for m in unused_materials if not m.use_fake_user]
        
        box = layout.box()
        box.label(text="材质统计:", icon='INFO')
        box.label(text=f"  场景材质总数: {len(bpy.data.materials)}")
        box.label(text=f"  实际被对象使用: {len(used_materials)}")
        box.label(text=f"  未被任何对象使用: {len(unused_materials)}")
        if fake_user_unused:
            box.label(text=f"    其中有假用户(F): {len(fake_user_unused)}")
        if no_fake_user_unused:
            box.label(text=f"    其中无假用户: {len(no_fake_user_unused)}")
        
        layout.separator()
        layout.prop(self, "include_fake_user")
        
        if not self.include_fake_user and fake_user_unused:
            box = layout.box()
            box.label(text=f"提示: {len(fake_user_unused)} 个未使用材质有假用户(F)标记", icon='INFO')
            box.label(text="勾选上方选项可一并清理")
        
        if self.include_fake_user and fake_user_unused:
            box = layout.box()
            box.alert = True
            box.label(text="⚠️ 将同时删除假用户材质", icon='ERROR')
        
        # 预览要删除的材质
        materials_to_show = self._get_materials_to_remove(used_materials)
        if materials_to_show:
            layout.separator()
            box = layout.box()
            box.label(text=f"将删除的材质 ({len(materials_to_show)}):", icon='TRASH')
            preview_count = min(10, len(materials_to_show))
            for i in range(preview_count):
                mat = materials_to_show[i]
                icon = 'FAKE_USER_ON' if mat.use_fake_user else 'MATERIAL'
                box.label(text=f"  • {mat.name}", icon=icon)
            if len(materials_to_show) > 10:
                box.label(text=f"  ... 还有 {len(materials_to_show) - 10} 个材质")
        else:
            layout.separator()
            box = layout.box()
            box.label(text="没有需要清理的材质", icon='CHECKMARK')
    
    def _get_actually_used_materials(self):
        """获取实际被对象使用的材质集合（遍历所有对象）"""
        used = set()
        
        # 遍历所有对象的材质槽
        for obj in bpy.data.objects:
            if obj.type == 'MESH' and obj.data:
                for slot in obj.material_slots:
                    if slot.material:
                        used.add(slot.material.name)
            # 也检查曲线、文本等其他类型
            elif hasattr(obj.data, 'materials'):
                for mat in obj.data.materials:
                    if mat:
                        used.add(mat.name)
        
        return used
    
    def _get_unused_materials(self, used_materials):
        """获取未被任何对象使用的材质列表"""
        unused = []
        for mat in bpy.data.materials:
            if mat.name not in used_materials:
                unused.append(mat)
        return unused
    
    def _get_materials_to_remove(self, used_materials):
        """根据设置获取要删除的材质列表"""
        to_remove = []
        for mat in bpy.data.materials:
            if mat.name not in used_materials:
                # 未被对象使用
                if mat.use_fake_user:
                    # 有假用户，需要勾选选项才删除
                    if self.include_fake_user:
                        to_remove.append(mat)
                else:
                    # 无假用户，直接可删除
                    to_remove.append(mat)
        return to_remove
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=380)
    
    def execute(self, context):
        # 获取实际使用的材质
        used_materials = self._get_actually_used_materials()
        
        # 收集要删除的材质
        materials_to_remove = self._get_materials_to_remove(used_materials)
        
        removed_count = 0
        removed_names = []
        
        # 删除材质
        for mat in materials_to_remove:
            try:
                mat_name = mat.name
                bpy.data.materials.remove(mat)
                removed_count += 1
                removed_names.append(mat_name)
            except Exception as e:
                self.report({'WARNING'}, f"删除材质失败: {str(e)}")
        
        if removed_count > 0:
            self.report({'INFO'}, f"已清理 {removed_count} 个未使用的材质")
            print(f"[材质清理] 已删除: {', '.join(removed_names)}")
        else:
            self.report({'INFO'}, "没有未使用的材质需要清理")
        
        return {'FINISHED'}


# ==================== 材质槽整理 ====================

class MATERIAL_OT_cleanup_slots(Operator):
    """整理选中对象的材质槽（删除空槽、合并重复材质）"""
    bl_idname = "material.cleanup_slots"
    bl_label = "整理材质槽"
    bl_options = {'REGISTER', 'UNDO'}
    
    remove_empty: BoolProperty(
        name="删除空材质槽",
        description="删除没有分配材质的槽位",
        default=True
    )
    
    merge_duplicates: BoolProperty(
        name="合并重复材质",
        description="将同一材质的多个槽位合并为一个",
        default=True
    )
    
    reassign_faces: BoolProperty(
        name="重新分配面",
        description="合并时将原来使用重复槽位的面重新分配到保留的槽位",
        default=True
    )
    
    def draw(self, context):
        layout = self.layout
        
        selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        box = layout.box()
        box.label(text=f"选中对象: {len(selected_meshes)} 个网格", icon='INFO')
        
        # 统计信息
        total_slots = 0
        empty_slots = 0
        duplicate_slots = 0
        
        for obj in selected_meshes:
            total_slots += len(obj.material_slots)
            materials_seen = set()
            for slot in obj.material_slots:
                if slot.material is None:
                    empty_slots += 1
                elif slot.material.name in materials_seen:
                    duplicate_slots += 1
                else:
                    materials_seen.add(slot.material.name)
        
        box.label(text=f"  材质槽总数: {total_slots}")
        box.label(text=f"  空槽位: {empty_slots}")
        box.label(text=f"  重复槽位: {duplicate_slots}")
        
        layout.separator()
        layout.prop(self, "remove_empty")
        layout.prop(self, "merge_duplicates")
        if self.merge_duplicates:
            sub = layout.row()
            sub.enabled = self.merge_duplicates
            sub.prop(self, "reassign_faces")
        
        # 预览每个对象的情况
        if selected_meshes:
            layout.separator()
            box = layout.box()
            box.label(text="对象材质槽详情:", icon='OBJECT_DATA')
            preview_count = min(5, len(selected_meshes))
            for i in range(preview_count):
                obj = selected_meshes[i]
                slot_count = len(obj.material_slots)
                empty_count = sum(1 for s in obj.material_slots if s.material is None)
                row = box.row()
                row.label(text=f"  {obj.name}: {slot_count} 槽", icon='MESH_DATA')
                if empty_count > 0:
                    row.label(text=f"({empty_count} 空)")
            if len(selected_meshes) > 5:
                box.label(text=f"  ... 还有 {len(selected_meshes) - 5} 个对象")
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=380)
    
    def execute(self, context):
        selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not selected_meshes:
            self.report({'ERROR'}, "未选中任何网格对象")
            return {'CANCELLED'}
        
        total_removed = 0
        total_merged = 0
        processed_count = 0
        
        for obj in selected_meshes:
            removed, merged = self._cleanup_object_slots(obj)
            total_removed += removed
            total_merged += merged
            if removed > 0 or merged > 0:
                processed_count += 1
        
        # 构建报告信息
        msg_parts = []
        if total_removed > 0:
            msg_parts.append(f"删除 {total_removed} 个空槽")
        if total_merged > 0:
            msg_parts.append(f"合并 {total_merged} 个重复槽")
        
        if msg_parts:
            self.report({'INFO'}, f"已处理 {processed_count} 个对象: " + ", ".join(msg_parts))
        else:
            self.report({'INFO'}, "材质槽已经是整理好的状态")
        
        return {'FINISHED'}
    
    def _cleanup_object_slots(self, obj):
        """清理单个对象的材质槽"""
        import bmesh
        
        removed_count = 0
        merged_count = 0
        
        # 确保在对象模式
        was_edit_mode = obj.mode == 'EDIT'
        if was_edit_mode:
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # 第一步：合并重复材质
        if self.merge_duplicates and self.reassign_faces:
            merged_count = self._merge_duplicate_materials(obj)
        
        # 第二步：删除空槽
        if self.remove_empty:
            removed_count = self._remove_empty_slots(obj)
        
        # 恢复编辑模式
        if was_edit_mode:
            bpy.ops.object.mode_set(mode='EDIT')
        
        return removed_count, merged_count
    
    def _merge_duplicate_materials(self, obj):
        """合并重复的材质槽"""
        merged_count = 0
        
        if not obj.data.materials:
            return 0
        
        # 建立材质到最小索引的映射
        material_to_index = {}
        index_mapping = {}  # 旧索引 -> 新索引
        
        for i, slot in enumerate(obj.material_slots):
            mat = slot.material
            if mat is None:
                index_mapping[i] = i
                continue
            
            if mat.name not in material_to_index:
                material_to_index[mat.name] = i
                index_mapping[i] = i
            else:
                # 这是重复材质
                index_mapping[i] = material_to_index[mat.name]
                merged_count += 1
        
        if merged_count == 0:
            return 0
        
        # 重新分配面的材质索引
        mesh = obj.data
        for poly in mesh.polygons:
            old_index = poly.material_index
            if old_index in index_mapping:
                poly.material_index = index_mapping[old_index]
        
        # 删除重复的材质槽（从后往前删除）
        slots_to_remove = []
        for i, slot in enumerate(obj.material_slots):
            if slot.material and i != material_to_index.get(slot.material.name, i):
                slots_to_remove.append(i)
        
        # 从后往前删除
        for i in sorted(slots_to_remove, reverse=True):
            obj.active_material_index = i
            bpy.ops.object.material_slot_remove({'object': obj})
        
        return merged_count
    
    def _remove_empty_slots(self, obj):
        """删除空的材质槽"""
        removed_count = 0
        
        # 从后往前检查并删除空槽
        i = len(obj.material_slots) - 1
        while i >= 0:
            if obj.material_slots[i].material is None:
                # 检查是否有面使用这个槽
                has_faces = False
                for poly in obj.data.polygons:
                    if poly.material_index == i:
                        has_faces = True
                        break
                
                if not has_faces:
                    obj.active_material_index = i
                    bpy.ops.object.material_slot_remove({'object': obj})
                    removed_count += 1
            i -= 1
        
        return removed_count


# ==================== 材质预览面板 ====================

class MATERIAL_PT_quick_preview(bpy.types.Panel):
    """快速材质预览面板"""
    bl_label = "材质预览"
    bl_idname = "MATERIAL_PT_quick_preview"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Item"
    bl_order = 10
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'
    
    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            layout.label(text="请选择网格对象", icon='INFO')
            return
        
        # 材质槽统计
        slot_count = len(obj.material_slots)
        empty_count = sum(1 for s in obj.material_slots if s.material is None)
        
        row = layout.row()
        row.label(text=f"材质槽: {slot_count}", icon='MATERIAL')
        if empty_count > 0:
            row.label(text=f"({empty_count} 空)", icon='ERROR')
        
        layout.separator()
        
        # 材质列表预览
        if obj.material_slots:
            box = layout.box()
            for i, slot in enumerate(obj.material_slots):
                row = box.row(align=True)
                
                # 材质索引
                row.label(text=f"{i}:")
                
                if slot.material:
                    # 材质颜色预览
                    mat = slot.material
                    sub = row.row(align=True)
                    sub.scale_x = 0.3
                    sub.prop(mat, "diffuse_color", text="")
                    
                    # 材质名称
                    row.label(text=mat.name)
                    
                    # 用户数
                    if mat.users > 1:
                        row.label(text=f"[{mat.users}]")
                else:
                    row.label(text="(空)", icon='ERROR')
            
            # 整理按钮
            layout.separator()
            row = layout.row(align=True)
            row.operator("material.cleanup_slots", text="整理材质槽", icon='BRUSH_DATA')
        else:
            layout.label(text="无材质", icon='INFO')
        
        # 材质工具按钮
        layout.separator()
        box = layout.box()
        box.label(text="材质工具:", icon='TOOL_SETTINGS')
        col = box.column(align=True)
        col.operator("material.apply_to_selected", text="批量应用材质", icon='MATERIAL')
        col.operator("material.cleanup_unused", text="清理未使用材质", icon='TRASH')


# ==================== 材质自动同步系统 ====================

# 存储材质的上一次状态，用于检测变化
_material_cache = {}

# 防止递归同步的标志
_syncing = False


def get_principled_bsdf(material):
    """获取材质的 Principled BSDF 节点"""
    if not material or not material.use_nodes:
        return None
    
    for node in material.node_tree.nodes:
        if node.type == 'BSDF_PRINCIPLED':
            return node
    return None


def cache_material_state(material):
    """缓存材质状态"""
    principled = get_principled_bsdf(material)
    if not principled:
        return
    
    # 缓存视图显示参数（包含 Alpha）
    viewport_color = tuple(material.diffuse_color[:4])
    viewport_metallic = material.metallic
    viewport_roughness = material.roughness
    
    # 缓存节点参数（包含 Alpha）
    node_color = tuple(principled.inputs['Base Color'].default_value[:4]) if 'Base Color' in principled.inputs else (0.8, 0.8, 0.8, 1.0)
    node_alpha = principled.inputs['Alpha'].default_value if 'Alpha' in principled.inputs else 1.0
    node_metallic = principled.inputs['Metallic'].default_value if 'Metallic' in principled.inputs else 0.0
    node_roughness = principled.inputs['Roughness'].default_value if 'Roughness' in principled.inputs else 0.5
    
    _material_cache[material.name] = {
        'viewport_color': viewport_color,
        'viewport_metallic': viewport_metallic,
        'viewport_roughness': viewport_roughness,
        'node_color': node_color,
        'node_alpha': node_alpha,
        'node_metallic': node_metallic,
        'node_roughness': node_roughness,
    }


def sync_material_auto(material):
    """自动同步材质参数（双向）"""
    global _syncing
    
    if _syncing:
        return
    
    principled = get_principled_bsdf(material)
    if not principled:
        return
    
    cache = _material_cache.get(material.name)
    if not cache:
        cache_material_state(material)
        return
    
    _syncing = True
    
    try:
        # 当前视图显示参数（包含 Alpha）
        viewport_color = tuple(material.diffuse_color[:4])
        viewport_metallic = material.metallic
        viewport_roughness = material.roughness
        
        # 当前节点参数（包含 Alpha）
        node_color = tuple(principled.inputs['Base Color'].default_value[:4]) if 'Base Color' in principled.inputs else (0.8, 0.8, 0.8, 1.0)
        node_alpha = principled.inputs['Alpha'].default_value if 'Alpha' in principled.inputs else 1.0
        node_metallic = principled.inputs['Metallic'].default_value if 'Metallic' in principled.inputs else 0.0
        node_roughness = principled.inputs['Roughness'].default_value if 'Roughness' in principled.inputs else 0.5
        
        # 检测哪边发生了变化
        viewport_changed = (
            viewport_color != cache['viewport_color'] or
            abs(viewport_metallic - cache['viewport_metallic']) > 0.001 or
            abs(viewport_roughness - cache['viewport_roughness']) > 0.001
        )
        
        node_changed = (
            node_color != cache['node_color'] or
            abs(node_alpha - cache.get('node_alpha', 1.0)) > 0.001 or
            abs(node_metallic - cache['node_metallic']) > 0.001 or
            abs(node_roughness - cache['node_roughness']) > 0.001
        )
        
        if viewport_changed and not node_changed:
            # 视图显示变化 → 同步到节点
            if 'Base Color' in principled.inputs:
                principled.inputs['Base Color'].default_value = viewport_color
            if 'Alpha' in principled.inputs:
                principled.inputs['Alpha'].default_value = viewport_color[3]
            if 'Metallic' in principled.inputs:
                principled.inputs['Metallic'].default_value = viewport_metallic
            if 'Roughness' in principled.inputs:
                principled.inputs['Roughness'].default_value = viewport_roughness
        
        elif node_changed and not viewport_changed:
            # 节点变化 → 同步到视图显示
            material.diffuse_color = (node_color[0], node_color[1], node_color[2], node_alpha)
            material.metallic = node_metallic
            material.roughness = node_roughness
        
        # 更新缓存
        cache_material_state(material)
    
    finally:
        _syncing = False


def clear_material_cache():
    """清除材质缓存"""
    global _material_cache
    _material_cache = {}


# ==================== 类注册列表 ====================

classes = (
    MATERIAL_OT_apply_to_selected,
    MATERIAL_OT_cleanup_unused,
    MATERIAL_OT_cleanup_slots,
    MATERIAL_PT_quick_preview,
)
