# ==================== 机构运动学模块 ====================
"""
bofu_enhanced/operators_kinematics.py

2D 平面机构运动学求解器和相关操作符

功能：
- 关节定义（旋转关节、平移关节）
- Newton-Raphson 迭代求解器
- 实时驱动动画（滑块驱动）
- 原始变换保存/恢复
"""

import bpy
import math
import json
from bpy.types import Operator
from bpy.props import EnumProperty, BoolProperty, FloatVectorProperty
from mathutils import Vector

from .config import Config


# ==================== numpy 检测 ====================

_numpy_available = None


def check_numpy():
    """检查 numpy 是否可用"""
    global _numpy_available
    if _numpy_available is None:
        try:
            import numpy
            _numpy_available = True
        except ImportError:
            _numpy_available = False
    return _numpy_available


# ==================== 2D 坐标工具函数 ====================

def get_2d_pos(location, plane):
    """从 3D 位置提取 2D 坐标"""
    if plane == 'XY':
        return (location[0], location[1])
    elif plane == 'XZ':
        return (location[0], location[2])
    else:  # YZ
        return (location[1], location[2])


def get_rotation_angle(obj, plane):
    """从对象提取 2D 旋转角度（弧度）"""
    euler = obj.rotation_euler
    if plane == 'XY':
        return euler.z
    elif plane == 'XZ':
        return -euler.y  # XZ 平面绕 Y 轴，取负以保持右手系
    else:  # YZ
        return euler.x


def set_2d_pos(obj, pos_2d, plane):
    """将 2D 位置写回对象的 3D 位置"""
    if plane == 'XY':
        obj.location.x = pos_2d[0]
        obj.location.y = pos_2d[1]
    elif plane == 'XZ':
        obj.location.x = pos_2d[0]
        obj.location.z = pos_2d[1]
    else:  # YZ
        obj.location.y = pos_2d[0]
        obj.location.z = pos_2d[1]


def set_rotation_angle(obj, angle, plane):
    """将 2D 旋转角度写回对象"""
    if plane == 'XY':
        obj.rotation_euler.z = angle
    elif plane == 'XZ':
        obj.rotation_euler.y = -angle
    else:  # YZ
        obj.rotation_euler.x = angle


def world_to_local_2d(pivot_world_2d, obj_pos_2d, obj_angle):
    """将 2D 世界坐标铰接点转换为对象局部坐标"""
    dx = pivot_world_2d[0] - obj_pos_2d[0]
    dy = pivot_world_2d[1] - obj_pos_2d[1]
    cos_a = math.cos(-obj_angle)
    sin_a = math.sin(-obj_angle)
    local_x = cos_a * dx - sin_a * dy
    local_y = sin_a * dx + cos_a * dy
    return (local_x, local_y)


def local_to_world_2d(pivot_local_2d, obj_pos_2d, obj_angle):
    """将对象局部 2D 坐标转换为世界坐标"""
    cos_a = math.cos(obj_angle)
    sin_a = math.sin(obj_angle)
    wx = obj_pos_2d[0] + cos_a * pivot_local_2d[0] - sin_a * pivot_local_2d[1]
    wy = obj_pos_2d[1] + sin_a * pivot_local_2d[0] + cos_a * pivot_local_2d[1]
    return (wx, wy)


def get_prismatic_axis_2d(axis_direction, plane):
    """获取平移关节在 2D 平面中的单位方向向量"""
    if plane == 'XY':
        if axis_direction == 'X':
            return (1.0, 0.0)
        elif axis_direction == 'Y':
            return (0.0, 1.0)
        else:
            return (0.0, 0.0)  # Z 轴在 XY 平面中无效
    elif plane == 'XZ':
        if axis_direction == 'X':
            return (1.0, 0.0)
        elif axis_direction == 'Z':
            return (0.0, 1.0)
        else:
            return (0.0, 0.0)
    else:  # YZ
        if axis_direction == 'Y':
            return (1.0, 0.0)
        elif axis_direction == 'Z':
            return (0.0, 1.0)
        else:
            return (0.0, 0.0)


# ==================== 2D 平面机构求解器 ====================

