# ==================== 配置常量模块 ====================
"""
bofu_enhanced/config.py

统一管理所有配置常量和默认值
"""


class Config:
    """插件配置常量"""
    
    # ==================== 标注系统 ====================
    MAX_ANNOTATIONS = 500           # 最大标注数量
    MAX_TEMP_ANNOTATIONS = 100      # 最大临时标注数量
    CLEANUP_INTERVAL = 5.0          # 自动清理间隔（秒）
    COORDINATE_PRECISION = 4        # 坐标精度（小数位数）
    
    # ==================== 绘制样式 ====================
    DEFAULT_FONT_SIZE = 28          # 默认字体大小
    SMALL_FONT_SIZE = 26            # 小字体大小
    MINI_FONT_SIZE = 24             # 迷你字体大小
    
    LABEL_PADDING = 10              # 标签内边距
    LABEL_PADDING_LARGE = 15        # 大标签内边距
    LABEL_PADDING_SMALL = 8         # 小标签内边距
    
    LINE_HEIGHT = 35                # 行高
    LINE_HEIGHT_SMALL = 30          # 小行高
    LINE_HEIGHT_MINI = 28           # 迷你行高
    LINE_SPACING = 15               # 行间距
    LINE_SPACING_SMALL = 5          # 小行间距
    
    # ==================== 颜色预设 (RGBA) ====================
    class Colors:
        """颜色配置"""
        # 背景颜色
        DISTANCE_BG = (0.2, 0.2, 0.2, 0.5)      # 距离标签背景
        ANGLE_BG = (0.1, 0.3, 0.5, 0.5)         # 角度标签背景
        RADIUS_BG = (0.2, 0.5, 0.3, 0.5)        # 半径标签背景
        EDGE_ANGLE_BG = (0.5, 0.3, 0.1, 0.5)    # 边夹角标签背景
        EDGE_LENGTH_BG = (0.1, 0.4, 0.5, 0.5)   # 边长标签背景
        VERTEX_ANGLE_BG = (0.4, 0.2, 0.5, 0.5)  # 顶点角度标签背景
        LINE_ANGLE_BG = (0.4, 0.2, 0.5, 0.5)    # 线段角度标签背景
        
        # 文本颜色
        TEXT_PRIMARY = (1.0, 1.0, 1.0, 1.0)     # 主要文本颜色（白色）
        TEXT_HIGHLIGHT = (1.0, 0.9, 0.3, 1.0)   # 高亮文本颜色（黄色）
        TEXT_ANGLE_YELLOW = (1.0, 1.0, 0.5, 1.0) # 角度黄色文本
        
        # 轴向颜色
        AXIS_X = (1.0, 0.5, 0.5, 1.0)           # X轴颜色（红）
        AXIS_Y = (0.5, 1.0, 0.5, 1.0)           # Y轴颜色（绿）
        AXIS_Z = (0.5, 0.5, 1.0, 1.0)           # Z轴颜色（蓝）
        AXIS_HORIZONTAL = (1.0, 1.0, 0.5, 1.0)  # 水平面颜色（黄）
    
    # ==================== 格式化设置 ====================
    DISTANCE_FORMAT = "{:.6f} m"        # 距离格式
    DISTANCE_FORMAT_SHORT = "{:.4f} m"  # 短距离格式
    ANGLE_FORMAT = "{:.2f}°"            # 角度格式
    VALUE_FORMAT = "{:.6f}"             # 通用数值格式
    
    # ==================== 视距裁剪 ====================
    MAX_ANNOTATION_DISTANCE = 500.0     # 标注最大显示距离
    ENABLE_DISTANCE_CULLING = False     # 是否启用视距裁剪（默认关闭）
    
    # ==================== 几何体创建 ====================
    MEASURE_OBJECT_PREFIX = "测量_"      # 测量对象名称前缀
    
    # ==================== 数值阈值 ====================
    EPSILON = 1e-6                      # 通用浮点数阈值
    COORDINATE_EPSILON = 0.0001         # 坐标比较阈值
    VECTOR_LENGTH_EPSILON = 1e-8        # 向量长度阈值
    PLANE_EPSILON = 1e-6                # 平面计算阈值


class AnnotationType:
    """标注类型枚举"""
    DISTANCE = 'distance'
    DISTANCE_TEMP = 'distance_temp'
    ANGLE = 'angle'
    ANGLE_TEMP = 'angle_temp'
    EDGE_ANGLE = 'edge_angle'
    EDGE_LENGTH = 'edge_length'
    VERTEX_ANGLES = 'vertex_angles'
    LINE_ANGLES = 'line_angles'
    RADIUS = 'radius'
    RADIUS_TEMP = 'radius_temp'
    
    # 兼容类型对
    COMPATIBLE_PAIRS = [
        (ANGLE, ANGLE_TEMP),
        (RADIUS, RADIUS_TEMP),
        (DISTANCE, DISTANCE_TEMP),
    ]
    
    @classmethod
    def are_compatible(cls, type1, type2):
        """判断两个类型是否兼容"""
        if type1 == type2:
            return True
        for pair in cls.COMPATIBLE_PAIRS:
            if type1 in pair and type2 in pair:
                return True
        return False


class MeasureMode:
    """测量模式枚举"""
    CENTER_DISTANCE = 'CENTER_DISTANCE'
    EDGE_LENGTH = 'EDGE_LENGTH'
    XYZ_SPLIT = 'XYZ_SPLIT'
    ANGLE_EDGES = 'ANGLE_EDGES'
    ANGLE_FACES = 'ANGLE_FACES'
    ANGLE_VERTS = 'ANGLE_VERTS'
    RADIUS = 'RADIUS'
