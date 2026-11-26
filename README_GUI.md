# MiService GUI（Windows 图形界面版）

基于 [Yonsm/MiService](https://github.com/Yonsm/MiService) (MIT) 的 Windows 图形界面衍生版，
把小米云 / 小爱音箱的命令行能力做成了可直接双击运行的 GUI，并新增了本地音频播放功能。

## 功能

- **文字播报 (TTS)**：输入文字让小爱音箱朗读，可指定单台 / 多台 / 全部设备
- **设备列表**：自动拉取小爱设备（名称、型号、deviceID、miotDID），支持多选
- **播放控制**：暂停 / 继续 / 停止、音量调节、播放网络音频链接、查看播放状态、最近问答
- **本地音频**：选择电脑上的音频文件，通过本机局域网 HTTP 服务让小爱直接拉取播放
  （支持 mp3 / wav / m4a / flac 等，支持 Range 续播与中文文件名）
- **账号管理**：首次登录支持二次验证弹窗，token 保存在本机，可一键清除登录

## 直接下载使用

`dist/` 目录提供两个**单文件 exe**，无需安装 Python 或任何依赖：

| 文件 | 说明 |
| --- | --- |
| `MiService-GUI.exe` | 图形界面版（推荐） |
| `miservice.exe` | 原命令行版 |

双击 `MiService-GUI.exe`，填写小米账号密码 → 【获取设备】→ 选设备 → 输入文字 → 【立即播报】。
详细步骤见 [使用说明.txt](使用说明.txt)。

### 本地音频播放的前提

- 小爱音箱与电脑处于**同一局域网**
- Windows 防火墙允许本程序通过「专用网络」
- 播放期间保持程序开启（关闭后音频地址失效）

## 从源码打包

需要 Windows + Python 3.8+：

```bash
pip install pyinstaller aiohttp pycryptodome
pyinstaller --noconfirm --clean --onefile --windowed --name MiService-GUI \
  -p . miservice_gui.py
pyinstaller --noconfirm --clean --onefile --console --name miservice \
  -p . miservice_cli.py
```

## 文件说明

- `miservice_gui.py` — GUI 主程序（tkinter + 后台 asyncio 线程）
- `miservice_cli.py` — 命令行版打包入口（双击无参数时保持窗口）
- `miservice/` — 上游核心库（未修改）
- `使用说明.txt` — 中文使用说明（GUI + CLI）

## 致谢与许可

核心库来自 [Yonsm/MiService](https://github.com/Yonsm/MiService)，遵循 MIT 协议。
GUI 与本地音频扩展部分同样以 MIT 协议开源。
