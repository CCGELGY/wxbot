# wxbot · 微信群 AI 机器人

通过微信本地数据库增量读取群消息，调用 DeepSeek API 生成回复，使用本机 Hook HTTP 服务后台发送文字与图片。支持角色卡、选择性接话、分条回复、SQLite 长期记忆、本地表情和联网找图。

本仓库是当前运行版本的脱敏导出：保留角色卡与功能实现，使用虚构测试成员；真实群号、成员标识、特殊成员名单、API Key、聊天与记忆数据均未包含。运行中的私人实例不受此目录影响。

## 1. 环境要求

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows x64；已验证环境为 Windows 11 桌面会话 |
| Python | 已验证 Python 3.10 x64，需包含 `py` 启动器和 pip |
| 微信 | **4.1.10.27 x64**；其他版本不能直接沿用此 Hook |
| 登录状态 | 微信已登录，机器人账号已加入目标群，本地数据库可读 |
| API | 自行配置有效的 DeepSeek API Key；示例使用 `deepseek-flash`，以账户实际可用模型为准 |
| 网络 | 可访问 API；联网搜索和找图还需要相关外部网站可达 |
| 内存 | 建议至少 4 GB，是部署建议，未进行 2 GB 服务器压力测试 |

微信窗口可以收起，微信进程必须保持运行。锁屏、注销、无桌面 Windows 服务和不同服务器环境未做完整验收，不保证可用。无需 DSH、Node.js 或本地大模型。

## 2. 依赖声明

直接依赖锁定于 [requirements.txt](requirements.txt)：

```text
wechatauto-replica==1.2.7.0
requests==2.34.2
```

`wechatauto-replica` 提供微信数据库访问；它还会安装 Windows、图像、解密及 GUI 相关的传递依赖。`requests` 用于 API 和本地 HTTP 调用；图片处理使用传递依赖 Pillow，SQLite、FTS5、unittest 等来自 Python 标准库。

Hook 是独立的第三方本机组件，**仓库不包含 DLL、微信安装包或下载的网络表情**。来源、许可证和功能边界见 [依赖声明](docs/DEPENDENCIES.md)；安装前先看 [Hook 准备说明](docs/HOOK_SETUP.md)。

## 3. 快速使用

以下命令在项目目录内的 PowerShell 执行。不要在已有私人运行目录覆盖配置。

### 安装 Python 依赖

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
Copy-Item .\config.example.json .\config.json
```

### 准备 Hook 并登录微信

按 [Hook 准备说明](docs/HOOK_SETUP.md) 配置 **4.1.10.27 x64** 和仅绑定 `::1` 的 DLL，然后手动启动微信、完成登录。不要同时启动多个微信主实例。

### 保存 API Key

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\set-api-key.ps1
```

脚本隐藏输入，将 Key 保存到当前用户环境变量，不写进仓库。重新打开 PowerShell 后进入项目目录，测试 API：

```powershell
.\.venv\Scripts\python.exe .\api_bridge.py --test-api
```

### 查询并配置群

```powershell
.\.venv\Scripts\python.exe .\api_bridge.py --list
```

找到目标群的 `数字@chatroom`，修改本机 `config.json`：

```json
"groups": [
  {
    "name": "替换为实际群ID@chatroom",
    "aliases": ["小鲸鱼", "小助手"],
    "trigger": "mention_or_name"
  }
]
```

`aliases` 是机器人的称呼。全局名字触发还受 `bot.bot_aliases`、`bot.name_aliases` 控制。监控多个群就在数组中增加条目，修改配置后重启生效。

示例已清空特定成员调侃与保护名单；只有自行设置 `banter_target_ids` / `banter_target_names` / `banter_names` 等字段才适用对应特殊规则。普通角色的轻怼、拒绝和嘴硬仍然保留。

### 验证发送

以下命令**会向自己的文件传输助手发送一条测试消息**：

