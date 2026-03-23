# ==================== 视口 FPS 计数器 ====================
"""
bofu_enhanced/fps_overlay.py

在 3D 视口左下角绘制实时帧率（FPS）。
使用 Modal Timer 主动驱动视口重绘，确保静止时 FPS 也能持续更新。
使用滑动窗口平均值，避免数值剧烈跳动。
点击 FPS 显示区域可暂停/恢复计数。
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

# Timer 驱动
_timer_running = False

# 暂停状态（用户手动点击切换）
_paused = False

# FPS 显示区域的像素坐标（由绘制回调更新，供点击检测使用）
_hit_rect = (0, 0, 0, 0)  # (x1, y1, x2, y2)

# FPS 颜色阈值
_FPS_COLOR_HIGH   = (0.0, 1.0, 0.4, 1.0)    # 绿色: >= 30 FPS
_FPS_COLOR_MED    = (1.0, 0.9, 0.0, 1.0)    # 黄色: 15-29 FPS
_FPS_COLOR_LOW    = (1.0, 0.25, 0.25, 1.0)  # 红色: < 15 FPS
_FPS_COLOR_PAUSED = (0.6, 0.6, 0.6, 1.0)    # 灰色: 暂停


# ==================== Modal Timer Operator ====================

class BOFU_OT_fps_timer(bpy.types.Operator):
    """FPS Timer: 定期刷新视口以保持 FPS 计数器更新，点击 FPS 区域暂停/恢复"""
    bl_idname = "wm.bofu_fps_timer"
    bl_label = "FPS Refresh Timer"
    bl_options = {'INTERNAL'}

    _timer = None

    def modal(self, context, event):
        global _paused, _frame_times, _cached_fps_text, _last_update_time

        # 如果被外部停止
        if not _timer_running:
            self._cleanup(context)
            return {'CANCELLED'}

        # 检测点击 FPS 区域
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            # 获取鼠标在当前 region 的坐标
            mx, my = event.mouse_region_x, event.mouse_region_y
            x1, y1, x2, y2 = _hit_rect
            if x1 <= mx <= x2 and y1 <= my <= y2:
                _paused = not _paused
                if not _paused:
                    # 恢复时重置帧时间，避免计算出异常值
                    _frame_times = []
                    _cached_fps_text = "FPS: --"
                    _last_update_time = 0.0
                else:
                    _cached_fps_text = "FPS: Paused"
                # 立即刷新显示
                if context.screen:
                    for area in context.screen.areas:
                        if area.type == 'VIEW_3D':
                            area.tag_redraw()
                # 不消费事件，让 Blender 正常处理
                return {'PASS_THROUGH'}

        if event.type == 'TIMER':
            # 刷新所有 3D 视口
            if context.screen:
                for area in context.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()

        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        # 每 50ms 触发一次 timer（20Hz 刷新率，足以保持 FPS 数字更新）
        self._timer = context.window_manager.event_timer_add(
            0.05, window=context.window
        )
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _cleanup(self, context):
        if self._timer is not None:
            try:
                context.window_manager.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None


# 需要注册的类列表
classes = (BOFU_OT_fps_timer,)


# ==================== 绘制回调 ====================

def _fps_draw_callback():
    """视口绘制回调：计算并绘制 FPS"""
    global _frame_times, _cached_fps_text, _last_update_time, _hit_rect

    now = time.perf_counter()

    # 暂停时只绘制，不更新帧数据
    if not _paused:
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
                    fps_val = (len(_frame_times) - 1) / elapsed
                    _cached_fps_text = f"FPS: {fps_val:.0f}"
                else:
                    _cached_fps_text = "FPS: --"
            else:
                _cached_fps_text = "FPS: --"

    # ---- 确定文本颜色 ----
    if _paused:
        text_color = _FPS_COLOR_PAUSED
    else:
        try:
            fps_num = float(_cached_fps_text.split(": ")[1])
            if fps_num >= 30:
                text_color = _FPS_COLOR_HIGH
            elif fps_num >= 15:
                text_color = _FPS_COLOR_MED
            else:
                text_color = _FPS_COLOR_LOW
        except (ValueError, IndexError):
            text_color = _FPS_COLOR_HIGH

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

        # 更新点击检测区域
        _hit_rect = (bg_x1, bg_y1, bg_x2, bg_y2)

        gpu.state.blend_set('ALPHA')

        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        shader.bind()

        vertices = (
            (bg_x1, bg_y1), (bg_x2, bg_y1),
            (bg_x2, bg_y2), (bg_x1, bg_y2),
        )
        indices = ((0, 1, 2), (0, 2, 3))
        batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)

        # 暂停时背景稍微加深，表示可交互
        bg_alpha = 0.65 if _paused else 0.55
        shader.uniform_float("color", (0.0, 0.0, 0.0, bg_alpha))
        batch.draw(shader)

        # 文本
        blf.position(font_id, x, y, 0)
        blf.color(font_id, *text_color)
        blf.draw(font_id, _cached_fps_text)

        gpu.state.blend_set('NONE')

    except Exception as e:
        import traceback
        traceback.print_exc()


# ==================== 启用 / 禁用 ====================

def enable_fps_overlay():
    """启用 FPS 覆盖层"""
    global _fps_draw_handler, _frame_times, _cached_fps_text, _last_update_time
    global _timer_running, _paused

    if _fps_draw_handler is not None:
        return
    _frame_times = []
    _cached_fps_text = "FPS: --"
    _last_update_time = 0.0
    _paused = False

    _fps_draw_handler = bpy.types.SpaceView3D.draw_handler_add(
        _fps_draw_callback, (), 'WINDOW', 'POST_PIXEL'
    )

    # 启动 Modal Timer
    _timer_running = True
    bpy.ops.wm.bofu_fps_timer('INVOKE_DEFAULT')

    _tag_redraw_all()


def disable_fps_overlay():
    """禁用 FPS 覆盖层"""
    global _fps_draw_handler, _frame_times, _timer_running, _paused
    if _fps_draw_handler is None:
        return

    # 先停止 Timer
    _timer_running = False
    _paused = False

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
