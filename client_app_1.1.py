# 客户端桌面窗体程序：Tkinter实现 + 多网卡手动选择 + 精准IP-MAC配对
# 依赖安装：pip install requests psutil
import tkinter as tk
from tkinter import ttk, messagebox
import socket
import psutil
import requests
import json
import re  # 【新增】导入内置正则模块，用于中文校验
import configparser  # 【新增】导入内置ini配置解析模块
import os  # 【新增】导入内置模块，用于获取文件路径、创建配置文件
import sys

# ---------------------- 核心：定义中文姓名正则表达式（精准匹配） ----------------------
# 正则规则：仅允许中文汉字（\u4e00-\u9fa5）、姓名间隔符·，长度2-20个字符
CHINESE_NAME_PATTERN = re.compile(r'^[\u4e00-\u9fa5·]{2,20}$')

# ---------------------- 新增核心：读取config.ini配置文件，获取服务器IP和端口 ----------------------


def get_server_config():
    """
    读取config.ini（适配源码运行+PyInstaller打包EXE）
    返回：(server_ip, server_port)，默认(127.0.0.1, 5000)
    新增：打印绝对路径+可视化弹窗提示
    """
    # 关键修复：获取程序运行的真实目录（适配源码/EXE打包）
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller打包后，EXE的运行目录
        base_dir = os.path.dirname(os.path.abspath(sys.executable))
    else:
        # 源码运行时，脚本的所在目录
        base_dir = os.path.dirname(os.path.abspath(__file__))
    # 配置文件绝对路径（确保和程序同目录）
    config_path = os.path.join(base_dir, "config.ini")
    # 默认配置
    default_ip = "127.0.0.1"
    default_port = 5000
    config = configparser.ConfigParser()

    try:
        # 打印绝对路径，方便排查（核心！）
        print(f"【配置文件】实际读取路径：{config_path}")
        # 1. 文件不存在则创建标准默认配置
        if not os.path.exists(config_path):
            config["Server"] = {"ip": default_ip, "port": str(default_port)}
            with open(config_path, "w", encoding="utf-8") as f:
                config.write(f)
            print(f"【配置文件】不存在，已自动创建默认文件：{config_path}")
            return default_ip, default_port

        # 2. 读取配置文件（UTF-8编码）
        config.read(config_path, encoding="utf-8")
        # 3. 严格校验[Server]节是否存在
        if "Server" not in config.sections():
            print(f"【配置文件】无[Server]节，使用默认地址：{default_ip}:{default_port}")
            return default_ip, default_port

        # 4. 读取IP，去除多余空格，缺失则用默认
        server_ip = config.get("Server", "ip", fallback=default_ip).strip()
        # 5. 读取端口，处理非数字/超出范围，缺失则用默认
        server_port_str = config.get(
            "Server", "port", fallback=str(default_port)).strip()
        try:
            server_port = int(server_port_str)
            if not 1 <= server_port <= 65535:
                raise ValueError("端口超出1-65535范围")
        except (ValueError, TypeError):
            print(f"【配置文件】端口{server_port_str}无效，使用默认端口：{default_port}")
            server_port = default_port

        # 读取成功日志
        print(f"【配置文件】成功读取，服务器地址：{server_ip}:{server_port}")
        return server_ip, server_port

    except Exception as e:
        print(f"【配置文件】读取异常：{str(e)}，使用默认地址：{default_ip}:{default_port}")
        return default_ip, default_port


# ---------------------- 核心重构：获取所有有效网卡信息（适配多网卡） ----------------------