class PlanarMechanismSolver:
    """
    2D 平面机构运动学求解器

    使用 Newton-Raphson 迭代法求解约束方程组。
    每个活动对象有 3 个自由度 (x, y, θ)，
    每个关节提供 2 个约束方程。
    """

    def __init__(self, plane='XY'):
        self.plane = plane
        # 活动对象列表 [{name, obj, init_x, init_y, init_theta}]
        self.moving_objects = []
        # 对象名 -> 在状态向量中的起始索引
        self.obj_index_map = {}
        # 关节数据 [{type, a_name, b_name, ...}]
        self.joints_data = []
        # 驱动信息
        self.driver_info = None
        # 缓存的上一次解（用作下次初始猜测）
        self._last_solution = None

    def build_from_scene(self, context):
        """从场景的 kinematics_props 构建求解模型"""
        props = context.scene.kinematics_props
        plane = props.working_plane
        self.plane = plane
        self.moving_objects = []
        self.obj_index_map = {}
        self.joints_data = []
        self.driver_info = None

        # 收集所有参与的活动对象
        moving_names = set()
        for j in props.joints:
            if not j.a_is_ground and j.object_a:
                moving_names.add(j.object_a.name)
            if j.object_b:
                moving_names.add(j.object_b.name)

        # 去掉被地面关节约束死的对象？不，所有非地面对象都是活动的
        # 但如果一个对象只通过 ground 旋转关节连接，它仍然是活动的（有 1 DOF 旋转）

        idx = 0
        for name in sorted(moving_names):
            obj = bpy.data.objects.get(name)
            if obj is None:
                continue
            pos_2d = get_2d_pos(obj.location, plane)
            angle = get_rotation_angle(obj, plane)
            self.moving_objects.append({
                'name': name,
                'obj': obj,
                'init_x': pos_2d[0],
                'init_y': pos_2d[1],
                'init_theta': angle,
            })
            self.obj_index_map[name] = idx
            idx += 1

        # 构建关节数据
        for ji, j in enumerate(props.joints):
            jd = {
                'type': j.joint_type,
                'a_is_ground': j.a_is_ground,
                'a_name': j.object_a.name if (j.object_a and not j.a_is_ground) else None,
                'b_name': j.object_b.name if j.object_b else None,
                'is_driver': (ji == props.driver_joint_index),
            }

            if j.joint_type == 'REVOLUTE':
                pivot_w = get_2d_pos(j.pivot_world, plane)
                jd['pivot_world'] = pivot_w

                # 计算局部铰接点坐标
                if jd['a_name'] and jd['a_name'] in self.obj_index_map:
                    oi = self._get_obj_info(jd['a_name'])
                    jd['pivot_local_a'] = world_to_local_2d(
                        pivot_w, (oi['init_x'], oi['init_y']), oi['init_theta']
                    )
                else:
                    jd['pivot_local_a'] = None  # ground

                if jd['b_name'] and jd['b_name'] in self.obj_index_map:
                    oi = self._get_obj_info(jd['b_name'])
                    jd['pivot_local_b'] = world_to_local_2d(
                        pivot_w, (oi['init_x'], oi['init_y']), oi['init_theta']
                    )
                else:
                    jd['pivot_local_b'] = None

            elif j.joint_type == 'PRISMATIC':
                axis_2d = get_prismatic_axis_2d(j.axis_direction, plane)
                jd['axis'] = axis_2d
                jd['axis_perp'] = (-axis_2d[1], axis_2d[0])

                # 记录 B 的初始状态
                if jd['b_name'] and jd['b_name'] in self.obj_index_map:
                    oi = self._get_obj_info(jd['b_name'])
                    jd['b_init_pos'] = (oi['init_x'], oi['init_y'])
                    jd['b_init_theta'] = oi['init_theta']

                if jd['a_name'] and jd['a_name'] in self.obj_index_map:
                    oi = self._get_obj_info(jd['a_name'])
                    jd['a_init_pos'] = (oi['init_x'], oi['init_y'])
                    jd['a_init_theta'] = oi['init_theta']

            self.joints_data.append(jd)

            if jd['is_driver']:
                self.driver_info = {
                    'joint_index': len(self.joints_data) - 1,
                    'joint_data': jd,
                }

    def _get_obj_info(self, name):
        """获取活动对象的初始状态信息"""
        for mo in self.moving_objects:
            if mo['name'] == name:
                return mo
        return None

    def compute_dof(self):
        """
        计算机构自由度 (Gruebler 公式)
        DOF = 3 * n_moving - sum(constraints_per_joint)
        """
        n_moving = len(self.moving_objects)
        n_constraints = 0
        for jd in self.joints_data:
            if jd['type'] == 'REVOLUTE':
                n_constraints += 2
            elif jd['type'] == 'PRISMATIC':
                n_constraints += 2
        return 3 * n_moving - n_constraints

    def _build_state_vector(self):
        """构建初始状态向量"""
        import numpy as np
        n = len(self.moving_objects)
        q = np.zeros(3 * n)
        for mo in self.moving_objects:
            i = self.obj_index_map[mo['name']]
            q[3 * i] = mo['init_x']
            q[3 * i + 1] = mo['init_y']
            q[3 * i + 2] = mo['init_theta']
        return q

    def _get_obj_state(self, q, name):
        """从状态向量中获取对象状态"""
        i = self.obj_index_map.get(name)
        if i is None:
            return None, None, None
        return q[3 * i], q[3 * i + 1], q[3 * i + 2]

    def _constraints_and_jacobian(self, q, driver_value):
        """
        计算约束方程值 Phi(q) 和雅可比矩阵 J = dPhi/dq

        返回: (Phi, J)
        """
        import numpy as np

        n_obj = len(self.moving_objects)
        n_state = 3 * n_obj

        # 计算总约束数
        n_constraints = 0
        for jd in self.joints_data:
            n_constraints += 2  # 每个关节 2 个约束
        if self.driver_info is not None:
            n_constraints += 1  # 驱动约束

        Phi = np.zeros(n_constraints)
        J = np.zeros((n_constraints, n_state))

        row = 0
        for jd in self.joints_data:
            if jd['type'] == 'REVOLUTE':
                row = self._add_revolute_constraints(q, jd, Phi, J, row)
            elif jd['type'] == 'PRISMATIC':
                row = self._add_prismatic_constraints(q, jd, Phi, J, row)

        # 驱动约束
        if self.driver_info is not None:
            row = self._add_driver_constraint(q, driver_value, Phi, J, row)

        return Phi, J

    def _add_revolute_constraints(self, q, jd, Phi, J, row):
        """
        添加旋转关节约束方程

        P_A = pos_A + R(θ_A) * r_A = P_B = pos_B + R(θ_B) * r_B
        """
        pw = jd['pivot_world']

        # 对象 B 侧（总是活动对象）
        b_name = jd['b_name']
        if b_name and b_name in self.obj_index_map:
            bi = self.obj_index_map[b_name]
            xb, yb, tb = q[3 * bi], q[3 * bi + 1], q[3 * bi + 2]
            rb = jd['pivot_local_b']
            cos_b, sin_b = math.cos(tb), math.sin(tb)
            # B 端铰接点世界坐标
            pb_x = xb + rb[0] * cos_b - rb[1] * sin_b
            pb_y = yb + rb[0] * sin_b + rb[1] * cos_b
        else:
            return row  # 不应该发生

        # 对象 A 侧
        if jd['a_is_ground'] or jd['a_name'] is None:
            # A 是地面，铰接点固定在初始世界位置
            pa_x, pa_y = pw[0], pw[1]

            Phi[row] = pb_x - pa_x
            Phi[row + 1] = pb_y - pa_y

            # 对 B 的偏导
            J[row, 3 * bi] = 1.0
            J[row, 3 * bi + 2] = -rb[0] * sin_b - rb[1] * cos_b
            J[row + 1, 3 * bi + 1] = 1.0
            J[row + 1, 3 * bi + 2] = rb[0] * cos_b - rb[1] * sin_b
        else:
            a_name = jd['a_name']
            if a_name not in self.obj_index_map:
                return row
            ai = self.obj_index_map[a_name]
            xa, ya, ta = q[3 * ai], q[3 * ai + 1], q[3 * ai + 2]
            ra = jd['pivot_local_a']
            cos_a, sin_a = math.cos(ta), math.sin(ta)
            pa_x = xa + ra[0] * cos_a - ra[1] * sin_a
            pa_y = ya + ra[0] * sin_a + ra[1] * cos_a

            Phi[row] = pa_x - pb_x
            Phi[row + 1] = pa_y - pb_y

            # 对 A 的偏导
            J[row, 3 * ai] = 1.0
            J[row, 3 * ai + 2] = -ra[0] * sin_a - ra[1] * cos_a
            J[row + 1, 3 * ai + 1] = 1.0
            J[row + 1, 3 * ai + 2] = ra[0] * cos_a - ra[1] * sin_a

            # 对 B 的偏导
            J[row, 3 * bi] = -1.0
            J[row, 3 * bi + 2] = rb[0] * sin_b + rb[1] * cos_b
            J[row + 1, 3 * bi + 1] = -1.0
            J[row + 1, 3 * bi + 2] = -rb[0] * cos_b + rb[1] * sin_b

        return row + 2

    def _add_prismatic_constraints(self, q, jd, Phi, J, row):
        """
        添加平移关节约束方程

        约束1: 垂直于滑动方向的位移为零
        约束2: 相对旋转为零
        """
        axis = jd['axis']
        axis_perp = jd['axis_perp']

        b_name = jd['b_name']
        if b_name and b_name in self.obj_index_map:
            bi = self.obj_index_map[b_name]
            xb, yb, tb = q[3 * bi], q[3 * bi + 1], q[3 * bi + 2]
        else:
            return row

        if jd['a_is_ground'] or jd['a_name'] is None:
            # A 是地面
            b_init = jd.get('b_init_pos', (0, 0))
            b_init_theta = jd.get('b_init_theta', 0)

            # 约束1: 垂直方向位移 = 0
            dx = xb - b_init[0]
            dy = yb - b_init[1]
            Phi[row] = axis_perp[0] * dx + axis_perp[1] * dy

            J[row, 3 * bi] = axis_perp[0]
            J[row, 3 * bi + 1] = axis_perp[1]

            # 约束2: 旋转不变
            Phi[row + 1] = tb - b_init_theta

            J[row + 1, 3 * bi + 2] = 1.0
        else:
            a_name = jd['a_name']
            if a_name not in self.obj_index_map:
                return row
            ai = self.obj_index_map[a_name]
            xa, ya, ta = q[3 * ai], q[3 * ai + 1], q[3 * ai + 2]

            a_init = jd.get('a_init_pos', (0, 0))
            b_init = jd.get('b_init_pos', (0, 0))
            a_init_theta = jd.get('a_init_theta', 0)
            b_init_theta = jd.get('b_init_theta', 0)

            # 约束1: 垂直方向相对位移不变
            rel_dx = (xb - xa) - (b_init[0] - a_init[0])
            rel_dy = (yb - ya) - (b_init[1] - a_init[1])
            Phi[row] = axis_perp[0] * rel_dx + axis_perp[1] * rel_dy

            J[row, 3 * ai] = -axis_perp[0]
            J[row, 3 * ai + 1] = -axis_perp[1]
            J[row, 3 * bi] = axis_perp[0]
            J[row, 3 * bi + 1] = axis_perp[1]

            # 约束2: 相对旋转不变
            Phi[row + 1] = (tb - ta) - (b_init_theta - a_init_theta)

            J[row + 1, 3 * ai + 2] = -1.0
            J[row + 1, 3 * bi + 2] = 1.0

        return row + 2

    def _add_driver_constraint(self, q, driver_value, Phi, J, row):
        """
        添加驱动约束方程

        平移驱动: 沿轴方向位移 = driver_value
        旋转驱动: 旋转角度变化 = driver_value
        """
        jd = self.driver_info['joint_data']

        if jd['type'] == 'PRISMATIC':
            axis = jd['axis']
            b_name = jd['b_name']
            if b_name and b_name in self.obj_index_map:
                bi = self.obj_index_map[b_name]
                xb, yb = q[3 * bi], q[3 * bi + 1]
                b_init = jd.get('b_init_pos', (0, 0))

                if jd['a_is_ground'] or jd['a_name'] is None:
                    dx = xb - b_init[0]
                    dy = yb - b_init[1]
                    Phi[row] = axis[0] * dx + axis[1] * dy - driver_value

                    J[row, 3 * bi] = axis[0]
                    J[row, 3 * bi + 1] = axis[1]
                else:
                    a_name = jd['a_name']
                    if a_name in self.obj_index_map:
                        ai = self.obj_index_map[a_name]
                        xa, ya = q[3 * ai], q[3 * ai + 1]
                        a_init = jd.get('a_init_pos', (0, 0))

                        rel_dx = (xb - xa) - (b_init[0] - a_init[0])
                        rel_dy = (yb - ya) - (b_init[1] - a_init[1])
                        Phi[row] = axis[0] * rel_dx + axis[1] * rel_dy - driver_value

                        J[row, 3 * ai] = -axis[0]
                        J[row, 3 * ai + 1] = -axis[1]
                        J[row, 3 * bi] = axis[0]
                        J[row, 3 * bi + 1] = axis[1]

        elif jd['type'] == 'REVOLUTE':
            b_name = jd['b_name']
            if b_name and b_name in self.obj_index_map:
                bi = self.obj_index_map[b_name]
                tb = q[3 * bi + 2]
                oi = self._get_obj_info(b_name)
                b_init_theta = oi['init_theta'] if oi else 0

                if jd['a_is_ground'] or jd['a_name'] is None:
                    Phi[row] = tb - b_init_theta - driver_value
                    J[row, 3 * bi + 2] = 1.0
                else:
                    a_name = jd['a_name']
                    if a_name in self.obj_index_map:
                        ai = self.obj_index_map[a_name]
                        ta = q[3 * ai + 2]
                        a_oi = self._get_obj_info(a_name)
                        a_init_theta = a_oi['init_theta'] if a_oi else 0
                        Phi[row] = (tb - ta) - (b_init_theta - a_init_theta) - driver_value
                        J[row, 3 * ai + 2] = -1.0
                        J[row, 3 * bi + 2] = 1.0

        return row + 1

    def solve(self, driver_value):
        """
        使用阻尼 Newton-Raphson 方法求解机构位置

        参数:
            driver_value: 驱动值（平移:m，旋转:rad）

        返回:
            dict[obj_name -> (x, y, theta)] 或 None（求解失败）
        """
        if not check_numpy():
            return None

        import numpy as np

        n_obj = len(self.moving_objects)
        if n_obj == 0:
            return {}

        # 保存上次成功的解（用于失败时回滚）
        prev_solution = self._last_solution.copy() if self._last_solution is not None else None

        # 初始猜测：使用上次解或初始状态
        if self._last_solution is not None:
            q = self._last_solution.copy()
        else:
            q = self._build_state_vector()

        max_iter = Config.Kinematics.MAX_ITERATIONS
        tol = Config.Kinematics.CONVERGENCE_TOL
        converged = False

        for iteration in range(max_iter):
            Phi, J_mat = self._constraints_and_jacobian(q, driver_value)

            residual = np.linalg.norm(Phi)
            if residual < tol:
                converged = True
                break

            try:
                # 求解线性系统 J * dq = -Phi
                dq, _, _, _ = np.linalg.lstsq(J_mat, -Phi, rcond=None)

                # 阻尼限幅：防止单步跳跃过大导致越过奇异点
                max_step = np.max(np.abs(dq))
                if max_step > 0.5:
                    dq *= 0.5 / max_step

                q = q + dq
            except np.linalg.LinAlgError:
                self._last_solution = prev_solution
                return None

        # 检查 NaN / Inf
        if np.any(np.isnan(q)) or np.any(np.isinf(q)):
            self._last_solution = prev_solution
            return None

        # 检查是否收敛
        if not converged:
            final_Phi, _ = self._constraints_and_jacobian(q, driver_value)
            if np.linalg.norm(final_Phi) > 1e-6:
                # 未收敛 → 回滚缓存，返回失败
                self._last_solution = prev_solution
                return None

        # 缓存成功的解
        self._last_solution = q.copy()

        # 构建结果
        result = {}
        for mo in self.moving_objects:
            i = self.obj_index_map[mo['name']]
            result[mo['name']] = (q[3 * i], q[3 * i + 1], q[3 * i + 2])

        return result

    def compute_driver_limits(self, safety_factor=1.0):
        """
        自动计算驱动值的安全极限范围

        从 driver_value=0 开始，向正/负两个方向连续扫描，
        直到求解器无法收敛（即机构达到物理极限/死点）。
        求解器在精确死点处本身就无法收敛，因此自然失败边界
        就是天然的安全余量，默认不再额外缩减。

        参数:
            safety_factor: 安全系数 (0.0-1.0)，极限值乘以此系数
                           1.0 表示直接使用求解器能到达的最远位置

        返回: (min_limit, max_limit) 或 None（计算失败）
        """
        if not check_numpy():
            return None

        if self.driver_info is None:
            return None

        # 保存当前求解器状态
        saved_solution = self._last_solution.copy() if self._last_solution is not None else None

        # 确保初始状态可解（driver_value=0 即初始位置）
        self._last_solution = self._build_state_vector()
        test = self.solve(0.0)
        if test is None:
            self._last_solution = saved_solution
            return None
        initial_solution = self._last_solution.copy()

        # 正方向极限
        self._last_solution = initial_solution.copy()
        max_limit = self._probe_limit(direction=+1)

        # 负方向极限
        self._last_solution = initial_solution.copy()
        min_limit = self._probe_limit(direction=-1)

        # 恢复求解器状态
        self._last_solution = saved_solution

        # 应用安全系数（正值变小、负值绝对值变小，都向 0 靠拢）
        max_limit *= safety_factor
        min_limit *= safety_factor

        return (min_limit, max_limit)

    def _probe_limit(self, direction):
        """
        向指定方向探测驱动极限值

        纯粹依赖求解器收敛性检测：连续递增驱动值直到求解器失败，
        然后多轮回退精搜逼近真实死点。

        利用 solve() 的回滚机制：失败时 _last_solution 自动恢复到
        上一次成功的解，因此精搜轮次之间无需手动保存/恢复状态。

        参数:
            direction: +1（正方向）或 -1（负方向）

        返回: 该方向上的极限驱动值（求解器能收敛的最后一个值）
        """
        MAX_PROBE_VALUE = 10.0  # 最大探测值（安全上限）
        MAX_STEPS = 1000        # 每轮最大步数
        REFINEMENT_ROUNDS = 3   # 精搜轮数（步长逐轮缩小 10 倍）

        # 根据驱动类型确定初始步长
        jd = self.driver_info['joint_data']
        if jd['type'] == 'REVOLUTE':
            step = math.radians(1.0)  # 1° ≈ 0.0175 rad
        else:
            step = 0.002  # 2mm

        last_good = 0.0

        for _ in range(1 + REFINEMENT_ROUNDS):
            value = last_good
            steps_taken = 0
            # _last_solution 已处于 last_good 对应的解
            # （初始时由 compute_driver_limits 设置，
            #   后续由 solve 的失败回滚机制自动保持）

            while abs(value) < MAX_PROBE_VALUE and steps_taken < MAX_STEPS:
                value += direction * step
                if self.solve(value) is None:
                    # 求解失败 → _last_solution 已自动回滚到 last_good
                    break
                last_good = value
                steps_taken += 1

            # 缩小步长进入下一轮精搜
            step /= 10.0

        return last_good


