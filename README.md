# 开启5GA / unicom-5ga-enabler

面向 **iPhone 14 Pro（iPhone15,2 / D73）+ iOS 27.0.1（24A446）+ 中国联通** 的 Windows 运营商配置工具。

配套教程：**[中国联通 5GA 操作说明](https://maaio.com/archives/5ga.html)**。本仓库提供对应的操作程序；参数、权限及流程以本仓库随附说明为准。

> 仅适用于上述配置，其他机型、系统版本或运营商请勿直接混用。如需适配，应同时调整设备检查、载荷、路径、权限和校验清单。本工具修改运营商配置及显示参数，不保证所在网络、套餐和基站实际提供 5G-A 能力。

## 下载使用

1. 到 **[Releases](https://github.com/liyansum/unicom-5ga-enabler/releases/latest)** 下载 Windows 完整包 `Enable5GA-Windows.zip`。
2. 完整解压，保留 `runtime`、`tools` 和 `payloads` 等目录，双击 **开启5GA.bat**。
3. 首次使用选择 **1 完整模式**。以后每次手机重启后，选择 **2 普通模式**。
4. 如需恢复原版：进入 **3 调试模式 → 1 加载原版 73.0 IPCC**，然后手动重启手机。

电脑需安装 64 位 iTunes / Apple Mobile Device Support。手机通过 USB 连接、解锁并信任电脑，开启开发者模式且开发服务可用。发行包包含 Python 和依赖，不包含 Apple 的电脑端驱动或 DLL。

公开版每项操作开始前自动选择唯一的 USB 设备，并检查机型、系统版本及构建号。请只连接一台设备；不需要填写或上传 UDID，不保存配对记录。

## 模式

| 入口 | 操作 |
|---|---|
| 1 完整模式 | 加载原版 IPCC → 三件套 0644 → 其他三个 bundle 文件 0600 → overlay 0555 → 重载 CommCenter → 再补写 overlay 0555 |
| 2 普通模式 | 写入两个 overlay 0555 → 重载 CommCenter → 再补写两个 overlay 0555 |
| 3 调试模式 | 打开下列五项独立操作 |

调试选项：

1. 加载 iPhone 14 Pro 联通原版 73.0 IPCC。
2. 以 0644 写入 bundle 三件套。
3. 以 0600 重写 bundle 其他三个文件。
4. 以 0555 写入修改后的两个 overlay。
5. 只重载一次 CommCenter。

每项调试独立执行，不自动串联。写 bundle 前只检查目录是否存在；目录缺失会停止。

## 权限和等待

| 文件 | 写入权限 |
|---|---|
| PRI、对应 overrides、对应签名 | 0644 |
| `carrier.plist`、`Info.plist`、`signatures/common.plist` | 0600 |
| 联通 72.0.1、73.0 两个 overlay | 0555 |

0600 文件即使内容相同也会重新写入，不按内容相同跳过。写入结束后等待至少 5 秒，只向准确的 CommCenter 进程号发送一次结束信号；观察到新进程号持续运行至少 15 秒，再继续补写。最多观察 90 秒，失败即停止。

程序不搬出或回读 overlay / bundle 内容；目录检查查询元数据。本次操作的 Media 暂存、链接和 IPCC 上传暂存会在收尾时清理，不沿链接删除其目标目录。写后目标内容、实际权限和网络效果没有通过回读测量，步骤结束不等于运营商网络能力已经验证。

## 从源码运行

Windows 上安装 64 位 Python 3.13 后，在仓库目录运行：

```powershell
python -m venv runtime
.\runtime\Scripts\python.exe -m pip install -r requirements.txt
.\开启5GA.bat
```

无需连接手机的本地检查：

```powershell
.\runtime\Scripts\python.exe -I -X utf8 -u restore.py check
```

发行包的解释器位置为 `runtime/python.exe`，源码创建的虚拟环境为 `runtime/Scripts/python.exe`，启动文件均支持。

## 隐私与发布内容

- 不包含原作者的手机 UDID、设备昵称、个人邮箱或电脑用户目录。
- 不提交 `logs`、历史备份、`__pycache__`、配对文件、凭据或本地 `.env`。
- 运行日志仅保存在本地，程序不自动上传日志或设备资料；若自行分享日志，仍请先检查内容。
- 原包及修改载荷均附大小和 SHA-384 校验；公开的签名、证书与协议常量不属于个人凭据。

## 来源与许可

操作流程配合 [maaio.com 教程](https://maaio.com/archives/5ga.html)。设备通信依赖 [pymobiledevice3](https://github.com/doronz88/pymobiledevice3)，Airlift 部分改编自 [AirliftSilence](https://github.com/YiHoooong/AirliftSilence) 及其列出的上游工作。

本项目自有代码采用 GPL-3.0-or-later；第三方代码、Python、依赖库和 Apple / 运营商载荷保留各自许可和权利，不因本仓库的代码许可证改变。详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

使用流程和权限方案来自该特定配置的实测反馈；公开版的去绑定、机型检查及流程经过离线测试，公开版未额外在手机上执行完整实测。详细文件与操作说明见 [使用说明.md](使用说明.md)。

## 重要补充！！！

实测完整模式可能由于刚更新了ipcc 所以触发了commcenter的额外update流程 如果执行完整模式后设置里仍未出现5gsa开关和vonr开关 请重启设备然后执行一次普通模式！！！
也就是说安装ipcc最好和后续操作留一定间隔时间，另外也可以在不生效时尝试进入调试选项，依次执行2345
