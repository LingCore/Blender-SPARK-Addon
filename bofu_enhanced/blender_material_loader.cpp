/**
 * blender_material_loader.cpp
 *
 * 适用版本：Blender 4.0
 *
 * 功能说明：
 *   从外部 .blend 文件中加载（追加/链接）材质数据块，
 *   并将其应用到指定的网格物体上。
 *
 * Blender 4.0 API 变更说明：
 *   - 大量 BKE 头文件从 .h 改为 .hh（C++ 化）
 *   - 链接/追加 API 完全重构：
 *     旧 API（3.x）：BLO_library_link_begin / _named_part / _end
 *     新 API（4.0）：BKE_blendfile_link_append_context_* 系列函数
 *   - LibraryLink_Params 结构体已重构
 *   - BLO_readfile.h → BLO_readfile.hh
 *   - BKE_lib_id_make_local 已被新的追加流程内部处理
 *
 * 对应的 Python 等效代码：
 *   with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
 *       data_to.materials = data_from.materials
 *
 * 编译说明：
 *   此文件需放入 Blender 4.0 源码树中编译，依赖 Blender 内部头文件。
 *   不能作为独立程序编译。
 *
 * 作者：bofu_enhanced
 * 日期：2026-02-06
 */

/* ============================================================
 *  Blender 4.0 内部头文件引用
 *
 *  【重要】Blender 4.0 将许多头文件从 .h 改为 .hh
 *  DNA 头文件仍保持 .h，BKE/BLO 大部分改为 .hh
 *  如果编译报错找不到头文件，尝试切换 .h ↔ .hh 后缀
 * ============================================================ */

/* C++ 标准库 */
#include <cstdio>
#include <cstring>
#include <cstdlib>

/* ---- Blender DNA（数据结构定义，仍然是 .h）---- */
#include "DNA_material_types.h"    /* Material 结构体定义 */
#include "DNA_mesh_types.h"        /* Mesh 结构体定义 */
#include "DNA_object_types.h"      /* Object 结构体定义 */
#include "DNA_scene_types.h"       /* Scene 结构体定义 */
#include "DNA_ID.h"                /* ID 基础结构体 */

/* ---- Blender 内核（BKE）—— 4.0 大部分改为 .hh ---- */
#include "BKE_context.hh"         /* bContext 上下文 */
#include "BKE_main.hh"            /* Main 数据库（bmain） */
#include "BKE_material.h"         /* 材质操作函数（此文件在 4.0 仍为 .h） */
#include "BKE_report.h"           /* 报告/日志系统 */
#include "BKE_lib_id.hh"          /* ID 数据块操作 */
#include "BKE_object.hh"          /* 物体操作函数 */

/* ---- Blender 4.0 链接/追加 API（核心变更） ---- */
#include "BKE_blendfile_link_append.hh"  /* 新的链接/追加上下文 API */

/* ---- Blender 加载器 ---- */
#include "BLO_readfile.hh"         /* BlendHandle、BLO_blendhandle_* 系列函数 */

/* ---- 内存管理 ---- */
#include "MEM_guardedalloc.h"      /* Blender 自定义内存分配器 */

/* ---- 工具库 ---- */
#include "BLI_listbase.h"          /* ListBase 链表操作宏 */
#include "BLI_path_util.h"         /* 路径工具函数 */
#include "BLI_string.h"            /* 字符串工具函数 */


/* ============================================================
 *  函数一：列出 .blend 文件中的所有材质名称
 * ============================================================
 *
 * 功能：
 *   打开一个外部 .blend 文件，读取其中所有材质数据块的名称，
 *   并打印到控制台。不会导入任何数据。
 *
 * 等效 Python：
 *   with bpy.data.libraries.load(blend_path) as (data_from, data_to):
 *       for mat_name in data_from.materials:
 *           print(mat_name)
 *
 * 参数：
 *   blend_filepath - .blend 文件的完整绝对路径
 *
 * 返回值：
 *   成功返回 0，失败返回 -1
 */
