# ==================== 视口渲染模块 ====================
"""
bofu_enhanced/operators_render.py

所见即所得视口渲染 —— 解决 Blender 默认视口渲染（bpy.ops.render.opengl）
在 Filmic / AgX 等色彩管理下导致颜色偏差的问题。

原理：临时将色彩管理切换为 Standard（直通 sRGB），渲染后由用户
手动恢复，确保渲染结果查看期间色彩与视口完全一致。
"""

import bpy
from bpy.types import Operator


# 保存渲染前的色彩管理设置，供恢复操作符使用
_saved_color_settings = {}


def has_saved_settings():
    """外部模块用来检查是否有待恢复的色彩设置"""
    return bool(_saved_color_settings)


class BOFU_OT_viewport_render_wysiwyg(Operator):
    """临时切换为 Standard 色彩管理后渲染视口，确保输出色彩与视口一致"""
    bl_idname = "bofu.viewport_render_wysiwyg"
    bl_label = "渲染视口预览（所见即所得）"
    bl_description = (
        "临时将色彩管理切换为 Standard，然后渲染视口预览，\n"
        "确保输出色彩与视口完全一致。渲染后可点击「恢复色彩设置」还原"
    )
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.area and context.area.type == 'VIEW_3D'

    def execute(self, context):
        global _saved_color_settings

        scene = context.scene
        vs = scene.view_settings

        if vs.view_transform == 'Standard':
            bpy.ops.render.opengl('INVOKE_DEFAULT')
            self.report({'INFO'}, "渲染完成")
            return {'FINISHED'}

        _saved_color_settings = {
            'view_transform': vs.view_transform,
            'look': vs.look,
            'exposure': vs.exposure,
            'gamma': vs.gamma,
        }

        try:
            vs.view_transform = 'Standard'
            vs.look = 'None'
        except Exception:
            _saved_color_settings.clear()
            self.report({'ERROR'}, "无法切换到 Standard 色彩管理")
            return {'CANCELLED'}

        try:
            bpy.ops.render.opengl('INVOKE_DEFAULT')
        except Exception as e:
            for k, v in _saved_color_settings.items():
                try:
                    setattr(vs, k, v)
                except Exception:
                    pass
            _saved_color_settings.clear()
            self.report({'ERROR'}, f"渲染失败: {e}")
            return {'CANCELLED'}

        self.report(
            {'INFO'},
            "渲染完成 ── 色彩管理已临时切换为 Standard，"
            "完成查看后请点击 视图 → 恢复色彩设置",
        )
        return {'FINISHED'}


class BOFU_OT_restore_color_settings(Operator):
    """恢复视口渲染前的色彩管理设置"""
    bl_idname = "bofu.restore_color_settings"
    bl_label = "恢复色彩设置"
    bl_description = "恢复所见即所得渲染前的色彩管理设置（如 Filmic / AgX）"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return bool(_saved_color_settings)

    def execute(self, context):
        global _saved_color_settings

        if not _saved_color_settings:
            self.report({'INFO'}, "无需恢复，没有保存的设置")
            return {'CANCELLED'}

        vs = context.scene.view_settings
        orig_name = _saved_color_settings.get('view_transform', '')

        for k, v in _saved_color_settings.items():
            try:
                setattr(vs, k, v)
            except Exception:
                pass

        _saved_color_settings.clear()
        self.report({'INFO'}, f"色彩管理已恢复为: {orig_name}")
        return {'FINISHED'}


# ==================== 菜单绘制函数 ====================

def menu_func_render(self, context):
    """追加到 VIEW3D_MT_view（3D 视口 → 视图菜单）"""
    self.layout.separator()
    self.layout.operator(
        BOFU_OT_viewport_render_wysiwyg.bl_idname,
        text="渲染视口预览（所见即所得）",
        icon='RESTRICT_RENDER_OFF',
    )

    if _saved_color_settings:
        row = self.layout.row()
        row.alert = True
        row.operator(
            BOFU_OT_restore_color_settings.bl_idname,
            icon='LOOP_BACK',
        )


# ==================== 类注册列表 ====================

classes = (
    BOFU_OT_viewport_render_wysiwyg,
    BOFU_OT_restore_color_settings,
)