# ==================== 全局求解器缓存 ====================

_solver_cache = None


def _get_or_build_solver(context):
    """获取或构建求解器（带缓存）"""
    global _solver_cache
    if _solver_cache is None:
        _solver_cache = PlanarMechanismSolver()
        _solver_cache.build_from_scene(context)
    return _solver_cache


def invalidate_solver_cache():
    """使求解器缓存失效（关节变更时调用）"""
    global _solver_cache
    _solver_cache = None


# ==================== 原始变换保存/恢复 ====================

def save_original_transforms(context):
    """保存参与机构的所有对象的初始变换"""
    props = context.scene.kinematics_props
    transforms = {}

    # 收集所有对象名
    obj_names = set()
    for j in props.joints:
        if j.object_a and not j.a_is_ground:
            obj_names.add(j.object_a.name)
        if j.object_b:
            obj_names.add(j.object_b.name)

    for name in obj_names:
        obj = bpy.data.objects.get(name)
        if obj:
            transforms[name] = {
                'location': list(obj.location),
                'rotation_euler': list(obj.rotation_euler),
                'rotation_mode': obj.rotation_mode,
            }

    props.original_transforms_json = json.dumps(transforms)


def restore_original_transforms(context):
    """恢复所有对象到激活前的初始变换"""
    props = context.scene.kinematics_props
    if not props.original_transforms_json:
        return False

    try:
        transforms = json.loads(props.original_transforms_json)
    except (json.JSONDecodeError, ValueError):
        return False

    for name, data in transforms.items():
        obj = bpy.data.objects.get(name)
        if obj:
            obj.rotation_mode = data.get('rotation_mode', 'XYZ')
            obj.location = Vector(data['location'])
            obj.rotation_euler.x = data['rotation_euler'][0]
            obj.rotation_euler.y = data['rotation_euler'][1]
            obj.rotation_euler.z = data['rotation_euler'][2]

    return True


