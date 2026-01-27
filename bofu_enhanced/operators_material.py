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


# ==================== 类注册列表 ====================

classes = (
    MATERIAL_OT_apply_to_selected,
)