int list_materials_in_blend_file(const char *blend_filepath)
{
    /* ----------------------------------------------------------
     * 第一步：打开 .blend 文件，获取 BlendHandle
     *
     * BlendHandle 是 Blender 用于读取 .blend 文件的句柄。
     * Blender 4.0 中 BlendFileReadReport 结构体仍然需要，
     * 用于收集读取过程中的警告/错误信息。
     * ---------------------------------------------------------- */
    BlendFileReadReport bf_reports = {};
    bf_reports.reports = nullptr;  /* 可选：传入 ReportList 以收集详细报告 */

    BlendHandle *bh = BLO_blendhandle_from_file(blend_filepath, &bf_reports);

    if (bh == nullptr) {
        printf("[错误] 无法打开文件: %s\n", blend_filepath);
        return -1;
    }

    /* ----------------------------------------------------------
     * 第二步：获取文件中所有材质数据块的名称列表
     *
     * Blender 4.0 中 BLO_blendhandle_get_datablock_names 签名：
     *   LinkNode *BLO_blendhandle_get_datablock_names(
     *       BlendHandle *bh,
     *       int ofblocktype,       // ID 类型代码，ID_MA = Material
     *       bool use_assets_only,  // true = 只列出标记为 Asset 的
     *       int *r_tot_names       // [输出] 总数量
     *   );
     * ---------------------------------------------------------- */
    int total_materials = 0;
    LinkNode *names = BLO_blendhandle_get_datablock_names(
        bh,                   /* 文件句柄 */
        ID_MA,                /* ID 类型：ID_MA = Material */
        false,                /* use_assets_only: 不限制，列出全部 */
        &total_materials      /* [输出] 材质总数 */
    );

    /* ----------------------------------------------------------
     * 第三步：遍历并打印所有材质名称
     * LinkNode 是一个单向链表，每个节点的 link 指向名称字符串
     * ---------------------------------------------------------- */
    printf("=== 文件: %s ===\n", blend_filepath);
    printf("共有 %d 个材质:\n\n", total_materials);

    int index = 1;
    for (LinkNode *node = names; node; node = node->next) {
        const char *mat_name = static_cast<const char *>(node->link);
        printf("  %d. %s\n", index, mat_name);
        index++;
    }

    /* ----------------------------------------------------------
     * 第四步：释放资源
     * ---------------------------------------------------------- */
    BLI_linklist_freeN(names);   /* 释放名称链表及其中的字符串 */
    BLO_blendhandle_close(bh);   /* 关闭文件句柄 */

    return 0;
}


/* ============================================================
 *  函数二：从 .blend 文件中追加（Append）指定材质
 * ============================================================
 *
 * 功能：
 *   从外部 .blend 文件中追加一个材质到当前场景的 Main 数据库中。
 *   追加（Append）= 完整拷贝，与原文件脱离关系。
 *   链接（Link）= 保持引用，修改原文件会同步。
 *
 *   【Blender 4.0 重大变更】
 *   旧版（3.x）使用 BLO_library_link_begin / _named_part / _end
 *   新版（4.0）使用 BKE_blendfile_link_append_context 系列函数：
 *     1. BKE_blendfile_link_append_context_new()    - 创建上下文
 *     2. BKE_blendfile_link_append_context_library_add()  - 添加库文件
 *     3. BKE_blendfile_link_append_context_item_add()     - 添加要导入的项
 *     4. BKE_blendfile_link() 或 BKE_blendfile_append()  - 执行链接/追加
 *     5. BKE_blendfile_link_append_context_free()   - 释放上下文
 *
 * 等效 Python：
 *   with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
 *       data_to.materials = ["material_name"]
 *
 * 参数：
 *   bmain          - Blender 主数据库指针（通过 CTX_data_main 获取）
 *   scene          - 当前场景指针
 *   view_layer     - 当前视图层指针
 *   blend_filepath - .blend 文件的完整绝对路径
 *   material_name  - 要追加的材质名称
 *   do_append      - true = 追加(Append)，false = 链接(Link)
 *
 * 返回值：
 *   成功返回指向导入的 Material 的指针，失败返回 nullptr
 */
