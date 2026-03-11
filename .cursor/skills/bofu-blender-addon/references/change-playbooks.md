# 改动套路与验证

这个文件给出高频改动的最小实现清单，以及在没有 Blender 自动化环境时如何做低成本验证。

## 先问清楚的点

需求不够明确时，优先确认这些信息：

1. 功能要挂在哪个入口：饼图、子菜单、侧栏面板还是快捷键。
2. 是否需要持久化到 `.blend`。
3. 是否只影响对象模式，还是也要支持编辑模式。
4. 是否需要多选、活动对象、活动元素语义。
5. 是否需要更新 README 和版本说明。
6. 是否需要生成新的发布 zip。

## Playbook: 新增操作符

1. 选定最接近的 `operators_*.py`。
2. 新建 `Operator` 类，写清楚 `bl_idname`、`bl_label`、说明文字。
3. 如有上下文限制，优先写 `poll()`。
4. 在 `execute()` / `invoke()` 里使用现有工具函数和现有状态对象。
5. 用 `self.report()` 返回用户可理解的结果。
6. 加入本模块 `classes`。
7. 按需求补 UI 入口或快捷键。

最小静态检查：

```bash
python -m compileall bofu_enhanced
```

建议手工验证：

- 从预期入口触发一次
- 无选中 / 错误模式下触发一次
- 多选或边界输入触发一次

## Playbook: 新增面板或菜单项

1. 先找现有菜单分组，不要随意新开一级结构。
2. 如果从弹出菜单调用需要弹窗的操作符，设置 `layout.operator_context = 'INVOKE_DEFAULT'`。
3. 与现有中文文案、icon、排列顺序保持一致。
4. 如果是新面板，确认 `bl_space_type`、`bl_region_type`、`bl_category` 是否与当前 UI 体系一致。

建议手工验证：

- 入口是否出现在预期位置
- 点击后是否真的触发 `invoke()` / 弹窗
- 不同模式下 UI 是否显示正确

## Playbook: 新增 Scene 属性

1. 在 `properties.py` 定义属性或 `PropertyGroup` 字段。
2. 在 `register_properties()` / `unregister_properties()` 成对处理。
3. 在 UI 显示该属性前，先确认默认值和更新回调不会产生副作用。
4. 让操作符和 UI 都通过同一属性来源读取，避免状态重复。

建议手工验证：

- 新建文件后默认值是否正确
- 修改属性后相关功能是否立刻生效
- 保存并重新打开 `.blend` 后行为是否符合预期

## Playbook: 新增 handler / 持久化

1. handler 生命周期放在 `__init__.py`。
2. 需要跨文件保留时，使用 `@persistent`。
3. 注册前检查是否已存在，避免重复 append。
4. 注销时对称清理。
5. 涉及缓存时，考虑 `load_post` 清空旧文件残留状态。
6. 处理器内部优先容错返回，不要让异常持续打断 Blender 事件流。

建议手工验证：

- 重新启用插件后是否只注册一次
- 保存文件前后是否按预期读写数据
- 打开新文件或切换文件后是否残留旧状态

## Playbook: 修改打包或发布

默认先做静态检查，再做打包检查。

静态检查：

```bash
python -m compileall bofu_enhanced pack_addon.py
```

非交互打包：

```bash
python -c "import os, pack_addon; ok = pack_addon.pack_addon(os.getcwd()); print('OK' if ok else 'FAIL')"
```

打包后核对：

- zip 根目录是否仍为 `bofu_enhanced/`
- 版本号是否来自 `bl_info`
- 是否混入 `__pycache__`、`.pyc`、临时文件

## README 什么时候要改

以下情况通常要同步改 `README.md`：

- 新增用户可见功能
- 更改入口、快捷键、面板位置
- 修改打包或发布方式
- 改动版本号或兼容 Blender 版本
- 调整核心工作流，导致旧文档不再准确

## 没有 Blender 运行时的时候

如果当前环境只能做静态改动，最终说明里要明确写出：

- 已完成哪些代码修改
- 已做哪些静态检查
- 哪些 Blender 内的交互验证尚未执行
- 建议用户在 Blender 里最少验证哪 2 到 3 个动作
