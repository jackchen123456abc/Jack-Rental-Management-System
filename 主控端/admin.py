import binascii
import platform
import socket
import subprocess
import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
from kongzhi import remote_control_client
from chakan import view_remote_screen
from chuanshu import send_command_via_tcp
from datetime import datetime, timedelta
import calendar
import threading
import time

ctk.set_appearance_mode("System")


class RentalManagementApp:
    def __init__(self):
        self.main = ctk.CTk()
        self.main.title("Jack租机管理系统")
        self.main.geometry("1000x600")
        self.main.minsize(800, 500)
        self.selected_item = None
        self.ip_column_index = 6
        self.status_column_index = 7
        self.mac_column_index = 2
        self.df = self.load_data()
        self.setup_ui()
        self.setup_context_menu()
        self.populate_tree()
        self.auto_check_status()

    def load_data(self):
        try:
            import os
            base_dir = os.path.dirname(os.path.abspath(__file__))
            file_path = os.path.join(base_dir, "users.xlsx")
            if not os.path.exists(file_path):
                file_path = os.path.join(base_dir, "jack_rental_management_system", "admin", "users.xlsx")
            return pd.read_excel(file_path)
        except Exception as e:
            print(f"加载数据失败: {e}")
            return pd.DataFrame()

    def get_theme_colors(self):
        is_dark = ctk.get_appearance_mode() == "Dark"
        return {
            "tree_bg": "#2b2b2b" if is_dark else "#ffffff",
            "tree_fg": "#ffffff" if is_dark else "#000000",
            "heading_bg": "#1f308d" if is_dark else "#e0e0e0",
            "heading_fg": "#ffffff" if is_dark else "#000000",
            "select_bg": "#14375e" if is_dark else "#0078d7",
            "select_fg": "#ffffff",
            "menu_active_bg": "#1f308d" if is_dark else "#0078d7",
            "menu_active_fg": "#ffffff"
        }

    def setup_ui(self):
        main_frame = ctk.CTkFrame(self.main, corner_radius=10)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        style = ttk.Style()
        style.theme_use("clam")
        colors = self.get_theme_colors()
        style.configure("Treeview", background=colors["tree_bg"], foreground=colors["tree_fg"],
                         fieldbackground=colors["tree_bg"], borderwidth=0, rowheight=30)
        style.configure("Treeview.Heading", background=colors["heading_bg"],
                         foreground=colors["heading_fg"], font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Treeview", background=[("selected", colors["select_bg"])])
        tree_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        tree_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tree_frame, columns=list(self.df.columns), show="headings")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        self.tree.bind("<Button-3>", self.show_context_menu)

    def setup_context_menu(self):
        colors = self.get_theme_colors()
        self.context_menu = tk.Menu(self.tree, tearoff=0, bg=colors["tree_bg"], fg=colors["tree_fg"],
                                     activebackground=colors["menu_active_bg"],
                                     activeforeground=colors["menu_active_fg"])
        self.context_menu.add_command(label="远程控制", command=self.kongzhi)
        self.context_menu.add_command(label="远程查看", command=self.chakan)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="上机", command=self.shangji)
        self.context_menu.add_command(label="下机", command=self.xiaji)
        self.context_menu.add_command(label="续时", command=self.xushi)
        self.context_menu.add_command(label="换机", command=self.huanji)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="开机", command=self.kaiji)
        self.context_menu.add_command(label="关机", command=self.guanji)
        self.context_menu.add_command(label="重启", command=self.chongqi)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="锁屏", command=self.suoping)
        self.context_menu.add_command(label="解锁", command=self.jiesuo)

    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.selected_item = item
            self.context_menu.post(event.x_root, event.y_root)

    def populate_tree(self):
        for col in self.df.columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=120, anchor="center")
        for row in self.df.itertuples(index=False):
            self.tree.insert("", "end", values=[str(x) for x in row])

    def get_target_ip(self):
        if not self.selected_item:
            return None
        values = self.tree.item(self.selected_item, "values")
        return values[self.ip_column_index] if len(values) > self.ip_column_index else None

    def get_target_mac(self):
        if not self.selected_item:
            return None
        values = self.tree.item(self.selected_item, "values")
        return values[self.mac_column_index] if len(values) > self.mac_column_index else None

    def _run_in_thread(self, func, *args, callback=None, **kwargs):
        def wrapper():
            try:
                result = func(*args, **kwargs)
                if callback:
                    self.main.after(0, callback, result)
            except Exception as e:
                print(f"[线程异常] {e}")
                if callback:
                    self.main.after(0, callback, f"错误：{e}")
        threading.Thread(target=wrapper, daemon=True).start()

    def _show_result(self, result):
        """如果需要，显示操作结果"""
        if result and str(result).startswith("错误"):
            messagebox.showerror("操作失败", str(result))

    def kongzhi(self):
        ip = self.get_target_ip()
        if ip:
            threading.Thread(target=remote_control_client, kwargs={"target_ip": ip}, daemon=True).start()

    def chakan(self):
        ip = self.get_target_ip()
        if ip:
            threading.Thread(target=view_remote_screen, kwargs={"remote_ip": ip}, daemon=True).start()

    def calculate_end_time(self, start_dt, years, months, days, hours, minutes):
        year = start_dt.year + years + (start_dt.month + months - 1) // 12
        month = (start_dt.month + months - 1) % 12 + 1
        max_day = calendar.monthrange(year, month)[1]
        day = min(start_dt.day, max_day)
        new_dt = start_dt.replace(year=year, month=month, day=day)
        new_dt = new_dt + timedelta(days=days, hours=hours, minutes=minutes)
        return new_dt

    def monitor_and_lock(self, ip, end_time_str):
        end_dt = datetime.strptime(end_time_str, "%Y-%m-%d %H:%M:%S")
        while True:
            if datetime.now() >= end_dt:
                send_command_via_tcp(host=ip, port=6000, command="suoping", wait_response=False)
                break
            time.sleep(10)

    def shangji(self):
        if not self.selected_item:
            messagebox.showwarning("警告", "请先在表格中选择一台机器")
            return

        shangji_window = ctk.CTkToplevel(self.main)
        shangji_window.title("上机")
        shangji_window.geometry("450x280")
        shangji_window.resizable(False, False)
        shangji_window.transient(self.main)
        shangji_window.grab_set()

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        ctk.CTkLabel(shangji_window, text="用户名:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        user_name_entry = ctk.CTkEntry(shangji_window, width=250, placeholder_text="请输入用户名")
        user_name_entry.grid(row=0, column=1, padx=10, pady=10, columnspan=5)

        ctk.CTkLabel(shangji_window, text="开始时间:").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        start_time_entry = ctk.CTkEntry(shangji_window, width=250, state="disabled")
        start_time_entry.grid(row=1, column=1, padx=10, pady=10, columnspan=5)
        start_time_entry.configure(state="normal")
        start_time_entry.insert(0, current_time)
        start_time_entry.configure(state="disabled")

        ctk.CTkLabel(shangji_window, text="租机时长:").grid(row=2, column=0, padx=10, pady=10, sticky="w")
        time_frame = ctk.CTkFrame(shangji_window, fg_color="transparent")
        time_frame.grid(row=2, column=1, padx=10, pady=10, columnspan=5, sticky="w")

        entries = {}
        units = ["年", "月", "日", "时", "分"]
        for i, unit in enumerate(units):
            entry = ctk.CTkEntry(time_frame, width=40, placeholder_text="0")
            entry.grid(row=0, column=i * 2, padx=2)
            entry.insert(0, "0")
            entries[unit] = entry
            ctk.CTkLabel(time_frame, text=unit).grid(row=0, column=i * 2 + 1, padx=2)

        def confirm_shangji():
            name = user_name_entry.get().strip()
            if not name:
                messagebox.showerror("错误", "请输入用户名")
                return

            try:
                y = int(entries["年"].get() or 0)
                mo = int(entries["月"].get() or 0)
                d = int(entries["日"].get() or 0)
                h = int(entries["时"].get() or 0)
                mi = int(entries["分"].get() or 0)
            except ValueError:
                messagebox.showerror("错误", "租机时长必须输入数字")
                return

            if y == 0 and mo == 0 and d == 0 and h == 0 and mi == 0:
                messagebox.showwarning("警告", "租机时长不能全为0！")
                return

            start_dt = datetime.strptime(current_time, "%Y-%m-%d %H:%M:%S")
            end_dt = self.calculate_end_time(start_dt, y, mo, d, h, mi)
            end_time_str = end_dt.strftime("%Y-%m-%d %H:%M:%S")

            cols = list(self.tree["columns"])
            values = list(self.tree.item(self.selected_item, "values"))

            for i, c in enumerate(cols):
                col_str = str(c)
                if "用户" in col_str or "姓名" in col_str:
                    values[i] = name
                elif "开始" in col_str:
                    values[i] = current_time
                elif "结束" in col_str:
                    values[i] = end_time_str

            self.tree.item(self.selected_item, values=values)

            ip = self.get_target_ip()
            if ip:
                self._run_in_thread(
                    send_command_via_tcp,
                    host=ip, port=6000, command="kaiji", wait_response=False,
                    callback=self._show_result
                )
                threading.Thread(target=self.monitor_and_lock, args=(ip, end_time_str), daemon=True).start()

            shangji_window.destroy()

        yes_button = ctk.CTkButton(shangji_window, text="确认上机", command=confirm_shangji, width=200)
        yes_button.grid(row=3, column=0, padx=10, pady=20, columnspan=6)

    def xiaji(self):
        if not self.selected_item:
            messagebox.showwarning("警告", "请先在表格中选择一台机器")
            return

        cols = list(self.tree["columns"])
        values = list(self.tree.item(self.selected_item, "values"))

        for i, c in enumerate(cols):
            col_str = str(c)
            if "用户" in col_str or "姓名" in col_str or "开始" in col_str or "结束" in col_str:
                values[i] = "/"

        self.tree.item(self.selected_item, values=values)

        ip = self.get_target_ip()
        if ip:
            self._run_in_thread(
                send_command_via_tcp,
                host=ip, port=6000, command="guanji", wait_response=False,
                callback=self._show_result
            )

    def xushi(self):
        if not self.selected_item:
            messagebox.showwarning("警告", "请先在表格中选择一台机器")
            return

        cols = list(self.tree["columns"])
        values = list(self.tree.item(self.selected_item, "values"))

        current_end_time_str = None
        for i, c in enumerate(cols):
            if "结束" in str(c):
                current_end_time_str = values[i]
                break

        if not current_end_time_str or current_end_time_str == "/":
            messagebox.showwarning("警告", "该机器未上机或已下机，无法续时")
            return

        xushi_window = ctk.CTkToplevel(self.main)
        xushi_window.title("续时")
        xushi_window.geometry("450x180")
        xushi_window.resizable(False, False)
        xushi_window.transient(self.main)
        xushi_window.grab_set()

        ctk.CTkLabel(xushi_window, text="续机时长:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        time_frame = ctk.CTkFrame(xushi_window, fg_color="transparent")
        time_frame.grid(row=0, column=1, padx=10, pady=10, columnspan=5, sticky="w")

        entries = {}
        units = ["年", "月", "日", "时", "分"]
        for i, unit in enumerate(units):
            entry = ctk.CTkEntry(time_frame, width=40, placeholder_text="0")
            entry.grid(row=0, column=i * 2, padx=2)
            entry.insert(0, "0")
            entries[unit] = entry
            ctk.CTkLabel(time_frame, text=unit).grid(row=0, column=i * 2 + 1, padx=2)

        def confirm_xushi():
            try:
                y = int(entries["年"].get() or 0)
                mo = int(entries["月"].get() or 0)
                d = int(entries["日"].get() or 0)
                h = int(entries["时"].get() or 0)
                mi = int(entries["分"].get() or 0)
            except ValueError:
                messagebox.showerror("错误", "续机时长必须输入数字")
                return

            if y == 0 and mo == 0 and d == 0 and h == 0 and mi == 0:
                messagebox.showwarning("警告", "续机时长不能全为0！")
                return

            base_dt = datetime.strptime(current_end_time_str, "%Y-%m-%d %H:%M:%S")
            new_end_dt = self.calculate_end_time(base_dt, y, mo, d, h, mi)
            new_end_time_str = new_end_dt.strftime("%Y-%m-%d %H:%M:%S")

            for i, c in enumerate(cols):
                if "结束" in str(c):
                    values[i] = new_end_time_str

            self.tree.item(self.selected_item, values=values)

            ip = self.get_target_ip()
            if ip:
                threading.Thread(target=self.monitor_and_lock, args=(ip, new_end_time_str), daemon=True).start()

            xushi_window.destroy()

        yes_button = ctk.CTkButton(xushi_window, text="确认续时", command=confirm_xushi, width=200)
        yes_button.grid(row=1, column=0, padx=10, pady=20, columnspan=6)

    def huanji(self):
        if not self.selected_item:
            messagebox.showwarning("警告", "请先在表格中选择一台机器")
            return

        cols = list(self.tree["columns"])
        values = list(self.tree.item(self.selected_item, "values"))

        user_val, start_val, end_val = None, None, None
        for i, c in enumerate(cols):
            col_str = str(c)
            if "用户" in col_str or "姓名" in col_str:
                user_val = values[i]
            elif "开始" in col_str:
                start_val = values[i]
            elif "结束" in col_str:
                end_val = values[i]

        if not user_val or user_val == "/":
            messagebox.showwarning("警告", "该机器未上机，无法换机")
            return

        available_ips = []
        for item in self.tree.get_children():
            item_vals = self.tree.item(item, "values")
            item_user = item_vals[0]
            for idx, c in enumerate(cols):
                if "用户" in str(c) or "姓名" in str(c):
                    item_user = item_vals[idx]
                    break
            if not item_user or item_user == "/":
                available_ips.append(item_vals[self.ip_column_index])

        if not available_ips:
            messagebox.showwarning("警告", "没有可用的空闲机器")
            return

        huanji_window = ctk.CTkToplevel(self.main)
        huanji_window.title("换机")
        huanji_window.geometry("300x150")
        huanji_window.resizable(False, False)
        huanji_window.transient(self.main)
        huanji_window.grab_set()

        ctk.CTkLabel(huanji_window, text="选择目标机器:").pack(pady=10)
        target_ip_combo = ctk.CTkComboBox(huanji_window, values=available_ips, width=200)
        target_ip_combo.pack(pady=10)

        def confirm_huanji():
            target_ip = target_ip_combo.get()
            if not target_ip:
                messagebox.showerror("错误", "请选择目标机器")
                return

            target_item = None
            for item in self.tree.get_children():
                if self.tree.item(item, "values")[self.ip_column_index] == target_ip:
                    target_item = item
                    break

            if not target_item:
                messagebox.showerror("错误", "未找到目标机器")
                return

            target_values = list(self.tree.item(target_item, "values"))
            for i, c in enumerate(cols):
                col_str = str(c)
                if "用户" in col_str or "姓名" in col_str:
                    target_values[i] = user_val
                elif "开始" in col_str:
                    target_values[i] = start_val
                elif "结束" in col_str:
                    target_values[i] = end_val
            self.tree.item(target_item, values=target_values)

            for i, c in enumerate(cols):
                col_str = str(c)
                if "用户" in col_str or "姓名" in col_str or "开始" in col_str or "结束" in col_str:
                    values[i] = "/"
            self.tree.item(self.selected_item, values=values)

            old_ip = self.get_target_ip()

            def do_network():
                if old_ip:
                    send_command_via_tcp(host=old_ip, port=6000, command="guanji", wait_response=False)
                send_command_via_tcp(host=target_ip, port=6000, command="kaiji", wait_response=False)

            self._run_in_thread(do_network)

            if end_val and end_val != "/":
                threading.Thread(target=self.monitor_and_lock, args=(target_ip, end_val), daemon=True).start()

            huanji_window.destroy()

        confirm_btn = ctk.CTkButton(huanji_window, text="确认换机", command=confirm_huanji, width=150)
        confirm_btn.pack(pady=20)

    def _update_tree_item_status(self, item, new_status):
        try:
            values = list(self.tree.item(item, "values"))
            if len(values) > self.status_column_index:
                values[self.status_column_index] = new_status
                self.tree.item(item, values=values)
        except Exception:
            pass

    def auto_check_status(self):
        def check():
            while True:
                items_snapshot = []
                try:
                    for item in self.tree.get_children():
                        values = self.tree.item(item, "values")
                        ip = values[self.ip_column_index]
                        items_snapshot.append((item, ip, values))
                except Exception:
                    time.sleep(10)
                    continue

                for item, ip, values in items_snapshot:
                    try:
                        param = '-n' if platform.system().lower() == 'windows' else '-c'
                        timeout_param = '-w' if platform.system().lower() == 'windows' else '-W'
                        cmd = ['ping', param, '1', timeout_param, '1', ip]
                        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                                 timeout=5)
                        new_status = "开机" if result.returncode == 0 else "关机"
                    except Exception:
                        new_status = "关机"

                    current_status = values[self.status_column_index] if len(
                        values) > self.status_column_index else ""
                    if current_status != new_status:
                        self.main.after(0, self._update_tree_item_status, item, new_status)
                time.sleep(10)

        threading.Thread(target=check, daemon=True).start()

    def wake_on_lan(self, mac_address):
        try:
            mac = mac_address.replace(':', '').replace('-', '').replace('.', '')
            if len(mac) != 12:
                return False
            mac_bytes = bytes.fromhex(mac)
            send_data = b'\xff' * 6 + mac_bytes * 16
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(send_data, ('255.255.255.255', 9))
            sock.close()
            return True
        except Exception:
            return False

    def kaiji(self):
        if not self.selected_item:
            messagebox.showwarning("警告", "请先选择一台机器")
            return
        mac_address = self.get_target_mac()
        if mac_address and mac_address != "/":
            if not self.wake_on_lan(mac_address):
                messagebox.showerror("错误", "MAC地址格式错误或唤醒失败")
        else:
            messagebox.showerror("错误", "未找到有效的MAC地址")

    def guanji(self):
        ip = self.get_target_ip()
        if ip:
            self._run_in_thread(
                send_command_via_tcp,
                host=ip, port=6000, command="guanji", wait_response=False,
                callback=self._show_result
            )

    def chongqi(self):
        ip = self.get_target_ip()
        if ip:
            self._run_in_thread(
                send_command_via_tcp,
                host=ip, port=6000, command="chongqi", wait_response=False,
                callback=self._show_result
            )

    def suoping(self):
        ip = self.get_target_ip()
        if ip:
            self._run_in_thread(
                send_command_via_tcp,
                host=ip, port=6000, command="suoping", wait_response=False,
                callback=self._show_result
            )

    def jiesuo(self):
        ip = self.get_target_ip()
        if ip:
            self._run_in_thread(
                send_command_via_tcp,
                host=ip, port=6000, command="jiesuo", wait_response=False,
                callback=self._show_result
            )

    def run(self):
        self.main.mainloop()


if __name__ == "__main__":
    app = RentalManagementApp()
    app.run()