# ==================== 驱动更新核心函数 ====================

def solve_and_apply(context):
    """
    驱动滑块的核心函数：求解机构并应用变换

    由 properties.py 中 driver_progress 的更新回调调用
    """
    props = context.scene.kinematics_props
    if not props.is_active or props.driver_joint_index < 0:
        return

    # 计算实际驱动值
    progress = props.driver_progress
    actual_value = props.driver_min + progress * (props.driver_max - props.driver_min)

    # 如果驱动关节是旋转类型，将度数转为弧度
    if props.driver_joint_index < len(props.joints):
        driver_joint = props.joints[props.driver_joint_index]
        if driver_joint.joint_type == 'REVOLUTE':
            actual_value = math.radians(actual_value)

    # 获取求解器
    solver = _get_or_build_solver(context)

    # 求解
    result = solver.solve(actual_value)
    if result is None:
        return

    # 应用变换
    plane = props.working_plane
    for obj_name, (x, y, theta) in result.items():
        obj = bpy.data.objects.get(obj_name)
        if obj:
            set_2d_pos(obj, (x, y), plane)
            set_rotation_angle(obj, theta, plane)

    # 刷新视图
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


# ==================== 操作符 ====================

class BOFU_OT_add_revolute_joint(Operator):
    """添加旋转关节：选中2个对象（或1个对象+勾选地面），铰接点使用3D游标位置"""
    bl_idname = "bofu.add_revolute_joint"
    bl_label = "添加旋转关节"
    bl_options = {'REGISTER', 'UNDO'}

    use_ground: BoolProperty(
        name="一端为地面",
        description="勾选时，关节一端连接到固定地面",
        default=False,
    )

    pivot_source: EnumProperty(
        name="铰接点来源",
        items=[
            ('CURSOR', '3D游标', '使用3D游标位置作为铰接点'),
            ('MANUAL', '手动输入', '手动输入铰接点坐标'),
        ],
        default='CURSOR',
    )

    pivot_manual: FloatVectorProperty(
        name="铰接点坐标",
        size=3,
        default=(0.0, 0.0, 0.0),
        subtype='TRANSLATION',
        precision=6,
    )

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and len(context.selected_objects) >= 1

    def invoke(self, context, event):
        # 预填充游标位置到手动输入
        self.pivot_manual = context.scene.cursor.location.copy()
        # 自动判断是否需要地面
        if len(context.selected_objects) == 1:
            self.use_ground = True
        else:
            self.use_ground = False
        return context.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, context):
        layout = self.layout

        selected = context.selected_objects
        box = layout.box()
        if len(selected) == 1:
            box.label(text=f"对象: {selected[0].name}", icon='OBJECT_DATA')
            box.prop(self, "use_ground")
            if self.use_ground:
                box.label(text="  地面 ↔ " + selected[0].name, icon='PINNED')
        elif len(selected) >= 2:
            box.label(text=f"对象A: {selected[0].name}", icon='OBJECT_DATA')
            box.label(text=f"对象B: {selected[1].name}", icon='OBJECT_DATA')
            box.prop(self, "use_ground")
            if self.use_ground:
                box.label(text=f"  地面 ↔ {selected[0].name}", icon='PINNED')

        layout.separator()
        layout.prop(self, "pivot_source")
        if self.pivot_source == 'CURSOR':
            cursor_loc = context.scene.cursor.location
            layout.label(text=f"  游标位置: ({cursor_loc.x:.4f}, {cursor_loc.y:.4f}, {cursor_loc.z:.4f})")
        else:
            layout.prop(self, "pivot_manual")

    def execute(self, context):
        props = context.scene.kinematics_props
        selected = list(context.selected_objects)

        if self.use_ground:
            if len(selected) < 1:
                self.report({'WARNING'}, "请至少选中1个对象")
                return {'CANCELLED'}
            obj_a = None
            obj_b = selected[0]
        else:
            if len(selected) < 2:
                self.report({'WARNING'}, "请选中2个对象，或勾选「一端为地面」")
                return {'CANCELLED'}
            obj_a = selected[0]
            obj_b = selected[1]

        # 获取铰接点
        if self.pivot_source == 'CURSOR':
            pivot = context.scene.cursor.location.copy()
        else:
            pivot = Vector(self.pivot_manual)

        # 添加关节
        joint = props.joints.add()
        joint.joint_type = 'REVOLUTE'
        joint.a_is_ground = self.use_ground
        if obj_a:
            joint.object_a = obj_a
        joint.object_b = obj_b
        joint.pivot_world = pivot

        # 计算并存储局部坐标
        plane = props.working_plane
        pivot_2d = get_2d_pos(pivot, plane)

        if obj_a and not self.use_ground:
            pos_a = get_2d_pos(obj_a.location, plane)
            angle_a = get_rotation_angle(obj_a, plane)
            local_a = world_to_local_2d(pivot_2d, pos_a, angle_a)
            joint.pivot_local_a = local_a

        pos_b = get_2d_pos(obj_b.location, plane)
        angle_b = get_rotation_angle(obj_b, plane)
        local_b = world_to_local_2d(pivot_2d, pos_b, angle_b)
        joint.pivot_local_b = local_b

        # 设为活动关节
        props.active_joint_index = len(props.joints) - 1

        invalidate_solver_cache()

        a_label = "地面" if self.use_ground else obj_a.name
        self.report({'INFO'}, f"已添加旋转关节: {a_label} ↔ {obj_b.name}")
        return {'FINISHED'}


