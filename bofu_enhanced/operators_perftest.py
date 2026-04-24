# ==================== 性能测试模块 ====================
"""
bofu_enhanced/operators_perftest.py

性能测试功能：
- BOFU_OT_perftest_create: 创建500个随机材质立方体
- BOFU_OT_perftest_start: 开始 Modal Timer 随机运动测试
- BOFU_OT_perftest_stop: 停止测试
"""

import bpy
import random
import logging
from bpy.types import Operator

logger = logging.getLogger(__name__)

# ==================== 常量 ====================

PERFTEST_PREFIX = "PerfTest_"
PERFTEST_MAT_PREFIX = "PerfTestMat_"
CUBE_COUNT = 500
SPAWN_RANGE = 5.0       # 立方体初始分布范围 (±m)
CUBE_SIZE = 0.15         # 立方体半边长 (m)
MOVE_SPEED = 0.05        # 每帧最大随机位移 (m)
TIMER_INTERVAL = 0.016   # Modal timer 间隔 (~60fps)


def _ensure_fps_for_perftest(context):
    """若当前未开启视口 FPS，则自动开启并记录，便于停止时恢复。"""
    scene = context.scene
    if not hasattr(scene, "perftest_settings") or not hasattr(scene, "misc_settings"):
        return
    pt = scene.perftest_settings
    misc = scene.misc_settings
    if misc.show_viewport_fps:
        pt.fps_auto_enabled_for_perftest = False
    else:
        pt.fps_auto_enabled_for_perftest = True
        misc.show_viewport_fps = True


def _restore_fps_after_perftest(context):
    """若 FPS 是开始测试时自动打开的，则关闭；用户原本就开的则不动。"""
    scene = context.scene
    if not hasattr(scene, "perftest_settings") or not hasattr(scene, "misc_settings"):
        return
    pt = scene.perftest_settings
    if not pt.fps_auto_enabled_for_perftest:
        return
    pt.fps_auto_enabled_for_perftest = False
    scene.misc_settings.show_viewport_fps = False


# ==================== 辅助函数 ====================

def cleanup_perftest_objects():
    """清理所有 PerfTest_ 前缀的对象和材质"""
    removed = 0
    for obj in list(bpy.data.objects):
        if obj.name.startswith(PERFTEST_PREFIX):
            bpy.data.objects.remove(obj, do_unlink=True)
            removed += 1

    # 清理孤立网格
    for mesh in list(bpy.data.meshes):
        if mesh.name.startswith(PERFTEST_PREFIX) and mesh.users == 0:
            bpy.data.meshes.remove(mesh)

    # 清理孤立材质
    for mat in list(bpy.data.materials):
        if mat.name.startswith(PERFTEST_MAT_PREFIX) and mat.users == 0:
            bpy.data.materials.remove(mat)

    return removed


def _create_random_material(index):
    """创建一个随机颜色的 Principled BSDF 材质"""
    mat = bpy.data.materials.new(name=f"{PERFTEST_MAT_PREFIX}{index:03d}")
    mat.use_nodes = True
    tree = mat.node_tree

    r = random.random()
    g = random.random()
    b = random.random()
    metallic = random.uniform(0.0, 1.0)
    roughness = random.uniform(0.1, 1.0)

    # 设置 Principled BSDF 节点（渲染模式用）
    bsdf = tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = roughness

    # 设置视图显示颜色（实体视图模式用）
    mat.diffuse_color = (r, g, b, 1.0)
    mat.metallic = metallic
    mat.roughness = roughness

    return mat


def _create_cube_mesh(name):
    """创建一个小立方体网格数据"""
    h = CUBE_SIZE
    verts = [
        (-h, -h, -h), (h, -h, -h),
        (h, h, -h), (-h, h, -h),
        (-h, -h, h), (h, -h, h),
        (h, h, h), (-h, h, h),
    ]
    faces = [
        (0, 1, 2, 3), (4, 5, 6, 7),
        (0, 1, 5, 4), (2, 3, 7, 6),
        (0, 3, 7, 4), (1, 2, 6, 5),
    ]
    mesh = bpy.data.meshes.new(f"{PERFTEST_PREFIX}{name}")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    return mesh


# ==================== 操作符 ====================

