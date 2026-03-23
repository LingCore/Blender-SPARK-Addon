# ==================== 视口 FPS 计数器 ====================
"""
bofu_enhanced/fps_overlay.py

在 3D 视口左下角绘制实时帧率（FPS）。
使用滑动窗口平均值，避免数值剧烈跳动。
"""

import time
import blf
import gpu
from gpu_extras.batch import batch_for_shader
import bpy

# ==================== 全局状态 ====================

_fps_draw_handler = None
_frame_times = []          # 最近 N 帧的时间戳
_MAX_SAMPLES = 60          # 滑动窗口大小
_cached_fps_text = "FPS: --"
_last_update_time = 0.0    # 上次更新文本的时间
_UPDATE_INTERVAL = 0.25    # 文本更新间隔（秒），避免数字闪烁


# ==================== 绘制回调 ====================

def _fps_draw_callback():
    """视口绘制回调：计算并绘制 FPS"""
    global _frame_times, _cached_fps_text, _last_update_time

    now = time.perf_counter()
    _frame_times.append(now)

    # 保留窗口内的帧
    if len(_frame_times) > _MAX_SAMPLES:
        _frame_times = _frame_times[-_MAX_SAMPLES:]

    # 定时更新显示文本（避免每帧刷新导致数字闪烁）
    if now - _last_update_time >= _UPDATE_INTERVAL:
        _last_update_time = now
        if len(_frame_times) >= 2:
            elapsed = _frame_times[-1] - _frame_times[0]
            if elapsed > 0:
                fps = (len(_frame_times) - 1) / elapsed
                _cached_fps_text = f"FPS: {fps:.0f}"
            else:
                _cached_fps_text = "FPS: --"
        else:
            _cached_fps_text = "FPS: --"

    # ---- 绘制 ----
    try:
        region = bpy.context.region
        if not region:
            return

        # DPI 感知字体大小
        ui_scale = bpy.context.preferences.system.ui_scale
        pixel_size = bpy.context.preferences.system.pixel_size
        dpi_fac = ui_scale * pixel_size
        font_id = 0
        font_size = int(14 * dpi_fac)

        margin = int(20 * dpi_fac)
        x = margin
        y = margin

        # 测量文本宽度
        blf.size(font_id, font_size)
        text_w, text_h = blf.dimensions(font_id, _cached_fps_text)

        # 半透明背景
        padding = int(6 * dpi_fac)
        bg_x1 = x - padding
        bg_y1 = y - padding
        bg_x2 = x + text_w + padding
        bg_y2 = y + text_h + padding

        gpu.state.blend_set('ALPHA')

        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        shader.bind()

        vertices = (
            (bg_x1, bg_y1), (bg_x2, bg_y1),
            (bg_x2, bg_y2), (bg_x1, bg_y2),
        )
        indices = ((0, 1, 2), (0, 2, 3))
        batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
        shader.uniform_float("color", (0.0, 0.0, 0.0, 0.55))
        batch.draw(shader)

        # 文本
        blf.position(font_id, x, y, 0)
        blf.color(font_id, 0.0, 1.0, 0.4, 1.0)  # 绿色
        blf.draw(font_id, _cached_fps_text)

        gpu.state.blend_set('NONE')

    except Exception as e:
        import traceback
        traceback.print_exc()


# ==================== 启用 / 禁用 ====================

def enable_fps_overlay():
    """启用 FPS 覆盖层"""
    global _fps_draw_handler, _frame_times, _cached_fps_text, _last_update_time
    if _fps_draw_handler is not None:
        return
    _frame_times = []
    _cached_fps_text = "FPS: --"
    _last_update_time = 0.0
    _fps_draw_handler = bpy.types.SpaceView3D.draw_handler_add(
        _fps_draw_callback, (), 'WINDOW', 'POST_PIXEL'
    )
    _tag_redraw_all()


def disable_fps_overlay():
    """禁用 FPS 覆盖层"""
    global _fps_draw_handler, _frame_times
    if _fps_draw_handler is None:
        return
    try:
        bpy.types.SpaceView3D.draw_handler_remove(_fps_draw_handler, 'WINDOW')
    except Exception:
        pass
    _fps_draw_handler = None
    _frame_times = []
    _tag_redraw_all()


def _tag_redraw_all():
    """刷新所有 3D 视口"""
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
    except Exception:
        pass


# ==================== 属性更新回调 ====================

def update_show_fps(self, context):
    """show_viewport_fps 属性变化时的回调"""
    if self.show_viewport_fps:
        enable_fps_overlay()
    else:
        disable_fps_overlay()