class BOFU_OT_add_prismatic_joint(Operator):
    """添加平移关节：选中对象沿指定轴滑动"""
    bl_idname = "bofu.add_prismatic_joint"
    bl_label = "添加平移关节"
    bl_options = {'REGISTER', 'UNDO'}

    use_ground: BoolProperty(
        name="一端为地面",
        description="勾选时，对象相对于固定地面滑动",
        default=True,
    )

    axis_direction: EnumProperty(
        name="滑动方向",
        items=[
            ('X', 'X轴', '沿X轴方向平移'),
            ('Y', 'Y轴', '沿Y轴方向平移'),
            ('Z', 'Z轴', '沿Z轴方向平移'),
        ],
        default='Y',
    )

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and len(context.selected_objects) >= 1

    def invoke(self, context, event):
        if len(context.selected_objects) == 1:
            self.use_ground = True
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        layout = self.layout
        selected = context.selected_objects

        box = layout.box()
        if len(selected) == 1:
            box.label(text=f"对象: {selected[0].name}", icon='OBJECT_DATA')
        elif len(selected) >= 2:
            box.label(text=f"对象A: {selected[0].name}", icon='OBJECT_DATA')
            box.label(text=f"对象B: {selected[1].name}", icon='OBJECT_DATA')
        box.prop(self, "use_ground")

        layout.separator()
        layout.prop(self, "axis_direction")

    def execute(self, context):
        props = context.scene.kinematics_props
        selected = list(context.selected_objects)

        if self.use_ground:
            if len(selected) < 1:
                self.report({'WARNING'}, "请至少选中1个对象")
                return {'CANCELLED'}
            obj_a = None
            obj_b = selected[0]
        else:
            if len(selected) < 2:
                self.report({'WARNING'}, "请选中2个对象，或勾选「一端为地面」")
                return {'CANCELLED'}
            obj_a = selected[0]
            obj_b = selected[1]

        joint = props.joints.add()
        joint.joint_type = 'PRISMATIC'
        joint.a_is_ground = self.use_ground
        if obj_a:
            joint.object_a = obj_a
        joint.object_b = obj_b
        joint.axis_direction = self.axis_direction

        props.active_joint_index = len(props.joints) - 1

        invalidate_solver_cache()

        a_label = "地面" if self.use_ground else obj_a.name
        axis_label = self.axis_direction
        self.report({'INFO'}, f"已添加平移关节: {a_label} ↔ {obj_b.name} (沿{axis_label}轴)")
        return {'FINISHED'}