Material *append_material_from_blend(
    Main *bmain,
    Scene *scene,
    ViewLayer *view_layer,
    const char *blend_filepath,
    const char *material_name,
    bool do_append)
{
    /* ----------------------------------------------------------
     * 第一步：配置链接/追加参数
     *
     * LibraryLink_Params 在 Blender 4.0 中的关键字段：
     *   - bmain:  主数据库
     *   - flag:   控制标志（FILE_LINK 等）
     *
     * 追加（Append）：不设 FILE_LINK 标志
     * 链接（Link）：设置 FILE_LINK 标志
     * ---------------------------------------------------------- */
    LibraryLink_Params link_params = {};
    link_params.bmain = bmain;

    if (!do_append) {
        /* 链接模式：数据块保持对外部文件的引用 */
        link_params.flag |= FILE_LINK;
    }
    /* 追加模式：flag 不包含 FILE_LINK，追加完成后数据块会自动变为本地 */

    /* ----------------------------------------------------------
     * 第二步：创建链接/追加上下文
     *
     * BlendfileLinkAppendContext 是 Blender 4.0 新引入的核心结构，
     * 取代了旧版的 LibraryLink_Context。
     * 它管理整个链接/追加操作的生命周期。
     * ---------------------------------------------------------- */
    BlendfileLinkAppendContext *lapp_context =
        BKE_blendfile_link_append_context_new(&link_params);

    if (lapp_context == nullptr) {
        printf("[错误] 无法创建链接/追加上下文\n");
        return nullptr;
    }

    /* ----------------------------------------------------------
     * 第三步：向上下文中添加库文件（.blend 文件路径）
     *
     * 一个上下文可以添加多个库文件，这里只添加一个。
     * 返回值是该库在上下文中的索引（从 0 开始）。
     * ---------------------------------------------------------- */
    int lib_index = BKE_blendfile_link_append_context_library_add(
        lapp_context,
        blend_filepath,    /* .blend 文件的完整路径 */
        nullptr            /* BlendHandle* 可选，传 nullptr 让函数自己打开 */
    );

    if (lib_index < 0) {
        printf("[错误] 无法添加库文件: %s\n", blend_filepath);
        BKE_blendfile_link_append_context_free(lapp_context);
        return nullptr;
    }

    printf("[信息] 已添加库文件 (索引=%d): %s\n", lib_index, blend_filepath);

    /* ----------------------------------------------------------
     * 第四步：向上下文中添加要导入的数据块项
     *
     * BKE_blendfile_link_append_context_item_add 参数：
     *   - lapp_context: 上下文
     *   - idname:       数据块名称（如 "arcuchi_material_gold"）
     *   - id_code:      数据块类型代码（ID_MA = Material）
     *   - userdata:     用户自定义数据（可选，传 nullptr）
     *
     * 返回 BlendfileLinkAppendContextItem 指针，用于后续查询结果。
     * ---------------------------------------------------------- */
    BlendfileLinkAppendContextItem *item =
        BKE_blendfile_link_append_context_item_add(
            lapp_context,
            material_name,   /* 材质名称 */
            ID_MA,           /* 类型代码：Material */
            nullptr          /* userdata */
        );

    if (item == nullptr) {
        printf("[错误] 无法添加导入项: %s\n", material_name);
        BKE_blendfile_link_append_context_free(lapp_context);
        return nullptr;
    }

    /*
     * 标记该项应从哪个库文件中导入
     * 因为一个上下文可以有多个库，需要指定库索引
     */
    BKE_blendfile_link_append_context_item_library_index_enable(
        lapp_context,
        item,
        lib_index    /* 上面添加库文件时返回的索引 */
    );

    /* ----------------------------------------------------------
     * 第五步：执行链接或追加操作
     *
     * Blender 4.0 将链接和追加分为两个独立函数：
     *   - BKE_blendfile_link():   链接（保持外部引用）
     *   - BKE_blendfile_append(): 追加（完整拷贝到本地）
     *
     * 追加操作内部会自动执行 make_local，
     * 不需要像旧版那样手动调用 BKE_lib_id_make_local()。
     * ---------------------------------------------------------- */
    ReportList reports;
    BKE_reports_init(&reports, RPT_STORE);

    if (do_append) {
        /* 追加模式：数据块会被拷贝并转为本地 */
        BKE_blendfile_append(lapp_context, &reports);
        printf("[信息] 执行追加(Append)操作...\n");
    }
    else {
        /* 链接模式：数据块保持对外部 .blend 文件的引用 */
        BKE_blendfile_link(lapp_context, &reports);
        printf("[信息] 执行链接(Link)操作...\n");
    }

    /* 检查报告中是否有错误 */
    if (BKE_reports_contain(&reports, RPT_ERROR)) {
        printf("[错误] 链接/追加过程中发生错误\n");
        BKE_reports_print(&reports, RPT_ERROR);
    }

    /* ----------------------------------------------------------
     * 第六步：从上下文中获取导入的数据块
     *
     * 导入完成后，可以通过 item 获取导入的 ID 指针。
     * BKE_blendfile_link_append_context_item_newid_get
     * 返回导入的新 ID 数据块。
     * ---------------------------------------------------------- */
    ID *new_id = BKE_blendfile_link_append_context_item_newid_get(
        lapp_context,
        item
    );

    /* ----------------------------------------------------------
     * 第七步：清理并返回结果
     * ---------------------------------------------------------- */
    BKE_blendfile_link_append_context_free(lapp_context);
    BKE_reports_free(&reports);

    if (new_id == nullptr) {
        printf("[错误] 导入后未能获取材质: %s\n", material_name);
        return nullptr;
    }

    /*
     * 将 ID* 转为 Material*
     * ID 是所有数据块的基类，Material 的第一个成员就是 ID
     * id.name 格式为 "MAxxxx"，前两个字符是类型代码，+2 跳过
     */
    Material *mat = reinterpret_cast<Material *>(new_id);
    printf("[成功] 已导入材质: %s (ID类型: %.2s)\n",
           mat->id.name + 2,   /* 材质名称 */
           mat->id.name);      /* 类型代码（应为 "MA"） */

    return mat;
}


