# 本地测试

测试覆盖触发判断、消息合并、分条、记忆隔离与确认、表情选择、发送确认、群图片上下文与像素传入、账号对齐与绑定保护及 Hook 准备工具。使用标准库 unittest，不需要 pytest。

安装依赖后在项目目录执行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -p "test_*.py" -q
.\.venv\Scripts\python.exe .\selftest_local.py
```

测试使用模拟 API、发送器和临时数据库，不调用真实微信发送。部分自检会在项目目录生成运行数据，已由 .gitignore 排除。

单元测试通过只能证明所覆盖的逻辑在测试条件下通过，不能证明真实微信兼容、消息一定送达、模型回复总是正确，也不能证明账号不会受限或封禁。

真实部署按 [使用文档](USAGE.md) 分别验证 API 和文件传输助手发送；两项测试均可能有外部效果，其中 API 测试会调用服务，发送测试会产生一条实际微信消息。
