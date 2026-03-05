# 客户端桌面窗体程序：Tkinter实现，精准获取IP-MAC配对（修复psutil属性错误）
# 依赖安装：pip install requests psutil
import tkinter as tk
from tkinter import ttk, messagebox
import socket
import psutil
import requests
import json

# ---------------------- 核心修复：标准psutil读取逻辑，解决'snicaddr'属性错误 ----------------------


def get_real_ip_mac_pair():
    """
    精准获取「当前使用的内网IP」及其「对应网卡的真实MAC地址」
    修复点：1. 用address替代hwaddr 2. AF_LINK过滤MAC 3. AF_INET过滤IPv4 4. 网卡级IP-MAC提取
    返回：tuple(真实内网IP, 对应MAC地址)
    """
    try:
        # 步骤1：获取客户端真实内网出口IP（原有逻辑，稳定可用）
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        real_ip = s.getsockname()[0]
        s.close()

        # 步骤2：获取所有网卡的地址信息（snicaddr）和启用状态
        net_addrs = psutil.net_if_addrs()  # 所有网卡地址：{网卡名: [snicaddr对象列表]}
        net_stats = psutil.net_if_stats()  # 所有网卡状态：{网卡名: 状态对象}

        # 步骤3：定义网卡优先级（优先有线→无线，排除虚拟网卡，跨平台兼容）
        priority_iface = ['Ethernet', '以太网', '本地连接',
                          'Wi-Fi', 'WLAN', '无线局域网', 'eth0', 'wlan0']

        # 步骤4：遍历网卡，提取IP和MAC并精准匹配（核心修复逻辑）
        for iface_name in priority_iface:
            # 过滤：网卡存在+已启用+非回环
            if iface_name not in net_addrs or iface_name not in net_stats:
                continue
            if not net_stats[iface_name].isup or iface_name.startswith('lo'):
                continue

            # 为当前网卡提取：IPv4地址（AF_INET）、MAC地址（AF_LINK）
            iface_ip = None
            iface_mac = None
            for addr in net_addrs[iface_name]:
                if addr.family == socket.AF_INET:  # 过滤IPv4地址
                    iface_ip = addr.address  # 标准属性：address
                elif addr.family == psutil.AF_LINK:  # 过滤MAC地址（硬件地址）
                    iface_mac = addr.address.upper()  # 标准属性：address，转大写标准化

            # 匹配：当前网卡的IPv4 == 真实出口IP，且MAC存在
            if iface_ip == real_ip and iface_mac:
                return (real_ip, iface_mac)

        # 步骤5：优先级网卡未匹配，遍历所有网卡兜底
        for iface_name, addr_list in net_addrs.items():
            if iface_name not in net_stats or not net_stats[iface_name].isup or iface_name.startswith('lo'):
                continue
            # 提取当前网卡的IP和MAC
            iface_ip = None
            iface_mac = None
            for addr in addr_list:
                if addr.family == socket.AF_INET:
                    iface_ip = addr.address
                elif addr.family == psutil.AF_LINK:
                    iface_mac = addr.address.upper()
            # 精准匹配
            if iface_ip == real_ip and iface_mac:
                return (real_ip, iface_mac)

        # 匹配失败：IP存在但无对应MAC
        return (real_ip, "MAC匹配失败：未找到IP对应网卡")

    except socket.error:
        return ("IP获取失败：请检查网络连接", "无MAC")
    except Exception as e:
        return (f"获取失败：{str(e)[:30]}", "无MAC")

# ---------------------- 窗体主程序类（无任何修改，完全复用） ----------------------