class BOFU_OT_remove_joint(Operator):
    """删除选中的关节"""
    bl_idname = "bofu.remove_joint"
    bl_label = "删除关节"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = context.scene.kinematics_props
        return len(props.joints) > 0

    def execute(self, context):
        props = context.scene.kinematics_props
        idx = props.active_joint_index

        if idx < 0 or idx >= len(props.joints):
            self.report({'WARNING'}, "没有选中的关节")
            return {'CANCELLED'}

        # 如果删除的是驱动关节，清除驱动
        if idx == props.driver_joint_index:
            props.driver_joint_index = -1
        elif idx < props.driver_joint_index:
            props.driver_joint_index -= 1

        props.joints.remove(idx)

        # 调整活动索引
        if props.active_joint_index >= len(props.joints):
            props.active_joint_index = max(0, len(props.joints) - 1)

        invalidate_solver_cache()

        self.report({'INFO'}, "已删除关节")
        return {'FINISHED'}


class BOFU_OT_set_driver(Operator):
    """将当前选中的关节设为驱动"""
    bl_idname = "bofu.set_driver_joint"
    bl_label = "设为驱动"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = context.scene.kinematics_props
        return len(props.joints) > 0

    def execute(self, context):
        props = context.scene.kinematics_props
        idx = props.active_joint_index

        if idx < 0 or idx >= len(props.joints):
            self.report({'WARNING'}, "请先选中一个关节")
            return {'CANCELLED'}

        props.driver_joint_index = idx
        invalidate_solver_cache()

        joint = props.joints[idx]
        jtype = "旋转" if joint.joint_type == 'REVOLUTE' else "平移"
        self.report({'INFO'}, f"已设置驱动关节: [{jtype}] 索引 {idx}")
        return {'FINISHED'}


class BOFU_OT_activate_mechanism(Operator):
    """激活机构：保存初始状态并进入驱动模式"""
    bl_idname = "bofu.activate_mechanism"
    bl_label = "激活机构"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = context.scene.kinematics_props
        return (len(props.joints) > 0
                and props.driver_joint_index >= 0
                and not props.is_active)

    def execute(self, context):
        if not check_numpy():
            self.report({'ERROR'}, "运动学求解器需要 numpy。请安装: pip install numpy")
            return {'CANCELLED'}

        props = context.scene.kinematics_props

        # 确保所有对象使用 XYZ 欧拉旋转
        obj_names = set()
        for j in props.joints:
            if j.object_a and not j.a_is_ground:
                obj_names.add(j.object_a.name)
            if j.object_b:
                obj_names.add(j.object_b.name)

        for name in obj_names:
            obj = bpy.data.objects.get(name)
            if obj and obj.rotation_mode != 'XYZ':
                obj.rotation_mode = 'XYZ'

        # 保存原始变换
        save_original_transforms(context)

        # 构建求解器
        invalidate_solver_cache()
        solver = _get_or_build_solver(context)

        # 检查自由度
        dof = solver.compute_dof()
        if dof != 1:
            self.report({'WARNING'},
                        f"机构自由度为 {dof}（需要 1）。请检查关节配置。"
                        f"活动对象: {len(solver.moving_objects)}，"
                        f"约束: {sum(2 for _ in solver.joints_data)}")
            # 仍然允许激活，但给出警告

        # 重置驱动进度
        props.driver_progress = 0.0
        props.is_active = True

        self.report({'INFO'}, f"机构已激活（自由度: {dof}，活动对象: {len(solver.moving_objects)}）")
        return {'FINISHED'}


