#!/usr/bin/env python3
"""MiService GUI - 小爱音箱(TTS/播控)图形界面.

基于 tkinter，异步网络操作在后台 event loop 线程执行，GUI 线程通过队列
接收结果；二次验证 (OTP) 通过弹窗输入。
"""

import asyncio
import http.server
import json
import mimetypes
import os
import queue
import socket
import sys
import threading
import traceback
import urllib.parse
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog

from miservice import MiAccount, MiNAService, __version__

CONFIG_PATH = Path.home() / '.miservice_gui.json'
TOKEN_PATH = Path.home() / '.mi.token'


def _load_config():
    try:
        if CONFIG_PATH.exists():
            return json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    except Exception:
        pass
    return {}


def _save_config(cfg):
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass


def get_lan_ip():
    """Detect the LAN IP that XiaoAi speakers can reach (not 127.0.0.1)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(('223.5.5.5', 80))  # does not actually send data, just picks a route
        return sock.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return None
    finally:
        sock.close()


class LocalFileHandler(http.server.BaseHTTPRequestHandler):
    """Serves a single file with HTTP Range support (needed by audio players)."""

    file_path = None  # set on the subclass before serving

    def _resolve(self):
        return type(self).file_path

    def _handle(self, send_body=True):
        path = self._resolve()
        if not path or not os.path.isfile(path):
            self.send_error(404, 'File not found')
            return
        size = os.path.getsize(path)
        ctype = mimetypes.guess_type(path)[0] or 'application/octet-stream'
        start, end, status = 0, size - 1, 200
        rng = self.headers.get('Range')
        if rng and rng.startswith('bytes='):
            spec = rng[6:].split(',')[0].strip()
            if '-' in spec:
                a, _, b = spec.partition('-')
                try:
                    if a == '':
                        start = max(0, size - int(b))
                    else:
                        start = int(a)
                        end = int(b) if b.strip() else size - 1
                    end = min(end, size - 1)
                    if 0 <= start <= end:
                        status = 206
                except ValueError:
                    pass
        length = max(0, end - start + 1)
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(length))
        if status == 206:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.end_headers()
        if send_body:
            try:
                with open(path, 'rb') as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(min(65536, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def do_GET(self):
        self._handle(True)

    def do_HEAD(self):
        self._handle(False)

    def log_message(self, fmt, *args):
        pass  # keep the console quiet


class LocalFileServer:
    """A tiny threaded HTTP server exposing the selected local audio file."""

    def __init__(self):
        self._httpd = None
        self._thread = None

    def start(self, file_path, port=0):
        """Start (or restart onto a new file) and return the bound port."""
        self.stop()
        handler = type('BoundHandler', (LocalFileHandler,), {'file_path': file_path})
        self._httpd = http.server.ThreadingHTTPServer(('0.0.0.0', port), handler)
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True,
                                        name='miservice-http')
        self._thread.start()
        return self._httpd.server_address[1]

    def stop(self):
        if self._httpd:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:
                pass
            self._httpd = None
            self._thread = None


class Backend:
    """Runs an asyncio event loop in a background thread."""

    def __init__(self, otp_queue):
        self.loop = asyncio.new_event_loop()
        self.otp_queue = otp_queue          # GUI -> loop: (method, future)
        self.result_queue = queue.Queue()   # loop -> GUI: (callback, future)
        self.session = None
        self.account = None
        self.service = None
        self.devices = []
        self._user = None
        self._pwd = None
        self.local_server = LocalFileServer()
        self._thread = threading.Thread(target=self._run, daemon=True, name='miservice-loop')

    def start(self):
        self._thread.start()

    def stop(self):
        try:
            self.loop.call_soon_threadsafe(self.loop.stop)
        except Exception:
            pass

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def call(self, coro_func, callback=None, *args):
        """Schedule coro_func(*args) on the loop; callback(future) runs on GUI thread."""
        future = asyncio.run_coroutine_threadsafe(coro_func(*args), self.loop)
        if callback:
            def _done(f):
                self.result_queue.put((callback, f))
            future.add_done_callback(_done)
        return future

    # ---- async helpers -------------------------------------------------
    async def _otp(self, method):
        fut = self.loop.create_future()
        self.otp_queue.put((method, fut))
        return await fut

    async def ensure(self, user, pwd):
        if self.session is None:
            try:
                from aiohttp import ClientSession
            except ImportError:
                from miservice.biohttp import ClientSession
            self.session = ClientSession()
        if self.account is None or self._user != user or self._pwd != pwd:
            self._user, self._pwd = user, pwd
            self.account = MiAccount(self.session, user, pwd, str(TOKEN_PATH),
                                     otp_callback=self._otp)
            self.service = MiNAService(self.account)
        return self.service

    async def close(self):
        if self.session:
            try:
                await self.session.close()
            except Exception:
                pass
            self.session = None
        self.local_server.stop()

    async def list_devices(self, user, pwd):
        service = await self.ensure(user, pwd)
        devices = await service.device_list()
        self.devices = devices or []
        await service._init_devices(self.devices)
        return self.devices

    async def _targets(self, indices):
        if indices is None:
            return list(range(len(self.devices)))
        return [i for i in indices if 0 <= i < len(self.devices)]

    async def tts(self, indices, text, user, pwd):
        service = await self.ensure(user, pwd)
        targets = await self._targets(indices)
        if not targets:
            return []
        results = []
        for i in targets:
            d = self.devices[i]
            ok = await service.text_to_speech(d['deviceID'], text)
            results.append((d.get('name', d['deviceID']), ok))
        return results

    async def play_url(self, indices, url, user, pwd):
        service = await self.ensure(user, pwd)
        targets = await self._targets(indices)
        results = []
        for i in targets:
            d = self.devices[i]
            ok = await service.play_by_url(d['deviceID'], url)
            results.append((d.get('name', d['deviceID']), ok))
        return results

    async def play_local_file(self, indices, file_path, port, user, pwd):
        """Expose a local audio file over LAN HTTP, then ask devices to play it."""
        ip = get_lan_ip()
        if not ip:
            raise RuntimeError('无法获取本机局域网 IP，请检查网络连接')
        actual_port = self.local_server.start(file_path, port)
        filename = urllib.parse.quote(os.path.basename(file_path))
        url = f'http://{ip}:{actual_port}/{filename}'
        results = await self.play_url(indices, url, user, pwd)
        return results, url

    async def control(self, indices, action, value, user, pwd):
        service = await self.ensure(user, pwd)
        targets = await self._targets(indices)
        results = []
        for i in targets:
            d = self.devices[i]
            did = d['deviceID']
            if action == 'pause':
                ok = await service.player_pause(did)
            elif action == 'play':
                ok = await service.player_play(did)
            elif action == 'stop':
                ok = await service.player_stop(did)
            elif action == 'volume':
                ok = await service.player_set_volume(did, value)
            elif action == 'status':
                st = await service.player_get_status(did)
                results.append((d.get('name', did), st))
                continue
            elif action == 'ask':
                msgs = await service.get_latest_ask(did)
                results.append((d.get('name', did), msgs))
                continue
            else:
                ok = False
            results.append((d.get('name', did), ok))
        return results

    async def logout(self):
        if self.account:
            try:
                await self.account.close()
            except Exception:
                pass
        self.account = None
        self.service = None
        if TOKEN_PATH.exists():
            try:
                TOKEN_PATH.unlink()
            except Exception:
                pass


class App:
    def __init__(self, root):
        self.root = root
        self.root.title(f'MiService 小爱音箱控制台 v{__version__}')
        self.root.geometry('1000x720')
        self.root.minsize(880, 620)
        self.otp_queue = queue.Queue()
        self.backend = Backend(self.otp_queue)
        self.backend.start()
        self.cfg = _load_config()
        self.busy = 0

        self._setup_style()
        self._build_ui()
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)
        self.root.after(100, self._poll)

        if self.cfg.get('user'):
            self.user_var.set(self.cfg['user'])
            self.remember_var.set(True)
            self._log('已载入上次账号，点击「获取设备」开始。')

    # ---- UI -------------------------------------------------------------
    def _setup_style(self):
        self.root.option_add('*Font', ('Microsoft YaHei UI', 10))
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except Exception:
            pass
        style.configure('Title.TLabel', font=('Microsoft YaHei UI', 13, 'bold'))
        style.configure('Hint.TLabel', foreground='#666666')
        style.configure('Accent.TButton', foreground='#ffffff', background='#2d7ff9')
        style.map('Accent.TButton', background=[('active', '#1f6ee0')])

    def _build_ui(self):
        root = self.root
        main = ttk.Frame(root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # ---- login bar ----
        login = ttk.LabelFrame(main, text=' 小米账号 ', padding=8)
        login.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(login, text='账号：').grid(row=0, column=0, sticky='w')
        self.user_var = tk.StringVar()
        ttk.Entry(login, textvariable=self.user_var, width=24).grid(row=0, column=1, padx=(0, 12))
        ttk.Label(login, text='密码：').grid(row=0, column=2, sticky='w')
        self.pwd_var = tk.StringVar()
        ttk.Entry(login, textvariable=self.pwd_var, show='*', width=24).grid(row=0, column=3, padx=(0, 12))
        self.remember_var = tk.BooleanVar()
        ttk.Checkbutton(login, text='记住账号', variable=self.remember_var).grid(row=0, column=4, padx=(0, 12))
        self.get_btn = ttk.Button(login, text='获取设备', style='Accent.TButton', command=self.on_get_devices)
        self.get_btn.grid(row=0, column=5)
        ttk.Button(login, text='清除登录', command=self.on_logout).grid(row=0, column=6, padx=(8, 0))
        ttk.Label(login, text='首次登录或验证码会弹窗；登录状态保存在本机 .mi.token',
                  style='Hint.TLabel').grid(row=1, column=0, columnspan=7, sticky='w', pady=(6, 0))

        # ---- middle ----
        mid = ttk.Frame(main)
        mid.pack(fill=tk.BOTH, expand=True)

        left = ttk.LabelFrame(mid, text=' 设备列表 ', padding=8, width=490)
        left.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 8))
        left.pack_propagate(False)

        cols = ('name', 'hardware', 'did', 'miot')
        self.tree = ttk.Treeview(left, columns=cols, show='headings', selectmode='extended', height=14)
        for key, text, width in zip(cols, ('设备名称', '型号', 'deviceID', 'miotDID'), (150, 90, 170, 90)):
            self.tree.heading(key, text=text)
            self.tree.column(key, width=width, anchor='w')
        sb = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind('<<TreeviewSelect>>', self._on_select)

        target = ttk.Frame(left)
        target.pack(fill=tk.X, pady=(8, 0))
        self.target_var = tk.StringVar(value='selected')
        ttk.Radiobutton(target, text='选中的设备', variable=self.target_var, value='selected').pack(side=tk.LEFT)
        ttk.Radiobutton(target, text='全部设备', variable=self.target_var, value='all').pack(side=tk.LEFT, padx=(12, 0))
        self.sel_label = ttk.Label(target, text='未选择设备', style='Hint.TLabel')
        self.sel_label.pack(side=tk.RIGHT)

        right = ttk.LabelFrame(mid, text=' 操作 ', padding=8)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        nb = ttk.Notebook(right)
        nb.pack(fill=tk.BOTH, expand=True)

        # TTS tab
        tts_tab = ttk.Frame(nb, padding=10)
        nb.add(tts_tab, text=' 文字播报 (TTS) ')
        ttk.Label(tts_tab, text='输入要让小爱同学播报的文字：').pack(anchor='w')
        self.tts_text = scrolledtext.ScrolledText(tts_tab, height=7, wrap=tk.WORD)
        self.tts_text.pack(fill=tk.BOTH, expand=True, pady=(6, 8))
        row = ttk.Frame(tts_tab)
        row.pack(fill=tk.X)
        self.tts_btn = ttk.Button(row, text='立即播报', style='Accent.TButton', command=self.on_tts)
        self.tts_btn.pack(side=tk.LEFT)
        ttk.Button(row, text='清空', command=lambda: self.tts_text.delete('1.0', tk.END)).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(tts_tab, text='提示：勾选「全部设备」可广播；未选设备时默认向全部设备播报。',
                  style='Hint.TLabel', wraplength=390).pack(anchor='w', pady=(8, 0))

        # Control tab
        ctrl_tab = ttk.Frame(nb, padding=10)
        nb.add(ctrl_tab, text=' 播放控制 ')
        row1 = ttk.Frame(ctrl_tab)
        row1.pack(fill=tk.X, pady=(0, 10))
        self.pause_btn = ttk.Button(row1, text='暂停', command=lambda: self.on_control('pause'))
        self.pause_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.play_btn = ttk.Button(row1, text='继续播放', command=lambda: self.on_control('play'))
        self.play_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.stop_btn = ttk.Button(row1, text='停止', command=lambda: self.on_control('stop'))
        self.stop_btn.pack(side=tk.LEFT)

        vol = ttk.LabelFrame(ctrl_tab, text=' 音量 ', padding=8)
        vol.pack(fill=tk.X, pady=(0, 10))
        self.vol_var = tk.IntVar(value=50)
        ttk.Scale(vol, from_=0, to=100, orient=tk.HORIZONTAL, variable=self.vol_var, length=220).pack(side=tk.LEFT)
        self.vol_label = ttk.Label(vol, text='50')
        self.vol_label.pack(side=tk.LEFT, padx=8)
        self.vol_var.trace_add('write', lambda *_: self.vol_label.config(text=str(self.vol_var.get())))
        self.vol_btn = ttk.Button(vol, text='设置音量', command=self.on_volume)
        self.vol_btn.pack(side=tk.LEFT)

        urlf = ttk.LabelFrame(ctrl_tab, text=' 播放网络音频 ', padding=8)
        urlf.pack(fill=tk.X, pady=(0, 10))
        self.url_var = tk.StringVar()
        ttk.Entry(urlf, textvariable=self.url_var).pack(fill=tk.X, pady=(0, 6))
        self.url_btn = ttk.Button(urlf, text='播放链接', command=self.on_play_url)
        self.url_btn.pack(anchor='w')

        misc = ttk.Frame(ctrl_tab)
        misc.pack(fill=tk.X)
        self.status_btn = ttk.Button(misc, text='播放状态', command=lambda: self.on_control('status'))
        self.status_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.ask_btn = ttk.Button(misc, text='最近问答', command=lambda: self.on_control('ask'))
        self.ask_btn.pack(side=tk.LEFT)

        # Local audio tab
        local_tab = ttk.Frame(nb, padding=10)
        nb.add(local_tab, text=' 本地音频 ')
        ttk.Label(local_tab, text='选择电脑上的音频文件，通过局域网让小爱音箱播放：').pack(anchor='w')

        pick = ttk.Frame(local_tab)
        pick.pack(fill=tk.X, pady=(8, 4))
        self.local_var = tk.StringVar()
        ttk.Entry(pick, textvariable=self.local_var, state='readonly').pack(side=tk.LEFT,
                                                                           fill=tk.X, expand=True)
        ttk.Button(pick, text='浏览…', command=self.on_pick_file).pack(side=tk.LEFT, padx=(6, 0))

        # Port setting
        portf = ttk.Frame(local_tab)
        portf.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(portf, text='服务端口：').pack(side=tk.LEFT)
        self.port_var = tk.StringVar(value='0')
        ttk.Entry(portf, textvariable=self.port_var, width=8).pack(side=tk.LEFT)
        ttk.Label(portf, text='（0 = 自动分配，推荐）', style='Hint.TLabel').pack(side=tk.LEFT, padx=(6, 0))

        self.local_file_btn = ttk.Button(local_tab, text='播放本地音频',
                                         style='Accent.TButton', command=self.on_play_local)
        self.local_file_btn.pack(anchor='w', pady=(0, 8))

        tips = ('说明：\n'
                '• 小爱音箱需与本机处于同一局域网，且能访问本机 IP。\n'
                '• 首次使用请在 Windows 防火墙中允许“Python / MiService-GUI”通过专用网络。\n'
                '• 支持 mp3 / wav / m4a / flac 等常见格式；播放由小爱直接拉取文件。\n'
                '• 播放期间请保持本程序开启，关闭后音频地址即失效。')
        ttk.Label(local_tab, text=tips, style='Hint.TLabel', justify=tk.LEFT,
                  wraplength=400).pack(anchor='w', pady=(4, 0))

        # ---- log ----
        logf = ttk.LabelFrame(main, text=' 日志 ', padding=6)
        logf.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.log = scrolledtext.ScrolledText(logf, height=8, state=tk.DISABLED)
        self.log.pack(fill=tk.BOTH, expand=True)

        self.buttons = [self.get_btn, self.tts_btn, self.pause_btn, self.play_btn,
                        self.stop_btn, self.vol_btn, self.url_btn, self.status_btn,
                        self.ask_btn, self.local_file_btn]

    # ---- helpers --------------------------------------------------------
    def _log(self, msg):
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, msg + '\n')
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _busy(self, busy):
        self.busy = max(0, self.busy + (1 if busy else -1))
        state = tk.DISABLED if self.busy else tk.NORMAL
        for b in self.buttons:
            b.configure(state=state)

    def _credentials(self):
        return self.user_var.get().strip(), self.pwd_var.get()

    def _indices(self):
        if self.target_var.get() == 'all':
            return None
        sel = self.tree.selection()
        if not sel:
            return None  # no selection -> all
        return [int(s) for s in sel]

    def _save_remember(self):
        cfg = {}
        if self.remember_var.get():
            cfg['user'] = self.user_var.get().strip()
        _save_config(cfg)

    def _callback(self, title, formatter):
        def cb(fut):
            try:
                result = fut.result()
            except Exception as e:
                self._busy(False)
                self._log(f'[{title}] 失败：{e}')
                return
            self._busy(False)
            formatter(result)
        return cb

    # ---- OTP ------------------------------------------------------------
    def _otp_in(self):
        """Called on GUI thread by _poll; reads OTP from a modal dialog."""
        method, fut = self.otp_queue.get()
        code = simpledialog.askstring('二次验证', f'请输入 {method} 验证码：', parent=self.root)
        self.backend.loop.call_soon_threadsafe(fut.set_result, (code or '').strip())

    def _poll(self):
        try:
            while True:
                cb, fut = self.backend.result_queue.get_nowait()
                cb(fut)
        except queue.Empty:
            pass
        try:
            while not self.otp_queue.empty():
                self._otp_in()
        except Exception as e:
            self._log(f'验证码处理异常：{e}')
        self.root.after(100, self._poll)

    # ---- events ---------------------------------------------------------
    def _on_select(self, _event=None):
        sel = self.tree.selection()
        self.sel_label.config(text=f'已选 {len(sel)} 台' if sel else '未选择设备（将作用于全部）')

    def on_get_devices(self):
        user, pwd = self._credentials()
        if not user or not pwd:
            messagebox.showwarning('提示', '请输入小米账号和密码。', parent=self.root)
            return
        self._save_remember()
        self._log('正在获取设备列表…')
        self._busy(True)
        def done(devices):
            self.tree.delete(*self.tree.get_children())
            for i, d in enumerate(devices):
                self.tree.insert('', tk.END, iid=str(i), values=(
                    d.get('name', ''), d.get('hardware', ''), d.get('deviceID', ''), d.get('miotDID', '')))
            self._on_select()
            self._log(f'获取到 {len(devices)} 台小爱设备。')
        self.backend.call(self.backend.list_devices,
                          self._callback('获取设备', done), user, pwd)

    def on_logout(self):
        self.user_var.set('')
        self.pwd_var.set('')
        self.tree.delete(*self.tree.get_children())
        self.backend.devices = []
        self._save_config({})
        self.backend.call(self.backend.logout, self._callback('清除登录', lambda r: self._log('已清除登录状态。')))
        self._log('正在清除本机登录状态…')
        self._busy(True)

    def on_tts(self):
        text = self.tts_text.get('1.0', tk.END).strip()
        if not text:
            messagebox.showwarning('提示', '请输入要播报的文字。', parent=self.root)
            return
        idx = self._indices()
        user, pwd = self._credentials()
        if not user or not pwd:
            messagebox.showwarning('提示', '请先填写账号密码并获取设备。', parent=self.root)
            return
        self._log(f'正在播报：{text[:60]}{"…" if len(text) > 60 else ""}')
        self._busy(True)
        def done(results):
            if not results:
                self._log('没有可用设备。')
                return
            for name, ok in results:
                self._log(f'  {"成功" if ok else "失败"} · {name}')
        self.backend.call(self.backend.tts, self._callback('TTS', done), idx, text, user, pwd)

    def on_control(self, action):
        idx = self._indices()
        user, pwd = self._credentials()
        self._log(f'正在执行 {action}…')
        self._busy(True)
        labels = {'pause': '暂停', 'play': '继续播放', 'stop': '停止', 'status': '播放状态', 'ask': '最近问答'}
        def done(results):
            if not results:
                self._log('没有可用设备。')
                return
            for name, value in results:
                if action == 'status':
                    self._log(f'[{name}] 状态：{json.dumps(value, ensure_ascii=False) if value else "无"}')
                elif action == 'ask':
                    if not value:
                        self._log(f'[{name}] 暂无最近问答')
                    else:
                        for m in value[:5]:
                            answers = m.get('response', {}).get('answer', [])
                            spoken = ' / '.join(str(a.get('to_speak') or a.get('content', '')) for a in answers)
                            self._log(f'[{name}] {spoken[:200]}')
                else:
                    self._log(f'  {"成功" if value else "失败"} · {name} · {labels[action]}')
        self.backend.call(self.backend.control,
                          self._callback(labels[action], done), idx, action, None, user, pwd)

    def on_volume(self):
        idx = self._indices()
        user, pwd = self._credentials()
        vol = self.vol_var.get()
        self._log(f'正在设置音量 {vol}…')
        self._busy(True)
        def done(results):
            for name, ok in results:
                self._log(f'  {"成功" if ok else "失败"} · {name} · 音量 {vol}')
        self.backend.call(self.backend.control,
                          self._callback('音量', done), idx, 'volume', vol, user, pwd)

    def on_play_url(self):
        url = self.url_var.get().strip()
        if not url.startswith('http'):
            messagebox.showwarning('提示', '请输入以 http:// 或 https:// 开头的音频地址。', parent=self.root)
            return
        idx = self._indices()
        user, pwd = self._credentials()
        self._log(f'正在播放链接：{url[:80]}')
        self._busy(True)
        def done(results):
            for name, ok in results:
                self._log(f'  {"成功" if ok else "失败"} · {name} · 播放链接')
        self.backend.call(self.backend.play_url, self._callback('播放链接', done), idx, url, user, pwd)

    def on_pick_file(self):
        types = [('音频文件', '*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.wma'),
                 ('所有文件', '*.*')]
        path = filedialog.askopenfilename(title='选择本地音频文件', filetypes=types, parent=self.root)
        if path:
            self.local_var.set(path)
            size = os.path.getsize(path) / 1024 / 1024
            self._log(f'已选择音频：{os.path.basename(path)}（{size:.1f} MB）')

    def on_play_local(self):
        path = self.local_var.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showwarning('提示', '请先浏览并选择要播放的本地音频文件。', parent=self.root)
            return
        user, pwd = self._credentials()
        if not user or not pwd:
            messagebox.showwarning('提示', '请先填写账号密码并获取设备。', parent=self.root)
            return
        try:
            port = int(self.port_var.get().strip() or 0)
        except ValueError:
            messagebox.showwarning('提示', '端口必须是数字（0 表示自动分配）。', parent=self.root)
            return
        idx = self._indices()
        ip = get_lan_ip()
        self._log(f'正在准备本地音频服务：{os.path.basename(path)}'
                  f'{f"（本机 IP {ip}）" if ip else ""}')
        self._busy(True)
        def done(payload):
            results, url = payload
            self._log(f'音频地址：{url}')
            if not results:
                self._log('没有可用设备。')
                return
            for name, ok in results:
                self._log(f'  {"成功" if ok else "失败"} · {name} · 播放本地音频')
        self.backend.call(self.backend.play_local_file,
                          self._callback('本地音频', done), idx, path, port, user, pwd)

    def _on_close(self):
        self._save_remember()
        self.backend.call(self.backend.close)
        self.backend.stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        app = App(root)  # noqa: F841 - keep reference
        root.mainloop()
    except Exception:
        traceback.print_exc()
        messagebox.showerror('启动失败', traceback.format_exc())


if __name__ == '__main__':
    main()
