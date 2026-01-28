# ==================== 插件偏好设置模块 ====================
"""
bofu_enhanced/preferences.py

插件偏好设置面板，允许用户自定义：
- 标注字体大小
- 标注颜色
- 功能开关
"""

import bpy
from bpy.types import AddonPreferences
from bpy.props import (
    IntProperty, FloatProperty, BoolProperty, 
    FloatVectorProperty, EnumProperty
)

from .config import Config


class BofuEnhancedPreferences(AddonPreferences):
    """Blender增强工具偏好设置"""
    bl_idname = "bofu_enhanced"
    
    # ==================== 标注显示设置 ====================
    
    annotation_font_size: IntProperty(
        name="标注字体大小",
        description="标注文字的字体大小",
        default=Config.DEFAULT_FONT_SIZE,
        min=12,
        max=48,
    )
    
    annotation_max_distance: FloatProperty(
        name="标注最大显示距离",
        description="超过此距离的标注将不显示（0表示无限制）",
        default=0.0,
        min=0.0,
        max=10000.0,
        unit='LENGTH',
    )
    
    enable_distance_culling: BoolProperty(
        name="启用视距裁剪",
        description="是否根据距离自动隐藏远处的标注",
        default=False,
    )
    
    # ==================== 颜色设置 ====================
    
    distance_bg_color: FloatVectorProperty(
        name="距离标注背景色",
        description="距离标注的背景颜色",
        subtype='COLOR',
        size=4,
        default=Config.Colors.DISTANCE_BG,
        min=0.0,
        max=1.0,
    )
    
    angle_bg_color: FloatVectorProperty(
        name="角度标注背景色",
        description="角度标注的背景颜色",
        subtype='COLOR',
        size=4,
        default=Config.Colors.ANGLE_BG,
        min=0.0,
        max=1.0,
    )
    
    radius_bg_color: FloatVectorProperty(
        name="半径标注背景色",
        description="半径/直径标注的背景颜色",
        subtype='COLOR',
        size=4,
        default=Config.Colors.RADIUS_BG,
        min=0.0,
        max=1.0,
    )
    
    edge_angle_bg_color: FloatVectorProperty(
        name="边夹角标注背景色",
        description="两边夹角标注的背景颜色",
        subtype='COLOR',
        size=4,
        default=Config.Colors.EDGE_ANGLE_BG,
        min=0.0,
        max=1.0,
    )
    
    edge_length_bg_color: FloatVectorProperty(
        name="边长标注背景色",
        description="边长标注的背景颜色",
        subtype='COLOR',
        size=4,
        default=Config.Colors.EDGE_LENGTH_BG,
        min=0.0,
        max=1.0,
    )
    
    vertex_angle_bg_color: FloatVectorProperty(
        name="顶点角度标注背景色",
        description="顶点角度标注的背景颜色",
        subtype='COLOR',
        size=4,
        default=Config.Colors.VERTEX_ANGLE_BG,
        min=0.0,
        max=1.0,
    )
    
    # ==================== 功能开关 ====================
    
    auto_save_annotations: BoolProperty(
        name="自动保存标注",
        description="保存文件时自动保存标注数据到场景",
        default=True,
    )
    
    auto_load_annotations: BoolProperty(
        name="自动加载标注",
        description="打开文件时自动加载保存的标注数据",
        default=True,
    )
    
    show_annotation_count: BoolProperty(
        name="显示标注计数",
        description="在状态栏显示当前标注数量",
        default=False,
    )
    
    # ==================== 测量设置 ====================
    
    default_create_geometry: BoolProperty(
        name="默认创建辅助几何体",
        description="测量时默认是否创建辅助几何体",
        default=True,
    )
    
    distance_precision: IntProperty(
        name="距离精度",
        description="距离数值显示的小数位数",
        default=6,
        min=1,
        max=10,
    )
    
    angle_precision: IntProperty(
        name="角度精度",
        description="角度数值显示的小数位数",
        default=2,
        min=0,
        max=6,
    )
    
    # ==================== 面板绘制 ====================
    
    def draw(self, context):
        layout = self.layout
        
        # 标注显示设置
        box = layout.box()
        box.label(text="标注显示设置", icon='FONT_DATA')
        col = box.column(align=True)
        col.prop(self, "annotation_font_size")
        col.prop(self, "enable_distance_culling")
        if self.enable_distance_culling:
            col.prop(self, "annotation_max_distance")
        
        # 颜色设置
        box = layout.box()
        box.label(text="标注颜色设置", icon='COLOR')
        col = box.column(align=True)
        col.prop(self, "distance_bg_color")
        col.prop(self, "angle_bg_color")
        col.prop(self, "radius_bg_color")
        col.prop(self, "edge_angle_bg_color")
        col.prop(self, "edge_length_bg_color")
        col.prop(self, "vertex_angle_bg_color")
        
        # 重置颜色按钮
        row = box.row()
        row.operator("bofu.reset_annotation_colors", text="重置为默认颜色", icon='LOOP_BACK')
        
        # 功能开关
        box = layout.box()
        box.label(text="功能设置", icon='PREFERENCES')
        col = box.column(align=True)
        col.prop(self, "auto_save_annotations")
        col.prop(self, "auto_load_annotations")
        col.prop(self, "show_annotation_count")
        col.prop(self, "default_create_geometry")
        
        # 精度设置
        box = layout.box()
        box.label(text="数值精度", icon='PREFERENCES')
        row = box.row()
        row.prop(self, "distance_precision")
        row.prop(self, "angle_precision")


class BOFU_OT_reset_annotation_colors(bpy.types.Operator):
    """重置标注颜色为默认值"""
    bl_idname = "bofu.reset_annotation_colors"
    bl_label = "重置标注颜色"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        prefs = context.preferences.addons.get('bofu_enhanced')
        if prefs:
            p = prefs.preferences
            p.distance_bg_color = Config.Colors.DISTANCE_BG
            p.angle_bg_color = Config.Colors.ANGLE_BG
            p.radius_bg_color = Config.Colors.RADIUS_BG
            p.edge_angle_bg_color = Config.Colors.EDGE_ANGLE_BG
            p.edge_length_bg_color = Config.Colors.EDGE_LENGTH_BG
            p.vertex_angle_bg_color = Config.Colors.VERTEX_ANGLE_BG
            self.report({'INFO'}, "标注颜色已重置为默认值")
        return {'FINISHED'}


# ==================== 类注册列表 ====================

classes = (
    BofuEnhancedPreferences,
    BOFU_OT_reset_annotation_colors,
)
