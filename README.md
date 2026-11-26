# MiService GUI

**中文** | [English](README_EN.md)

[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)

小米云服务 / 小爱音箱工具的 **Windows 图形界面版**，基于 [Yonsm/MiService](https://github.com/Yonsm/MiService) (MIT) 构建。
提供可直接双击运行的单文件 exe，支持文字 TTS 播报、设备列表点选播放、播放控制、本地音频文件播放，同时保留原项目的完整命令行与 Python 库能力。

## 功能

### 图形界面版（MiService-GUI.exe，推荐）

- 输入文字让小爱音箱播报 TTS，可指定单台 / 多台 / 全部设备
- 自动拉取小爱设备列表（名称、型号、deviceID、miotDID），支持 Ctrl / Shift 多选
- 播放控制：暂停 / 继续 / 停止、音量调节（0–100）、播放网络音频链接
- **本地音频播放**：选择电脑上的音乐文件，通过本机局域网 HTTP 服务让小爱直接拉取播放（支持 mp3 / wav / m4a / flac、Range 续播、中文文件名）
- 播放状态查询、最近 AI 问答查看
- 账号登录支持 OTP 二次验证弹窗，token 保存在本机，可一键清除登录

### 命令行 / 库（源自上游，功能完整）

- 小米账号登录与服务令牌管理（支持 SMS/Email OTP 两步验证）
- MiIO 协议设备控制（属性读取 / 设置、动作调用）
- MIoT Spec 接口文档查询（[miot-spec.com](https://home.miot-spec.com/)，支持 text/python 格式化输出）
- MiNA 小爱音箱控制：TTS 语音播报、音量、播放控制、状态查询、AI 应答获取
- 局域网本地直连设备（`MiIOLocalService`），无需云端账号
- 命令行工具 `miservice`，一行命令操作设备；亦支持 `python -m miservice`
- 零硬依赖：`aiohttp` 未安装时自动回退到内置 `biohttp`；`pycryptodome` 未安装时 AES 自动回退到内置纯 Python 实现

## 直接下载使用（Windows）

`dist/` 目录提供两个**单文件 exe**，无需安装 Python 或任何依赖：

| 文件 | 说明 |
|------|------|
| [`MiService-GUI.exe`](dist/MiService-GUI.exe) | 图形界面版（推荐），双击即用 |
| [`miservice.exe`](dist/miservice.exe) | 原命令行版，适合脚本化调用 |

详细的中文步骤见 [使用说明.txt](使用说明.txt)，GUI 实现说明见 [README_GUI.md](README_GUI.md)。

### 图形界面使用步骤

1. 双击 `MiService-GUI.exe` 启动。
2. 顶部输入小米账号和密码，点击【获取设备】。首次登录若触发二次验证会弹窗要求输入验证码；登录状态保存在 `%USERPROFILE%\.mi.token`，之后无需重复登录。勾选「记住账号」只保存用户名，不保存密码。
3. 设备列表区以表格列出所有小爱设备，可点选一台或多台（按住 Ctrl / Shift）。目标范围可选「选中的设备」或「全部设备」；未选中任何设备时默认作用于全部设备。
4. 【文字播报 (TTS)】页签：输入播报内容（如「今晚八点开会，请准时参加」），点击【立即播报】即会朗读。
5. 【播放控制】页签：暂停 / 继续播放 / 停止；音量滑块 0–100 后点【设置音量】；输入 http(s) 音频直链点【播放链接】；【播放状态】查看 JSON 信息；【最近问答】查看最近回答。
6. 【本地音频】页签：点【浏览…】选择本机音频文件，端口保持 `0`（自动分配），点【播放本地音频】。程序会启动临时 HTTP 服务，生成本机局域网地址（如 `http://192.168.x.x:51926/歌曲.mp3`），让所选小爱直接拉取播放，日志区会显示该地址。
7. 底部「日志」区显示每步操作的成功 / 失败结果，便于排查。
8. 【清除登录】按钮可清空本机 token 与界面账号信息，下次需重新登录。

**本地音频播放的前提条件：**

- 小爱音箱与电脑须处于**同一局域网**（同一路由器 / Wi-Fi）。
- 首次使用若被拦截，请在 Windows 防火墙中允许本程序通过「专用网络」。
- 播放期间请保持程序开启；关闭程序后音频地址立即失效。
- 若小爱无法播放，可在浏览器打开日志里的地址验证是否可访问。

### 命令行版使用（PowerShell / CMD）

```powershell
# PowerShell
$env:MI_USER = "你的小米账号"
$env:MI_PASS = "你的小米密码"
$env:MI_DID  = "设备ID或设备名"
.\miservice.exe list
```

```bat
:: CMD
set MI_USER=你的小米账号
set MI_PASS=你的小米密码
set MI_DID=设备ID或设备名
miservice.exe list
```

局域网直连（无需云端账号）：

```bat
set MI_LOCAL=设备IP:设备Token
miservice.exe power
```

## 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `MI_USER` | 是 | 小米账号用户名 |
| `MI_PASS` | 是 | 小米账号密码 |
| `MI_DID` | 否 | 设备 ID 或设备名称（操作设备时必填；MiNA 设备级命令亦用它定位目标音箱） |
| `MI_LOCAL` | 否 | `<IP>:<Token>`，设置后走局域网本地直连，无需 `MI_USER`/`MI_PASS`/`MI_DID` |

## 命令行用法

```
MiService 3.0.2 - XiaoMi Cloud Service

Usage: The following variables must be set:
           export MI_USER=<Username>
           export MI_PASS=<Password>
           export MI_DID=<Device ID|Name>

Get Props: miservice <siid[-piid]>[,...]
           miservice 1,1-2,1-3,1-4,2-1,2-2,3
Set Props: miservice <siid[-piid]=[#]value>[,...]
           miservice 2=60,2-1=#60,2-2=false,2-3="null",3=test
Do Action: miservice <siid[-piid]> <arg1|[]> [...]
           miservice 2 []
           miservice 5 Hello
           miservice 5-4 Hello 1

Call MIoT: miservice <cmd=prop/get|/prop/set|action> <params>
           miservice action '{"did":"267090026","siid":5,"aiid":1,"in":["Hello"]}'

Call MiIO: miservice /<uri> <data>
           miservice /home/device_list '{"getVirtualModel":false,"getHuamiDevices":1}'

Devs List: miservice list [name_keyword|full] [getVirtualModel=false|true] [getHuamiDevices=0|1]
           miservice list Light true 0
           miservice list full

Home List: miservice home [name_keyword|full]
           miservice home
           miservice home full
           miservice home 我的家

MIoT Spec: miservice spec [model_keyword|type_urn] [text|python]
           miservice spec
           miservice spec speaker
           miservice spec xiaomi.wifispeaker.lx04 text

MIoT Decode: miservice decode <ssecurity> <nonce> <data> [gzip]

MiNA Commands:
           miservice mina            # List MiNA devices
           miservice mina <text>     # TTS broadcast to all devices
           miservice mina pause      # Pause playback
           miservice mina stop       # Stop playback
           miservice mina play       # Resume playback
           miservice mina play <url> # Play audio from URL
           miservice mina loop <url> # Play URL on single-track loop
           miservice mina volume <n> # Set volume (0-100)
           miservice mina status     # Get playback status
           miservice mina ask        # Get latest AI response

Local Device (no cloud account, direct LAN control):
           export MI_LOCAL=<IP>:<Token>
           miservice power,brightness
           miservice power=on,brightness=80
           miservice /miIO.info
```

> 也可通过 `python -m miservice` 运行，参数与 `miservice` 命令完全一致。

### 调试日志

通过 `-v` 参数控制日志级别（0–5）：

```bash
miservice -v5 list        # DEBUG 级别
miservice -v2 list        # ERROR 级别
miservice -v3 list        # WARN 级别
miservice list            # 默认 WARNING 级别
```

## 命令行示例

### 查询设备列表与设置 DID

```bash
export MI_USER=<Username>
export MI_PASS=<Password>
miservice list                      # 列出设备（含 DID、Token 等）
export MI_DID=<Device ID|Name>      # DID 或设备名称
```

### 查询设备接口文档

```bash
miservice spec xiaomi.wifispeaker.lx04 text
```

### 读取 / 设置属性

```bash
miservice 2-1       # 读取 siid=2, piid=1 的属性（piid 为 1 可省略）
miservice 2=#60     # 设置为文本类型 60
```

参数类型根据接口文档确定：`#` 强制文本类型（单引号 `'`、双引号 `"` 亦可）；不强制时自动检测为 JSON `null`/`false`/`true`、整数、浮点数或文本。

### 动作调用：TTS 播报与执行文本

```bash
miservice 5 您好          # 小爱播报"您好"（siid=5，aiid 默认 1）
miservice 5-4 查询天气 1  # 相当于说"小爱同学，查询天气"，1 表示语音回应
miservice 5-4 关灯 0      # 默默关灯，不要音箱回应
```

没有参数时传 `[]` 占位。

### 小爱音箱控制（MiNA）

```bash
miservice mina                      # 列出 MiNA 设备
miservice mina 你好世界              # 向所有音箱 TTS 播报
export MI_DID=<miotDID>             # 设备级命令需用它定位目标音箱
miservice mina pause                # 暂停
miservice mina stop                 # 停止
miservice mina play                 # 继续播放
miservice mina play <url>           # 播放指定 URL（列表循环）
miservice mina loop <url>           # 单曲循环播放 URL
miservice mina volume 50            # 设置音量 0-100
miservice mina status               # 查询播放状态
miservice mina ask                  # 获取最近一次 AI 应答
```

> 注：`mina <text>` 中若文本恰好为子命令名（如 `pause`），会被视为子命令；如需播报此类文本，请加引号或前缀文字。

### 局域网本地直连

```bash
export MI_LOCAL=192.168.1.10:0123456789abcdef0123456789abcdef
miservice power,brightness          # 读取属性
miservice power=on,brightness=80    # 设置属性
miservice /miIO.info                # 调用原始 miIO 方法
```

Token 可从 `miservice list` 的云端查询结果中获取，或用 APP 抓取。

## 库结构

```
MiService：XiaoMi Cloud Service
  |
  |-- MiAccount：账号登录与令牌管理
  |     |-- 用户名密码登录
  |     |-- OTP 两步验证（SMS/Email）
  |     |-- 服务令牌持久化（~/.mi.token）
  |
  |-- MiIOService：MiIO 服务 (sid=xiaomiio)
  |     |-- MiIO 协议请求（签名/加密）
  |     |-- MIoT 属性获取/设置/动作调用
  |     |-- 设备列表查询
  |     |-- 家庭/房间层级查询
  |     |-- MIoT Spec 接口文档查询
  |     |-- MIoT 数据解密
  |
  |-- MiNAService：MiAI 服务 (sid=micoapi)
  |     |-- 小爱音箱设备列表
  |     |-- TTS 语音播报 / 音量控制
  |     |-- 播放控制（暂停/停止/继续/URL 播放/单曲循环）
  |     |-- 播放状态查询
  |     |-- 最新 AI 应答获取
  |     |-- 设备型号自动适配（部分机型使用 play_music API）
  |
  |-- miio_command：MiIO 命令风格接口
  |
  |-- MiIOLocalService：局域网本地直连设备（无需云端账号）
  |     |-- 属性获取/设置
  |     |-- 原始 miIO 方法调用
  |
  |-- aes：内置 AES-128-CBC 纯 Python 实现（pycryptodome 未安装时的回退）
  |
  |-- local_command：本地设备命令风格接口
```

## 作为库使用

```bash
pip3 install miservice
# 可选：aiohttp 获得更好异步性能；pycryptodome 获得更快 AES
pip3 install aiohttp pycryptodome
```

要求 Python 3.8+。

```python
import asyncio
from miservice import MiAccount, MiIOService, MiNAService

async def main():
    account = MiAccount(None, 'username', 'password', '~/.mi.token')

    # 查询设备列表
    io_service = MiIOService(account)
    devices = await io_service.device_list()
    print(devices)

    # 获取 / 设置设备属性
    value = await io_service.miot_get_prop('device_id', (2, 1))
    await io_service.miot_set_prop('device_id', (2, 1), 60)

    # 小爱音箱 TTS 与播放控制
    na_service = MiNAService(account)
    devices = await na_service.device_list()
    if devices:
        device_id = devices[0]['deviceID']
        await na_service.text_to_speech(device_id, '你好')
        await na_service.player_set_volume(device_id, 50)
        await na_service.player_pause(device_id)
        await na_service.player_play(device_id)
        await na_service.play_by_url(device_id, 'http://.../music.mp3')  # 自动适配机型
        await na_service.player_set_loop(device_id, 0)  # 0=单曲循环, 1=列表循环
        status = await na_service.player_get_status(device_id)
        messages = await na_service.get_latest_ask(device_id)

    # 局域网本地直连（无需云端账号）
    from miservice import MiIOLocalService
    local_service = MiIOLocalService('192.168.1.10', '0123456789abcdef0123456789abcdef')
    power = await local_service.get_prop('power')
    await local_service.set_prop('power', 'on')

asyncio.run(main())
```

## 从源码打包（Windows）

需要 Windows + Python 3.8+：

```bash
pip install pyinstaller aiohttp pycryptodome
pyinstaller --noconfirm --clean --onefile --windowed --name MiService-GUI -p . miservice_gui.py
pyinstaller --noconfirm --clean --onefile --console --name miservice -p . miservice_cli.py
```

## 文件说明

- `miservice_gui.py` — GUI 主程序（tkinter + 后台 asyncio 线程）
- `miservice_cli.py` — 命令行版打包入口（双击无参数时保持窗口）
- `miservice/` — 核心库（来自上游）
- `使用说明.txt` — 中文使用说明（GUI + CLI）
- `README_GUI.md` — GUI 功能与打包说明

## 致谢与许可

核心库来自 [Yonsm/MiService](https://github.com/Yonsm/MiService)，遵循 MIT 协议。
GUI 与本地音频扩展部分同样以 MIT 协议开源。

账号密码仅用于向小米服务器登录；token 保存在本机用户目录，不会上传第三方。
若登录一直失败（触发风控），请稍后再试或在手机上退出其他米家登录设备。