/* ============================================================
 *  函数三：将材质应用到指定的网格物体
 * ============================================================
 *
 * 功能：
 *   将一个 Material 赋值给 Object 的第一个材质槽位。
 *   如果物体没有材质槽，则新建一个。
 *
 * 等效 Python：
 *   if obj.data.materials:
 *       obj.data.materials[0] = mat
 *   else:
 *       obj.data.materials.append(mat)
 *
 * 参数：
 *   bmain  - Blender 主数据库指针
 *   ob     - 目标物体指针（必须是 MESH 类型）
 *   mat    - 要应用的材质指针
 *
 * 返回值：
 *   成功返回 true，失败返回 false
 *
 * 【注意】此函数在 Blender 4.0 中 API 无变化。
 */
bool apply_material_to_object(Main *bmain, Object *ob, Material *mat)
{
    /* 检查参数有效性 */
    if (ob == nullptr || mat == nullptr) {
        printf("[错误] 物体或材质指针为空\n");
        return false;
    }

    /* 只对网格物体（Mesh）操作 */
    if (ob->type != OB_MESH) {
        printf("[错误] 物体 '%s' 不是网格类型, 类型代码=%d\n",
               ob->id.name + 2, ob->type);
        return false;
    }

    /* ----------------------------------------------------------
     * 获取物体当前的材质槽数量
     * ob->totcol 表示物体拥有的材质槽总数
     * ---------------------------------------------------------- */
    if (ob->totcol > 0) {
        /*
         * 已有材质槽：替换第一个槽位
         *
         * BKE_object_material_assign 参数说明：
         *   bmain   - 主数据库
         *   ob      - 物体
         *   mat     - 材质
         *   act     - 材质槽编号（1-based，第一个槽位=1）
         *   assign_type - 赋值类型
         *     BKE_MAT_ASSIGN_USERPREF = 根据用户偏好决定赋给物体还是网格数据
         *     BKE_MAT_ASSIGN_OBJECT   = 赋给物体级别
         *     BKE_MAT_ASSIGN_OBDATA   = 赋给网格数据级别
         */
        BKE_object_material_assign(
            bmain, ob, mat,
            1,                         /* 槽位编号，1-based */
            BKE_MAT_ASSIGN_USERPREF    /* 根据用户偏好 */
        );
    }
    else {
        /*
         * 没有材质槽：先添加槽位，再赋值
         * BKE_object_material_slot_add 为物体添加一个新的空材质槽
         */
        BKE_object_material_slot_add(bmain, ob);
        BKE_object_material_assign(
            bmain, ob, mat,
            1,
            BKE_MAT_ASSIGN_USERPREF
        );
    }

    printf("[成功] 已将材质 '%s' 应用到物体 '%s'\n",
           mat->id.name + 2,   /* 材质名 */
           ob->id.name + 2);   /* 物体名 */

    return true;
}