class BOFU_OT_deactivate_mechanism(Operator):
    """停用机构：恢复初始位置"""
    bl_idname = "bofu.deactivate_mechanism"
    bl_label = "停用机构"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene.kinematics_props.is_active

    def execute(self, context):
        props = context.scene.kinematics_props

        # 恢复原始变换
        restore_original_transforms(context)

        props.is_active = False
        props.driver_progress = 0.0
        invalidate_solver_cache()

        # 刷新视图
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

        self.report({'INFO'}, "机构已停用，对象已恢复初始位置")
        return {'FINISHED'}


class BOFU_OT_reset_to_start(Operator):
    """重置驱动到起始位置"""
    bl_idname = "bofu.reset_to_start"
    bl_label = "回到起点"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene.kinematics_props.is_active

    def execute(self, context):
        props = context.scene.kinematics_props
        props.driver_progress = 0.0
        self.report({'INFO'}, "已重置到起始位置")
        return {'FINISHED'}


class BOFU_OT_update_pivot_from_cursor(Operator):
    """将当前选中关节的铰接点更新为3D游标位置"""
    bl_idname = "bofu.update_pivot_from_cursor"
    bl_label = "铰接点 ← 3D游标"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = context.scene.kinematics_props
        if len(props.joints) == 0:
            return False
        idx = props.active_joint_index
        return 0 <= idx < len(props.joints) and props.joints[idx].joint_type == 'REVOLUTE'

    def execute(self, context):
        props = context.scene.kinematics_props
        joint = props.joints[props.active_joint_index]

        pivot = context.scene.cursor.location.copy()
        joint.pivot_world = pivot

        # 重新计算局部坐标
        plane = props.working_plane
        pivot_2d = get_2d_pos(pivot, plane)

        if joint.object_a and not joint.a_is_ground:
            pos_a = get_2d_pos(joint.object_a.location, plane)
            angle_a = get_rotation_angle(joint.object_a, plane)
            joint.pivot_local_a = world_to_local_2d(pivot_2d, pos_a, angle_a)

        if joint.object_b:
            pos_b = get_2d_pos(joint.object_b.location, plane)
            angle_b = get_rotation_angle(joint.object_b, plane)
            joint.pivot_local_b = world_to_local_2d(pivot_2d, pos_b, angle_b)

        invalidate_solver_cache()

        self.report({'INFO'}, f"铰接点已更新为 ({pivot.x:.4f}, {pivot.y:.4f}, {pivot.z:.4f})")
        return {'FINISHED'}


class BOFU_OT_clear_all_joints(Operator):
    """清除所有关节定义"""
    bl_idname = "bofu.clear_all_joints"
    bl_label = "清除所有关节"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(context.scene.kinematics_props.joints) > 0

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        props = context.scene.kinematics_props

        if props.is_active:
            restore_original_transforms(context)
            props.is_active = False

        count = len(props.joints)
        props.joints.clear()
        props.active_joint_index = 0
        props.driver_joint_index = -1
        props.driver_progress = 0.0
        invalidate_solver_cache()

        self.report({'INFO'}, f"已清除 {count} 个关节")
        return {'FINISHED'}


# ==================== 演示操作符 ====================

DEMO_PREFIX = "运动学演示_"


