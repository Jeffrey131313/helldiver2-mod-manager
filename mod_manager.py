import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter
import tkinter as tk
import webbrowser
import winreg
import zipfile
from collections import defaultdict
from pathlib import Path
from tkinter import ttk, filedialog, messagebox, font

import dns.resolver
import requests
from tkinterdnd2 import TkinterDnD, DND_FILES
import yaml
from PIL import Image, ImageFont, ImageDraw, ImageTk, ImageGrab
from py7zr import py7zr
from ttkbootstrap import Style


characters = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
MOD_FOLDER = "./mods"

try:
    resolver = dns.resolver.Resolver()
    resolver.nameservers = ['223.6.6.6']
    answers = resolver.resolve('status.helldiver2mod.cn', 'TXT')
    answer = resolver.resolve('helldiver2mod.cn', 'A')
    updataip = answer[0].address
    logurl = f"http://{updataip}/updata/log.txt"

    try:
        response = requests.get(logurl)
        response.raise_for_status()
        text = response.text
    except requests.exceptions.RequestException as e:
        messagebox.showwarning(f"获取公告失败:", f" {str(e)}")

    for record in [record.strings[0].decode("utf-8") for record in answers]:
        if float(record) > 1.4:
            update_confirm = messagebox.askyesno(
                "更新提示",
                f"您当前使用的不是最新版本, 点击\"是\"自动更新\n"
                         f"{float(record)}更新内容:\n"
                         f"{text}",
                icon='warning'
            )
            if update_confirm:
                try:
                    url = f"http://{updataip}/updata/{float(record)}.exe"
                    save_path = f"./helldiver2mod_manager-{float(record)}.exe"
                    response = requests.get(url, stream=True)
                    response.raise_for_status()

                    with open(save_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    print(f"文件已下载到: {save_path}")

                    with open("./old_file.txt", "a", encoding="utf-8") as f:
                        f.write(sys.executable)

                    time.sleep(1)

                    messagebox.showinfo("更新完成!", f"双击helldiver2mod_manager-{float(record)}.exe以启动新版本")

                    sys.exit(0)

                except requests.exceptions.RequestException as e:
                    messagebox.showwarning(f"下载失败:", f"{e}")
except:
    None

if not os.path.exists("./UnRAR.exe"):
    response = requests.get(r"https://www.rarlab.com/rar/unrarw64.exe", stream=True)
    if response.status_code == 200:
        with open("./unrarw64.exe", 'wb') as file:
            file.write(response.content)
        subprocess.run("./unrarw64.exe -s path=./")
        os.remove("./license.txt")
        os.remove("./unrarw64.exe")
        print("安装UnRAR成功")
    else:
        print("UnRAR下载失败")

if os.path.exists("./temp"):
    for delete in os.listdir("./temp"):
        shutil.rmtree(os.path.join("./temp", delete))
else:
    os.mkdir("./temp")

if not os.path.exists(MOD_FOLDER):
    os.makedirs(MOD_FOLDER)

if os.path.exists("./old_file.txt"):
    time.sleep(1)
    print("找到文件")
    try:
        with open("./old_file.txt", "r", encoding="utf-8") as f:
            old_file_name = f.read()
        os.remove(old_file_name)
        os.remove("./old_file.txt")
    except Exception as e:
        print(f"发生错误: {e}")

def resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

def get_steam_install_path():
    try:
        registry_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        steam_path, _ = winreg.QueryValueEx(registry_key, "SteamPath")
        return steam_path
    except FileNotFoundError:
        return None

def movefiletofatherpath(source_folder):
    items = os.listdir(source_folder)

    if len(items) == 1 and os.path.isdir(os.path.join(source_folder, items[0])):
        subfolder = os.path.join(source_folder, items[0])

        for item in os.listdir(subfolder):
            item_path = os.path.join(subfolder, item)
            destination_path = os.path.join(source_folder, item)

            shutil.move(item_path, destination_path)

        os.rmdir(subfolder)

def get_steam_game_paths():
    steam_path = get_steam_install_path()
    if steam_path:
        common_games_path = os.path.join(steam_path, "steamapps", "common", "Helldivers 2", "data")
        if os.path.exists(common_games_path):
            return common_games_path
    return False


if not os.path.exists(r".\config.yml"):
    if get_steam_game_paths():
        steam_game_paths = get_steam_game_paths()
        with open("config.yml", "w") as f:
            f.write(steam_game_paths)
    else:
        tk.Tk().withdraw()
        with open("config.yml", "w") as f:
            f.write(tkinter.filedialog.askdirectory(title="请选择HD2文件夹"))
        messagebox.showwarning("提示", "请重新运行软件")

with open("config.yml", "r") as f:
    install_dir = f.read()

if not install_dir:
    os.remove("config.yml")
    messagebox.showwarning("警告", "未找到HD2游戏,请自行前往config.yml修改！")
    sys.exit()


class ModManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Helldivers 2 模组管理器")
        self.root.geometry("1200x800")
        self.style = Style(theme="flatly")
        self.style.configure("TButton", padding=6, font=("Segoe UI", 10))
        self.style.configure("TLabel", font=("Segoe UI", 10))
        self.style.configure("Card.TFrame", background="#ffffff", borderwidth=1, relief="solid")
        self.style.map("Card.TFrame", background=[("active", "#f8f9fa")])

        self.primary_color = "#2c3e50"
        self.secondary_color = "#3498db"
        self.success_color = "#27ae60"
        self.danger_color = "#e74c3c"
        self.bg_color = "#f8f9fa"
        self.text_color = "#2c3e50"

        root.drop_target_register(DND_FILES)
        root.dnd_bind('<<Drop>>', self.on_drop)

        self.default_preview_image = self.create_default_preview_image()
        self.create_widgets()
        self.refresh_mod_list()

    def create_default_preview_image(self):
        image = Image.new("RGB", (100, 100), color="#f0f3f5")
        draw = ImageDraw.Draw(image)

        try:
            icon_font = ImageFont.truetype("seguiemj.ttf", 60)
            draw.text((10, 20), "🎮", font=icon_font, fill="#2c3e50")
        except:
            try:
                font = ImageFont.truetype("arial.ttf", 40)
                draw.text((30, 25), "MOD", font=font, fill="#3498db")
            except:
                draw.rectangle([20, 20, 80, 80], fill="#3498db", outline="#2c3e50")

        return ImageTk.PhotoImage(image)

    def create_widgets(self):
        main_container = ttk.Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        control_panel = ttk.Frame(main_container, width=300, style="Card.TFrame")
        control_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 20))

        ttk.Label(control_panel, text="模组管理", font=("Segoe UI", 14, "bold"),
                 foreground=self.primary_color, background="#ffffff").pack(pady=15, anchor=tk.W)

        search_frame = ttk.Frame(control_panel)
        search_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, font=("Segoe UI", 11), foreground=self.text_color)
        self.search_entry.pack(fill=tk.X, ipady=4)
        self.search_entry.bind("<Return>", self.refresh_mod_list)

        btn_style = {"style": "TButton", "width": 15}
        ttk.Button(
            control_panel,
            text="📂 添加模组",
            command=self.add_mod_ui,
            style="success.TButton"
        ).pack(pady=5, fill=tk.X, padx=15)

        ttk.Button(
            control_panel,
            text="🔄 刷新列表",
            command=self.refresh_mod_list,
            style="info.TButton"
        ).pack(pady=5, fill=tk.X, padx=15)

        ttk.Button(
            control_panel,
            text="🚀 应用到游戏",
            command=self.install_mod,
            style="primary.TButton"
        ).pack(pady=5, fill=tk.X, padx=15)

        ttk.Button(
            control_panel,
            text="⚠️ 从游戏删除",
            command=self.uninstall,
            style="danger.TButton"
        ).pack(pady=5, fill=tk.X, padx=15)

        ttk.Button(
            control_panel,
            text="🎮 启动游戏",
            command=self.start_game,
            style="secondary.TButton"
        ).pack(pady=5, fill=tk.X, padx=15)
        mod_list_container = ttk.Frame(main_container, style="Card.TFrame")
        mod_list_container.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(mod_list_container, bg="#ffffff", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(mod_list_container, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollbar.pack(side=tk.RIGHT, fill="y")
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.mod_list_frame = ttk.Frame(self.canvas, style="Card.TFrame")
        self.canvas_window = self.canvas.create_window((0, 0), window=self.mod_list_frame, anchor="nw")

        self.mod_list_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))

        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1*(e.delta//120), "units"))

    def on_frame_configure(self, event):

        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def on_canvas_resize(self, event):

        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def on_mouse_wheel(self, event):

        self.canvas.yview_scroll(-1 * int(event.delta / 120), "units")

    def start_game(self):
        os.system("start steam://rungameid/553850")

    def real_install(self):
        mod_number = {}

        mod_suffix = ["", ".gpu_resources", ".stream"]
        try:
            with open(r".\mods\mod_name.json", "r", encoding="utf-8") as f:
                mod_name = json.load(f)
        except:
            print("未找到modname")
        try:
            with open(r".\mods\mod_list.json", "r", encoding="utf-8") as f:
                mod_list = json.load(f)
        except:
            print("未找到modlist")

        try:
            for temp_mod_name in mod_name.values():
                for temp_mod_list in mod_list.values():
                    for temp_mod_suffix in mod_suffix:
                        delete_file = os.path.join(install_dir, f"{temp_mod_name}.patch_{temp_mod_list}{temp_mod_suffix}")
                        if os.path.exists(delete_file):
                            os.remove(delete_file)
        except Exception as e:
            print("未删除", e)
        print("文件删除完毕")

        mod_name = {}
        mod_list = {}
        mod_install = 1

        if os.path.exists(os.path.join(".", "mods", "mod_sorted.yml")):
            with open(os.path.join(".", "mods", "mod_sorted.yml"), "r", encoding="utf-8") as f:
                mod_sorted_pre = yaml.safe_load(f)
        else:
            with open(os.path.join(".", "mods", "mod_sorted.yml"), "w", encoding="utf-8") as f:
                yaml.dump({}, f, default_flow_style=True, allow_unicode=True)
            mod_sorted_pre = {}

        mod_sorted_pre = {k: (float(v) if isinstance(v, str) and v.isdigit() else v) for k, v in mod_sorted_pre.items()}
        mod_sorted_list = os.listdir(MOD_FOLDER)

        for mod_folder in mod_sorted_list:
            if mod_folder not in mod_sorted_pre:
                mod_sorted_pre[mod_folder] = "9999"

        for key, value in mod_sorted_pre.items():
            mod_sorted_pre[key] = int(value)

        with open(os.path.join(".", "mods", "mod_sorted.yml"), "w", encoding="utf-8") as f:
            yaml.dump(mod_sorted_pre, f, allow_unicode=True)

        mod_sorted_list = sorted(mod_sorted_list, key=lambda f: mod_sorted_pre.get(f, float('inf')))

        for mod_folder in mod_sorted_list:
            mod_folder_path = os.path.join(MOD_FOLDER, mod_folder)
            print("开始安装mod")
            if not os.path.isdir(mod_folder_path):
                continue

            mod_info_path = os.path.join(mod_folder_path, "mod_info.yml")
            if not os.path.exists(mod_info_path):
                print(f"模组 {mod_folder} 缺少 mod_info.yml，跳过...")
                continue

            with open(mod_info_path, "r", encoding="utf-8") as f:
                mod_info = yaml.safe_load(f)

            if not mod_info.get("enabled", False):
                continue

            mod_files_path = os.path.join(mod_folder_path, "files")
            mod_files = os.listdir(mod_files_path)

            mod_file_prefix = None
            for file_name in mod_files:

                match = re.match(r"^(.+?)\.patch_\d+$", file_name)
                if match:
                    mod_file_prefix = match.group(1)
                    break

            if mod_file_prefix is None:
                print(f"模组 {mod_folder} 没有符合条件的 patch 文件，跳过...")
                continue

            grouped_files = defaultdict(lambda: defaultdict(list))

            for file in mod_files:
                match = re.match(r"^(.*?\.patch_\d+)", file)
                if match:
                    head_and_patch = match.group(1)
                    head_match = re.match(r"^(\S+)\.patch_(\d+)", head_and_patch)
                    if head_match:
                        file_head = head_match.group(1)
                        patch_number = head_match.group(2)
                        grouped_files[file_head][patch_number].append(file)

            for file_head, patch_group in grouped_files.items():
                for patch_number, files_in_group in patch_group.items():
                    max_number = -1
                    if not file_head in mod_number:
                        print(f"未找到已有数据. {file_head}")
                        existing_files = [
                            f for f in os.listdir(install_dir)
                            if re.match(fr"^{re.escape(file_head)}\.patch_\d+$", f)
                        ]
                        for file_name in existing_files:
                            match = re.match(rf"^{re.escape(file_head)}\.patch_(\d+)$", file_name)
                            if match:
                                patch_number = int(match.group(1))
                                if patch_number > max_number:
                                    max_number = patch_number
                        max_number += 1
                        if max_number < 0:
                            max_number = 0
                        if mod_number.get(file_head, -1) == -1:
                            mod_number[file_head] = max_number
                            print(f"{file_head}被赋值为{max_number}")
                    else:
                        max_number = mod_number[file_head]
                        print(f"{file_head}被赋值为{max_number}")
                    for file in files_in_group:
                        match = re.match(r"^(.+?)\.patch_(\d+)(\.\w+)?$", file)
                        if match:
                            file_prefix = match.group(1)
                            file_suffix = match.group(3)
                            if file_suffix is None:
                                new_file_name = f"{file_prefix}.patch_{max_number}"
                            else:
                                new_file_name = f"{file_prefix}.patch_{max_number}{file_suffix}"
                            source_file_path = os.path.join(mod_files_path, file)
                            destination_file_path = os.path.join(install_dir, new_file_name)
                            shutil.copy(source_file_path, destination_file_path)
                            print(f"文件 {file} 已复制为 {new_file_name} 到 {install_dir}")
                        mod_list[mod_install] = max_number
                        mod_name[mod_install] = file_prefix
                        mod_install += 1
                    mod_number[file_head] += 1

        with open(r".\mods\mod_name.json", "w", encoding="utf-8") as f:
            json.dump(mod_name, f, ensure_ascii=False, indent=4)
        with open(r".\mods\mod_list.json", "w", encoding="utf-8") as f:
            json.dump(mod_list, f, ensure_ascii=False, indent=4)
        messagebox.showinfo("模组安装完成！", "新版本改成异步而且优化了史山代码")

    def install_mod(self):
        thread = threading.Thread(target=self.real_install)
        thread.start()

    def uninstall(self):
        thread = threading.Thread(target=self.real_uninstall)
        thread.start()

    def real_uninstall(self):
        mod_suffix = ["", ".gpu_resources", ".stream"]
        try:
            with open(r".\mods\mod_name.json", "r", encoding="utf-8") as f:
                mod_name = json.load(f)
        except:
            print("未找到modname")
        try:
            with open(r".\mods\mod_list.json", "r", encoding="utf-8") as f:
                mod_list = json.load(f)
        except:
            print("未找到modlist")

        try:
            for temp_mod_name in mod_name.values():
                for temp_mod_list in mod_list.values():
                    for temp_mod_suffix in mod_suffix:
                        delete_file = os.path.join(install_dir,
                                                   f"{temp_mod_name}.patch_{temp_mod_list}{temp_mod_suffix}")
                        if os.path.exists(delete_file):
                            os.remove(delete_file)
        except Exception as e:
            print("未删除", e)

        messagebox.showinfo("删除完成!", "这个按钮的作用是, 删除所有由管理器安装的mod, 这样你就可以自己把mod安装为9ba_1来调试, 然后不会和管理器冲突")

    def update_visible_items(self, event=None):
        canvas_height = self.canvas.winfo_height()
        canvas_top = self.canvas.yview()[0] * self.canvas.bbox("all")[3]

        for widget in self.mod_list_frame.winfo_children():
            widget_top = widget.winfo_y()
            widget_bottom = widget_top + widget.winfo_height()
            if widget_bottom > canvas_top and widget_top < canvas_top + canvas_height:
                if widget not in self.rendered_mod_folders:
                    widget.grid()
                    self.rendered_mod_folders.add(widget)
            else:
                if widget in self.rendered_mod_folders:
                    widget.grid_forget()
                    self.rendered_mod_folders.remove(widget)

    def refresh_mod_list(self, event=None):
        search_term = self.search_var.get().lower()

        for widget in self.mod_list_frame.winfo_children():
            widget.destroy()

        mod_sorted_pre = {}
        sorted_yml_path = os.path.join(".", "mods", "mod_sorted.yml")
        if os.path.exists(sorted_yml_path):
            with open(sorted_yml_path, "r", encoding="utf-8") as f:
                mod_sorted_pre = yaml.safe_load(f) or {}

        mod_sorted_pre = {k: int(v) if str(v).isdigit() else 9999
                          for k, v in mod_sorted_pre.items()}

        mod_folders = [f for f in os.listdir(MOD_FOLDER)
                       if os.path.isdir(os.path.join(MOD_FOLDER, f))]

        for mod_folder in mod_folders:
            if mod_folder not in mod_sorted_pre:
                mod_sorted_pre[mod_folder] = 9999

        mod_sorted_list = sorted(mod_folders,
                                 key=lambda x: mod_sorted_pre.get(x, 9999))


        for index, mod_folder in enumerate(mod_sorted_list):
            row = index // 2
            column = index % 2

            mod_path = os.path.join(MOD_FOLDER, mod_folder)
            if not os.path.isdir(mod_path):
                continue

            mod_info_path = os.path.join(mod_path, "mod_info.yml")
            if not os.path.exists(mod_info_path):
                continue

            with open(mod_info_path, "r", encoding="utf-8") as f:
                mod_info = yaml.safe_load(f)

            mod_name = mod_info.get("name", "").lower()
            mod_author = mod_info.get("author", "").lower()
            mod_desc = mod_info.get("description", "").lower()
            if search_term not in f"{mod_name} {mod_author} {mod_desc}":
                continue

            container = ttk.Frame(self.mod_list_frame, style="CardContainer.TFrame", padding=2)
            container.grid(row=row, column=column, sticky="nsew", padx=5, pady=5)

            card = ttk.Frame(container, style="Card.TFrame", width=500)
            card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

            content_frame = ttk.Frame(card)
            content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

            top_frame = ttk.Frame(content_frame)
            top_frame.pack(fill=tk.BOTH, expand=True)

            preview_frame = ttk.Frame(top_frame)
            preview_frame.pack(side=tk.LEFT, fill=tk.Y)

            preview_image = self.default_preview_image
            preview_path = os.path.join(mod_path, "preview.png")
            if os.path.exists(preview_path):
                try:
                    img = Image.open(preview_path)
                    img = img.resize((100, 100), Image.LANCZOS)
                    preview_image = ImageTk.PhotoImage(img)
                except Exception as e:
                    print(f"Error loading preview image: {e}")

            img_label = ttk.Label(preview_frame, image=preview_image)
            img_label.image = preview_image
            img_label.pack()

            info_frame = ttk.Frame(top_frame)
            info_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)

            title_text = mod_info.get("name", "未命名模组")
            title_container = ttk.Frame(info_frame, height=60)
            title_container.pack(fill=tk.X, pady=(0, 5))

            check_text = font.Font(family="Segoe UI", size=12, weight="bold")
            text_width = check_text.measure(title_text)
            default_width = 291
            while text_width < default_width:
                title_text += "\n"
                default_width -= 291
            if text_width > 580:
                while text_width > 580:
                    title_text = title_text[:-1]
                    text_width = check_text.measure(title_text)
                title_text = title_text[:-1]
                title_text += "..."

            title_label = ttk.Label(
                title_container,
                text=title_text,
                font=("Segoe UI", 12, "bold"),
                foreground=self.primary_color,
                wraplength=300,
                anchor=tk.W,
                width=18,
                justify="left"
            )
            title_label.pack(fill=tk.X, pady=(0, 5))

            enabled = mod_info.get("enabled", False)
            status_icon = "🟢" if enabled else "🔴"
            status_color = self.success_color if enabled else self.danger_color
            status_label = ttk.Label(
                info_frame,
                text=f"{status_icon} {'已启用' if enabled else '已禁用'}",
                foreground=status_color,
                font=("Segoe UI", 10)
            )
            status_label.pack(anchor=tk.E)

            meta_frame = ttk.Frame(info_frame)
            meta_frame.pack(fill=tk.X, pady=(0, 5))
            if mod_info.get('author', '未知') == "":
                anthor = "未知作者"
            else:
                anthor = mod_info.get('author', '未知')
            ttk.Label(
                meta_frame,
                text=f"作者：{anthor}",
                font=("Segoe UI", 9),
                foreground="#6c757d"
            ).pack(side=tk.LEFT)

            ttk.Label(
                meta_frame,
                text=f"排序：{mod_sorted_pre.get(mod_folder, 9999)}",
                font=("Segoe UI", 9),
                foreground="#6c757d"
            ).pack(side=tk.RIGHT)

            desc_text = mod_info.get("description", "")
            desc_label = ttk.Label(
                content_frame,
                text=desc_text,
                wraplength=400,
                font=("Segoe UI", 9),
                justify=tk.LEFT,
                foreground="#495057"
            )
            desc_label.pack(fill=tk.X, anchor=tk.W, pady=(5, 0))

            btn_frame = ttk.Frame(content_frame)
            btn_frame.pack(fill=tk.X, pady=(5, 0))

            btn_container = ttk.Frame(btn_frame)
            btn_container.pack(expand=True)
            btn_style = {
                "style": "TButton",
                "width": 9,
                "padding": (3, 3)
            }

            buttons = [
                ("⚠️ 删除", 'danger.TButton', lambda m=mod_folder: self.delete_mod(m)),
                ("🔄 开关", 'info.TButton', lambda m=mod_folder, sl=status_label: self.toggle_mod(m, sl)),
                ("⚙️ 配置", 'secondary.TButton', lambda m=mod_folder: self.edit_mod_ui(m)),
                ("🌐 链接", 'primary.TButton', lambda m=mod_folder: self.open_url(m)),
                ("📁 文件夹", 'success.TButton', lambda m=mod_folder: os.startfile(os.path.join(MOD_FOLDER, mod_folder, "files")))
            ]

            for text, style_type, cmd in buttons:
                btn = ttk.Button(
                    btn_container,
                    text=text,
                    command=cmd,
                    style=style_type,
                    width=9,
                    padding=(3, 3)
                )
                btn.pack(side=tk.LEFT, padx=5)

        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.mod_list_frame.update_idletasks()

    def add_mod_ui(self, dropfile=None):

        def on_close():
            for delete in os.listdir("./temp"):
                shutil.rmtree(os.path.join("./temp", delete))
            self.root.destroy()

        def validate_input():
            errors = []
            if not mod_folder_var.get():
                errors.append("必须选择模组来源")
            if not mod_name_var.get():
                errors.append("必须填写模组名称")

            if errors:
                messagebox.showwarning("输入不完整", "\n".join(errors))
                return False
            return True

        def enhanced_save_mod():
            if validate_input():
                save_mod()

        def select_mod_folder():
            if dropfile is None:
                folder_path = filedialog.askdirectory(title="选择模组文件夹", parent=add_mod_window)
            else:
                folder_path = dropfile
            if folder_path:
                mod_folder_var.set(folder_path)
                mod_name_var.set(os.path.basename(folder_path))

                for file in os.listdir(folder_path):
                    if file.lower().endswith((".png", ".jpg", ".jpeg")):
                        preview_path = os.path.join(folder_path, file)
                        preview_path_var.set(preview_path)
                        img = Image.open(preview_path).resize((150, 150))
                        preview_image = ImageTk.PhotoImage(img)
                        preview_label.config(image=preview_image)
                        preview_label.image = preview_image
                        break

                patch_files = [
                    f for f in os.listdir(folder_path)
                    if re.match(r".+\.patch_\d+", f)
                ]
                if not patch_files:
                    messagebox.showwarning("警告", "未找到模组文件，请重新选择！")
                    mod_folder_var.set("")
                    preview_path_var.set("")
                    mod_name_var.set("")
                    return

        def select_mod_zip():
            global temp_floder
            if dropfile is None:
                file_types = [
                    ("压缩文件", "*.zip;*.7z;*.rar")
                ]

                folder_path = filedialog.askopenfilename(
                    title="选择压缩文件",
                    filetypes=file_types,
                    parent=add_mod_window
                )
            else:
                folder_path = dropfile

            if folder_path:
                temp_dir = os.path.join("./temp", ''.join(random.choice(characters) for _ in range(8)))
                file_extension = os.path.splitext(folder_path)[1].lower()

                if file_extension == '.zip':
                    with zipfile.ZipFile(folder_path, 'r') as zip_ref:
                        zip_ref.extractall(temp_dir)

                elif file_extension == '.rar':
                    if not os.path.exists(temp_dir):
                        os.makedirs(temp_dir)
                    new_file = os.path.join(temp_dir, os.path.basename(folder_path))
                    shutil.copy(folder_path, new_file)

                    dir_name, old_file_name = os.path.split(new_file)
                    new_file_name = 'new_file.rar'
                    new_path = os.path.join(dir_name, new_file_name)

                    os.rename(new_file, new_path)
                    subprocess.run(f"UnRAR.exe x {new_path} {temp_dir}")

                    os.remove(new_path)
                    try:
                        all_files = os.listdir(temp_dir)
                        folders = [f for f in all_files if os.path.isdir(os.path.join(temp_dir, f))]
                        folder_path = os.path.join(temp_dir, folders[0])
                    except:
                        None

                elif file_extension == '.7z':
                    with py7zr.SevenZipFile(folder_path, mode='r') as z:
                        z.extractall(path=temp_dir)

                items = os.listdir(temp_dir)

                dirs = [item for item in items if os.path.isdir(os.path.join(temp_dir, item))]
                files = [item for item in items if os.path.isfile(os.path.join(temp_dir, item))]

                if len(dirs) == 1 and len(files) == 0:
                    print(f"目录 '{temp_dir}' 中只有一个文件夹，无需移动文件。")
                    all_files = os.listdir(temp_dir)
                    folders = [f for f in all_files if os.path.isdir(os.path.join(temp_dir, f))]
                    folder_path = os.path.join(temp_dir, folders[0])
                else:
                    new_folder_name = os.path.splitext(os.path.basename(folder_path))[0]
                    new_folder_path = os.path.join(temp_dir, new_folder_name)

                    if not os.path.exists(new_folder_path):
                        os.makedirs(new_folder_path)
                        print(f"创建新文件夹: {new_folder_path}")

                    for file in files:
                        source_path = os.path.join(temp_dir, file)
                        destination_path = os.path.join(new_folder_path, file)
                        shutil.move(source_path, destination_path)
                        print(f"已将文件 '{file}' 移动到 '{new_folder_name}' 文件夹。")

                    folder_path = os.path.join(temp_dir, new_folder_name)

                mod_folder_var.set(folder_path)
                mod_name_var.set(os.path.basename(folder_path))

                for file in os.listdir(folder_path):
                    if file.lower().endswith((".png", ".jpg", ".jpeg")):
                        preview_path = os.path.join(folder_path, file)
                        preview_path_var.set(preview_path)
                        img = Image.open(preview_path).resize((150, 150))
                        preview_image = ImageTk.PhotoImage(img)
                        preview_label.config(image=preview_image)
                        preview_label.image = preview_image
                        break

                patch_files = [
                    f for f in os.listdir(folder_path)
                    if re.match(r".+\.patch_\d+", f)
                ]
                if not patch_files:
                    messagebox.showwarning("警告", "未找到模组文件，请重新选择！")
                    mod_folder_var.set("")
                    preview_path_var.set("")
                    mod_name_var.set("")
                    return

        def select_preview_image():
            file_path = filedialog.askopenfilename(
                title="选择预览图文件",
                filetypes=[("图像文件", "*.png;*.jpg;*.jpeg")],
                parent=add_mod_window
            )
            if file_path:
                preview_path_var.set(file_path)
                img = Image.open(file_path).resize((150, 150))
                preview_image = ImageTk.PhotoImage(img)
                preview_label.config(image=preview_image)
                preview_label.image = preview_image
        def import_preview_image():
            image = ImageGrab.grabclipboard()

            if isinstance(image, list):
                image = image[0]
            try:
                if os.path.isfile(image):
                    print("剪贴板内容不是图片，检查是否为路径")
                    clipboard_text = root.clipboard_get()
                    if os.path.isfile(clipboard_text):
                        if clipboard_text.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff")):
                            image_path = clipboard_text
                            select_preview_image(image_path)
                        else:
                            print("路径指向的不是图片文件")
                    else:
                        print("剪贴板内容既不是图片也不是有效的路径")
            except TypeError as e:
                print("剪贴板内容是图片")
                temp_dir = os.path.join("./temp", ''.join(random.choice(characters) for _ in range(8)))
                os.mkdir(temp_dir)
                ext = image.format.lower()
                temp_file_path = os.path.join(temp_dir, f'img.{ext}')
                image.save(temp_file_path)
                image_path = temp_file_path
                print(image_path)
                select_preview_image(image_path)

        def save_mod():
            mod_folder = mod_folder_var.get().strip()
            mod_name = mod_name_var.get().strip()
            mod_link = mod_url_var.get().strip()
            mod_author = mod_author_var.get().strip()
            preview_path = preview_path_var.get()
            mod_sorted_value = mod_sorted_var.get()

            if not mod_sorted_value:
                mod_sorted_value = "9999"

            mod_sorted_value = int(mod_sorted_value)

            mod_sorted[os.path.basename(mod_folder)] = mod_sorted_value

            if not mod_folder:
                messagebox.showwarning("警告", "模组文件夹不能为空！")
                return

            cok = True
            mod_name_fix = None
            i = 1
            while cok:
                mod_folder_path = os.path.join(MOD_FOLDER, f"{mod_name}{mod_name_fix if mod_name_fix is not None else ''}")
                if os.path.exists(mod_folder_path):
                    mod_name_fix = f"({i})"
                    i += 1
                else:
                    cok = False

            os.makedirs(mod_folder_path)

            copied_folder_path = os.path.join(mod_folder_path, os.path.basename(mod_folder))
            shutil.copytree(mod_folder, os.path.join(mod_folder_path, os.path.basename(mod_folder)))

            new_folder_name = os.path.join(mod_folder_path, "files")
            os.rename(copied_folder_path, new_folder_name)

            for file in os.listdir(new_folder_name):
                if not re.match(r".+\.patch_\d+", file):
                    os.remove(os.path.join(new_folder_name, file))

            mod_info = {
                "name": mod_name,
                "author": mod_author,
                "enabled": True,
                "link": mod_link,
                "delete": False
            }

            with open(os.path.join(".", "mods", "mod_sorted.yml"), "w", encoding="utf-8") as f:
                yaml.dump(mod_sorted, f, allow_unicode=True)

            with open(os.path.join(mod_folder_path, "mod_info.yml"), "w", encoding="utf-8") as f:
                yaml.dump(mod_info, f, allow_unicode=True)

            if preview_path:
                shutil.copy(preview_path, os.path.join(mod_folder_path, "preview.png"))
            for delete in os.listdir("./temp"):
                shutil.rmtree(os.path.join("./temp", delete))

            add_mod_window.destroy()
            messagebox.showinfo("成功", f"模组 {mod_name} 已添加！")
            self.refresh_mod_list()

        add_mod_window = tk.Toplevel(self.root)
        add_mod_window.title("添加模组")
        add_mod_window.geometry("720x520")
        add_mod_window.resizable(False, False)
        style = Style(theme="flatly")

        try:
            add_mod_window.iconbitmap(resource_path("app_icon.ico"))
        except:
            None

        mod_folder_var = tk.StringVar()
        mod_name_var = tk.StringVar()
        mod_author_var = tk.StringVar()
        preview_path_var = tk.StringVar()
        mod_url_var = tk.StringVar()
        mod_sorted_var = tk.StringVar()

        if os.path.exists(os.path.join(".", "mods", "mod_sorted.yml")):
            with open(os.path.join(".", "mods", "mod_sorted.yml"), "r", encoding="utf-8") as f:
                mod_sorted = yaml.safe_load(f)
        else:
            with open(os.path.join(".", "mods", "mod_sorted.yml"), "w", encoding="utf-8") as f:
                yaml.dump({}, f, default_flow_style=True, allow_unicode=True)
            mod_sorted = {}

        main_frame = ttk.Frame(add_mod_window)
        main_frame.pack(padx=20, pady=20, fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 20))

        ttk.Label(left_frame, text="模组信息", font=("Segoe UI", 14, "bold"), foreground="#2c3e50").pack(anchor=tk.W, pady=10)

        field_style = {"font": ("Segoe UI", 10), "padding": 5}
        input_style = {"style": "TEntry", "font": ("Segoe UI", 10)}

        ttk.Label(left_frame, text="来源路径:", **field_style).pack(anchor=tk.W)
        path_frame = ttk.Frame(left_frame)
        path_frame.pack(fill=tk.X, pady=5)
        ttk.Entry(path_frame, textvariable=mod_folder_var, state="readonly", **input_style).pack(side=tk.LEFT,
                                                                                                 fill=tk.X, expand=True)
        ttk.Button(path_frame, text="文件夹", command=select_mod_folder, width=8).pack(side=tk.LEFT, padx=5)
        ttk.Button(path_frame, text="压缩包", command=select_mod_zip, width=8).pack(side=tk.LEFT)

        ttk.Label(left_frame, text="模组名称:", **field_style).pack(anchor=tk.W)
        ttk.Entry(left_frame, textvariable=mod_name_var, **input_style).pack(fill=tk.X, pady=5)

        ttk.Label(left_frame, text="模组作者:", **field_style).pack(anchor=tk.W)
        ttk.Entry(left_frame, textvariable=mod_author_var, **input_style).pack(fill=tk.X, pady=5)

        ttk.Label(left_frame, text="模组链接:", **field_style).pack(anchor=tk.W)
        ttk.Entry(left_frame, textvariable=mod_url_var, **input_style).pack(fill=tk.X, pady=5)

        ttk.Label(left_frame, text="加载排序:", **field_style).pack(anchor=tk.W)
        ttk.Entry(left_frame, textvariable=mod_sorted_var, **input_style).pack(fill=tk.X, pady=5)

        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.TOP, fill=tk.BOTH, pady=40, anchor="n")

        ttk.Label(right_frame, text="预览图", font=("Segoe UI", 12), foreground="#2c3e50").pack(pady=10)

        preview_container = ttk.Frame(right_frame, relief="solid", borderwidth=1)
        preview_container.pack()
        preview_label = ttk.Label(preview_container, image=self.default_preview_image)
        preview_label.pack(padx=10, pady=10)

        btn_container = ttk.Frame(right_frame)
        btn_container.pack(pady=10, fill=tk.X)

        self.style.configure("Blue.TButton", background="#4a86e8", foreground="white", borderwidth=1, font=("Segoe UI Emoji", 10), width=12)
        self.style.configure("Green.TButton",  background="#28a745", foreground="white")
        self.style.configure("Red.TButton", background="#dc3545", foreground="white")

        ttk.Button(btn_container, text="📸 选择图片", command=select_preview_image, style="Blue.TButton").pack(side=tk.TOP, fill=tk.X, pady=7, padx=5)
        ttk.Button(btn_container, text="📋 粘贴图片", command=import_preview_image, style="Blue.TButton").pack(side=tk.TOP, fill=tk.X, pady=7, padx=5)
        ttk.Button(btn_container, text="✅ 保存模组", command=save_mod, style="Green.TButton").pack(side=tk.TOP, fill=tk.X, pady=7, padx=5)
        ttk.Button(btn_container, text="❌ 取消保存", command=add_mod_window.destroy, style="Red.TButton").pack(side=tk.TOP, fill=tk.X, pady=7, padx=5)

        if not dropfile is None:
            dropfile = dropfile.strip("{}")
            dropfile_path = Path(dropfile)
            if dropfile_path.suffix in [".zip", ".7z", ".rar"]:
                select_mod_zip()
                dropfile = None
            elif os.path.isdir(dropfile_path):
                select_mod_folder()
                dropfile = None

    def on_drop(self, event):
        dropped_file = os.path.normpath(event.data)
        self.add_mod_ui(dropped_file)

    def edit_mod_ui(self, mod_folder):

        def on_close():
            for delete in os.listdir("./temp"):
                shutil.rmtree(os.path.join("./temp", delete))
            self.root.destroy()

        def select_preview_image(image_path=None):
            if image_path is None:
                file_path = filedialog.askopenfilename(
                    title="选择预览图文件",
                    filetypes=[("图像文件", "*.png;*.jpg;*.jpeg")],
                    parent=edit_window
                )
            else:
                file_path = image_path
                print(image_path)
            if file_path:
                preview_path_var.set(file_path)
                img = Image.open(file_path).resize((150, 150))
                preview_image = ImageTk.PhotoImage(img)
                preview_label.config(image=preview_image)
                preview_label.image = preview_image

        def import_preview_image():
            image = ImageGrab.grabclipboard()

            if isinstance(image, list):
                image = image[0]
            try:
                if os.path.isfile(image):
                    print("剪贴板内容不是图片，检查是否为路径")
                    clipboard_text = root.clipboard_get()
                    if os.path.isfile(clipboard_text):
                        if clipboard_text.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff")):
                            image_path = clipboard_text
                            select_preview_image(image_path)
                        else:
                            print("路径指向的不是图片文件")
                    else:
                        print("剪贴板内容既不是图片也不是有效的路径")
            except TypeError as e:
                print("剪贴板内容是图片")
                temp_dir = os.path.join("./temp", ''.join(random.choice(characters) for _ in range(8)))
                os.mkdir(temp_dir)
                ext = image.format.lower()
                temp_file_path = os.path.join(temp_dir, f'img.{ext}')
                image.save(temp_file_path)
                image_path = temp_file_path
                print(image_path)
                select_preview_image(image_path)

        def save_mod():
            mod_folder_path = os.path.join(".", "mods", mod_folder)

            mod_link = mod_url_var.get().strip()
            mod_author = mod_author_var.get().strip()
            preview_path = preview_path_var.get()
            mod_sorted_value = mod_sorted_var.get()
            mod_name = mod_name_var.get()
            """我也不知道为什么 这里不get一次组件里面就不显示了"""
            no_use_mod_folder = mod_folder_var.get()
            """我也不知道为什么 这里不get一次组件里面就不显示了"""

            if not mod_sorted_value:
                mod_sorted_value = "9999"

            mod_sorted_value = int(mod_sorted_value)

            mod_sorted[os.path.basename(mod_folder)] = mod_sorted_value

            mod_info = {
                "name": mod_name,
                "author": mod_author,
                "enabled": True,
                "link": mod_link,
                "delete": False
            }

            with open(os.path.join(mod_folder_path, "mod_info.yml"), "w", encoding="utf-8") as f:
                yaml.dump(mod_info, f, allow_unicode=True)

            with open(os.path.join(".", "mods", "mod_sorted.yml"), "w", encoding="utf-8") as f:
                yaml.dump(mod_sorted, f, allow_unicode=True)

            if preview_path:
                if not preview_path == os.path.join(mod_folder_path, "preview.png"):
                    shutil.copy(preview_path, os.path.join(mod_folder_path, "preview.png"))

            edit_window.destroy()
            messagebox.showinfo("成功", f"模组 {mod_name} 配置已修改！")
            self.refresh_mod_list()

        edit_window = tk.Toplevel(self.root)
        edit_window.title("编辑模组")
        edit_window.geometry("720x500")
        edit_window.resizable(False, False)
        style = Style(theme="flatly")

        try:
            edit_window.iconbitmap(resource_path("app_icon.ico"))
        except:
            None

        mod_name_var = tk.StringVar()
        mod_author_var = tk.StringVar()
        preview_path_var = tk.StringVar()
        mod_url_var = tk.StringVar()
        mod_folder_var = tk.StringVar()
        mod_sorted_var = tk.StringVar()

        mod_folder_path = os.path.join(".", "mods", mod_folder)

        with open(os.path.join(mod_folder_path, "mod_info.yml"), "r", encoding="utf-8") as f:
            mod_info = yaml.safe_load(f)

        if os.path.exists(os.path.join(".", "mods", "mod_sorted.yml")):
            with open(os.path.join(".", "mods", "mod_sorted.yml"), "r", encoding="utf-8") as f:
                mod_sorted = yaml.safe_load(f)
        else:
            with open(os.path.join(".", "mods", "mod_sorted.yml"), "w", encoding="utf-8") as f:
                yaml.dump({}, f, default_flow_style=True, allow_unicode=True)
            mod_sorted = {}

        mod_folder_var.set("不可修改,如要修改请重新添加mod")
        mod_name_var.set(mod_info["name"])
        mod_author_var.set(mod_info["author"])
        mod_url_var.set(mod_info["link"])
        if mod_sorted is not None and mod_folder in mod_sorted:
            if mod_sorted[os.path.basename(mod_folder)]:
                mod_sorted_var.set(mod_sorted[os.path.basename(mod_folder)])

        main_frame = ttk.Frame(edit_window)
        main_frame.pack(padx=20, pady=20, fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 20))

        ttk.Label(left_frame, text="修改配置", font=("Segoe UI", 14, "bold"), foreground="#2c3e50").pack(anchor=tk.W, pady=10)

        field_style = {"font": ("Segoe UI", 10), "padding": 5}
        input_style = {"style": "TEntry", "font": ("Segoe UI", 10)}

        ttk.Label(left_frame, text="安装路径:", **field_style).pack(anchor=tk.W)
        ttk.Entry(left_frame, textvariable=mod_folder_var, state="readonly", **input_style).pack(fill=tk.X, pady=5)

        ttk.Label(left_frame, text="模组名称:", **field_style).pack(anchor=tk.W)
        ttk.Entry(left_frame, textvariable=mod_name_var, **input_style).pack(fill=tk.X, pady=5)

        ttk.Label(left_frame, text="模组作者:", **field_style).pack(anchor=tk.W)
        ttk.Entry(left_frame, textvariable=mod_author_var, **input_style).pack(fill=tk.X, pady=5)

        ttk.Label(left_frame, text="模组链接:", **field_style).pack(anchor=tk.W)
        ttk.Entry(left_frame, textvariable=mod_url_var, **input_style).pack(fill=tk.X, pady=5)

        ttk.Label(left_frame, text="加载排序:", **field_style).pack(anchor=tk.W)
        ttk.Entry(left_frame, textvariable=mod_sorted_var, **input_style).pack(fill=tk.X, pady=5)

        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.TOP, fill=tk.BOTH, pady=40, anchor="n")

        ttk.Label(right_frame, text="预览图", font=("Segoe UI", 12),
                  foreground="#2c3e50").pack(pady=10)

        preview_container = ttk.Frame(right_frame, relief="solid", borderwidth=1)
        preview_container.pack()
        preview_label = ttk.Label(preview_container, image=self.default_preview_image)
        preview_label.pack(padx=10, pady=10)

        btn_container = ttk.Frame(right_frame)
        btn_container.pack(pady=10, fill=tk.X)

        self.style.configure("Blue.TButton", background="#4a86e8", foreground="white", borderwidth=1, font=("Segoe UI", 10), width=12)
        self.style.configure("Green.TButton",  background="#28a745", foreground="white")
        self.style.configure("Red.TButton", background="#dc3545", foreground="white")

        ttk.Button(btn_container, text="📸 选择图片", command=select_preview_image, style="Blue.TButton").pack(side=tk.TOP, fill=tk.X, pady=7, padx=5)
        ttk.Button(btn_container, text="📋 粘贴图片", command=import_preview_image, style="Blue.TButton").pack(side=tk.TOP, fill=tk.X, pady=7, padx=5)
        ttk.Button(btn_container, text="✅ 保存模组", command=save_mod, style="Green.TButton").pack(side=tk.TOP, fill=tk.X, pady=7, padx=5)
        ttk.Button(btn_container, text="❌ 取消保存", command=edit_window.destroy, style="Red.TButton").pack(side=tk.TOP, fill=tk.X, pady=7, padx=5)

        file_path =  os.path.join(mod_folder_path, "preview.png")
        if file_path:
            preview_path_var.set(file_path)
            img = Image.open(file_path).resize((150, 150))
            preview_image = ImageTk.PhotoImage(img)
            preview_label.config(image=preview_image)
            preview_label.image = preview_image

        self.root.protocol("WM_DELETE_WINDOW", on_close)

    def toggle_mod(self, mod_folder, status_label):
        mod_info_path = os.path.join(MOD_FOLDER, mod_folder, "mod_info.yml")

        with open(mod_info_path, "r", encoding="utf-8") as f:
            mod_info = yaml.safe_load(f)
        new_status = not mod_info.get("enabled", False)
        mod_info["enabled"] = new_status

        with open(mod_info_path, "w", encoding="utf-8") as f:
            yaml.dump(mod_info, f, allow_unicode=True)

        status_icon = "🟢" if new_status else "🔴"
        status_text = f"{status_icon} {'已启用' if new_status else '已禁用'}"
        status_label.config(
            text=status_text,
            foreground=self.success_color if new_status else self.danger_color
        )

    def open_url(self, mod_folder):

        mod_info_path = os.path.join(MOD_FOLDER, mod_folder, "mod_info.yml")
        with open(mod_info_path, "r", encoding="utf-8") as f:
            mod_info = yaml.safe_load(f)
            mod_link = mod_info.get("link", "none") or "none"
        if mod_link != "none":
            webbrowser.open(mod_link)
        else:
            messagebox.showinfo("提示", "该模组没有设置链接")

    def delete_mod(self, mod_folder):
        confirm = messagebox.askyesno(
            "确认删除",
            f"确定要删除模组 {mod_folder} 吗？\n\n"
            "注意：这将会从管理器移除模组，随后你要再点击一次应用到游戏以彻底删除",
            icon='warning'
        )
        if confirm:
            try:
                shutil.rmtree(os.path.join(MOD_FOLDER, mod_folder))
                self.refresh_mod_list()
                messagebox.showinfo("删除成功", f"模组 {mod_folder} 已删除")
            except Exception as e:
                messagebox.showerror("删除失败", f"删除时发生错误：{str(e)}")

if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = ModManagerApp(root)
    root.iconbitmap(resource_path("app_icon.ico"))
    root.mainloop()
