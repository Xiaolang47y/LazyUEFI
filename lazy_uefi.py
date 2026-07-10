#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LazyUEFI - A simple GUI tool to manage UEFI boot entries on Linux.
Requires: efibootmgr, python3-tk (tkinter)
"""

import os
import re
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk


class EfiBootEntry:
    def __init__(self, num: str, active: bool, name: str, path: str):
        self.num = num
        self.active = active
        self.name = name
        self.path = path

    def __repr__(self):
        return f"EfiBootEntry({self.num}, active={self.active}, name={self.name!r})"


class EfiBootManager:
    EFIBOOTMGR = "efibootmgr"

    @classmethod
    def available(cls) -> bool:
        return shutil.which(cls.EFIBOOTMGR) is not None

    @classmethod
    def run(cls, args: list, use_pkexec: bool = True, check: bool = True):
        """Run efibootmgr with optional privilege escalation."""
        cmd = [cls.EFIBOOTMGR] + args
        if os.geteuid() != 0 and use_pkexec:
            if shutil.which("pkexec"):
                cmd = ["pkexec"] + cmd
            else:
                # Fallback to sudo if pkexec is unavailable
                cmd = ["sudo", "-A"] + cmd
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=check,
            )
            return result
        except subprocess.CalledProcessError as exc:
            err = exc.stderr.strip() or exc.stdout.strip() or str(exc)
            raise RuntimeError(err)

    @classmethod
    def list_entries(cls) -> tuple[list[EfiBootEntry], list[str], str | None, str | None]:
        """
        Return (entries in boot order, raw boot order list, boot_current, timeout).
        """
        result = cls.run(["-v"], use_pkexec=False, check=True)
        lines = result.stdout.splitlines()

        boot_order: list[str] = []
        boot_current: str | None = None
        timeout: str | None = None
        entries: list[EfiBootEntry] = []
        entry_map: dict[str, EfiBootEntry] = {}

        # Pattern for a boot entry line produced by efibootmgr -v
        entry_re = re.compile(
            r"^Boot([0-9a-fA-F]{4})\s*([* ])\s+(.*)$"
        )

        for line in lines:
            line = line.rstrip()
            if line.startswith("BootCurrent:"):
                boot_current = line.split(":", 1)[1].strip()
            elif line.startswith("Timeout:"):
                timeout = line.split(":", 1)[1].strip()
            elif line.startswith("BootOrder:"):
                order_str = line.split(":", 1)[1].strip()
                boot_order = [x.strip() for x in order_str.split(",") if x.strip()]
            else:
                m = entry_re.match(line)
                if m:
                    num = m.group(1).upper()
                    active = m.group(2).strip() == "*"
                    rest = m.group(3).strip()
                    # Split name and device path. With -v the path starts with
                    # tokens like HD(...), PCI(...), ACPI(...), etc.
                    name, path = cls._split_name_path(rest)
                    entry = EfiBootEntry(num, active, name, path)
                    entries.append(entry)
                    entry_map[num] = entry

        ordered_entries = [entry_map[num] for num in boot_order if num in entry_map]
        # Append any entries not in BootOrder (shouldn't normally happen)
        ordered_nums = {e.num for e in ordered_entries}
        for e in entries:
            if e.num not in ordered_nums:
                ordered_entries.append(e)

        return ordered_entries, boot_order, boot_current, timeout

    @staticmethod
    def _split_name_path(rest: str) -> tuple[str, str]:
        """Separate the human-readable label from the device path."""
        # Device path tokens commonly seen in efibootmgr -v output
        path_tokens = (
            "HD(", "PCI(", "ACPI(", "VenMsg(", "VenHw(", "VenMedia(",
            "Media(", "UART(", "USB(", "SCSI(", "SATA(", "NVMe(",
            "MAC(", "IPv4(", "IPv6(", "File(", "Offset(", "MediaPath(",
        )
        for token in path_tokens:
            idx = rest.find(token)
            if idx > 0:
                name = rest[:idx].rstrip()
                path = rest[idx:].strip()
                return name, path
        return rest, ""

    @classmethod
    def create_entry(
        cls,
        label: str,
        loader: str,
        disk: str | None = None,
        part: int | None = None,
    ) -> str:
        args = ["-c", "-L", label, "-l", loader]
        if disk:
            args.extend(["-d", disk])
        if part is not None:
            args.extend(["-p", str(part)])
        result = cls.run(args)
        return result.stdout

    @classmethod
    def delete_entry(cls, num: str) -> str:
        result = cls.run(["-b", num, "-B"])
        return result.stdout

    @classmethod
    def set_active(cls, num: str, active: bool) -> str:
        flag = "-a" if active else "-A"
        result = cls.run(["-b", num, flag])
        return result.stdout

    @classmethod
    def rename_entry(cls, num: str, label: str) -> str:
        result = cls.run(["-b", num, "-L", label])
        return result.stdout

    @classmethod
    def set_boot_order(cls, nums: list[str]) -> str:
        order = ",".join(nums)
        result = cls.run(["-o", order])
        return result.stdout


class EntryDialog(tk.Toplevel):
    def __init__(self, parent, title: str, entry: EfiBootEntry | None = None):
        super().__init__(parent)
        self.entry = entry
        self.result = None
        self.title(title)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._center_on_parent()

        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self):
        pad = {"padx": 8, "pady": 6}

        lbl_name = ttk.Label(self, text="启动项名称:")
        lbl_name.grid(row=0, column=0, sticky=tk.W, **pad)
        self.var_name = tk.StringVar(value=self.entry.name if self.entry else "")
        ent_name = ttk.Entry(self, textvariable=self.var_name, width=50)
        ent_name.grid(row=0, column=1, sticky=tk.EW, **pad)
        ent_name.focus()

        lbl_loader = ttk.Label(self, text="EFI 文件路径:")
        lbl_loader.grid(row=1, column=0, sticky=tk.W, **pad)
        self.var_loader = tk.StringVar(value=self.entry.path if self.entry else "")
        ent_loader = ttk.Entry(self, textvariable=self.var_loader, width=50)
        ent_loader.grid(row=1, column=1, sticky=tk.EW, **pad)

        # Only show disk/partition for new entries
        if self.entry is None:
            lbl_disk = ttk.Label(self, text="磁盘 (可选, 例如 /dev/sda):")
            lbl_disk.grid(row=2, column=0, sticky=tk.W, **pad)
            self.var_disk = tk.StringVar()
            ttk.Entry(self, textvariable=self.var_disk, width=50).grid(
                row=2, column=1, sticky=tk.EW, **pad
            )

            lbl_part = ttk.Label(self, text="分区号 (可选, 例如 1):")
            lbl_part.grid(row=3, column=0, sticky=tk.W, **pad)
            self.var_part = tk.StringVar()
            ttk.Entry(self, textvariable=self.var_part, width=50).grid(
                row=3, column=1, sticky=tk.EW, **pad
            )

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="确定", command=self._on_ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(side=tk.LEFT, padx=5)

        self.columnconfigure(1, weight=1)

    def _center_on_parent(self):
        self.update_idletasks()
        parent = self.master
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _on_ok(self):
        name = self.var_name.get().strip()
        loader = self.var_loader.get().strip()
        if not name:
            messagebox.showerror("错误", "启动项名称不能为空", parent=self)
            return
        if self.entry is None and not loader:
            messagebox.showerror("错误", "EFI 文件路径不能为空", parent=self)
            return

        disk = None
        part = None
        if self.entry is None:
            disk = self.var_disk.get().strip() or None
            part_str = self.var_part.get().strip()
            if part_str:
                try:
                    part = int(part_str)
                except ValueError:
                    messagebox.showerror("错误", "分区号必须是整数", parent=self)
                    return

        self.result = {
            "name": name,
            "loader": loader,
            "disk": disk,
            "part": part,
        }
        self.destroy()


class LazyUEFIApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LazyUEFI - UEFI 启动项管理器")
        self.geometry("900x520")
        self.minsize(700, 400)

        self.entries: list[EfiBootEntry] = []

        self._build_menu()
        self._build_toolbar()
        self._build_tree()
        self._build_statusbar()

        self.load_entries()

    def _build_menu(self):
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="刷新", command=self.load_entries, accelerator="F5")
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.quit)
        menubar.add_cascade(label="文件", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="关于", command=self._show_about)
        menubar.add_cascade(label="帮助", menu=help_menu)

        self.config(menu=menubar)
        self.bind("<F5>", lambda e: self.load_entries())

    def _build_toolbar(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, padx=8, pady=6)

        buttons = [
            ("刷新", self.load_entries),
            ("新建", self.add_entry),
            ("编辑", self.edit_entry),
            ("删除", self.delete_entry),
            ("上移", self.move_up),
            ("下移", self.move_down),
            ("启用", self.enable_entry),
            ("禁用", self.disable_entry),
            ("应用顺序", self.apply_order),
        ]
        for text, cmd in buttons:
            ttk.Button(toolbar, text=text, command=cmd).pack(side=tk.LEFT, padx=2)

    def _build_tree(self):
        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        cols = ("num", "active", "name", "path")
        self.tree = ttk.Treeview(
            frame,
            columns=cols,
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("num", text="编号")
        self.tree.heading("active", text="状态")
        self.tree.heading("name", text="名称")
        self.tree.heading("path", text="路径")

        self.tree.column("num", width=70, anchor=tk.CENTER)
        self.tree.column("active", width=60, anchor=tk.CENTER)
        self.tree.column("name", width=250)
        self.tree.column("path", width=450)

        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky=tk.NSEW)
        vsb.grid(row=0, column=1, sticky=tk.NS)
        hsb.grid(row=1, column=0, sticky=tk.EW)

        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", lambda e: self.edit_entry())

    def _build_statusbar(self):
        self.status = ttk.Label(self, text="就绪", anchor=tk.W)
        self.status.pack(fill=tk.X, side=tk.BOTTOM, padx=8, pady=2)

    def _set_status(self, text: str):
        self.status.config(text=text)
        self.update_idletasks()

    def load_entries(self):
        if not EfiBootManager.available():
            messagebox.showerror(
                "错误",
                "未找到 efibootmgr，请先安装该工具。\n例如：sudo apt install efibootmgr",
            )
            return

        try:
            entries, order, current, timeout = EfiBootManager.list_entries()
        except Exception as exc:
            messagebox.showerror("错误", f"无法读取 UEFI 启动项：\n{exc}")
            return

        self.entries = entries
        self.tree.delete(*self.tree.get_children())
        for e in entries:
            active_text = "启用" if e.active else "禁用"
            values = (f"Boot{e.num}", active_text, e.name, e.path)
            item = self.tree.insert("", tk.END, values=values)
            if current and e.num.upper() == current.upper():
                self.tree.selection_set(item)
                self.tree.see(item)

        info_parts = []
        if current:
            info_parts.append(f"当前启动: Boot{current}")
        if timeout:
            info_parts.append(f"超时: {timeout}")
        info_parts.append(f"共 {len(entries)} 项")
        self._set_status(" | ".join(info_parts))

    def _selected_index(self) -> int | None:
        sel = self.tree.selection()
        if not sel:
            return None
        item = sel[0]
        return self.tree.index(item)

    def add_entry(self):
        dlg = EntryDialog(self, "新建启动项")
        self.wait_window(dlg)
        if dlg.result is None:
            return

        try:
            EfiBootManager.create_entry(
                label=dlg.result["name"],
                loader=dlg.result["loader"],
                disk=dlg.result["disk"],
                part=dlg.result["part"],
            )
            self.load_entries()
        except Exception as exc:
            messagebox.showerror("错误", f"创建失败：\n{exc}")

    def edit_entry(self):
        idx = self._selected_index()
        if idx is None:
            messagebox.showwarning("提示", "请先选择一个启动项")
            return
        entry = self.entries[idx]

        dlg = EntryDialog(self, "编辑启动项", entry=entry)
        self.wait_window(dlg)
        if dlg.result is None:
            return

        try:
            if dlg.result["name"] != entry.name:
                EfiBootManager.rename_entry(entry.num, dlg.result["name"])
            self.load_entries()
        except Exception as exc:
            messagebox.showerror("错误", f"编辑失败：\n{exc}")

    def delete_entry(self):
        idx = self._selected_index()
        if idx is None:
            messagebox.showwarning("提示", "请先选择一个启动项")
            return
        entry = self.entries[idx]
        if not messagebox.askyesno(
            "确认删除",
            f"确定要删除启动项 {entry.num}（{entry.name}）吗？",
        ):
            return
        try:
            EfiBootManager.delete_entry(entry.num)
            self.load_entries()
        except Exception as exc:
            messagebox.showerror("错误", f"删除失败：\n{exc}")

    def move_up(self):
        idx = self._selected_index()
        if idx is None or idx <= 0:
            return
        self.entries[idx - 1], self.entries[idx] = (
            self.entries[idx],
            self.entries[idx - 1],
        )
        self._refresh_tree(select_index=idx - 1)

    def move_down(self):
        idx = self._selected_index()
        if idx is None or idx >= len(self.entries) - 1:
            return
        self.entries[idx + 1], self.entries[idx] = (
            self.entries[idx],
            self.entries[idx + 1],
        )
        self._refresh_tree(select_index=idx + 1)

    def enable_entry(self):
        self._set_active(True)

    def disable_entry(self):
        self._set_active(False)

    def _set_active(self, active: bool):
        idx = self._selected_index()
        if idx is None:
            messagebox.showwarning("提示", "请先选择一个启动项")
            return
        entry = self.entries[idx]
        try:
            EfiBootManager.set_active(entry.num, active)
            self.load_entries()
        except Exception as exc:
            messagebox.showerror("错误", f"操作失败：\n{exc}")

    def apply_order(self):
        if not self.entries:
            return
        nums = [e.num for e in self.entries]
        try:
            EfiBootManager.set_boot_order(nums)
            self.load_entries()
            messagebox.showinfo("成功", "启动顺序已应用")
        except Exception as exc:
            messagebox.showerror("错误", f"应用顺序失败：\n{exc}")

    def _refresh_tree(self, select_index: int | None = None):
        current_idx = self._selected_index()
        self.tree.delete(*self.tree.get_children())
        for e in self.entries:
            active_text = "启用" if e.active else "禁用"
            values = (f"Boot{e.num}", active_text, e.name, e.path)
            self.tree.insert("", tk.END, values=values)

        target = select_index if select_index is not None else current_idx
        if target is not None and 0 <= target < len(self.tree.get_children()):
            item = self.tree.get_children()[target]
            self.tree.selection_set(item)
            self.tree.see(item)

    def _show_about(self):
        messagebox.showinfo(
            "关于 LazyUEFI",
            "LazyUEFI\n一个简单易用的 Linux UEFI 启动项管理工具。\n"
            "依赖：efibootmgr、python3-tk",
        )


def main():
    if not EfiBootManager.available():
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "缺少依赖",
            "未找到 efibootmgr。请先安装：\nsudo apt install efibootmgr\n"
            "或对应发行版的安装命令。",
        )
        sys.exit(1)

    app = LazyUEFIApp()
    app.mainloop()


if __name__ == "__main__":
    main()