def get_all_valid_nics():
    """
    获取客户端所有「已启用、非回环、非虚拟」的有效网卡信息
    返回：列表，每个元素为字典{"name":网卡名, "ip":IPv4, "mac":MAC, "type":网卡类型}
    过滤规则：isup=True（已启用）、非lo开头（非回环）、至少包含IP/MAC
    """
    valid_nics = []
    # 有线/无线网卡关键词（跨平台兼容）
    wired_keywords = ['Ethernet', '以太网', '本地连接', 'eth0', 'eth1', 'eth2']
    wireless_keywords = ['Wi-Fi', 'WLAN', '无线局域网', 'wlan0', 'wlan1', 'wlan2']

    try:
        net_addrs = psutil.net_if_addrs()  # 所有网卡地址信息
        net_stats = psutil.net_if_stats()  # 所有网卡启用状态

        # 遍历所有网卡，过滤有效网卡
        for iface_name, addr_list in net_addrs.items():
            # 过滤条件1：网卡存在状态信息 + 已启用 + 非回环网卡
            if iface_name not in net_stats or not net_stats[iface_name].isup or iface_name.startswith('lo'):
                continue

            nic_info = {
                "name": iface_name,
                "ip": "无IPv4地址",
                "mac": "无MAC地址",
                "type": "未知网卡"
            }

            # 提取IPv4（AF_INET）和MAC地址（AF_LINK）
            for addr in addr_list:
                if addr.family == socket.AF_INET:
                    nic_info["ip"] = addr.address  # 覆盖默认值
                elif addr.family == psutil.AF_LINK:
                    nic_info["mac"] = addr.address.upper()  # 转大写，覆盖默认值

            # 判断网卡类型（有线/无线/未知）
            if any(key in iface_name for key in wired_keywords):
                nic_info["type"] = "有线网卡"
            elif any(key in iface_name for key in wireless_keywords):
                nic_info["type"] = "无线网卡"

            # 过滤：至少有IP或MAC（排除空信息网卡）
            if nic_info["ip"] != "无IPv4地址" or nic_info["mac"] != "无MAC地址":
                valid_nics.append(nic_info)

        return valid_nics

    except Exception as e:
        print(f"获取网卡列表失败：{str(e)}")
        return []

# ---------------------- 窗体主程序类（核心改造：多网卡下拉选择 + 信息联动更新） ----------------------


