"""
AOE2 DE Replay 分析工具 — GUI Launcher
用法: python launcher.py  (或直接雙擊)
"""
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import subprocess, sys, threading, json, webbrowser, os, shutil
from pathlib import Path

# 打包成 exe 後，__file__ 在暫存目錄；用 sys.executable 的父目錄當根目錄
if getattr(sys, 'frozen', False):
    PROJECT_ROOT = Path(sys.executable).parent
    _PYTHON_EXE  = shutil.which('python') or shutil.which('python3') or 'python'
else:
    PROJECT_ROOT = Path(__file__).parent
    _PYTHON_EXE  = sys.executable

SCRIPTS_DIR  = PROJECT_ROOT / "scripts"
HISTORY_FILE = PROJECT_ROOT / ".analyzer_history.json"

STEPS = [
    ("① 解析標頭",        "parse_replay.py"),
    ("② 解析主體",        "parse_body.py"),
    ("③ 深度分析",        "parse_body_deep.py"),
    ("④ 文字報告",        "analyze.py"),
    ("⑤ 生成 HTML 報告",  "generate_web_report.py"),
]

# Palette
BG     = "#1a1a2e"
CARD   = "#16213e"
BORDER = "#0f3460"
GOLD   = "#c8a45e"
TEXT   = "#e8e8e8"
MUTED  = "#666"
WIN    = "#4caf50"
ERR    = "#ef5350"
WARN   = "#ff9800"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("⚔️  AOE2 DE Replay 分析工具")
        self.configure(bg=BG)
        self.minsize(700, 560)
        self._out_html = None
        self._out_txt  = None
        self._history  = []
        self._build_ui()
        self._load_history()
        # Center
        self.update_idletasks()
        W, H = 780, 620
        x = (self.winfo_screenwidth()  - W) // 2
        y = (self.winfo_screenheight() - H) // 2
        self.geometry(f"{W}x{H}+{x}+{y}")

    # ── UI Construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        # Header bar
        hdr = tk.Frame(self, bg=GOLD, pady=0)
        hdr.pack(fill="x")
        tk.Label(hdr, text="  ⚔️  AOE2 DE Replay 分析工具",
                 font=("Segoe UI", 14, "bold"), bg=GOLD, fg="#1a1a2e",
                 pady=10).pack(side="left")
        tk.Label(hdr, text="Age of Empires II DE  ",
                 font=("Segoe UI", 9), bg=GOLD, fg="#5a3a0a").pack(side="right")

        # Main body
        body = tk.Frame(self, bg=BG, padx=16, pady=12)
        body.pack(fill="both", expand=True)

        # ── File selection ──────────────────────────────────────────────────
        file_frame = self._lframe(body, " 選擇 .aoe2record 紀錄檔 ")
        file_frame.pack(fill="x", pady=(0, 10))
        inner = tk.Frame(file_frame, bg=CARD, padx=8, pady=8)
        inner.pack(fill="x")

        self.path_var = tk.StringVar()
        self._path_entry = tk.Entry(
            inner, textvariable=self.path_var,
            font=("Segoe UI", 10), bg="#0f2040", fg=TEXT,
            insertbackground=TEXT, relief="flat", bd=0,
            highlightthickness=1, highlightbackground=BORDER,
        )
        self._path_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))

        self._btn(inner, "瀏覽…", self._browse).pack(side="left")

        # Recent files dropdown
        self._recent_menu_btn = tk.Menubutton(
            inner, text="最近 ▾", bg=BORDER, fg=MUTED,
            relief="flat", font=("Segoe UI", 9), padx=10, pady=6, cursor="hand2",
        )
        self._recent_menu = tk.Menu(self._recent_menu_btn, tearoff=0,
                                    bg=CARD, fg=TEXT, activebackground=BORDER)
        self._recent_menu_btn["menu"] = self._recent_menu
        self._recent_menu_btn.pack(side="left", padx=(6, 0))

        # ── Start button ────────────────────────────────────────────────────
        self.start_btn = tk.Button(
            body, text="▶   開始分析", command=self._start,
            bg=GOLD, fg="#1a1a2e", font=("Segoe UI", 12, "bold"),
            relief="flat", pady=10, cursor="hand2", activebackground="#e0b96e",
        )
        self.start_btn.pack(fill="x", pady=(0, 10))

        # ── Progress bar ────────────────────────────────────────────────────
        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("gold.Horizontal.TProgressbar",
                         troughcolor=CARD, background=GOLD, borderwidth=0)
        self.progress = ttk.Progressbar(
            body, style="gold.Horizontal.TProgressbar",
            mode="indeterminate", length=100,
        )
        self.progress.pack(fill="x", pady=(0, 8))

        # ── Steps indicator ─────────────────────────────────────────────────
        steps_outer = self._lframe(body, " 分析步驟 ")
        steps_outer.pack(fill="x", pady=(0, 10))
        steps_inner = tk.Frame(steps_outer, bg=CARD)
        steps_inner.pack(fill="x", padx=6, pady=4)

        self._step_icons  = []
        self._step_labels = []
        for i, (name, _) in enumerate(STEPS):
            col = tk.Frame(steps_inner, bg=CARD)
            col.pack(side="left", expand=True)
            icon = tk.Label(col, text="○", font=("Segoe UI", 13),
                            bg=CARD, fg=MUTED)
            icon.pack()
            lbl = tk.Label(col, text=name, font=("Segoe UI", 8),
                           bg=CARD, fg=MUTED, wraplength=110, justify="center")
            lbl.pack()
            self._step_icons.append(icon)
            self._step_labels.append(lbl)
            if i < len(STEPS) - 1:
                tk.Frame(steps_inner, bg=BORDER, width=1).pack(
                    side="left", fill="y", padx=2)

        # ── Log ─────────────────────────────────────────────────────────────
        log_frame = self._lframe(body, " 分析日誌 ")
        log_frame.pack(fill="both", expand=True, pady=(0, 10))
        self.log = scrolledtext.ScrolledText(
            log_frame, font=("Consolas", 9), bg="#0d1b2a", fg="#aabbcc",
            insertbackground=TEXT, relief="flat", bd=0,
            state="disabled", wrap="word", height=8,
        )
        self.log.pack(fill="both", expand=True, padx=4, pady=4)
        self.log.tag_configure("ok",   foreground=WIN)
        self.log.tag_configure("err",  foreground=ERR)
        self.log.tag_configure("warn", foreground=WARN)
        self.log.tag_configure("step", foreground=GOLD,
                               font=("Consolas", 9, "bold"))
        self.log.tag_configure("info", foreground="#aabbcc")

        # ── Action buttons ───────────────────────────────────────────────────
        btn_row = tk.Frame(body, bg=BG)
        btn_row.pack(fill="x")

        self.html_btn = tk.Button(
            btn_row, text="🌐  開啟 HTML 報告", command=self._open_html,
            bg=BORDER, fg=GOLD, font=("Segoe UI", 10), relief="flat",
            padx=14, pady=7, cursor="hand2", state="disabled",
            activebackground="#1a4a80",
        )
        self.html_btn.pack(side="left", padx=(0, 8))

        self.txt_btn = tk.Button(
            btn_row, text="📄  開啟文字報告", command=self._open_txt,
            bg=BORDER, fg=MUTED, font=("Segoe UI", 10), relief="flat",
            padx=14, pady=7, cursor="hand2", state="disabled",
            activebackground="#1a4a80",
        )
        self.txt_btn.pack(side="left")

        self._status_lbl = tk.Label(
            btn_row, text="", font=("Segoe UI", 9),
            bg=BG, fg=MUTED,
        )
        self._status_lbl.pack(side="right")

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _lframe(self, parent, text):
        return tk.LabelFrame(parent, text=text, bg=CARD, fg=GOLD,
                             font=("Segoe UI", 9), bd=1, relief="solid")

    def _btn(self, parent, text, cmd):
        return tk.Button(parent, text=text, command=cmd,
                         bg=BORDER, fg=GOLD, relief="flat",
                         font=("Segoe UI", 9), padx=12, pady=5,
                         cursor="hand2", activebackground="#1a4a80")

    # ── History ───────────────────────────────────────────────────────────────
    def _load_history(self):
        try:
            if HISTORY_FILE.exists():
                self._history = json.loads(
                    HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            self._history = []
        self._refresh_recent()

    def _save_history(self, path: str):
        if path in self._history:
            self._history.remove(path)
        self._history.insert(0, path)
        self._history = self._history[:10]
        try:
            HISTORY_FILE.write_text(
                json.dumps(self._history, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        self._refresh_recent()

    def _refresh_recent(self):
        self._recent_menu.delete(0, "end")
        if not self._history:
            self._recent_menu.add_command(label="（無紀錄）", state="disabled")
            return
        for p in self._history:
            name = Path(p).name
            self._recent_menu.add_command(
                label=name,
                command=lambda v=p: self.path_var.set(v),
            )

    # ── Browse ────────────────────────────────────────────────────────────────
    def _browse(self):
        replays_dir = PROJECT_ROOT / "replays"
        init_dir = str(replays_dir) if replays_dir.exists() else str(PROJECT_ROOT)
        path = filedialog.askopenfilename(
            title="選擇 AOE2 紀錄檔",
            initialdir=init_dir,
            filetypes=[("AOE2 Replay", "*.aoe2record"), ("所有檔案", "*.*")],
        )
        if path:
            self.path_var.set(path)

    # ── Log write (thread-safe via after) ─────────────────────────────────────
    def _log(self, msg: str, tag: str = "info"):
        def _do():
            self.log.config(state="normal")
            self.log.insert("end", msg + "\n", tag)
            self.log.see("end")
            self.log.config(state="disabled")
        self.after(0, _do)

    def _set_step(self, idx: int, state: str):
        icons  = {"wait": ("○", MUTED), "run": ("◉", GOLD),
                  "ok":   ("✓", WIN),   "err": ("✗", ERR)}
        ic, color = icons.get(state, ("○", MUTED))
        fg_lbl    = TEXT if state in ("run", "ok", "err") else MUTED
        self.after(0, lambda: (
            self._step_icons[idx].config(text=ic, fg=color),
            self._step_labels[idx].config(fg=fg_lbl),
        ))

    def _set_status(self, msg: str, color: str = MUTED):
        self.after(0, lambda: self._status_lbl.config(text=msg, fg=color))

    # ── Pipeline ──────────────────────────────────────────────────────────────
    def _start(self):
        path = self.path_var.get().strip()
        if not path:
            self._log("⚠  請先選擇 .aoe2record 檔案", "warn")
            return
        if not Path(path).exists():
            self._log(f"⚠  找不到檔案: {path}", "err")
            return

        # Reset UI
        self.start_btn.config(state="disabled", text="分析中…")
        self.html_btn.config(state="disabled")
        self.txt_btn.config(state="disabled")
        self._out_html = self._out_txt = None
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")
        for i in range(len(STEPS)):
            self._set_step(i, "wait")
        self.progress.start(12)

        threading.Thread(target=self._run_pipeline,
                         args=(path,), daemon=True).start()

    def _run_pipeline(self, replay_path: str):
        base     = Path(replay_path)
        out_html = Path(str(base.with_suffix("")) + "_report.html")
        out_txt  = Path(str(base.with_suffix("")) + "_report.txt")

        self._log(f"📂  {base.name}", "step")
        self._log(f"📁  {base.parent}", "info")
        self._log("", "info")
        self._set_status("分析中…", WARN)

        success = True
        for i, (name, script) in enumerate(STEPS):
            script_path = SCRIPTS_DIR / script
            if not script_path.exists():
                self._log(f"  ⚠  找不到腳本: {script}，跳過", "warn")
                self._set_step(i, "ok")   # treat as skipped/ok
                continue

            self._set_step(i, "run")
            self._log(f"── {name} ──", "step")

            cmd = [_PYTHON_EXE, str(script_path), str(replay_path)]
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                    cwd=str(PROJECT_ROOT),
                )
                for line in proc.stdout:
                    line = line.rstrip()
                    if not line:
                        continue
                    lo = line.lower()
                    if any(k in lo for k in ("error", "traceback", "exception")):
                        tag = "err"
                    elif any(k in lo for k in ("warn", "warning")):
                        tag = "warn"
                    elif any(k in lo for k in ("saved", "✓", "ok", "done", "complete")):
                        tag = "ok"
                    else:
                        tag = "info"
                    self._log("  " + line, tag)
                proc.wait()

                if proc.returncode != 0:
                    self._set_step(i, "err")
                    self._log(f"  ✗  步驟失敗 (exit {proc.returncode})", "err")
                    success = False
                    break
                else:
                    self._set_step(i, "ok")

            except Exception as exc:
                self._set_step(i, "err")
                self._log(f"  ✗  例外錯誤: {exc}", "err")
                success = False
                break

        self.after(0, self.progress.stop)

        if success:
            self._log("", "info")
            self._log("✅  分析完成！", "ok")
            self._set_status("完成", WIN)
            self.after(0, self._on_done,
                       str(out_html), str(out_txt), replay_path)
        else:
            self._log("", "info")
            self._log("❌  分析中斷，請查看上方日誌", "err")
            self._set_status("失敗", ERR)
            self.after(0, self.start_btn.config,
                       {"state": "normal", "text": "▶   開始分析"})

    def _on_done(self, html_path: str, txt_path: str, replay_path: str):
        if Path(html_path).exists():
            self._out_html = html_path
            self.html_btn.config(state="normal")
            webbrowser.open("file:///" + Path(html_path).as_posix())
            self._log(f"🌐  HTML 報告已開啟: {Path(html_path).name}", "ok")
        if Path(txt_path).exists():
            self._out_txt = txt_path
            self.txt_btn.config(state="normal")

        self._save_history(replay_path)
        self.start_btn.config(state="normal", text="▶   開始分析")

    # ── Open report buttons ───────────────────────────────────────────────────
    def _open_html(self):
        if self._out_html:
            webbrowser.open("file:///" + Path(self._out_html).as_posix())

    def _open_txt(self):
        if self._out_txt:
            os.startfile(self._out_txt)


if __name__ == "__main__":
    app = App()
    app.mainloop()