class UserInfoClient(tk.Tk):
    def __init__(self, backend_url="http://127.0.0.1:5000"):
        super().__init__()
        # 基础配置
        self.backend_url = backend_url
        self.title("用户信息采集客户端 - 真实IP/MAC版")
        self.geometry("500x380")
        self.resizable(False, False)
        self.center_window()

        # 初始化精准配对的IP/MAC
        self.real_ip, self.real_mac = get_real_ip_mac_pair()

        # 创建UI界面
        self.create_widgets()

    # 窗体居中
    def center_window(self):
        self.update_idletasks()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width - self.winfo_width()) // 2
        y = (screen_height - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    # 创建UI组件（含占位符，无修改）
    def create_widgets(self):
        style = ttk.Style(self)
        style.configure("TLabel", font=("Microsoft YaHei", 10), padding=5)
        style.configure("TEntry", font=("Microsoft YaHei", 10), padding=5)
        style.configure("TButton", font=("Microsoft YaHei", 10), padding=8)
        self.font_tip = ("Microsoft YaHei", 10)

        # 1. 姓名输入区域（带占位符）
        label_name = ttk.Label(self, text="用户姓名 *", anchor="w")
        label_name.place(x=50, y=30, width=100, height=30)
        self.entry_name = ttk.Entry(self, font=("Microsoft YaHei", 10))
        self.entry_name.place(x=160, y=30, width=280, height=30)
        # 占位符实现
        PLACEHOLDER_TEXT = "请输入您的真实姓名"
        self.entry_name.insert(0, PLACEHOLDER_TEXT)
        self.entry_name.config(foreground="#999999")

        def on_focus_in(event):
            if self.entry_name.get() == PLACEHOLDER_TEXT:
                self.entry_name.delete(0, tk.END)
                self.entry_name.config(foreground="#000000")

        def on_focus_out(event):
            if not self.entry_name.get().strip():
                self.entry_name.insert(0, PLACEHOLDER_TEXT)
                self.entry_name.config(foreground="#999999")
        self.entry_name.bind("<FocusIn>", on_focus_in)
        self.entry_name.bind("<FocusOut>", on_focus_out)

        # 2. 真实IP展示（只读）
        label_ip = ttk.Label(self, text="物理内网IP", anchor="w")
        label_ip.place(x=50, y=90, width=100, height=30)
        self.entry_ip = ttk.Entry(self, state="readonly")
        self.entry_ip.place(x=160, y=90, width=280, height=30)
        self.entry_ip.config(state="normal")
        self.entry_ip.insert(0, self.real_ip)
        self.entry_ip.config(state="readonly")

        # 3. 真实MAC展示（只读）
        label_mac = ttk.Label(self, text="物理MAC地址", anchor="w")
        label_mac.place(x=50, y=150, width=100, height=30)
        self.entry_mac = ttk.Entry(self, state="readonly")
        self.entry_mac.place(x=160, y=150, width=280, height=30)
        self.entry_mac.config(state="normal")
        self.entry_mac.insert(0, self.real_mac)
        self.entry_mac.config(state="readonly")

        # 4. 提交按钮
        self.btn_submit = ttk.Button(
            self, text="提交信息到服务器", command=self.upload_data)
        self.btn_submit.place(x=100, y=220, width=300, height=40)

        # 5. 提示区域
        self.tip_label = tk.Label(self, text="", font=self.font_tip, fg="#FFFFFF", bg="#409eff",
                                  anchor="center", relief="solid", bd=1)
        self.tip_label.place(x=50, y=290, width=400, height=40)
        self.tip_label.config(text="温馨提示：已精准绑定IP-MAC对应网卡",
                              bg="#f0f7ff", fg="#1890ff")

    # 数据上传（无修改）
    def upload_data(self):
        user_name = self.entry_name.get().strip()
        PLACEHOLDER_TEXT = "请输入您的真实姓名"
        if not user_name or user_name == PLACEHOLDER_TEXT:
            self.show_tip("错误：用户姓名不能为空！", "error")
            self.entry_name.focus()
            return

        if "获取失败" in self.real_ip or "无MAC" in self.real_mac or "匹配失败" in self.real_mac:
            self.show_tip("错误：IP/MAC获取失败，请检查网络！", "error")
            return

        upload_data = {
            "user_name": user_name,
            "ip_addr": self.real_ip,
            "mac_addr": self.real_mac
        }

        try:
            self.show_tip("正在提交数据，请稍候...", "loading")
            self.btn_submit.config(state="disabled")
            self.update()

            res = requests.post(
                url=f"{self.backend_url}/upload",
                headers={"Content-Type": "application/json"},
                data=json.dumps(upload_data),
                timeout=5
            )
            result = res.json()

            if res.status_code == 200 and result.get("code") == 200:
                self.show_tip(f"成功：{result.get('msg')}", "success")
                self.entry_name.delete(0, tk.END)
                self.entry_name.insert(0, PLACEHOLDER_TEXT)
                self.entry_name.config(foreground="#999999")
            else:
                self.show_tip(f"错误：{result.get('msg', '提交失败')}", "error")

        except requests.exceptions.ConnectionError:
            self.show_tip("错误：无法连接到后端服务器！", "error")
        except requests.exceptions.Timeout:
            self.show_tip("错误：连接服务器超时，请检查网络！", "error")
        except Exception as e:
            self.show_tip(f"错误：{str(e)[:30]}", "error")
        finally:
            self.btn_submit.config(state="normal")

    # 提示信息（无修改）
    def show_tip(self, text, tip_type):
        style_map = {
            "loading": ("#1890ff", "#f0f7ff"),
            "success": ("#52c41a", "#e6f7ff"),
            "error": ("#f5222d", "#fff2f2")
        }
        fg, bg = style_map.get(tip_type, style_map["loading"])
        self.tip_label.config(text=text, fg=fg, bg=bg)
        self.update()


# ---------------------- 程序入口 ----------------------
if __name__ == "__main__":
    # 关键：修改为你的Flask后端服务器内网IP（如http://192.168.1.100:5000）
    client = UserInfoClient(backend_url="http://10.64.68.228:5000")
    client.mainloop()