/* ============================================================
 *  函数四：完整流程 —— 从文件加载材质并应用到选中物体
 * ============================================================
 *
 * 功能：
 *   综合调用以上函数，完成完整的"导入材质 → 应用到选中物体"流程。
 *   这个函数可以直接注册为 Blender 操作符（Operator）的 exec 回调。
 *
 * 等效 Python 完整流程：
 *   import bpy, os
 *   desktop = os.path.join(os.path.expanduser("~"), "Desktop")
 *   filepath = os.path.join(desktop, "exported_materials.blend")
 *
 *   with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
 *       data_to.materials = ["arcuchi_material_gold"]
 *
 *   mat = bpy.data.materials.get("arcuchi_material_gold")
 *   for obj in bpy.context.selected_objects:
 *       if obj.type == 'MESH':
 *           if obj.data.materials:
 *               obj.data.materials[0] = mat
 *           else:
 *               obj.data.materials.append(mat)
 *
 * 参数：
 *   C - Blender 上下文指针（包含 bmain、scene、选中物体等信息）
 */
void load_and_apply_material(bContext *C)
{
    /* ----------------------------------------------------------
     * 第一步：从上下文获取必要的指针
     *
     * Blender 4.0 中这些 CTX_data_* 函数 API 未变化
     * ---------------------------------------------------------- */
    Main *bmain           = CTX_data_main(C);           /* 主数据库 */
    Scene *scene          = CTX_data_scene(C);          /* 当前场景 */
    ViewLayer *view_layer = CTX_data_view_layer(C);     /* 当前视图层 */

    /* ----------------------------------------------------------
     * 第二步：构造桌面上 .blend 文件的路径
     *
     * Windows: 环境变量 USERPROFILE = C:\Users\<用户名>
     * Linux/macOS: 环境变量 HOME = /home/<用户名>
     * ---------------------------------------------------------- */
    char blend_filepath[FILE_MAX];

    const char *user_home = getenv("USERPROFILE");  /* Windows */
    if (user_home == nullptr) {
        user_home = getenv("HOME");                 /* Linux/macOS 回退 */
    }
    if (user_home == nullptr) {
        printf("[错误] 无法获取用户主目录，USERPROFILE 和 HOME 环境变量均为空\n");
        return;
    }

    BLI_snprintf(blend_filepath, sizeof(blend_filepath),
                 "%s" SEP_STR "Desktop" SEP_STR "exported_materials.blend",
                 user_home);
    /*
     * SEP_STR 是 Blender 定义的路径分隔符宏：
     *   Windows: "\\"
     *   Linux/macOS: "/"
     * 这样代码可以跨平台使用
     */

    printf("\n========================================\n");
    printf("  材质加载器 (Blender 4.0)\n");
    printf("  材质库路径: %s\n", blend_filepath);
    printf("========================================\n\n");

    /* ----------------------------------------------------------
     * 第三步：列出文件中的所有可用材质（可选，用于调试）
     * ---------------------------------------------------------- */
    list_materials_in_blend_file(blend_filepath);

    /* ----------------------------------------------------------
     * 第四步：追加指定材质
     *
     * do_append = true  → 追加模式（完整拷贝到当前文件，推荐）
     * do_append = false → 链接模式（保持外部引用）
     * ---------------------------------------------------------- */
    const char *target_material = "arcuchi_material_gold";

    Material *mat = append_material_from_blend(
        bmain,
        scene,
        view_layer,
        blend_filepath,
        target_material,
        true    /* do_append = true → 追加(Append)模式 */
    );

    if (mat == nullptr) {
        printf("[错误] 材质导入失败，终止操作\n");
        return;
    }

    /* ----------------------------------------------------------
     * 第五步：遍历所有选中的物体，应用材质
     *
     * CTX_DATA_BEGIN / CTX_DATA_END 是 Blender 的上下文遍历宏，
     * "selected_objects" 对应 Python 中的 bpy.context.selected_objects
     *
     * 宏展开后大致等价于：
     *   CollectionPointerLink *ctx_link;
     *   for (ctx_link = ...; ctx_link; ctx_link = ctx_link->next) {
     *       Object *ob = (Object *)ctx_link->ptr.data;
     *       // ...
     *   }
     * ---------------------------------------------------------- */
    int applied_count = 0;

    CTX_DATA_BEGIN (C, Object *, ob, selected_objects) {
        if (ob->type == OB_MESH) {
            if (apply_material_to_object(bmain, ob, mat)) {
                applied_count++;
            }
        }
    }
    CTX_DATA_END;

    printf("\n========================================\n");
    printf("  完成：已将材质 '%s' 应用到 %d 个物体\n",
           target_material, applied_count);
    printf("========================================\n");
}


