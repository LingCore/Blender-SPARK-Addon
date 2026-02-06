# ==================== 属性组定义模块 ====================
"""
bofu_enhanced/properties.py

定义所有 PropertyGroup 类和属性更新回调函数
"""

import bpy
from bpy.types import PropertyGroup
from bpy.props import (
    StringProperty, EnumProperty, FloatProperty,
    BoolProperty, FloatVectorProperty,
    IntProperty, CollectionProperty, PointerProperty
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


class MiscSettings(PropertyGroup):
    """杂项设置"""
    material_sync_enabled: BoolProperty(
        name="材质同步",
        description="开启后，视图显示和 Principled BSDF 节点的颜色、金属度、糙度会自动双向同步",
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


# ==================== 运动学属性更新回调 ====================

def update_driver_progress(self, context):
    """驱动进度更新回调 - 实时求解机构"""
    if not self.is_active:
        return
    try:
        from .operators_kinematics import solve_and_apply
        solve_and_apply(context)
    except Exception as e:
        print(f"[运动学] 求解更新失败: {e}")


# ==================== 运动学属性组 ====================

class KinematicJointProperties(PropertyGroup):
    """运动学关节属性"""
    joint_type: EnumProperty(
        name="关节类型",
        items=[
            ('REVOLUTE', '旋转', '铰接/旋转关节 - 两个对象绕共享铰接点相对旋转'),
            ('PRISMATIC', '平移', '滑动/平移关节 - 两个对象沿指定轴相对平移'),
        ],
        default='REVOLUTE',
    )

    object_a: PointerProperty(
        name="对象A",
        type=bpy.types.Object,
        description="关节连接的第一个对象",
    )

    object_b: PointerProperty(
        name="对象B",
        type=bpy.types.Object,
        description="关节连接的第二个对象",
    )

    a_is_ground: BoolProperty(
        name="A端为地面",
        description="勾选时，对象A视为固定地面（不运动）",
        default=False,
    )

    # 铰接点世界坐标 (旋转关节用)
    pivot_world: FloatVectorProperty(
        name="铰接点",
        size=3,
        default=(0.0, 0.0, 0.0),
        subtype='TRANSLATION',
        precision=6,
    )

    # 铰接点在各对象局部坐标系中的 2D 坐标（由求解器自动计算）
    pivot_local_a: FloatVectorProperty(
        name="A端局部铰接点(2D)",
        size=2,
        default=(0.0, 0.0),
        precision=6,
    )

    pivot_local_b: FloatVectorProperty(
        name="B端局部铰接点(2D)",
        size=2,
        default=(0.0, 0.0),
        precision=6,
    )

    # 平移关节的滑动方向
    axis_direction: EnumProperty(
        name="滑动方向",
        items=[
            ('X', 'X轴', '沿X轴方向平移'),
            ('Y', 'Y轴', '沿Y轴方向平移'),
            ('Z', 'Z轴', '沿Z轴方向平移'),
        ],
        default='Y',
    )


class KinematicMechanismProperties(PropertyGroup):
    """机构运动学属性（场景级别）"""
    joints: CollectionProperty(
        type=KinematicJointProperties,
    )

    active_joint_index: IntProperty(
        name="活动关节索引",
        default=0,
    )

    driver_joint_index: IntProperty(
        name="驱动关节索引",
        description="设为驱动的关节在列表中的索引（-1 表示未设置）",
        default=-1,
    )

    driver_progress: FloatProperty(
        name="驱动",
        description="拖动滑块驱动机构运动（0=起始位置，1=终止位置）",
        min=0.0,
        max=1.0,
        default=0.0,
        subtype='FACTOR',
        update=update_driver_progress,
    )

    driver_min: FloatProperty(
        name="最小值",
        description="驱动范围最小值（平移单位:m，旋转单位:°）",
        default=-0.05,
        precision=4,
    )

    driver_max: FloatProperty(
        name="最大值",
        description="驱动范围最大值（平移单位:m，旋转单位:°）",
        default=0.05,
        precision=4,
    )

    is_active: BoolProperty(
        name="机构激活",
        default=False,
        description="机构是否处于求解/驱动状态",
    )

    working_plane: EnumProperty(
        name="工作平面",
        description="2D机构的运动平面",
        items=[
            ('XY', 'XY 平面', '在XY平面内运动（绕Z轴旋转）'),
            ('XZ', 'XZ 平面', '在XZ平面内运动（绕Y轴旋转）'),
            ('YZ', 'YZ 平面', '在YZ平面内运动（绕X轴旋转）'),
        ],
        default='XY',
    )

    # 存储原始变换的 JSON 字符串（激活时自动保存）
    original_transforms_json: StringProperty(
        name="原始变换数据",
        default="",
    )


# ==================== 类注册列表 ====================

classes = (
    BatchObjExportProperties,
    BatchMaterialProperties,
    AnnotationSettings,
    MiscSettings,
    TransformPlusProperties,
    KinematicJointProperties,
    KinematicMechanismProperties,
)


def register_properties():
    """注册属性到 Scene"""
    bpy.types.Scene.batch_material_props = bpy.props.PointerProperty(type=BatchMaterialProperties)
    bpy.types.Scene.batch_obj_export_props = bpy.props.PointerProperty(type=BatchObjExportProperties)
    bpy.types.Scene.transform_plus_props = bpy.props.PointerProperty(type=TransformPlusProperties)
    bpy.types.Scene.annotation_settings = bpy.props.PointerProperty(type=AnnotationSettings)
    bpy.types.Scene.misc_settings = bpy.props.PointerProperty(type=MiscSettings)
    bpy.types.Scene.kinematics_props = bpy.props.PointerProperty(type=KinematicMechanismProperties)


def unregister_properties():
    """注销属性"""
    for attr in (
        'batch_obj_export_props',
        'batch_material_props',
        'transform_plus_props',
        'annotation_settings',
        'misc_settings',
        'kinematics_props',
    ):
        try:
            delattr(bpy.types.Scene, attr)
        except AttributeError:
            pass
