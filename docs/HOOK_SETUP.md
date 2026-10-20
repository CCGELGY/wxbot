# Hook 准备与后台发送

适配来源：[aixed/WeChat-Hook](https://github.com/aixed/WeChat-Hook)，Release `v411027_`，对应微信 **4.1.10.27 x64**。

本仓库不分发第三方 DLL；本地查看的上游副本未附独立 LICENSE，因此不把它当作已获 MIT 授权的部分。请自行从上游获取并阅读其最新说明和授权条件。

## 准备流程

1. 准备对应版本微信，正常退出全部微信主实例，包括后台残留实例。
2. 自行取得上游 `version.dll`，不要直接运行绑定全部网卡的原版。
3. 在项目目录执行下方命令，生成**新文件**，不会安装、加载或覆盖已有 DLL：

```powershell
.\.venv\Scripts\python.exe .\prepare_hook.py .\hook\version.upstream.dll .\hook\version.dll
```

脚本只接受已核对的原版 SHA256：

```text
23948e7d933ff40735ddc0cc516641fd9f935d67ffdec476bb8db61b79940f29
```

唯一修改是将一处等长 `0.0.0.0\0` 替换为 `::1\0\0\0\0\0`，将监听限制在 IPv6 本机回环；结果 SHA256 必须是：

```text
2c4fbc95babcf5324f54d947c2b1cc78168ead6183d4071696f665b3d1c25942
```

4. 备份微信主程序目录里已有的同名文件（如有），按上游部署方式将生成的 `version.dll` 放到 **Weixin.exe 所在目录**，不是 Python 项目目录。此步骤自行操作，不要覆盖 Windows 系统目录文件。
5. 启动一个微信主实例并完成登录，再检查：

```powershell
Get-NetTCPConnection -LocalPort 30001 -State Listen
```

应仅监听 `::1:30001`，所属进程应为当前使用的微信实例。配置中的地址保持 `http://[::1]:30001`。若仅出现 `0.0.0.0`，先退出微信并检查 DLL，勿将未鉴权接口暴露到局域网。

6. 运行 README 中的 `--send-test filehelper`。只有 `verified=True` 才通过本地发送确认；不等于对端收到或已读回执。

## 运行限制

- 微信更新后必须重新核对 Hook 兼容性，不要套用旧 DLL。
- 窗口可以隐藏，微信进程必须存在；未验收锁屏、注销、Session 0 服务等场景。
- 上游 HTTP 成功返回不能证明发送完成。机器人额外回读本地数据库确认，失败不自动重发，避免重复消息。
- 发送器串行化调用并限制目标为配置的群。`--send-test` 是显式测试入口，允许用户指定测试目标。
- 移除组件时先退出微信，移走自行部署的 DLL，再恢复原有文件（如有）。
