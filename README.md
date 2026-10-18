# Sidebar Organizer · 侧边栏整理

[English](README.en.md) · [下载 ZIP](https://github.com/VeraPyuyi/codex-sidebar-organizer/releases/latest) · [使用的 skill](plugins/sidebar-organizer/skills/organize-sidebar/SKILL.md)

在支持原生侧边栏工具的 Codex 桌面会话中，一句话按来源收纳项目和聊天。适合多台电脑、ChatGPT 云端项目和大量「最近」聊天混在一起的情况。

这是一个轻量技能插件：无需服务器、API Key 或额外 MCP 服务。**“自动归档”指分类收纳；不隐藏、删除或真正归档聊天。** 每次调用执行一轮，后续新增聊天可再次整理。也支持按需启用后台定时核对；目前不能自动同步网页端的删除。

## 本地 v4 安全规划（尚未发布）

新增离线 `doctor`、`safe-plan`、`receipt` 与 `undo-plan`，详见[协议说明](plugins/sidebar-organizer/skills/organize-sidebar/references/safe-protocol.md)。默认按需创建非空目标组；已确认类别→section ID 映射可跨语言复用。支持有限版本化配置、工具预算、pending/confirmed/unknown 回执和仅针对本轮已确认且关系未变条目的撤销预览。旧 `plan`/`verify` 保留为 v3 兼容接口，仍是旧标签匹配行为，不提供 v4 ID 确认保证。

此次验收只使用合成数据与隔离临时文件：90 项 unittest、两个 ZIP 解包冒烟和逐文件 manifest 检验。未运行真实 Codex 客户端；真实分组、默认分区移回、删除同步、折叠/打开与跨设备行为仍待宿主验收。计划/回执不是授权；预算和实际调用数由可信采集方提供，完整账户历史始终未知。

## 整理效果

```text
置顶                          ← 原有项目、聊天及顺序保留
▸ 本机 · 项目
▸ ChatGPT 云端 · 项目
▸ 本机 · 聊天
▸ ChatGPT 云端 · 聊天
▸ Codex 云端 · 聊天            ← 有逐条读取证据时收纳
▸ 远程 Workstation [host-a] · 项目   ← 有真实来源证据时增加
▸ 远程 Workstation [host-a] · 聊天
▸ 来源待确认
```

上图是布局示意，不表示自动折叠已完成。项目里的聊天继续留在项目下；原有手工分组保持原样。新分组使用原生折叠控件，是否能由助手收起取决于当前客户端提供的操作能力。

| 会做 | 处理方式 |
|---|---|
| 按实际来源分类 | 当前执行主机、已确认远程主机、ChatGPT 云端分别处理，不猜创建电脑 |
| 保留重要组织关系 | 保留置顶顺序、项目归属、文件路径和现有手工分组 |
| 重复运行 | 复用同名分区，只收纳尚未分类的条目 |
| 避免重复或错误移动 | 重名分区、未知身份、不可用来源跳过并报告 |
| 预览和核对 | 支持只预览；移动后回读元数据，报告失败和未验证项 |

## 快速安装：插件版

需要支持 `codex plugin` 命令的 Codex 版本。执行：

```sh
codex plugin marketplace add VeraPyuyi/codex-sidebar-organizer --ref v0.1.3
codex plugin add sidebar-organizer@sidebar-organizer-marketplace
```

重新打开一个 **Codex 桌面端会话**，选择 `organize-sidebar` 技能或输入：

```text
使用 $organize-sidebar，按来源整理我的项目和聊天，保留置顶和项目归属。
```

如果通过插件命名空间显示技能，选择 `sidebar-organizer:organize-sidebar`；也可以直接说「用 Sidebar Organizer 整理侧边栏」。CLI 用于安装，实际整理须在提供桌面侧边栏工具的会话里进行。没有这些工具时，插件会明确停止，不会尝试修改客户端内部文件。

如果 CLI 没有 `plugin add`，可先添加上述 marketplace，再在桌面插件目录选择 **Sidebar Organizer** 安装；或者使用下面的独立 skill。市场条目需要重新打开应用才能出现时，请先保存进行中的工作。

### 从旧版升级

如果此前按 旧版本标签 安装，先替换此插件的市场来源，再重新安装。直接添加新版本可能提示来源不同；以下流程已在本机验证，不会更改聊天和分组：

```sh
codex plugin marketplace remove sidebar-organizer-marketplace
codex plugin marketplace add VeraPyuyi/codex-sidebar-organizer --ref v0.1.3
codex plugin add sidebar-organizer@sidebar-organizer-marketplace
```

安装完成后，新建桌面会话以加载更新后的技能。独立 skill 用户按下方步骤备份并替换技能文件夹。

## ZIP 安装：独立 skill

1. 在 [Releases](https://github.com/VeraPyuyi/codex-sidebar-organizer/releases/latest) 下载 `organize-sidebar-skill-0.1.3.zip` 并解压。
2. 将其中完整的 `organize-sidebar` 文件夹复制到技能目录。Windows 默认是 `%USERPROFILE%\.codex\skills\`，macOS/Linux 默认是 `~/.codex/skills/`；自定义了 Codex 主目录时用对应目录。已有同名技能时先备份再替换。
3. 新建桌面会话，选择该技能并发出整理指令。

`sidebar-organizer-plugin-0.1.3.zip` 是标准插件目录包，供支持插件 ZIP 导入的客户端或自行维护 marketplace 的用户使用。不要把插件包当成独立技能文件夹复制。无需同时安装两个版本，避免出现两个同名技能。

## 常用说法

```text
使用 $organize-sidebar，先预览分类方案，不要移动。
使用 $organize-sidebar，把未分类的项目和聊天按来源整理。
使用 $organize-sidebar，再整理一下新增聊天，保留已有分组。
使用 $organize-sidebar，检查侧边栏里是否有待核对的聊天引用。
使用 $organize-sidebar，每小时在后台核对一次侧边栏，有新异常再提醒我。
```

首次整理会说明预计移动数量、未知来源和近期列表覆盖范围，随后执行已经请求的操作。默认将聊天设为最近更新时间排序；这是客户端共享的侧边栏偏好，置顶排序和分组显示模式保持原样。

## 0.1.3：刷新核对与后台检查

可主动重新读取侧边栏，或者明确要求后通过 Codex 原生自动化每小时核对一次。重复设置会查找并复用已有任务；安装插件本身不会开启后台任务。检查只读取元数据，不建立分组、不移动或删除聊天。无变化保持安静，有新的待核对引用或来源异常时才提醒。

**这还不能实现“网页端删除后，桌面残留自动消失”。** 当前原生工具没有提供强制刷新缓存、权威删除状态或独立清理残留引用的操作。最近列表最多 50 条；某条聊天不在列表里，也可能只是较旧、已归档或暂时未加载，不能据此删除。`refresh-check` 只报告这些不确定项，所有无法确认的记录保持原样；也不会修改客户端内部文件来绕过限制。

后台检查依赖宿主自动化运行环境，不承诺实时同步或固定的删除同步延迟。参见 [刷新机制与边界](plugins/sidebar-organizer/skills/organize-sidebar/references/refresh.md)。

## 0.1.2：识别 Codex 云端记录

新版把 Codex 云端执行记录与 ChatGPT 云端聊天分开收纳。遇到 `durable` 记录时，先逐条通过原生工具读取身份，再核对唯一的侧边栏位置；两处证据一致才归类。侧边栏内部的 `local` 前缀不会被当成创建电脑的证据。已有分组会复用，无法确认的记录保持原样。

前后快照和每次重跑都重新取证，避免沿用过期结果。完整历史、界面折叠和创建设备仍按各自的证据范围报告。

两轮本机实测均确认 20 条 Codex 云端记录，新增分组 0、移动 0、排除项 0、核对错误 0；6 个现有分组、23 个项目和 6 条置顶保持不变。49 项自动测试通过，完整范围见 [验证记录](docs/VALIDATION.md)。

## 0.1.1：修复临时聊天 ID 的核对问题

部分客户端会在分组里显示 `client-new-thread:` 临时 ID，却在最近列表里保留正式 ID。0.1.1 增加只读交叉核对：加载本机 Codex 状态文件，仅提取严格匹配的分组元数据，确认正式聊天已归类后不再重复移动。它不根据标题猜对应关系，也不会写回状态文件。这个兼容适配依赖已验证的本地状态格式；格式缺失或证据冲突时会保留未验证状态并停止相关移动。

0.1.1 的 Windows 实测独立运行两轮，每轮都正确识别已归类聊天，新增分组 0、移动 0、核对错误 0。原有 5 个分组、23 个项目和 6 条置顶保持不变。当时排除的 20 条后台记录现已通过 0.1.2 的独立云端身份核对。

## 能力边界

- **支持范围：** 提供原生分组工具的 Codex 桌面会话。安装本插件不会为独立 CLI、ChatGPT 网页或不支持的旧版本新增侧边栏接口。
- **历史覆盖：** 已验证的列表工具最多返回 50 条非置顶聊天，没有历史分页。技能会检查是否还有获准的历史读取方式；无法读取的更早聊天明确列为未覆盖，总量未知。项目数量、聊天数量均动态读取，不硬编码作者的账户规模。
- **来源含义：** 云端记录不代表由某台电脑或网页创建。本机标签指当前执行主机。无法可靠路由的后台记录会跳过，避免生成不可见的“空分类”。
- **折叠和打开：** 元数据核对不能证明 UI 可见或可打开。没有支持的界面能力时，会提示手动点击标题收起，不声称已完成自动折叠。
- **同步与定时：** 仅在明确要求后创建或更新后台核对任务。不支持自动删除同步，不承诺其他电脑或网页版同步。
- **结果：** 助手会报告已移动、保留、跳过和未验证数量。操作失败或期间状态改变时重新读取，避免盲目重试。

## 隐私与实现

插件没有网络客户端、遥测、凭据或远程执行服务，只使用宿主已有的桌面工具。助手可能在本机临时目录保存 ID、路径和分组信息以供核对；这些属于私人记录，不应提交到 GitHub。原生身份读取工具可能同时返回消息内容，整理流程只提取身份字段，不使用或保存正文。宿主 Codex/ChatGPT 的服务和数据处理方式仍由宿主决定。

存在临时 ID 时，可选辅助程序还会只读加载当前 Codex 主目录中的 `.codex-global-state.json`，从中提取匹配的分组记录作为证据。不会导出该文件的其他设置，不会搜集其他账户或历史备份。

可选的 Python 3.10+ 辅助程序只生成分类方案、核对前后元数据，不操作应用。没有 Python 时，助手可按技能规则直接使用原生工具。公开测试和示例全部使用虚构数据。

需要介绍本项目时，可使用这份 [项目简介](docs/INTRODUCTION.zh-CN.md)。

## 开发与验证

```sh
python -m unittest discover -s tests -v
python scripts/build_release.py
```

构建会校验包结构、仅收录明确允许的文件、生成插件和技能 ZIP 及 `SHA256SUMS.txt`，并重新解压运行辅助程序。GitHub Actions 在 Windows 与 Linux 上验证合成场景。新客户端的完整 UI 操作仍需实际验收；测试通过不代表所有客户端都提供所需工具。

参见 [测试范围](docs/VALIDATION.md) 和 [原生工具约定](plugins/sidebar-organizer/skills/organize-sidebar/references/native-tools.md)。插件格式和分发方式依据 [OpenAI 插件文档](https://developers.openai.com/plugins/build/plugins)；技能格式参见 [官方技能文档](https://developers.openai.com/plugins/build/skills)。本项目为社区项目，与 OpenAI 没有隶属关系。

MIT License · [提交问题](https://github.com/VeraPyuyi/codex-sidebar-organizer/issues)（请勿附带真实聊天内容、原始快照或凭据）。
