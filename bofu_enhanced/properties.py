# ==================== 属性组定义模块 ====================
"""
bofu_enhanced/properties.py

定义所有 PropertyGroup 类和属性更新回调函数
"""

import bpy
from bpy.types import PropertyGroup
from bpy.props import (
    StringProperty, EnumProperty, FloatProperty, 
    BoolProperty, FloatVectorProperty
)


# ==================== 属性更新回调函数 ====================

def update_origin_location(self, context):
    """原点位置更新回调"""
    obj = context.active_object
    if not obj or obj.type != 'MESH':
        return
    
    current_location = obj.location.copy()
    target_location = self.origin_location.copy()
    delta_vec = target_location - current_location
    
    if delta_vec.length < 0.000001:
        return
    
    mesh = obj.data
    vert_count = len(mesh.vertices)
    if vert_count == 0:
        return
    
    coords = [0.0] * (vert_count * 3)
    mesh.vertices.foreach_get("co", coords)
    
    try:
        basis_matrix = obj.matrix_basis.to_3x3()
        local_delta = basis_matrix.inverted_safe() @ delta_vec
    except Exception:
        local_delta = delta_vec.copy()
    
    for i in range(0, len(coords), 3):
        coords[i] -= local_delta.x
        coords[i + 1] -= local_delta.y
        coords[i + 2] -= local_delta.z
    
    mesh.vertices.foreach_set("co", coords)
    obj.location = target_location
    mesh.update_tag()
    
    if context.view_layer.objects.active:
        context.view_layer.update()


def update_only_modify_origin(self, context):
    """只修改原点模式切换回调"""
    obj = context.active_object
    if self.only_modify_origin and obj and obj.type == 'MESH':
        self.origin_location = obj.location
        self.last_origin_object = obj.name
    else:
        self.last_origin_object = ""


# ==================== PropertyGroup 定义 ====================

class BatchObjExportProperties(PropertyGroup):
    """批量 OBJ 导出属性组"""
    export_path: StringProperty(
        name="导出路径",
        description="指定导出目录",
        subtype='DIR_PATH',
        default=""
    )
    forward_axis: EnumProperty(
        name="前向轴",
        items=[
            ('X', 'X Forward', ''),
            ('Y', 'Y Forward', ''),
            ('Z', 'Z Forward', ''),
            ('NEGATIVE_X', '-X Forward', ''),
            ('NEGATIVE_Y', '-Y Forward', ''),
            ('NEGATIVE_Z', '-Z Forward', ''),
        ],
        default='NEGATIVE_Z'
    )
    up_axis: EnumProperty(
        name="向上轴",
        items=[
            ('X', 'X Up', ''),
            ('Y', 'Y Up', ''),
            ('Z', 'Z Up', ''),
        ],
        default='Y'
    )
    scale_factor: FloatProperty(
        name="缩放系数",
        default=1.0,
        min=0.01,
        max=1000.0
    )
    export_materials: BoolProperty(
        name="导出材质",
        default=True
    )
    export_origin_info: BoolProperty(
        name="导出原点信息",
        default=True
    )
    only_export_origin: BoolProperty(
        name="只导出原点信息",
        default=False
    )


class BatchMaterialProperties(PropertyGroup):
    """批量材质属性组"""
    selected_material: StringProperty(
        name="选择材质",
        default=""
    )


class AnnotationSettings(PropertyGroup):
    """标注系统设置"""
    auto_overwrite: BoolProperty(
        name="自动覆盖标注",
        description="对相同元素重复测量时，自动覆盖旧标注。关闭后会保留所有标注，允许叠加显示",
        default=True
    )


class TransformPlusProperties(PropertyGroup):
    """变换增强属性组"""
    only_modify_origin: BoolProperty(
        name="只修改原点位置",
        default=False,
        update=update_only_modify_origin
    )
    origin_location: FloatVectorProperty(
        name="原点位置",
        size=3,
        default=(0.0, 0.0, 0.0),
        update=update_origin_location,
        precision=6,
        subtype='TRANSLATION'
    )
    last_origin_object: StringProperty(
        name="原点同步对象",
        default=""
    )


# ==================== 类注册列表 ====================

classes = (
    BatchObjExportProperties,
    BatchMaterialProperties,
    AnnotationSettings,
    TransformPlusProperties,
)


def register_properties():
    """注册属性到 Scene"""
    bpy.types.Scene.batch_material_props = bpy.props.PointerProperty(type=BatchMaterialProperties)
    bpy.types.Scene.batch_obj_export_props = bpy.props.PointerProperty(type=BatchObjExportProperties)
    bpy.types.Scene.transform_plus_props = bpy.props.PointerProperty(type=TransformPlusProperties)
    bpy.types.Scene.annotation_settings = bpy.props.PointerProperty(type=AnnotationSettings)


def unregister_properties():
    """注销属性"""
    for attr in (
        'batch_obj_export_props',
        'batch_material_props',
        'transform_plus_props',
        'annotation_settings',
    ):
        try:
            delattr(bpy.types.Scene, attr)
        except AttributeError:
            pass
