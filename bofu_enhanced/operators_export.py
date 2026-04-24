# ==================== 批量导出操作符模块 ====================
"""
bofu_enhanced/operators_export.py

批量导出 OBJ 文件相关操作符
"""

import bpy
import json
import logging
import os
from bpy.types import Operator
from bpy.props import StringProperty, EnumProperty, FloatProperty, BoolProperty

logger = logging.getLogger(__name__)

ORIGIN_FORMAT_FLOAT_INITIALIZER = 'FLOAT_INITIALIZER'
ORIGIN_FORMAT_JSON_ARRAY = 'JSON_ARRAY'
ORIGIN_FORMAT_CSV = 'CSV'

ORIGIN_FORMAT_ITEMS = [
    (
        ORIGIN_FORMAT_FLOAT_INITIALIZER,
        "Float 初始化器",
        "模型名: { -2.350247f, 0.003200f, 0.911799f }",
    ),
    (
        ORIGIN_FORMAT_JSON_ARRAY,
        "JSON 对象",
        "{\"name\":\"模型名\",\"origin\":[-2.350247,0.003200,0.911799]}",
    ),
    (
        ORIGIN_FORMAT_CSV,
        "CSV",
        "模型名,-2.350247,0.003200,0.911799",
    ),
]


def format_float_literal(value):
    """格式化为开发可直接粘贴的 float 字面量。"""
    return f"{value:.6f}f"


def format_origin_initializer(data):
    return (
        f"{data['name']}: "
        f"{{ {format_float_literal(data['x'])}, "
        f"{format_float_literal(data['y'])}, "
        f"{format_float_literal(data['z'])} }}"
    )


def format_origin_json_array(data):
    payload = {
        "name": data["name"],
        "origin": [data["x"], data["y"], data["z"]],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def format_origin_csv(data):
    name = str(data["name"])
    if any(ch in name for ch in [",", '"', "\n", "\r"]):
        name = '"' + name.replace('"', '""') + '"'
    return f"{name},{data['x']:.6f},{data['y']:.6f},{data['z']:.6f}"


def format_origin_line(data, origin_format):
    if origin_format == ORIGIN_FORMAT_JSON_ARRAY:
        return format_origin_json_array(data)
    if origin_format == ORIGIN_FORMAT_CSV:
        return format_origin_csv(data)
    return format_origin_initializer(data)


class EXPORT_OT_batch_obj_with_origin(Operator):
    """批量导出OBJ文件并生成原点信息"""
    bl_idname = "export.batch_obj_with_origin"
    bl_label = "批量导出OBJ"
    bl_options = {'REGISTER'}

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
    origin_format: EnumProperty(
        name="原点格式",
        description="origin_info.txt 中每个原点坐标的输出格式",
        items=ORIGIN_FORMAT_ITEMS,
        default=ORIGIN_FORMAT_FLOAT_INITIALIZER,
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "export_path")
        layout.separator()
        box = layout.box()
        box.label(text="导出设置:", icon='SETTINGS')
        box.prop(self, "forward_axis")
        box.prop(self, "up_axis")
        box.prop(self, "scale_factor")
        box.prop(self, "export_materials")
        layout.separator()
        box = layout.box()
        box.label(text="原点信息:", icon='EMPTY_AXIS')
        box.prop(self, "export_origin_info")
        box.prop(self, "only_export_origin")
        row = box.row()
        row.enabled = self.export_origin_info or self.only_export_origin
        row.prop(self, "origin_format")
        layout.separator()
        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        layout.label(text=f"将导出 {len(meshes)} 个网格对象", icon='INFO')

    def invoke(self, context, event):
        if not self.export_path and bpy.data.filepath:
            self.export_path = os.path.dirname(bpy.data.filepath)
        return context.window_manager.invoke_props_dialog(self, width=400)

    def execute(self, context):
        if self.export_path:
            export_dir = bpy.path.abspath(self.export_path)
        else:
            if not bpy.data.filepath:
                self.report({'ERROR'}, "请先保存Blender文件或手动指定导出路径")
                return {'CANCELLED'}
            export_dir = os.path.dirname(bpy.data.filepath)
        
        try:
            os.makedirs(export_dir, exist_ok=True)
        except Exception as e:
            self.report({'ERROR'}, f"无法创建导出目录: {str(e)}")
            return {'CANCELLED'}
        
        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        if not meshes:
            self.report({'ERROR'}, "未检测到选中的网格对象")
            return {'CANCELLED'}

        origin_info_file = os.path.join(export_dir, "origin_info.txt")
        origin_data = []
        exported_count = 0
        
        for ob in meshes:
            try:
                world_location = ob.matrix_world.translation
                origin_data.append({
                    'name': ob.name,
                    'x': round(world_location.x, 6),
                    'y': round(world_location.y, 6),
                    'z': round(world_location.z, 6)
                })
                
                if not self.only_export_origin:
                    bpy.ops.object.select_all(action='DESELECT')
                    ob.select_set(True)
                    context.view_layer.objects.active = ob
                    filepath = os.path.join(export_dir, f"{ob.name}.obj")
                    bpy.ops.wm.obj_export(
                        filepath=filepath,
                        export_selected_objects=True,
                        forward_axis=self.forward_axis,
                        up_axis=self.up_axis,
                        global_scale=self.scale_factor,
                        path_mode='STRIP',
                        export_materials=self.export_materials
                    )
                    exported_count += 1
                    logger.debug("已导出: %s.obj", ob.name)
            except Exception as e:
                self.report({'WARNING'}, f"导出 {ob.name} 时发生错误: {str(e)}")
                continue
        
        if self.export_origin_info or self.only_export_origin:
            try:
                with open(origin_info_file, 'w', encoding='utf-8') as f:
                    for data in origin_data:
                        f.write(f"{format_origin_line(data, self.origin_format)}\n")
                self.report({'INFO'}, f"原点信息已写入: {origin_info_file}")
            except Exception as e:
                self.report({'WARNING'}, f"写入原点信息时发生错误: {str(e)}")
        
        if self.only_export_origin:
            self.report({'INFO'}, f"完成！已导出 {len(origin_data)} 个物体的原点信息 -> {export_dir}")
        else:
            self.report({'INFO'}, f"完成！共导出 {exported_count} 个 OBJ -> {export_dir}")
        return {'FINISHED'}


# ==================== 类注册列表 ====================

classes = (
    EXPORT_OT_batch_obj_with_origin,
)