/* ============================================================
 *  附录一：如何将此代码集成到 Blender 4.0 源码中
 * ============================================================
 *
 * 方式一：作为内部工具函数调用
 *   1. 将此文件放到 source/blender/editors/object/ 目录下
 *   2. 在该目录的 CMakeLists.txt 中添加此文件：
 *        set(SRC
 *          ...
 *          blender_material_loader.cpp   <-- 添加这一行
 *          ...
 *        )
 *   3. 创建对应的 .hh 头文件声明函数
 *   4. 在需要的地方 #include 头文件并调用 load_and_apply_material(C)
 *
 * 方式二：注册为操作符（Operator）
 *   在此文件中添加以下代码：
 */

#if 0  /* 将此改为 #if 1 以启用操作符注册代码 */

#include "WM_api.hh"           /* Blender 4.0 窗口管理 API */
#include "WM_types.hh"         /* wmOperator、wmOperatorType */
#include "ED_object.hh"        /* ED_operator_objectmode */

/**
 * 操作符执行回调函数
 * 当用户触发操作符时，Blender 会调用此函数
 */
static int material_loader_exec(bContext *C, wmOperator * /*op*/)
{
    load_and_apply_material(C);

    /*
     * 通知 Blender 数据已更改，需要刷新 UI
     * NC_MATERIAL = 材质数据类别
     * ND_SHADING_LINKS = 材质链接关系变更
     */
    WM_event_add_notifier(C, NC_MATERIAL | ND_SHADING_LINKS, nullptr);

    return OPERATOR_FINISHED;
}

/**
 * 操作符类型注册函数
 *
 * 定义操作符的元数据（名称、ID、描述等）和回调函数
 * 需要在 Blender 启动时被调用以注册操作符
 */
void OBJECT_OT_load_external_material(wmOperatorType *ot)
{
    /* 基本信息 */
    ot->name        = "Load External Material";
    ot->idname      = "OBJECT_OT_load_external_material";
    ot->description = "从外部 .blend 文件加载材质并应用到选中物体";

    /* 回调函数 */
    ot->exec = material_loader_exec;
    ot->poll = ED_operator_objectmode;   /* 仅在物体模式下可用 */

    /* 操作符标志 */
    ot->flag = OPTYPE_REGISTER | OPTYPE_UNDO;
    /*
     * OPTYPE_REGISTER = 在"信息"编辑器中显示操作记录
     * OPTYPE_UNDO     = 支持撤销（Ctrl+Z）
     */
}

/*
 * 最后，在 source/blender/editors/object/object_ops.cc 中注册：
 *
 *   // 在 object_operatortypes() 函数中添加：
 *   WM_operatortype_append(OBJECT_OT_load_external_material);
 *
 * 注册后可以通过以下方式调用：
 *   1. 在 Blender 中按 F3 搜索 "Load External Material"
 *   2. 通过 Python: bpy.ops.object.load_external_material()
 *   3. 绑定快捷键
 */

#endif /* 操作符注册代码结束 */


/* ============================================================
 *  附录二：Blender 4.0 vs 3.x API 对照表
 * ============================================================
 *
 *  功能             | Blender 3.x                        | Blender 4.0
 *  -----------------+------------------------------------+------------------------------------------
 *  头文件后缀       | .h                                  | 大部分改为 .hh（DNA 除外）
 *  链接/追加上下文   | LibraryLink_Context (BLO)           | BlendfileLinkAppendContext (BKE)
 *  开始会话         | BLO_library_link_begin()             | BKE_blendfile_link_append_context_new()
 *  添加库           | （隐含在 link_begin 中）              | BKE_blendfile_link_append_context_library_add()
 *  添加项           | BLO_library_link_named_part()        | BKE_blendfile_link_append_context_item_add()
 *  执行链接         | （隐含在 named_part 中）              | BKE_blendfile_link()
 *  执行追加         | BKE_lib_id_make_local() 手动调用     | BKE_blendfile_append()（内部自动 make_local）
 *  结束会话         | BLO_library_link_end()               | BKE_blendfile_link_append_context_free()
 *  获取导入的 ID    | BLO_library_link_named_part 返回值   | BKE_blendfile_link_append_context_item_newid_get()
 *  NULL 关键字      | NULL                                | nullptr（C++ 风格）
 *  类型转换         | (Type *)cast                        | static_cast / reinterpret_cast
 *
 * ============================================================ */
