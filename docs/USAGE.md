# 使用文档

部署前先阅读 [使用边界与风险声明](RISKS.md)。本项目需要已登录的微信桌面客户端，不能只把 Python 脚本放到无微信环境的服务器上运行。

## 首次部署顺序

1. 安装 Python 3.10 x64 和微信 4.1.10.27 x64。
2. 获取仓库，在项目目录运行 `install.ps1` 安装依赖，复制 `config.example.json` 为 `config.json`。
3. 按 [Hook 准备说明](HOOK_SETUP.md) 部署组件，手动启动并登录微信。
4. 运行 `set-api-key.ps1`，在隐藏输入中粘贴 API Key，重新打开终端后验证 API。
5. 用 `--list` 查询目标群 ID，修改 `config.json`。
6. 用 `--send-test filehelper` 验证发送，再启动机器人。

完整安装命令见 [README 快速使用](../README.md#3-快速使用)。不要在同一个配置上重复启动；不同目录的副本也不要同时监听同一个群。

## 群聊与称呼

```powershell
.\.venv\Scripts\python.exe .\api_bridge.py --list
```

会话列表按群名显示对应 `username`，将目标群的 `数字@chatroom` 填入 `groups[].name`。群名可能重复或变化，优先使用 ID。该命令只查询会话列表，不启动回复。

```json
"groups": [
  {
    "name": "替换为实际群ID@chatroom",
    "aliases": ["小鲸鱼", "小助手"],
    "trigger": "mention_or_name"
  }
]
```

添加多个对象可监听多个群。`aliases` 配置群内机器人称呼；若要更换称呼，同时检查 `bot.bot_aliases` 和 `bot.name_aliases`。JSON 不支持注释和末尾多余逗号，修改后需要重启。

### 常用配置

| 字段 | 含义 |
|---|---|
| `api.base_url` / `api.model` | API 地址与模型名，需要账户实际支持 |
| `api.api_key_env` | 保存 API Key 的环境变量名，默认 DEEPSEEK_API_KEY |
| `api.web_enabled` | 是否向模型开放网页工具 |
| `bot.fresh_start` | 默认 true，跳过启动前的聊天，不恢复上次短期对话 |
| `bot.proactive.enabled` | 是否开启主动评估、插话和冷场话题 |
| `bot.proactive.active_hours` | 主动参与的时段，使用运行主机本地时间 |
| `bot.proactive.casual_probability` | 普通闲聊进入主动评估的概率，不是每条必回概率 |
| `bot.multi_delay` | 多段回复之间的等待秒数，默认 2～5 秒 |
| `bot.verify_send` | 本地数据库发送确认，建议保持 true |
| `bot.transport.base_url` | Hook 本机地址，默认 http://[::1]:30001 |
| `bot.memory.enabled` / `structured` | 长期记忆开关与结构化记忆模式 |
| `bot.stickers.enabled` | 图片回复开关 |
| `bot.stickers.network_enabled` | 是否启用后台找图 |

特殊成员规则默认未配置。需要时可设置 `banter_target_ids`、`banter_target_names`、`banter_names`；仅明确 @ 机器人且满足调侃条件时允许针对目标轻度调侃。`roast_exclude_ids` / `roast_exclude` 是保护名单，推荐用稳定成员 ID。不要直接把他人的身份或个人信息写进公开配置。

## 角色与接话

`system_prompt.txt` 决定角色、语气与表达习惯，`wechat_simulation.txt` 决定接话、等待、潜水、分条及工具使用规则。修改后重启加载。

机器人会综合明确 @、名字、引用对象、上下文和公开提问判断是否回复。没有此前会话也能提问，群友之间的对话通常应让开。主动参与是选择性的，简单的“？”、短句或不回复可能是正常行为；是否误判应结合日志检查。

首次验证先使用微信真正的 @ 操作发送“@小鲸鱼 你好”，不要只凭冷场插话判断程序是否运行。还可先用 `--dry-run` 查看收取与生成情况而不发送；它仍可能调用付费 API、处理记忆和产生本地日志，不是完全无副作用的离线测试。

## 长期记忆

默认数据库为项目目录下的 `knowledge.sqlite3`，按群 ID 和成员 ID 隔离。

- 本人明确自我介绍可以直接记录。
- 第三方提供的昵称、偏好或个人信息先待确认，默认需要 3 个独立来源，或符合本人 / 受信写入者确认条件；同一个人重复说不会累加成多个来源。
- 本人否认的别名优先处理，其他成员不能靠重复宣称覆盖。
- 记忆是参考资料，不能更改核心角色或给予操作权限；程序不保证每次提取与检索都正确。

`fresh_start=true` 不会清空已确认的长期记忆。修改监听群也不会把旧群记忆混到新群。旧 `member_memory.json` 只用于一次性迁移，后续修改它不会自动更新 SQLite。

需要查看或更正记忆时，先停止机器人并备份数据库及同名 `-wal` / `-shm` 文件（如存在）；可用 SQLite 工具查看。不要只改 `memory` 表而不更新全文检索索引。清空记忆前确认影响范围，不要删除微信自己的数据库。

## 表情包

本地图在 `stickers/`，关键词映射在 `stickers/mapping.json`；当前语义图库还由 `sticker_choices.py` 的 `PACK` 定义 ID 和描述。新增图片若要参与模型选图，需要同步配置语义 ID / 描述，仅改映射不一定会进入语义图库。

默认每 2～3 次有效回复获得一次后台选图机会，10 秒冷却，每小时最多 60 张；没有合适图片时可以不发。网络找图会搜索、下载、审核并缓存到 `stickers/network/`，受额外的搜索预算与超时限制，文字不必等待图片。

`bot.stickers.image_proxy_url` 可设置媒体代理；默认空。API 与本机 Hook 不继承系统代理，调整这个字段不会改变模型 API 的连接方式。不要把带账号密码的代理地址提交到 Git。

## 启动、停止与更新

```powershell
# 前台，便于观察启动错误
.\start-bot.bat

# 也可以在终端直接启动，需已配置当前终端的 API Key
.\.venv\Scripts\python.exe .\api_bridge.py
```

双击 `start-bot-hidden.vbs` 可隐藏运行启动窗口。微信窗口可以收起，但客户端和登录会话必须保持；锁屏、注销、远程桌面断开及无桌面服务场景不能等同于窗口隐藏，未保证支持。

前台按 Ctrl+C 停止。后台停止时在任务管理器的“详细信息”中显示“命令行”列，识别指向本项目的 `api_bridge.py` 进程；虚拟环境可能有父子两个 Python 进程。不要结束所有 Python 进程。

更新前停止机器人，备份 `config.json`、自定义提示词、表情和记忆库。执行 `git pull` 并重新安装 requirements；配置模板有变化时手动合并字段，勿直接覆盖本机配置。不要跟随项目更新自动升级微信，先确认 Hook 对应版本。

## 日志与求助

前台 / 后台启动脚本分别重定向输出到 `logs/bot-stdout.log` 和 `logs/bot-stderr.log`，程序还会产生 `logs/api_bridge.log`。关注当前启动时间之后的日志。

提 Issue 前按 [故障排查](TROUBLESHOOTING.md) 检查，只提供必要错误片段、环境版本、复现步骤和预期行为；去掉成员标识、群名、聊天正文、密钥与本机用户路径。
