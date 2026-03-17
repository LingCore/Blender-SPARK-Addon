# ==================== 渲染工具模块 ====================
"""
bofu_enhanced/render_utils.py

提供绘制相关的工具类：
- ShaderCache: Shader 缓存管理
- LabelRenderer: 通用标签渲染器
"""

import bpy
import blf
import gpu
from gpu_extras.batch import batch_for_shader

from .config import Config


# ==================== Shader 缓存 ====================

class ShaderCache:
    """
    Shader 缓存单例
    
    避免每帧重复创建 shader，提升渲染性能
    """
    _shader = None
    
    @classmethod
    def get_shader(cls):
        """获取 UNIFORM_COLOR shader（带缓存）"""
        if cls._shader is None:
            cls._shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        return cls._shader
    
    @classmethod
    def clear(cls):
        """清除缓存（用于插件卸载时）"""
        cls._shader = None


# ==================== 标签渲染器 ====================

class LabelRenderer:
    """
    通用标签渲染器
    
    提供统一的标签绘制接口，支持：
    - 单行/多行文本
    - 自定义颜色
    - 背景绘制
    - 居中对齐
    """
    
    @staticmethod
    def draw_background(center_x, center_y, width, height, color, padding=None):
        """
        绘制标签背景
        
        参数:
            center_x, center_y: 背景中心位置
            width, height: 内容宽高（不含padding）
            color: RGBA颜色元组
            padding: 内边距，默认使用配置值
        """
        if padding is None:
            padding = Config.LABEL_PADDING
        
        bg_x = center_x - width / 2 - padding
        bg_y = center_y - height / 2 - padding
        bg_width = width + padding * 2
        bg_height = height + padding * 2
        
        vertices = (
            (bg_x, bg_y),
            (bg_x + bg_width, bg_y),
            (bg_x + bg_width, bg_y + bg_height),
            (bg_x, bg_y + bg_height),
        )
        indices = ((0, 1, 2), (2, 3, 0))
        
        gpu.state.blend_set('ALPHA')
        shader = ShaderCache.get_shader()
        batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)
        gpu.state.blend_set('NONE')
    
    @staticmethod
    def draw_text(x, y, text, color, font_id=0, font_size=None):
        """
        绘制单行文本
        
        参数:
            x, y: 文本位置（左下角）
            text: 文本内容
            color: RGBA颜色元组
            font_id: 字体ID
            font_size: 字体大小，默认使用配置值
        """
        if font_size is None:
            font_size = Config.DEFAULT_FONT_SIZE
        
        blf.size(font_id, font_size)
        blf.position(font_id, x, y, 0)
        blf.color(font_id, *color)
        blf.draw(font_id, text)
    
    @staticmethod
    def get_text_dimensions(text, font_id=0, font_size=None):
        """
        获取文本尺寸
        
        返回: (width, height)
        """
        if font_size is None:
            font_size = Config.DEFAULT_FONT_SIZE
        
        blf.size(font_id, font_size)
        return blf.dimensions(font_id, text)
    
    @staticmethod
    def draw_single_line_label(screen_pos, text, text_color=None, bg_color=None, 
                                font_size=None, padding=None):
        """
        绘制单行标签（带背景）
        
        参数:
            screen_pos: 屏幕位置 (x, y)
            text: 文本内容
            text_color: 文本颜色，默认白色
            bg_color: 背景颜色，默认距离标签颜色
            font_size: 字体大小
            padding: 内边距
        """
        if text_color is None:
            text_color = Config.Colors.TEXT_PRIMARY
        if bg_color is None:
            bg_color = Config.Colors.DISTANCE_BG
        if font_size is None:
            font_size = Config.DEFAULT_FONT_SIZE
        if padding is None:
            padding = Config.LABEL_PADDING
        
        font_id = 0
        text_width, text_height = LabelRenderer.get_text_dimensions(text, font_id, font_size)
        
        # 绘制背景
        LabelRenderer.draw_background(
            screen_pos[0], screen_pos[1],
            text_width, text_height,
            bg_color, padding
        )
        
        # 绘制文本（居中）
        text_x = screen_pos[0] - text_width / 2
        text_y = screen_pos[1] - text_height / 2
        LabelRenderer.draw_text(text_x, text_y, text, text_color, font_id, font_size)
    
    @staticmethod
    def draw_multi_line_label(screen_pos, lines, colors=None, bg_color=None,
                               font_size=None, padding=None, line_height=None, line_spacing=None):
        """
        绘制多行标签（带背景）
        
        参数:
            screen_pos: 屏幕位置 (x, y)
            lines: 文本行列表
            colors: 每行的颜色列表，如果为None则全部使用白色
            bg_color: 背景颜色
            font_size: 字体大小
            padding: 内边距
            line_height: 行高
            line_spacing: 行间距
        """
        if not lines:
            return
        
        if colors is None:
            colors = [Config.Colors.TEXT_PRIMARY] * len(lines)
        elif len(colors) < len(lines):
            # 补齐颜色列表
            colors = list(colors) + [Config.Colors.TEXT_PRIMARY] * (len(lines) - len(colors))
        
        if bg_color is None:
            bg_color = Config.Colors.ANGLE_BG
        if font_size is None:
            font_size = Config.DEFAULT_FONT_SIZE
        if padding is None:
            padding = Config.LABEL_PADDING_LARGE
        if line_height is None:
            line_height = Config.LINE_HEIGHT
        if line_spacing is None:
            line_spacing = Config.LINE_SPACING
        
        font_id = 0
        blf.size(font_id, font_size)
        
        # 计算最大宽度
        max_width = 0
        line_widths = []
        for line in lines:
            w, _ = blf.dimensions(font_id, line)
            line_widths.append(w)
            max_width = max(max_width, w)
        
        # 计算总高度
        total_height = line_height * len(lines) + line_spacing * (len(lines) - 1)
        
        # 绘制背景
        LabelRenderer.draw_background(
            screen_pos[0], screen_pos[1],
            max_width, total_height,
            bg_color, padding
        )
        
        # 绘制每行文本
        y_start = screen_pos[1] + total_height / 2 - line_height / 2
        for i, (line, color, width) in enumerate(zip(lines, colors, line_widths)):
            y = y_start - i * (line_height + line_spacing)
            x = screen_pos[0] - width / 2
            LabelRenderer.draw_text(x, y, line, color, font_id, font_size)
    
    @staticmethod
    def draw_label_with_offset(screen_pos, lines, colors=None, bg_color=None,
                                offset=(20, 20), font_size=None, padding=None):
        """
        绘制带偏移的标签（用于避免遮挡元素）
        
        参数:
            screen_pos: 基准屏幕位置
            offset: 偏移量 (x, y)
            其他参数同 draw_multi_line_label
        """
        offset_pos = (screen_pos[0] + offset[0], screen_pos[1] + offset[1])
        
        if len(lines) == 1:
            LabelRenderer.draw_single_line_label(
                offset_pos, lines[0],
                colors[0] if colors else None,
                bg_color, font_size, padding
            )
        else:
            LabelRenderer.draw_multi_line_label(
                offset_pos, lines, colors, bg_color,
                font_size, padding
            )


