# 依赖与来源声明

## 直接 Python 依赖

| 组件 | 当前锁定版本 | 用途 | 许可声明来源 |
|---|---|---|---|
| [wechatauto-replica](https://github.com/fanyuantaier/wechatauto-replica) | 1.2.7.0 | 微信本地数据库、消息与成员读取 | 安装包声明 Apache-2.0，见仓库根目录 WECHATAUTO_LICENSE.txt |
| [requests](https://requests.readthedocs.io/) | 2.34.2 | API、网页和 Hook HTTP 请求 | Apache-2.0，许可随安装包提供 |

使用 pip 安装对应版本即可，仓库不附虚拟环境、wheel 或这些依赖的源码。

## 传递依赖

`wechatauto-replica==1.2.7.0` 的安装包声明依赖：`uiautomation`、`pywin32`、`pyperclip`、`Pillow`、`psutil`、`colorama`、`cryptography`、`winsdk`、`imageio-ffmpeg`、`zstandard`、`pyautogui`、`opencv-python`。本项目的图片处理直接使用其中的 Pillow。

`requests` 会安装 `certifi`、`charset-normalizer`、`idna`、`urllib3` 等依赖。具体解析版本由平台和 pip 决定，只有两个直接依赖在 requirements.txt 中锁定；不宣称整个传递依赖树可逐位复现。各组件适用其安装包自带许可，不统一改为本项目 MIT 许可。

SQLite、FTS5、JSON、线程、unittest 等使用 Python 标准库。若换用自编译 Python，需确认 SQLite 启用了 FTS5。

## 角色卡与行为参考

来源：[Derpyu520/qq-bridge](https://github.com/Derpyu520/qq-bridge)，参考版本 `a56164e70a0521a7829138a42eee76066fde2b8b`。

`system_prompt.txt` 基于原版小鲸鱼角色卡；`wechat_simulation.txt` 参考 qq-chat / qq-chat-v2 的行为原则，针对本项目 API、微信和 SQLite 能力适配。保留完整 `QQ_BRIDGE_LICENSE.txt`，其中包含 MIT 原文和上游第三方说明。参考不代表本项目依赖 DSH、SnowLuma 或 QQ OneBot。

## Hook、微信和 API

Hook 来自 [aixed/WeChat-Hook](https://github.com/aixed/WeChat-Hook)，使用已核对的 `v411027_` 发布构件。查看的本地源码副本未附独立 LICENSE，仓库**不重新分发其 DLL 或源码**。`prepare_hook.py` 是本项目提供的本机回环地址准备工具，仅处理使用者自行取得的指定 SHA256 文件。

微信客户端与 DeepSeek API 分别遵循提供方的条款；本仓库不包含客户端安装包、API 凭据或微信账号数据。

## 表情图片

`stickers/*_opt.png` 为 12 张 AI 生成的本地示例图，配有关键词映射与语义描述；图片不是软件源码，不以 MIT 许可授予第三方商标或角色相关权利。网络下载的表情不随仓库分发，原作者的许可需单独核对。