class BOFU_OT_perftest_create(Operator):
    """创建500个随机材质立方体用于性能测试"""
    bl_idname = "bofu.perftest_create"
    bl_label = "创建测试模型"
    bl_description = "在世界原点附近创建500个不同材质的立方体"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # 先检查是否正在运行测试
        if hasattr(context.scene, 'perftest_settings'):
            if context.scene.perftest_settings.is_running:
                self.report({'WARNING'}, "请先停止测试再重新创建模型")
                return {'CANCELLED'}

        # 确保在物体模式
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # 清理旧的测试对象
        removed = cleanup_perftest_objects()
        if removed > 0:
            logger.debug("已清理 %d 个旧测试对象", removed)

        # 批量创建立方体
        collection = context.collection
        for i in range(CUBE_COUNT):
            mesh = _create_cube_mesh(f"Cube_{i:03d}")
            obj = bpy.data.objects.new(f"{PERFTEST_PREFIX}Cube_{i:03d}", mesh)

            # 随机初始位置
            obj.location = (
                random.uniform(-SPAWN_RANGE, SPAWN_RANGE),
                random.uniform(-SPAWN_RANGE, SPAWN_RANGE),
                random.uniform(-SPAWN_RANGE, SPAWN_RANGE),
            )

            # 分配随机材质
            mat = _create_random_material(i)
            obj.data.materials.append(mat)

            collection.objects.link(obj)

        # 更新属性
        if hasattr(context.scene, 'perftest_settings'):
            context.scene.perftest_settings.cube_count = CUBE_COUNT

        self.report({'INFO'}, f"已创建 {CUBE_COUNT} 个测试立方体")
        return {'FINISHED'}


class BOFU_OT_perftest_start(Operator):
    """开始性能测试 — 所有测试立方体随机运动"""
    bl_idname = "bofu.perftest_start"
    bl_label = "开始测试"
    bl_description = "启动 Modal Timer，驱动所有测试立方体随机移动"

    _timer = None
    _objects = None

    @classmethod
    def poll(cls, context):
        if not hasattr(context.scene, 'perftest_settings'):
            return False
        settings = context.scene.perftest_settings
        return not settings.is_running and settings.cube_count > 0

    def modal(self, context, event):
        # 检查是否被外部停止
        if hasattr(context.scene, 'perftest_settings'):
            if not context.scene.perftest_settings.is_running:
                self._cleanup(context)
                return {'CANCELLED'}

        if event.type == 'TIMER':
            # 刷新对象列表（对象可能被用户手动删除）
            if self._objects is None:
                self._objects = [
                    obj for obj in bpy.data.objects
                    if obj.name.startswith(PERFTEST_PREFIX)
                ]

            # 随机移动每个对象
            for obj in self._objects:
                try:
                    obj.location.x += random.uniform(-MOVE_SPEED, MOVE_SPEED)
                    obj.location.y += random.uniform(-MOVE_SPEED, MOVE_SPEED)
                    obj.location.z += random.uniform(-MOVE_SPEED, MOVE_SPEED)
                except ReferenceError:
                    # 对象可能已被删除
                    self._objects = None
                    break

        return {'PASS_THROUGH'}

    def execute(self, context):
        # 缓存对象引用
        self._objects = [
            obj for obj in bpy.data.objects
            if obj.name.startswith(PERFTEST_PREFIX)
        ]

        if not self._objects:
            self.report({'WARNING'}, "没有测试立方体，请先创建模型")
            return {'CANCELLED'}

        _ensure_fps_for_perftest(context)

        # 注册 modal timer
        wm = context.window_manager
        self._timer = wm.event_timer_add(TIMER_INTERVAL, window=context.window)
        wm.modal_handler_add(self)

        # 标记运行状态
        if hasattr(context.scene, 'perftest_settings'):
            context.scene.perftest_settings.is_running = True

        self.report({'INFO'}, f"性能测试已启动 — {len(self._objects)} 个对象")
        return {'RUNNING_MODAL'}

    def _cleanup(self, context):
        """清理 timer"""
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        self._objects = None

    def cancel(self, context):
        self._cleanup(context)
        if hasattr(context.scene, 'perftest_settings'):
            context.scene.perftest_settings.is_running = False
        _restore_fps_after_perftest(context)


class BOFU_OT_perftest_stop(Operator):
    """停止性能测试"""
    bl_idname = "bofu.perftest_stop"
    bl_label = "停止测试"
    bl_description = "停止所有测试立方体的随机运动"

    @classmethod
    def poll(cls, context):
        if not hasattr(context.scene, 'perftest_settings'):
            return False
        return context.scene.perftest_settings.is_running

    def execute(self, context):
        # 设置 is_running = False，modal 下一帧会自行退出
        if hasattr(context.scene, 'perftest_settings'):
            context.scene.perftest_settings.is_running = False

        _restore_fps_after_perftest(context)

        self.report({'INFO'}, "性能测试已停止")
        return {'FINISHED'}


# ==================== 类注册列表 ====================

classes = (
    BOFU_OT_perftest_create,
    BOFU_OT_perftest_start,
    BOFU_OT_perftest_stop,
)
