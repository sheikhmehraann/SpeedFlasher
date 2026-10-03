#!/usr/bin/env python3
import ctypes
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Optional, Dict, Any

from core.builder import FlashableBuilder, get_current_platform
from core.partitions import scan_partitions, get_zstd_uncompressed_size


def apply_windows_11_mica_theme(window: tk.Tk) -> bool:
    if sys.platform != "win32":
        return False
    try:
        window.update_idletasks()
        hwnd_client = window.winfo_id()
        hwnd = ctypes.windll.user32.GetParent(hwnd_client) or hwnd_client

        c_int = ctypes.c_int
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(c_int(1)), ctypes.sizeof(c_int))
        # DWMWA_WINDOW_CORNER_PREFERENCE = 33 (2 = DWMWCP_ROUND)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(c_int(2)), ctypes.sizeof(c_int))
        # DWMWA_BORDER_COLOR = 34 (0x00333333)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(c_int(0x00363636)), ctypes.sizeof(c_int))
        # DWMWA_CAPTION_COLOR = 35 (0x001B1A18 in BGR)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(c_int(0x001B1A18)), ctypes.sizeof(c_int))
        # DWMWA_SYSTEMBACKDROP_TYPE = 38 (4 = Tabbed / Mica Alt, 2 = Mica)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(c_int(4)), ctypes.sizeof(c_int))
        return True
    except Exception:
        return False


class QueueStdout:
    def __init__(self, log_queue: queue.Queue):
        self.log_queue = log_queue

    def write(self, text: str):
        if text:
            self.log_queue.put(text)

    def flush(self):
        pass


class SpeedFlasherGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SpeedFlasher - Android Flashable Package Maker")
        self.root.geometry("960x780")
        self.root.minsize(860, 680)

        # Theme Colors (Windows 11 Dark Fluent Glass)
        self.C_BG = "#16161a"
        self.C_CARD = "#212128"
        self.C_CARD_BORDER = "#2f2f3b"
        self.C_INPUT = "#1a1a20"
        self.C_INPUT_BORDER = "#383846"
        self.C_INPUT_FOCUS = "#60cdff"
        self.C_TEXT = "#ffffff"
        self.C_TEXT_MUTED = "#9d9da8"
        self.C_ACCENT = "#0078d4"
        self.C_ACCENT_HOVER = "#1888e0"
        self.C_ACCENT_TEXT = "#ffffff"
        self.C_CYAN = "#60cdff"
        self.C_GREEN = "#4cc38a"
        self.C_AMBER = "#f5a623"
        self.C_CONSOLE_BG = "#111114"
        self.C_CONSOLE_TEXT = "#d6d6e0"

        self.root.configure(bg=self.C_BG)
        apply_windows_11_mica_theme(self.root)

        self.partitions_dict: Dict[str, Dict[str, Any]] = {}
        self.build_thread: Optional[threading.Thread] = None
        self.log_queue: queue.Queue = queue.Queue()
        self.last_output_zip: Optional[str] = None

        self._configure_styles()
        self._build_ui()
        self._start_log_consumer()

    def _configure_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        # TProgressbar
        style.configure(
            "Fluent.Horizontal.TProgressbar",
            troughcolor=self.C_INPUT,
            background=self.C_CYAN,
            lightcolor=self.C_CYAN,
            darkcolor=self.C_CYAN,
            bordercolor=self.C_CARD_BORDER,
            thickness=6
        )

        # TCombobox
        style.configure(
            "Fluent.TCombobox",
            background=self.C_INPUT,
            fieldbackground=self.C_INPUT,
            foreground=self.C_TEXT,
            darkcolor=self.C_CARD_BORDER,
            lightcolor=self.C_CARD_BORDER,
            arrowcolor=self.C_CYAN,
            bordercolor=self.C_INPUT_BORDER,
            padding=5
        )
        style.map(
            "Fluent.TCombobox",
            fieldbackground=[("readonly", self.C_INPUT)],
            selectbackground=[("readonly", self.C_CARD)],
            selectforeground=[("readonly", self.C_TEXT)]
        )

        # TScale
        style.configure(
            "Fluent.Horizontal.TScale",
            background=self.C_CARD,
            troughcolor=self.C_INPUT,
            bordercolor=self.C_CARD_BORDER,
            lightcolor=self.C_CYAN,
            darkcolor=self.C_CYAN
        )

    def _build_ui(self):
        main_frame = tk.Frame(self.root, bg=self.C_BG)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)

        # 1. Top Header Banner
        header = tk.Frame(main_frame, bg=self.C_BG)
        header.pack(fill=tk.X, pady=(0, 12))

        title_lbl = tk.Label(
            header,
            text="SpeedFlasher",
            font=("Segoe UI Variable Display", 18, "bold"),
            fg=self.C_TEXT,
            bg=self.C_BG
        )
        title_lbl.pack(side=tk.LEFT)

        sub_lbl = tk.Label(
            header,
            text="Universal Android Flashable Package Maker",
            font=("Segoe UI Variable Text", 10),
            fg=self.C_TEXT_MUTED,
            bg=self.C_BG
        )
        sub_lbl.pack(side=tk.LEFT, padx=(12, 0), pady=(4, 0))

        # Target badge pills on header right
        badges_frame = tk.Frame(header, bg=self.C_BG)
        badges_frame.pack(side=tk.RIGHT)

        for text, color in [("Windows", self.C_CYAN), ("Linux", self.C_GREEN), ("Termux", self.C_AMBER), ("Recovery A/B", self.C_TEXT)]:
            b = tk.Label(
                badges_frame,
                text=text,
                font=("Segoe UI Variable Text", 8, "bold"),
                fg=color,
                bg="#262633",
                padx=8,
                pady=2,
                relief=tk.FLAT
            )
            b.pack(side=tk.LEFT, padx=3)

        # 2. Source Partition Selection Card
        src_card = tk.Frame(main_frame, bg=self.C_CARD, highlightthickness=1, highlightbackground=self.C_CARD_BORDER, padx=14, pady=12)
        src_card.pack(fill=tk.X, pady=(0, 10))

        src_head = tk.Frame(src_card, bg=self.C_CARD)
        src_head.pack(fill=tk.X)

        tk.Label(
            src_head,
            text="Partition Images Directory",
            font=("Segoe UI Variable Text", 10, "bold"),
            fg=self.C_TEXT,
            bg=self.C_CARD
        ).pack(side=tk.LEFT)

        self.scan_status_lbl = tk.Label(
            src_head,
            text="Select partition folder to scan",
            font=("Segoe UI Variable Text", 9),
            fg=self.C_TEXT_MUTED,
            bg=self.C_CARD
        )
        self.scan_status_lbl.pack(side=tk.RIGHT)

        input_row = tk.Frame(src_card, bg=self.C_CARD)
        input_row.pack(fill=tk.X, pady=(8, 8))

        self.path_var = tk.StringVar()
        self.path_entry = tk.Entry(
            input_row,
            textvariable=self.path_var,
            font=("Segoe UI Variable Text", 10),
            bg=self.C_INPUT,
            fg=self.C_TEXT,
            insertbackground=self.C_TEXT,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=self.C_INPUT_BORDER,
            highlightcolor=self.C_INPUT_FOCUS
        )
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5, padx=(0, 8))
        self.path_entry.bind("<KeyRelease>", lambda e: self._on_path_changed())

        browse_btn = tk.Button(
            input_row,
            text="Browse...",
            font=("Segoe UI Variable Text", 9, "bold"),
            bg="#2c2c36",
            fg=self.C_TEXT,
            activebackground="#383846",
            activeforeground=self.C_TEXT,
            relief=tk.FLAT,
            padx=14,
            pady=4,
            cursor="hand2",
            command=self._browse_folder
        )
        browse_btn.pack(side=tk.RIGHT)

        # Partition breakdown pills
        self.chips_frame = tk.Frame(src_card, bg=self.C_CARD)
        self.chips_frame.pack(fill=tk.X)

        self.chip_total = self._create_badge(self.chips_frame, "Total: 0", self.C_TEXT_MUTED)
        self.chip_super = self._create_badge(self.chips_frame, "Dynamic: 0", self.C_CYAN)
        self.chip_boot = self._create_badge(self.chips_frame, "Bootchain: 0", self.C_GREEN)
        self.chip_firmware = self._create_badge(self.chips_frame, "Firmware: 0", self.C_AMBER)
        self.chip_size = self._create_badge(self.chips_frame, "Size: 0 MB", self.C_TEXT_MUTED)

        # 3. Two-Column Configuration Card
        config_card = tk.Frame(main_frame, bg=self.C_CARD, highlightthickness=1, highlightbackground=self.C_CARD_BORDER, padx=14, pady=12)
        config_card.pack(fill=tk.X, pady=(0, 10))

        # Split 2 Columns
        col_left = tk.Frame(config_card, bg=self.C_CARD)
        col_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 12))

        col_right = tk.Frame(config_card, bg=self.C_CARD)
        col_right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(12, 0))

        # Column Left: Device & Version
        self.dev_var = tk.StringVar(value="Android Device")
        self.code_var = tk.StringVar(value="")
        self.ver_var = tk.StringVar(value="1.0")
        self.maint_var = tk.StringVar(value="Mehraan")

        self._create_field(col_left, "Device Name", self.dev_var)
        self._create_field(col_left, "Codename", self.code_var)
        self._create_field(col_left, "ROM Version", self.ver_var)
        self._create_field(col_left, "Maintainer", self.maint_var)

        # Column Right: Engine Tuning
        tk.Label(
            col_right,
            text="AVB 2.0 (vbmeta)",
            font=("Segoe UI Variable Text", 9, "bold"),
            fg=self.C_TEXT,
            bg=self.C_CARD
        ).pack(anchor=tk.W)

        self.avb_var = tk.StringVar(value="skip")
        avb_combo = ttk.Combobox(
            col_right,
            textvariable=self.avb_var,
            values=["skip", "disable", "enable"],
            state="readonly",
            style="Fluent.TCombobox"
        )
        avb_combo.pack(fill=tk.X, pady=(2, 8))

        # ZSTD Slider
        zstd_head = tk.Frame(col_right, bg=self.C_CARD)
        zstd_head.pack(fill=tk.X)
        tk.Label(zstd_head, text="Zstandard Compression", font=("Segoe UI Variable Text", 9, "bold"), fg=self.C_TEXT, bg=self.C_CARD).pack(side=tk.LEFT)
        self.zstd_val_lbl = tk.Label(zstd_head, text="Level 1", font=("Segoe UI Variable Text", 9), fg=self.C_CYAN, bg=self.C_CARD)
        self.zstd_val_lbl.pack(side=tk.RIGHT)

        self.zstd_var = tk.IntVar(value=1)
        zstd_slider = ttk.Scale(
            col_right,
            from_=0,
            to=22,
            orient=tk.HORIZONTAL,
            variable=self.zstd_var,
            command=self._on_zstd_slider,
            style="Fluent.Horizontal.TScale"
        )
        zstd_slider.pack(fill=tk.X, pady=(2, 8))

        # ZIP Slider
        zip_head = tk.Frame(col_right, bg=self.C_CARD)
        zip_head.pack(fill=tk.X)
        tk.Label(zip_head, text="ZIP Archive Compression", font=("Segoe UI Variable Text", 9, "bold"), fg=self.C_TEXT, bg=self.C_CARD).pack(side=tk.LEFT)
        self.zip_val_lbl = tk.Label(zip_head, text="Level 1", font=("Segoe UI Variable Text", 9), fg=self.C_CYAN, bg=self.C_CARD)
        self.zip_val_lbl.pack(side=tk.RIGHT)

        self.zip_var = tk.IntVar(value=1)
        zip_slider = ttk.Scale(
            col_right,
            from_=0,
            to=9,
            orient=tk.HORIZONTAL,
            variable=self.zip_var,
            command=self._on_zip_slider,
            style="Fluent.Horizontal.TScale"
        )
        zip_slider.pack(fill=tk.X, pady=(2, 8))

        # 4. Action & Build Bar
        action_bar = tk.Frame(main_frame, bg=self.C_BG)
        action_bar.pack(fill=tk.X, pady=(0, 8))

        self.build_btn = tk.Button(
            action_bar,
            text="Build Flashable Package",
            font=("Segoe UI Variable Text", 10, "bold"),
            bg=self.C_ACCENT,
            fg=self.C_ACCENT_TEXT,
            activebackground=self.C_ACCENT_HOVER,
            activeforeground=self.C_ACCENT_TEXT,
            relief=tk.FLAT,
            padx=20,
            pady=7,
            cursor="hand2",
            command=self._start_build
        )
        self.build_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.open_out_btn = tk.Button(
            action_bar,
            text="Open Output Folder",
            font=("Segoe UI Variable Text", 9),
            bg="#2c2c36",
            fg=self.C_TEXT,
            activebackground="#383846",
            activeforeground=self.C_TEXT,
            relief=tk.FLAT,
            padx=14,
            pady=7,
            cursor="hand2",
            command=self._open_output_dir
        )
        self.open_out_btn.pack(side=tk.LEFT)

        self.status_msg_lbl = tk.Label(
            action_bar,
            text="Ready",
            font=("Segoe UI Variable Text", 9),
            fg=self.C_TEXT_MUTED,
            bg=self.C_BG
        )
        self.status_msg_lbl.pack(side=tk.RIGHT, padx=4)

        # Progress bar
        self.progress = ttk.Progressbar(
            main_frame,
            style="Fluent.Horizontal.TProgressbar",
            mode="indeterminate"
        )
        self.progress.pack(fill=tk.X, pady=(0, 8))

        # 5. Live Terminal Log Console
        console_card = tk.Frame(main_frame, bg=self.C_CONSOLE_BG, highlightthickness=1, highlightbackground=self.C_CARD_BORDER)
        console_card.pack(fill=tk.BOTH, expand=True)

        log_head = tk.Frame(console_card, bg=self.C_CONSOLE_BG, padx=8, pady=4)
        log_head.pack(fill=tk.X)

        tk.Label(
            log_head,
            text="Build Output Stream",
            font=("Segoe UI Variable Text", 9, "bold"),
            fg=self.C_TEXT_MUTED,
            bg=self.C_CONSOLE_BG
        ).pack(side=tk.LEFT)

        clear_btn = tk.Button(
            log_head,
            text="Clear Log",
            font=("Segoe UI Variable Text", 8),
            bg="#1d1d24",
            fg=self.C_TEXT_MUTED,
            activebackground="#2a2a34",
            activeforeground=self.C_TEXT,
            relief=tk.FLAT,
            padx=8,
            pady=1,
            cursor="hand2",
            command=self._clear_log
        )
        clear_btn.pack(side=tk.RIGHT)

        self.log_text = tk.Text(
            console_card,
            bg=self.C_CONSOLE_BG,
            fg=self.C_CONSOLE_TEXT,
            insertbackground=self.C_TEXT,
            font=("Consolas", 9),
            relief=tk.FLAT,
            padx=10,
            pady=6,
            wrap=tk.CHAR
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scroll = tk.Scrollbar(console_card, command=self.log_text.yview, bg=self.C_CONSOLE_BG, relief=tk.FLAT)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scroll.set)

    def _create_badge(self, parent: tk.Widget, text: str, color: str) -> tk.Label:
        lbl = tk.Label(
            parent,
            text=text,
            font=("Segoe UI Variable Text", 8, "bold"),
            fg=color,
            bg="#262633",
            padx=8,
            pady=3,
            relief=tk.FLAT
        )
        lbl.pack(side=tk.LEFT, padx=(0, 6), pady=(4, 0))
        return lbl

    def _create_field(self, parent: tk.Widget, label_text: str, var: tk.StringVar):
        tk.Label(
            parent,
            text=label_text,
            font=("Segoe UI Variable Text", 9, "bold"),
            fg=self.C_TEXT,
            bg=self.C_CARD
        ).pack(anchor=tk.W)

        e = tk.Entry(
            parent,
            textvariable=var,
            font=("Segoe UI Variable Text", 9),
            bg=self.C_INPUT,
            fg=self.C_TEXT,
            insertbackground=self.C_TEXT,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=self.C_INPUT_BORDER,
            highlightcolor=self.C_INPUT_FOCUS
        )
        e.pack(fill=tk.X, pady=(2, 6), ipady=3)

    def _on_zstd_slider(self, val):
        lvl = int(float(val))
        self.zstd_var.set(lvl)
        desc = "Fast / Multi-thread" if lvl <= 3 else ("Ultra" if lvl >= 20 else "Standard")
        self.zstd_val_lbl.config(text=f"Level {lvl} ({desc})")

    def _on_zip_slider(self, val):
        lvl = int(float(val))
        self.zip_var.set(lvl)
        desc = "Store" if lvl == 0 else ("Fast" if lvl == 1 else f"Deflate {lvl}")
        self.zip_val_lbl.config(text=f"Level {lvl} ({desc})")

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="Select Extracted Partition Images Directory")
        if folder:
            self.path_var.set(os.path.abspath(folder))
            self._scan_folder(os.path.abspath(folder))

    def _on_path_changed(self):
        p = self.path_var.get().strip()
        if p and os.path.isdir(p):
            self._scan_folder(p)

    def _scan_folder(self, path: str):
        try:
            parts = scan_partitions(path)
            self.partitions_dict = parts
            if not parts:
                self.scan_status_lbl.config(text="No partition images found (.img / .img.zst)", fg=self.C_AMBER)
                self._update_badges(0, 0, 0, 0, 0)
                return

            super_cnt = sum(1 for p in parts.values() if p["type"] in ("super", "super_tr"))
            boot_cnt = sum(1 for p in parts.values() if p["type"] == "system")
            fw_cnt = sum(1 for p in parts.values() if p["type"] == "firmware")
            total_cnt = len(parts)

            total_bytes = 0
            for p in parts.values():
                if p["is_zstd"]:
                    sz = get_zstd_uncompressed_size(p["path"])
                    total_bytes += sz or os.path.getsize(p["path"])
                else:
                    total_bytes += os.path.getsize(p["path"])

            size_mb = total_bytes / (1024 * 1024)
            self._update_badges(total_cnt, super_cnt, boot_cnt, fw_cnt, size_mb)
            self.scan_status_lbl.config(text=f"Found {total_cnt} partition images", fg=self.C_GREEN)

            # Auto-detect build.prop
            self._inspect_build_prop(path)
        except Exception as e:
            self.scan_status_lbl.config(text=f"Scan error: {e}", fg=self.C_AMBER)

    def _update_badges(self, total: int, super_c: int, boot_c: int, fw_c: int, size_mb: float):
        self.chip_total.config(text=f"Total: {total}")
        self.chip_super.config(text=f"Dynamic: {super_c}")
        self.chip_boot.config(text=f"Bootchain: {boot_c}")
        self.chip_firmware.config(text=f"Firmware: {fw_c}")
        if size_mb >= 1024:
            self.chip_size.config(text=f"Size: {size_mb / 1024:.2f} GB")
        else:
            self.chip_size.config(text=f"Size: {size_mb:.1f} MB")

    def _inspect_build_prop(self, search_dir: str):
        def_device = ""
        def_codename = ""
        def_version = ""

        for root, _, files in os.walk(search_dir):
            for f in files:
                if f.endswith(".prop") or f == "build.prop":
                    try:
                        with open(os.path.join(root, f), "r", encoding="utf-8", errors="ignore") as pf:
                            for line in pf:
                                line = line.strip()
                                if "=" not in line or line.startswith("#"):
                                    continue
                                k, v = line.split("=", 1)
                                k, v = k.strip(), v.strip()
                                if k in ("ro.product.device", "ro.build.product", "ro.product.board") and not def_codename:
                                    def_codename = v
                                elif k in ("ro.product.model", "ro.product.marketname") and not def_device:
                                    def_device = v
                                elif k in ("ro.build.display.id", "ro.build.version.incremental") and not def_version:
                                    def_version = v
                    except OSError:
                        pass

        if def_device and self.dev_var.get() in ("Android Device", ""):
            self.dev_var.set(def_device)
        if def_codename and not self.code_var.get():
            self.code_var.set(def_codename)
        if def_version and self.ver_var.get() in ("1.0", ""):
            self.ver_var.set(def_version)

    def _clear_log(self):
        self.log_text.delete("1.0", tk.END)

    def _start_log_consumer(self):
        def check_queue():
            while True:
                try:
                    msg = self.log_queue.get_nowait()
                    self.log_text.insert(tk.END, msg)
                    self.log_text.see(tk.END)
                except queue.Empty:
                    break
            self.root.after(40, check_queue)

        self.root.after(40, check_queue)

    def _start_build(self):
        imgs_path = self.path_var.get().strip()
        if not imgs_path or not os.path.isdir(imgs_path):
            self.status_msg_lbl.config(text="Select a valid partition directory first", fg=self.C_AMBER)
            return

        if not self.partitions_dict:
            self._scan_folder(imgs_path)
            if not self.partitions_dict:
                self.status_msg_lbl.config(text="No images to package in directory", fg=self.C_AMBER)
                return

        self.build_btn.config(state=tk.DISABLED, text="Building Package...")
        self.progress.start(10)
        self.status_msg_lbl.config(text="Packaging in progress...", fg=self.C_CYAN)

        root_dir = os.path.dirname(os.path.abspath(__file__))
        out_dir = os.path.join(root_dir, "output")
        os.makedirs(out_dir, exist_ok=True)

        ver = self.ver_var.get().strip() or "1.0"
        code = self.code_var.get().strip()
        out_name = f"{ver}-{code}-Flashable.zip" if code else f"{ver}-Flashable.zip"
        output_zip = os.path.join(out_dir, out_name)

        params = {
            "output_zip": output_zip,
            "device": self.dev_var.get().strip() or "Android Device",
            "firmware": ver,
            "codename": code,
            "imgs_dir": imgs_path,
            "partitions": self.partitions_dict,
            "maintainer": self.maint_var.get().strip() or "Mehraan",
            "vbmeta_option": self.avb_var.get(),
            "zstd_level": self.zstd_var.get(),
            "zip_level": self.zip_var.get(),
            "include_fastboot": True
        }

        self.build_thread = threading.Thread(target=self._run_build_worker, args=(params,), daemon=True)
        self.build_thread.start()

    def _run_build_worker(self, params: Dict[str, Any]):
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        redirector = QueueStdout(self.log_queue)
        sys.stdout = redirector
        sys.stderr = redirector

        success = False
        err_msg = ""
        try:
            res = FlashableBuilder.build(**params)
            self.last_output_zip = str(res)
            success = True
        except Exception as e:
            err_msg = str(e)
            print(f"\n[Error] Build failed: {e}")
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            self.root.after(0, lambda: self._on_build_completed(success, err_msg))

    def _on_build_completed(self, success: bool, err: str):
        self.progress.stop()
        self.build_btn.config(state=tk.NORMAL, text="Build Flashable Package")

        if success:
            self.status_msg_lbl.config(text="Build Succeeded!", fg=self.C_GREEN)
            if self.last_output_zip and os.path.isfile(self.last_output_zip):
                sz_mb = os.path.getsize(self.last_output_zip) / (1024 * 1024)
                print(f"\n========================================================================")
                print(f"                      Package Ready")
                print(f"========================================================================")
                print(f"Output File : {self.last_output_zip}")
                print(f"Size        : {sz_mb:.2f} MB")
                print(f"Status      : SUCCESS")
                print(f"========================================================================\n")
        else:
            self.status_msg_lbl.config(text=f"Build failed: {err}", fg=self.C_AMBER)

    def _open_output_dir(self):
        target = self.last_output_zip
        if not target or not os.path.isfile(target):
            root_dir = os.path.dirname(os.path.abspath(__file__))
            target = os.path.join(root_dir, "output")

        if sys.platform == "win32":
            if os.path.isfile(target):
                subprocess.run(f'explorer /select,"{target}"', shell=True)
            else:
                os.startfile(target)
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R" if os.path.isfile(target) else "", target])
        else:
            subprocess.run(["xdg-open", os.path.dirname(target) if os.path.isfile(target) else target])


def launch_gui():
    root = tk.Tk()
    app = SpeedFlasherGUI(root)
    root.mainloop()


if __name__ == "__main__":
    launch_gui()