class UserInfoClient(tk.Tk):
    def __init__(self):
        super().__init__()
        # 1. 读取配置文件（核心修复后的函数）
        server_ip, server_port = get_server_config()
        self.backend_url = f"http://{server_ip}:{server_port}"
        # 2. 新增可视化弹窗：提示读取的IP/端口（无需看控制台）
        # messagebox.showinfo(
        #    "配置读取结果", f"成功读取服务器地址：\nIP：{server_ip}\n端口：{server_port}\n\n完整地址：{self.backend_url}")

        # 基础配置：窗体宽度不变，高度微调至480，适配多网卡选择布局
        self.title("用户信息采集客户端 - 多网卡选择版")
        self.geometry("500x480")
        self.resizable(False, False)
        self.center_window()

        # 核心变量：存储所有有效网卡、当前选择的网卡信息
        self.all_valid_nics = get_all_valid_nics()  # 所有有效网卡列表
        self.current_nic = None  # 当前选中的网卡信息（字典）

        # 创建UI界面
        self.create_widgets()
        # 初始化：默认选中第一个有效网卡
        self.init_default_nic()

    # 窗体居中（无修改）
    def center_window(self):
        self.update_idletasks()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width - self.winfo_width()) // 2
        y = (screen_height - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    # 创建UI组件（核心改造：新增下拉选择框 + 联动展示IP/MAC/类型）
    def create_widgets(self):
        style = ttk.Style(self)
        style.configure("TLabel", font=("Microsoft YaHei", 12), padding=5)
        style.configure("TEntry", font=("Microsoft YaHei", 12), padding=5)
        style.configure("TButton", font=("Microsoft YaHei", 12), padding=8)
        style.configure("TCombobox", font=(
            "Microsoft YaHei", 11), padding=5)  # 下拉框样式
        self.font_tip = ("Microsoft YaHei", 10)

        # 1. 姓名输入区域（无修改，保留占位符）
        label_name = ttk.Label(self, text="用户姓名 *", anchor="w")
        label_name.place(x=50, y=30, width=100, height=30)
        self.entry_name = ttk.Entry(self, font=("Microsoft YaHei", 12))
        self.entry_name.place(x=160, y=30, width=280, height=30)
        # 占位符实现
        self.PLACEHOLDER_TEXT = "请输入您的真实姓名"
        self.entry_name.insert(0, self.PLACEHOLDER_TEXT)
        self.entry_name.config(foreground="#999999")
        self.entry_name.bind("<FocusIn>", self.on_focus_in)
        self.entry_name.bind("<FocusOut>", self.on_focus_out)

        # ---------------------- 核心改造1：新增网卡下拉选择框（多网卡选择核心） ----------------------
        label_nic_select = ttk.Label(self, text="选择网卡 *", anchor="w")
        label_nic_select.place(x=50, y=90, width=100, height=30)
        # 下拉选择框：只读模式（禁止用户手动输入，仅可选择）
        self.cb_nic_select = ttk.Combobox(
            self, state="readonly", font=("Microsoft YaHei", 11))
        self.cb_nic_select.place(x=160, y=90, width=280, height=30)
        # 绑定下拉框选中事件：选择后联动更新IP/MAC/类型
        self.cb_nic_select.bind("<<ComboboxSelected>>", self.on_nic_selected)

        # ---------------------- 核心改造2：联动展示区域（只读，随下拉选择更新） ----------------------
        # 物理IP展示
        label_ip = ttk.Label(self, text="网卡IP地址", anchor="w")
        label_ip.place(x=50, y=150, width=100, height=30)
        self.entry_ip = ttk.Entry(self, state="readonly")
        self.entry_ip.place(x=160, y=150, width=280, height=30)

        # 物理MAC展示
        label_mac = ttk.Label(self, text="网卡MAC地址", anchor="w")
        label_mac.place(x=50, y=200, width=100, height=30)
        self.entry_mac = ttk.Entry(self, state="readonly")
        self.entry_mac.place(x=160, y=200, width=280, height=30)

        # 网卡类型展示
        label_nic_type = ttk.Label(self, text="网卡类型", anchor="w")
        label_nic_type.place(x=50, y=250, width=100, height=30)
        self.entry_nic_type = ttk.Entry(self, state="readonly")
        self.entry_nic_type.place(x=160, y=250, width=280, height=30)

        # 2. 提交按钮（布局微调：y=300，适配多网卡布局）
        self.btn_submit = ttk.Button(
            self, text="提交信息到服务器", command=self.upload_data)
        self.btn_submit.place(x=100, y=300, width=300, height=40)

        # 3. 提示信息区域（布局微调：y=350，提示文字更新为多网卡说明）
        self.tip_label = tk.Label(self, text="", font=self.font_tip, fg="#FFFFFF", bg="#409eff",
                                  anchor="center", relief="solid", bd=1)
        self.tip_label.place(x=50, y=350, width=400, height=40)
        self.tip_label.config(
            text="温馨提示：请选择需要提交的网卡，单网卡默认自动选中", bg="#f0f7ff", fg="#1890ff")

    # 姓名输入框焦点事件（抽离为独立方法，更简洁）
    def on_focus_in(self, event):
        if self.entry_name.get() == self.PLACEHOLDER_TEXT:
            self.entry_name.delete(0, tk.END)
            self.entry_name.config(foreground="#000000")

    def on_focus_out(self, event):
        if not self.entry_name.get().strip():
            self.entry_name.insert(0, self.PLACEHOLDER_TEXT)
            self.entry_name.config(foreground="#999999")

    # ---------------------- 核心方法1：初始化默认网卡（单网卡自动选中） ----------------------
    def init_default_nic(self):
        if not self.all_valid_nics:
            # 无有效网卡：禁用选择框和提交按钮，给出错误提示
            self.cb_nic_select.config(state="disabled")
            self.btn_submit.config(state="disabled")
            self.show_tip("错误：无可用启用网卡，请检查网络连接！", "error")
            return

        # 构造下拉框选项：格式「网卡类型 - 网卡名 - IP地址」，直观区分
        nic_options = []
        for nic in self.all_valid_nics:
            option = f"{nic['type']} - {nic['name']} - {nic['ip']}"
            nic_options.append(option)
        self.cb_nic_select['values'] = nic_options

        # 默认选中第一个有效网卡，并触发联动更新
        self.cb_nic_select.current(0)
        self.on_nic_selected(None)  # None表示无事件，直接执行更新

    # ---------------------- 核心方法2：下拉框选中事件（联动更新IP/MAC/类型） ----------------------
    def on_nic_selected(self, event):
        selected_index = self.cb_nic_select.current()
        if selected_index == -1 or not self.all_valid_nics:
            return
        # 获取当前选中的网卡信息
        self.current_nic = self.all_valid_nics[selected_index]
        # 联动更新展示区域（只读输入框赋值）
        # IP赋值
        self.entry_ip.config(state="normal")
        self.entry_ip.delete(0, tk.END)
        self.entry_ip.insert(0, self.current_nic["ip"])
        self.entry_ip.config(state="readonly")
        # MAC赋值
        self.entry_mac.config(state="normal")
        self.entry_mac.delete(0, tk.END)
        self.entry_mac.insert(0, self.current_nic["mac"])
        self.entry_mac.config(state="readonly")
        # 网卡类型赋值
        self.entry_nic_type.config(state="normal")
        self.entry_nic_type.delete(0, tk.END)
        self.entry_nic_type.insert(0, self.current_nic["type"])
        self.entry_nic_type.config(state="readonly")
        # 提示选中成功
        self.show_tip(
            f"已选中：{self.current_nic['type']} - {self.current_nic['name']}", "loading")

    # 提示信息展示（无修改）
    def show_tip(self, text, tip_type):
        style_map = {
            "loading": ("#1890ff", "#f0f7ff"),
            "success": ("#52c41a", "#e6f7ff"),
            "error": ("#f5222d", "#fff2f2")
        }
        fg, bg = style_map.get(tip_type, style_map["loading"])
        self.tip_label.config(text=text, fg=fg, bg=bg)
        self.update()

    # ---------------------- 核心改造3：数据上传（适配多网卡，获取选中网卡信息） ----------------------
    def upload_data(self):
        # 1. 校验姓名输入
        user_name = self.entry_name.get().strip()
        if not user_name or user_name == self.PLACEHOLDER_TEXT:
            self.show_tip("错误：用户姓名不能为空！", "error")
            self.entry_name.focus()
            return

        # 2. 【新增核心】中文姓名正则校验
        if not CHINESE_NAME_PATTERN.match(user_name):
            self.show_tip("错误：姓名仅支持中文和·，长度2-20个字符！", "error")
            self.entry_name.focus()  # 焦点聚焦到姓名输入框，方便重新输入
            self.entry_name.select_range(0, tk.END)  # 【新增】选中错误输入内容，一键替换
            return

        # 3. 校验是否选中有效网卡
        if not self.current_nic:
            self.show_tip("错误：未选择有效网卡，请检查！", "error")
            return

        # 4. 构造上传数据（从当前选中的网卡中提取信息）
        upload_data = {
            "user_name": user_name,
            "ip_addr": self.current_nic["ip"],
            "mac_addr": self.current_nic["mac"],
            "nic_type": self.current_nic["type"]  # 可选：上传网卡类型到后端
        }

        try:
            self.show_tip("正在提交数据，请稍候...", "loading")
            self.btn_submit.config(state="disabled")
            self.update()

            # 发送POST请求到后端（与原有接口一致，无修改）
            res = requests.post(
                url=f"{self.backend_url}/upload",
                headers={"Content-Type": "application/json"},
                data=json.dumps(upload_data),
                timeout=5
            )
            result = res.json()

            if res.status_code == 200 and result.get("code") == 200:
                self.show_tip(f"成功：{result.get('msg')}", "success")
                # 清空姓名，保留网卡选择
                self.entry_name.delete(0, tk.END)
                self.entry_name.insert(0, self.PLACEHOLDER_TEXT)
                self.entry_name.config(foreground="#999999")
            else:
                self.show_tip(f"错误：{result.get('msg', '提交失败')}", "error")

        except requests.exceptions.ConnectionError:
            self.show_tip(f"错误：无法连接到服务器{self.backend_url}！", "error")
        except requests.exceptions.Timeout:
            self.show_tip(f"错误：连接服务器{self.backend_url}超时！", "error")
        except Exception as e:
            self.show_tip(f"错误：{str(e)[:30]}", "error")
        finally:
            self.btn_submit.config(state="normal")


# ---------------------- 程序入口（无修改） ----------------------
if __name__ == "__main__":
    client = UserInfoClient()
    client.mainloop()