class BOFU_OT_kinematics_demo(Operator):
    """创建肘节夹钳演示：自动生成对象、配置关节和驱动，一键体验运动学求解"""
    bl_idname = "bofu.kinematics_demo"
    bl_label = "创建演示: 肘节夹钳"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        import bmesh

        if not check_numpy():
            self.report({'ERROR'}, "运动学求解器需要 numpy，请先安装: pip install numpy")
            return {'CANCELLED'}

        props = context.scene.kinematics_props

        # ── 1. 清理旧状态 ──
        if props.is_active:
            restore_original_transforms(context)
            props.is_active = False

        props.joints.clear()
        props.driver_joint_index = -1
        props.driver_progress = 0.0
        invalidate_solver_cache()

        # 删除旧演示对象和材质
        for obj in list(bpy.data.objects):
            if obj.name.startswith(DEMO_PREFIX):
                bpy.data.objects.remove(obj, do_unlink=True)

        # ── 2. 辅助函数 ──
        def make_material(name, rgba):
            mat = bpy.data.materials.get(name)
            if not mat:
                mat = bpy.data.materials.new(name)
            mat.diffuse_color = rgba
            return mat

        def make_box(name, sx, sy, sz, ox=0.0, oy=0.0):
            """创建一个偏移中心的盒体网格"""
            mesh = bpy.data.meshes.new(name)
            bm = bmesh.new()
            bmesh.ops.create_cube(bm, size=1.0)
            for v in bm.verts:
                v.co.x = v.co.x * sx + ox
                v.co.y = v.co.y * sy + oy
                v.co.z *= sz
            bm.to_mesh(mesh)
            bm.free()
            return mesh

        def make_sphere(name, radius=0.004):
            """创建铰接点标记小球"""
            mesh = bpy.data.meshes.new(name)
            bm = bmesh.new()
            bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=6, radius=radius)
            bm.to_mesh(mesh)
            bm.free()
            return mesh

        def spawn(mesh, location, material):
            """创建对象并放入场景"""
            obj = bpy.data.objects.new(mesh.name, mesh)
            obj.location = Vector(location)
            obj.rotation_mode = 'XYZ'
            if material:
                obj.data.materials.append(material)
            context.collection.objects.link(obj)
            return obj

        # ── 3. 材质 ──
        mat_clamp  = make_material("运动学_夹具", (0.90, 0.50, 0.10, 1.0))
        mat_link   = make_material("运动学_连杆", (0.70, 0.70, 0.70, 1.0))
        mat_piston = make_material("运动学_活塞", (0.75, 0.78, 0.82, 1.0))
        mat_base   = make_material("运动学_底座", (0.25, 0.25, 0.25, 1.0))
        mat_pivot  = make_material("运动学_铰点", (1.00, 0.20, 0.20, 1.0))

        # ── 4. 机构铰接点坐标（XY 平面）──
        #
        #   底座固定板 ═══════════════════
        #        A ──── 夹具(橙色) ──── B
        #      (0,0.1)               (0.1,0.1)
        #                               │
        #                          连杆(灰色)
        #                               │
        #                               C
        #                           (0.1, 0)
        #                               │
        #                          活塞(银色)
        #                            ↕ Y轴
        #
        A = (0.0,  0.10, 0.0)   # 地面↔夹具 固定铰点
        B = (0.10, 0.10, 0.0)   # 夹具↔连杆 铰点
        C = (0.10, 0.0,  0.0)   # 连杆↔活塞 铰点

        # ── 5. 创建对象 ──
        # 底座（纯视觉参考，不参与运动学）
        spawn(make_box(DEMO_PREFIX + "底座", 0.16, 0.006, 0.03, ox=0.05, oy=0.135),
              (0, 0, 0), mat_base)

        # 夹具（橙色）：origin 在铰点 A，向右延伸到 B
        clamp = spawn(
            make_box(DEMO_PREFIX + "夹具", 0.13, 0.022, 0.01, ox=0.055),
            A, mat_clamp)

        # 连杆（灰色）：origin 在 B、C 中点，竖直方向
        link = spawn(
            make_box(DEMO_PREFIX + "连杆", 0.016, 0.115, 0.008),
            (0.10, 0.05, 0), mat_link)

        # 活塞（银色）：origin 偏下，顶部对齐铰点 C
        piston = spawn(
            make_box(DEMO_PREFIX + "活塞", 0.030, 0.08, 0.015, oy=-0.01),
            (0.10, -0.03, 0), mat_piston)

        # 铰点标记小球（红色）
        for pos, label in [(A, "铰点A_地面↔夹具"),
                           (B, "铰点B_夹具↔连杆"),
                           (C, "铰点C_连杆↔活塞")]:
            spawn(make_sphere(DEMO_PREFIX + label), pos, mat_pivot)

        # ── 6. 工作平面 ──
        props.working_plane = 'XY'
        plane = 'XY'

        # ── 7. 配置关节 ──
        def add_revolute(obj_a, obj_b, pivot, ground_a=False):
            """添加一个旋转关节并自动计算局部坐标"""
            j = props.joints.add()
            j.joint_type = 'REVOLUTE'
            j.a_is_ground = ground_a
            if obj_a and not ground_a:
                j.object_a = obj_a
            j.object_b = obj_b
            j.pivot_world = pivot
            p2d = get_2d_pos(pivot, plane)
            if obj_a and not ground_a:
                pa = get_2d_pos(obj_a.location, plane)
                aa = get_rotation_angle(obj_a, plane)
                j.pivot_local_a = world_to_local_2d(p2d, pa, aa)
            pb = get_2d_pos(obj_b.location, plane)
            ab = get_rotation_angle(obj_b, plane)
            j.pivot_local_b = world_to_local_2d(p2d, pb, ab)

        # 关节1: 地面 ↔ 夹具  旋转 @ A
        add_revolute(None, clamp, A, ground_a=True)
        # 关节2: 夹具 ↔ 连杆  旋转 @ B
        add_revolute(clamp, link, B)
        # 关节3: 连杆 ↔ 活塞  旋转 @ C
        add_revolute(link, piston, C)
        # 关节4: 地面 ↔ 活塞  平移 ↕Y
        j4 = props.joints.add()
        j4.joint_type = 'PRISMATIC'
        j4.a_is_ground = True
        j4.object_b = piston
        j4.axis_direction = 'Y'

        # ── 8. 驱动配置 ──
        props.driver_joint_index = 3   # 关节4 = 活塞平移
        props.driver_min = -0.04       # 向下 4cm
        props.driver_max = 0.04        # 向上 4cm

        invalidate_solver_cache()

        # ── 9. 选中并聚焦 ──
        bpy.ops.object.select_all(action='DESELECT')
        for obj in bpy.data.objects:
            if obj.name.startswith(DEMO_PREFIX):
                obj.select_set(True)
        context.view_layer.objects.active = clamp

        # 尝试聚焦视图
        try:
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    with context.temp_override(area=area):
                        bpy.ops.view3d.view_selected()
                    break
        except Exception:
            pass

        self.report({'INFO'},
                    "肘节夹钳演示已创建！"
                    "下一步: 点击「激活机构」→ 拖动驱动滑块")
        return {'FINISHED'}


class BOFU_OT_auto_compute_limits(Operator):
    """根据机构几何自动计算驱动关节的安全极限范围"""
    bl_idname = "bofu.auto_compute_limits"
    bl_label = "自动计算极限"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if not check_numpy():
            return False
        props = context.scene.kinematics_props
        return (
            len(props.joints) > 0
            and props.driver_joint_index >= 0
            and props.driver_joint_index < len(props.joints)
            and not props.is_active
        )

    def execute(self, context):
        props = context.scene.kinematics_props

        # 构建临时求解器
        solver = PlanarMechanismSolver(props.working_plane)
        solver.build_from_scene(context)

        # 检查自由度
        dof = solver.compute_dof()
        if dof != 1:
            self.report(
                {'ERROR'},
                f"自由度为 {dof}，需要恰好为 1 才能计算极限"
            )
            return {'CANCELLED'}

        # 计算极限
        result = solver.compute_driver_limits()
        if result is None:
            self.report(
                {'ERROR'},
                "无法计算驱动极限（求解器初始化失败）"
            )
            return {'CANCELLED'}

        min_limit, max_limit = result

        # 转换单位：旋转关节 弧度→度
        driver_joint = props.joints[props.driver_joint_index]
        if driver_joint.joint_type == 'REVOLUTE':
            min_limit = math.degrees(min_limit)
            max_limit = math.degrees(max_limit)
            unit = "°"
        else:
            unit = "m"

        # 设置属性
        props.driver_min = min_limit
        props.driver_max = max_limit

        self.report(
            {'INFO'},
            f"驱动极限已计算: {min_limit:.4f}{unit} ~ {max_limit:.4f}{unit}"
        )
        return {'FINISHED'}


# ==================== 类注册列表 ====================

classes = (
    BOFU_OT_add_revolute_joint,
    BOFU_OT_add_prismatic_joint,
    BOFU_OT_remove_joint,
    BOFU_OT_set_driver,
    BOFU_OT_activate_mechanism,
    BOFU_OT_deactivate_mechanism,
    BOFU_OT_reset_to_start,
    BOFU_OT_update_pivot_from_cursor,
    BOFU_OT_clear_all_joints,
    BOFU_OT_auto_compute_limits,
    BOFU_OT_kinematics_demo,
)
