# wxbot · 微信群 AI 机器人

通过微信本地数据库增量读取群消息，调用 DeepSeek API 生成回复，使用本机 Hook HTTP 服务后台发送文字与图片。支持角色卡、选择性接话、分条回复、SQLite 长期记忆、本地表情和联网找图。

## 使用边界与封号风险

**本项目使用非官方 Hook 和客户端自动化，存在账号被限制功能、限制登录或封禁的风险。开源、低频发送、隐藏窗口和模拟群友聊天都不代表平台许可，也不能保证账号安全。**

- 本项目与腾讯、微信和 DeepSeek 官方无隶属关系，不提供“防封”“零风险”或账号恢复承诺；风险无法用固定发送频率消除。
- 使用前请阅读微信现行协议和账号规范，确认使用方式获得所需授权。无法接受账号、数据或服务中断风险时，请勿部署，尤其不要使用承载重要业务或关系的账号。
- 仅在本人有权使用的账号和已获授权的群内使用；向群成员说明机器人及模型服务的数据处理方式。不得用于群发广告、刷屏、骚扰、欺诈、未经授权的数据采集或绕过平台限制。
- 群聊上下文、成员信息和相关记忆可能发送到配置的模型服务；日志、记忆库和 API Key 由部署者自行保护。模型可能误判对话对象、记错信息或生成不当内容，需要有人能及时停止机器人。
- 微信更新、第三方组件失效、账号风控、网络故障都可能导致中断或丢失发送确认。API 调用与联网处理可能产生费用。

详细说明见 [使用边界与风险声明](docs/RISKS.md)。此声明不替代平台规则、第三方许可或应承担的义务。

## 文档导航

- [快速使用](#3-快速使用)：安装、配置群聊、验证发送和启动。
- [使用文档](docs/USAGE.md)：配置说明、后台运行、记忆、表情、停止与更新。
- [故障排查](docs/TROUBLESHOOTING.md)：按接收、触发、模型、发送四个环节定位。
- [Hook 准备说明](docs/HOOK_SETUP.md) · [依赖与来源声明](docs/DEPENDENCIES.md) · [本地测试](docs/TESTING.md)。

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

先获取项目，再在项目目录内的 PowerShell 执行以下命令。已有部署升级前先备份配置与数据。

```powershell
git clone https://github.com/CCGELGY/wxbot.git
Set-Location .\wxbot
```

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

特定成员调侃与保护名单默认不启用，需要时自行配置。角色的普通轻怼、拒绝和嘴硬不依赖这些名单。完整字段说明见 [使用文档](docs/USAGE.md)。

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

前台窗口中按 Ctrl+C 停止；隐藏运行需在任务管理器确认本项目的 `api_bridge.py` Python 进程后结束，避免误停其他 Python 程序。不要让多个部署同时监听同一群，以免重复回复。

## 配置与数据

| 文件 / 配置 | 作用 |
|---|---|
| `config.example.json` | 配置模板，首次部署时复制为 config.json |
| `config.json` | 本机配置，被 Git 忽略 |
| `system_prompt.txt` | 基于 qq-bridge 的小鲸鱼角色卡，保留第一至十节 |
| `wechat_simulation.txt` | 接话、潜水、分条、记忆、工具与表情规则 |
| `knowledge.sqlite3` | 本机长期记忆，按群与成员隔离，不上传 |
| `stickers/` | 12 张本地示例表情及关键词映射 |
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

测试使用临时数据库和模拟 API / 发送器。实际微信发送还需单独按上文验证；测试通过不代表账号没有风控或封禁风险。

## 故障排查

先查看 `logs/bot-stderr.log`。有收到消息但没有触发记录，检查群和触发条件；有模型回复但出现 `database confirmation timed out`，检查 Hook 发送链路。不要通过反复重发来排查，也不要直接关闭发送确认。

完整的检查命令、判断表和处理步骤见 [故障排查](docs/TROUBLESHOOTING.md)。

本项目未开放群图片读取、语音条、拍一拍和合并转发等能力。网络表情的权利归原作者，收藏成功不表示允许再分发。

## 来源与许可

项目代码使用 MIT 许可；角色卡与 qq-chat-v2 行为参考来自 [Derpyu520/qq-bridge](https://github.com/Derpyu520/qq-bridge)，保留其 [完整许可和附加说明](QQ_BRIDGE_LICENSE.txt)。第三方依赖分别适用其自己的许可，详见 [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md)。本项目与微信、腾讯或 DeepSeek 官方无隶属关系。
