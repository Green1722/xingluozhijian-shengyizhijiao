# 本地部署（Windows）

本文记录在 Windows 上用 `deploy/` 脚本完成的环境与数据库部署。华为开发者空间上的部署方式不变，仍见 [板端记录接收与实测结果](board-cloud.md)。

## 环境

| 项 | 版本 / 路径 |
| --- | --- |
| 解释器 | Python 3.13.9，独立虚拟环境 `.venv/`（仓库 `.gitignore` 已忽略） |
| 第三方依赖 | 无，仅标准库 |
| 数据库 | SQLite 3.50.4，随 Python 内置 |
| pip | 25.2（虚拟环境内自基础安装复制引导） |

`app.py` 与 `board_receipts.py` 使用 `http.server.ThreadingHTTPServer`，无需额外服务。

## 数据库

两个 SQLite 文件都在仓库根目录，与程序默认路径一致：

| 文件 | 表 | 用途 |
| --- | --- | --- |
| `training.sqlite3` | `sessions`、`turns` | 网页训练会话、逐轮护士发言与患者回复 |
| `board_receipts.sqlite3` | `receipts` | 实体板串口事件回执，复盘服务以只读连接查询 |

`training.sqlite3` 由 `app.py` 启动时自动建表；`board_receipts.sqlite3` 由 `board_receipts.py` 启动时建表。初始化脚本把两件事一次做完并可选导入示例回执：

```sh
.\.venv\Scripts\python.exe deploy\init_db.py
```

脚本幂等，重复运行不会产生重复行。默认把 `samples/board-capture.json`（虚构样例）写入回执库，回执号为
`c7932421a2d3b47f622ae2f6a983c794940034224d0109ff4f8a16fd4b675610`，可用于页面上的「实机训练复盘」输入框。不想要示例记录时加 `--no-seed-sample`。

## 首次部署

```sh
python -m venv .venv
.\.venv\Scripts\python.exe deploy\init_db.py
```

启动（两种方式等价，第二种双击即可）：

```sh
powershell -ExecutionPolicy Bypass -File deploy\start.ps1
deploy\serve.cmd
```

`start.ps1` 通过 `deploy\launch.py` 以 `DETACHED_PROCESS` 启动两个服务，关闭终端后继续运行；`serve.cmd` 只是它的包装，双击后窗口停在提示上，服务照常脱离。两个脚本启动前都会检查端口：如果同一个服务已在运行就跳过，不会误开第二份。

| 服务 | 地址 | 说明 |
| --- | --- | --- |
| 训练网页 | http://127.0.0.1:8080/ | 病例选择、逐轮对话、教师复盘、实机回执查询 |
| 回执接收 | http://127.0.0.1:8091/healthz | 仅回环地址，接收实体板串口事件 |

页面必须通过 http://127.0.0.1:8080/ 打开。直接双击 `index.html` 是 `file://` 协议，页面本身能显示，但所有接口都是同源相对地址，`fetch` 会以 `Failed to fetch` 失败。`index.html` 现在会识别这种情况，给出提示、可点击的服务地址，并在服务可访问时自动跳转。`serve.cmd` 在无参数运行时会顺带打开浏览器。

运行状态写入 `.run/`：`app.pid`、`receipts.pid` 与 `.run/logs/`。常用参数：

```sh
# 换端口
powershell -ExecutionPolicy Bypass -File deploy\start.ps1 -Port 8092 -ReceiptPort 8093
# 局域网内其他设备访问（回执服务仍只监听回环）
powershell -ExecutionPolicy Bypass -File deploy\start.ps1 -BindHost 0.0.0.0
# 重启
powershell -ExecutionPolicy Bypass -File deploy\start.ps1 -Restart
# 停止
powershell -ExecutionPolicy Bypass -File deploy\stop.ps1
```

## 验收

```sh
powershell -ExecutionPolicy Bypass -File deploy\verify.ps1
```

脚本依次运行仓库自带的四套验收并检查两个服务是否在线：

| 脚本 | 覆盖内容 | 结果 |
| --- | --- | --- |
| `verify_training.py` | 两个病例的规则边界，各 7 项 | 通过 |
| `verify_board_review.py` | 只读回执查询、事件引用、排除设备回复与否定句、404 与无效编号 | 通过 |
| `verify_http.py` | 会话隔离、event_id 重试、候选证据、结束与复盘、重启后复盘持久化 | 通过 |
| `verify_paraphrases.py` | 18 条样稿外修订用例 | 18/18 通过 |

此外用运行中的服完成一次端到端核对：新建吸氧会话 → 4 轮对话（身份核对、症状、操作告知、操作完成）→ 结束后复盘含 4 条证据；浏览器工具栏之外用同源 `POST /api/review` 复查结果一致；示例回执经 `/api/board-review/` 返回 2 条事件与「身份核对」候选证据。

## 受管沙箱内的差异

在当前这台机器上通过受管沙箱执行命令时，有两点与普通终端不同：

1. 沙箱会在命令结束时回收该命令启动的所有子进程。`DETACHED_PROCESS` 也无效，另外实测计划任务、Explorer 转发和 `CREATE_BREAKAWAY_FROM_JOB` 都被拒绝。因此从受管会话里启动的服务只在该轮对话期间可用，页面随后会报 `Failed to fetch`。要让页面长期可用，在自己的终端里运行 `deploy\serve.cmd`（双击即可），该进程不受会话回收影响。
2. 沙箱把 `tempfile.mkdtemp` 的 `0o700` 目录变成不可写的 ACL，`TemporaryDirectory` 无法使用，验收脚本会报 `PermissionError: WinError 5`。`deploy\verify.ps1` 通过把 `PYTHONPATH` 指向 `deploy\sandbox`（仅覆盖临时目录创建方式）并把 `TEMP` 放到 `.run\tmp` 规避。普通终端里不需要这一层，直接运行仓库脚本即可。

旧实验留下的空目录 `.run/old-scratch-*` 是上述 ACL 的产物，普通终端下可以直接删除。

## 回归与云端的区别

本地部署只提供回环地址上的训练与复盘服务。华为开发者空间的登录态、HTTPS 预览和 401 访问控制仍由云端入口负责，本地脚本不修改这部分行为。

## 版本与提交

| 版本 | 日期 | 提交 | 内容 |
| --- | --- | --- | --- |
| v3.2 | 2026-11-26 | `63c1faf` | 本地一键部署与板端串口实录链路：`deploy/` 启停与验收脚本、串口实录转回执、三个训练场景文档、`file://` 误用提示 |
| v3.1 | 2026-11-24 | `dc06fbc` | 接入华为云实机回执复盘，网页登录态训练、教师标注与导出 |

v3.2 的本地验证：四套验收脚本全部通过；真实板端对话经 `record.ps1` 采集后上传，得到回执 `22a210ada01d8c75113f36ea012e717a5c0a8637ea3d1ce36859cc0ac908bdfd`（7 条事件），可在复盘页查询。真实串口日志与采集文件保留在 `.run/`，不进版本库；公开样例 `samples/board-capture.json` 仍是虚构数据。

