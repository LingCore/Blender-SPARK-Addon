# ==================== 批量材质操作符模块 ====================
"""
bofu_enhanced/operators_material.py

批量材质管理相关操作符
"""

import bpy
from bpy.types import Operator
from bpy.props import StringProperty, EnumProperty


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
)