```powershell
.\.venv\Scripts\python.exe .\api_bridge.py --send-test filehelper
```

看到 `is_success=True`、`verified=True` 后再启动机器人。HTTP 返回成功本身不能证明发送成功，确认超时不会自动重发。

### 启动

前台启动，便于查看错误：

```powershell
.\start-bot.bat
```

后台隐藏运行：双击 `start-bot-hidden.vbs`。日志在 `logs/bot-stderr.log`、`logs/bot-stdout.log`，启动时只处理新消息，不补读旧群聊。可在群里 `@小鲸鱼` 测试实际对话；自主接话是选择性的，不保证每条消息回复。

前台窗口中按 Ctrl+C 停止；隐藏运行需在任务管理器确认本项目的 `api_bridge.py` Python 进程后结束，避免误停其他 Python 程序。不要同时运行私人实例与此导出副本监听同一群，以免重复回复。

## 配置与数据

| 文件 / 配置 | 作用 |
|---|---|
| `config.example.json` | 可提交的脱敏配置模板 |
| `config.json` | 本机配置，被 Git 忽略 |
| `system_prompt.txt` | 基于 qq-bridge 的小鲸鱼角色卡，保留第一至十节 |
| `wechat_simulation.txt` | 接话、潜水、分条、记忆、工具与表情规则 |
| `knowledge.sqlite3` | 本机长期记忆，按群与成员隔离，不上传 |
| `stickers/` | 本次对话中生成的 12 张本地示例表情及映射 |
| `stickers/network/` | 下载后的网络表情缓存，不上传 |
| `bot.stickers.image_proxy_url` | 可选媒体代理，默认空；只用于网络媒体请求 |

API 和 Hook 调用不继承系统代理。表情约每 2～3 次回复获得选图机会，仍受语境、10 秒冷却和每小时上限约束。第三方起外号先待确认，本人确认或足够独立来源支持后才采用；默认需要 3 个独立来源。

群内容会按对话与记忆提取需要发送给所配置的模型服务；联网找图还可能把候选图交给该服务审核。本地记录是敏感运行数据，勿提交到 Git。自行编辑 SQLite 时应先停止机器人并备份；全文检索索引与正文需要保持一致。

## 本地测试

不需要真实 API Key，也不会发送微信消息：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -p "test_*.py" -q
.\.venv\Scripts\python.exe .\selftest_local.py
```

测试使用虚构成员、临时数据库、模拟 API / 发送器；不访问私人实例目录。实际微信发送还需单独按上文验证。

## 故障排查

- **有生成回复但群里没显示**：查看是否出现 `database confirmation timed out`；先检查 Hook 发送，不要仅调整触发词。
- **端口被旧微信占用**：`Get-NetTCPConnection -LocalPort 30001 -State Listen` 查看所属 PID，结合任务管理器识别残留实例。正常退出多余微信后检查端口是否归当前登录实例；不要无差别结束全部进程。
- **Hook 健康接口 `IsLogin=0`**：此上游字段未可靠维护，不能单独判断离线；仍需检查模块、账号数据库及实际发送。
- **收不到新群消息**：检查群 ID、登录账号及监听就绪日志；启动前的消息会跳过。
- **发送慢**：区分模型耗时、分条等待 2～5 秒、排队、Hook 发送和 8 秒确认超时；搜索图片在后台进行。

本项目未开放群图片读取、语音条、拍一拍和合并转发等能力。网络表情的权利归原作者，收藏成功不表示允许再分发。

## 来源与许可

项目代码使用 MIT 许可；角色卡与 qq-chat-v2 行为参考来自 [Derpyu520/qq-bridge](https://github.com/Derpyu520/qq-bridge)，保留其 [完整许可和附加说明](QQ_BRIDGE_LICENSE.txt)。第三方依赖分别适用其自己的许可，详见 [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md)。本项目与微信、腾讯或 DeepSeek 官方无隶属关系。