# ==================== 工具函数 ====================

def get_preferences():
    """
    获取插件偏好设置
    
    返回偏好设置对象，如果不存在则返回 None
    """
    try:
        addon_prefs = bpy.context.preferences.addons.get(__package__)
        if addon_prefs:
            return addon_prefs.preferences
    except Exception:
        pass
    return None


def get_pref_value(attr_name, default):
    """
    获取偏好设置的某个属性值
    
    参数:
        attr_name: 属性名
        default: 默认值
    
    返回:
        偏好设置中的值，如果不存在则返回默认值
    """
    prefs = get_preferences()
    if prefs and hasattr(prefs, attr_name):
        return getattr(prefs, attr_name)
    return default


def get_font_size():
    """获取字体大小（优先使用偏好设置）"""
    return get_pref_value('annotation_font_size', Config.DEFAULT_FONT_SIZE)


def get_bg_color(color_type):
    """
    获取背景颜色（优先使用偏好设置）
    
    参数:
        color_type: 颜色类型 ('distance', 'angle', 'radius', 等)
    """
    # 尝试从偏好设置获取
    attr_name = f'{color_type}_bg_color'
    prefs = get_preferences()
    if prefs and hasattr(prefs, attr_name):
        color = getattr(prefs, attr_name)
        if len(color) == 4:
            return tuple(color)
    
    # 返回默认颜色
    color_map = {
        'distance': Config.Colors.DISTANCE_BG,
        'angle': Config.Colors.ANGLE_BG,
        'radius': Config.Colors.RADIUS_BG,
        'edge_angle': Config.Colors.EDGE_ANGLE_BG,
        'edge_length': Config.Colors.EDGE_LENGTH_BG,
        'vertex_angle': Config.Colors.VERTEX_ANGLE_BG,
        'line_angle': Config.Colors.LINE_ANGLE_BG,
        'face_area': Config.Colors.FACE_AREA_BG,
        'perimeter': Config.Colors.PERIMETER_BG,
        'arc_length': Config.Colors.ARC_LENGTH_BG,
    }
    return color_map.get(color_type, Config.Colors.DISTANCE_BG)
