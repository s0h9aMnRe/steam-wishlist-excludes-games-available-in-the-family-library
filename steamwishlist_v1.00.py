import os
import sys
import time
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import psutil
import pyautogui
import numpy as np
import easyocr
from datetime import datetime
import ctypes

# 资源路径处理函数
def resource_path(relative_path):
    """获取资源的绝对路径，兼容PyInstaller打包后的路径"""
    try:
        # PyInstaller 创建临时文件夹，将路径存储在 _MEIPASS 中
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path)

# 设置DPI感知，解决高分辨率屏幕问题
try:
    # 设置为Per-Monitor DPI Aware
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception as e:
    print(f"DPI感知设置失败: {e}", file=sys.stderr)

# 确保中文显示正常
font_family = "微软雅黑" if sys.platform.startswith("win") else "Heiti TC"

# 全局变量
wishlist_path = ""
result_dir = ""
processing = False
paused = False
current_index = 0
total_games = 0
wishlist_games = []
progress_file = "progress.json"
hint_window = None  # 存储提示窗口引用

# 常驻提示窗口类
class PermanentHintWindow:
    def __init__(self, master):
        self.master = master
        self.is_visible = True
        
        # 创建半透明顶层窗口
        self.hint_window = tk.Toplevel(master)
        self.hint_window.attributes("-topmost", True)
        self.hint_window.attributes("-alpha", 0.8)
        self.hint_window.overrideredirect(True)  # 去除窗口装饰
        
        # 设置指定大小（531×91像素）
        window_width = 531
        window_height = 91
        screen_width = master.winfo_screenwidth()
        screen_height = master.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.hint_window.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        # 创建Canvas用于绘制边框和文字
        self.canvas = tk.Canvas(self.hint_window, bg="white", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # 绘制红色边框（更粗更明显）
        self.canvas.create_rectangle(
            5, 5, window_width-5, window_height-5,
            outline="#FF0000", width=4, tags="border"
        )
        
        # 添加提示文字（适应长方形布局）
        self.canvas.create_text(
            window_width//2, window_height//2,
            text="将Steam库的搜索栏放到此框内",
            fill="#FF0000", font=(font_family, 12, "bold"),
            tags="text"
        )
        
        # 绑定鼠标拖动窗口
        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.drag_window)
        
    def start_drag(self, event):
        """开始拖动窗口"""
        self.x = event.x
        self.y = event.y
        
    def drag_window(self, event):
        """拖动窗口"""
        x = self.hint_window.winfo_x() - self.x + event.x
        y = self.hint_window.winfo_y() - self.y + event.y
        self.hint_window.geometry(f"+{x}+{y}")
        
    def show(self):
        """显示提示窗口"""
        if not self.is_visible:
            self.hint_window.deiconify()
            self.is_visible = True
            
    def hide(self):
        """隐藏提示窗口"""
        if self.is_visible:
            self.hint_window.withdraw()
            self.is_visible = False
            
    def get_position(self):
        """获取窗口位置和大小"""
        x = self.hint_window.winfo_x()
        y = self.hint_window.winfo_y()
        width = self.hint_window.winfo_width()
        height = self.hint_window.winfo_height()
        
        # 返回实际有效区域（去掉边框）
        return (x + 5, y + 5, width - 10, height - 10)

# Steam控制类
class SteamController:
    def __init__(self):
        self.steam_process_name = "steamwebhelper.exe"
        self.target_region = None
        # 初始化EasyOCR阅读器（使用打包的模型文件）
        try:
            self.reader = easyocr.Reader(
                ['ch_sim', 'en'],
                model_storage_directory=resource_path('easyocr/model'),
                download_enabled=False
            )
        except Exception as e:
            print(f"初始化OCR阅读器失败: {e}")
            self.reader = None
    
    def is_steam_running(self):
        for proc in psutil.process_iter(['name']):
            if proc.info['name'].lower() == self.steam_process_name.lower():
                return True
        return False
    
    def set_target_region(self, region):
        self.target_region = region
    
    def search_game(self, game_name):
        if not self.target_region:
            return False
        
        if not self.reader:
            print("OCR阅读器未初始化")
            return False
        
        try:
            region_x, region_y, region_width, region_height = self.target_region
            
            # 计算搜索框位置
            search_x = region_x + region_width // 2
            search_y = region_y + region_height // 2
            
            # 点击搜索框
            pyautogui.moveTo(search_x, search_y, duration=0.3)
            pyautogui.click()
            time.sleep(0.2)
            
            # 全选并删除现有内容
            pyautogui.hotkey('ctrl', 'a')
            pyautogui.press('backspace')
            time.sleep(0.1)
            
            # 输入游戏名称
            pyautogui.typewrite(game_name, interval=0.05)
            pyautogui.press('enter')
            
            # 等待搜索结果加载
            time.sleep(3)
            
            # OCR识别区域（红框下方531×300）
            ocr_x = region_x
            ocr_y = region_y + region_height
            ocr_width = 531
            ocr_height = 300
            
            # 截图识别区域
            screenshot = pyautogui.screenshot(region=(ocr_x, ocr_y, ocr_width, ocr_height))
            img_array = np.array(screenshot)
            
            # 进行OCR识别
            result = self.reader.readtext(img_array)
            
            # 检查是否出现目标文字 - 修改逻辑：找到文字表示游戏存在，没找到表示游戏不存在
            target_texts = ["找不到您要找的游戏吗"]
            found = any(any(text in line[1] for line in result) for text in target_texts)
            
            # 识别完成后删除搜索内容
            pyautogui.hotkey('ctrl', 'a')
            pyautogui.press('backspace')
            time.sleep(0.1)
            
            # 修改：如果找到"找不到您要找的游戏吗"，说明游戏不存在，返回False
            # 如果没找到这个文字，说明游戏存在，返回True
            return not found  # 这里取反，修正逻辑
            
        except Exception as e:
            print(f"搜索游戏失败: {e}", file=sys.stderr)
            return False

# 文件处理类
class FileHandler:
    @staticmethod
    def load_wishlist(path):
        """加载愿望单文件"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip()]
            return lines
        except Exception as e:
            print(f"加载愿望单失败: {e}", file=sys.stderr)
            return []
    
    @staticmethod
    def save_results(results, output_dir):
        """保存检查结果"""
        try:
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"检查结果_{timestamp}.txt"
            filepath = os.path.join(output_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Steam愿望单检查结果\n")
                f.write(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"总游戏数: {len(results)}\n")
                f.write(f"未找到游戏数: {sum(1 for game, status in results if not status)}\n")
                f.write("=" * 50 + "\n\n")
                
                for i, (game, status) in enumerate(results, 1):
                    status_text = "✓ 存在" if status else "✗ 未找到"
                    f.write(f"{i:3d}. {game:<50} {status_text}\n")
            
            return filepath
        except Exception as e:
            print(f"保存结果失败: {e}", file=sys.stderr)
            return None
    
    @staticmethod
    def save_progress(progress_data):
        """保存进度"""
        try:
            with open(progress_file, 'w', encoding='utf-8') as f:
                json.dump(progress_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存进度失败: {e}", file=sys.stderr)
    
    @staticmethod
    def load_progress():
        """加载进度"""
        try:
            if os.path.exists(progress_file):
                with open(progress_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"加载进度失败: {e}", file=sys.stderr)
        return None

# 主应用类
class WishlistCheckerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Steam愿望单检查工具")
        
        # 设置更大的默认窗口尺寸，适应4K屏幕
        self.root.geometry("1000x700")
        self.root.minsize(800, 600)  # 防止窗口过小
        
        # 设置窗口图标（如果有）
        try:
            self.root.iconbitmap(resource_path("icon.ico"))
        except:
            pass
        
        # 初始化Steam控制器
        self.steam_controller = SteamController()
        
        # 初始化文件处理器
        self.file_handler = FileHandler()
        
        # 存储结果
        self.results = []
        
        # 初始化UI
        self.init_ui()
        
        # 检查是否有保存的进度
        self.check_progress()
        
        # 绑定窗口关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def init_ui(self):
        """初始化UI界面"""
        # 创建主框架，使用更灵活的布局
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 配置权重，使框架可以扩展
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)  # 结果区域可扩展
        
        # 创建工具栏 - 使用网格布局，更灵活
        toolbar = ttk.Frame(main_frame)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        toolbar.columnconfigure(0, weight=1)
        
        # 工具栏内部框架，容纳按钮
        button_frame = ttk.Frame(toolbar)
        button_frame.pack(fill=tk.X, expand=True)
        
        # 加载愿望单按钮
        self.btn_load = ttk.Button(button_frame, text="加载愿望单", command=self.load_wishlist)
        self.btn_load.pack(side=tk.LEFT, padx=(0, 5))
        
        # 选择输出目录按钮
        self.btn_output = ttk.Button(button_frame, text="选择输出目录", command=self.select_output_dir)
        self.btn_output.pack(side=tk.LEFT, padx=(0, 5))
        
        # 开始检查按钮
        self.btn_start = ttk.Button(button_frame, text="开始检查", command=self.start_check, state=tk.DISABLED)
        self.btn_start.pack(side=tk.LEFT, padx=(0, 5))
        
        # 暂停/继续按钮
        self.btn_pause = ttk.Button(button_frame, text="暂停", command=self.toggle_pause, state=tk.DISABLED)
        self.btn_pause.pack(side=tk.LEFT, padx=(0, 5))
        
        # 停止按钮
        self.btn_stop = ttk.Button(button_frame, text="停止", command=self.stop_check, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 5))
        
        # 显示/隐藏红框按钮
        self.btn_toggle_hint = ttk.Button(button_frame, text="显示红框", command=self.toggle_hint_window)
        self.btn_toggle_hint.pack(side=tk.LEFT)
        
        # 创建状态框架
        status_frame = ttk.Frame(main_frame)
        status_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        
        # 状态标签
        self.lbl_status = ttk.Label(status_frame, text="状态: 就绪", font=(font_family, 10, "bold"))
        self.lbl_status.pack(side=tk.LEFT)
        
        # 进度条
        self.progress = ttk.Progressbar(status_frame, orient=tk.HORIZONTAL, mode='determinate')
        self.progress.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0))
        
        # 创建结果显示区域 - 使用网格并设置权重使其可扩展
        result_frame = ttk.Frame(main_frame)
        result_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(0, weight=1)
        
        # 结果树 - 使用网格布局
        columns = ("index", "game", "status")
        self.result_tree = ttk.Treeview(result_frame, columns=columns, show="headings", height=20)
        
        # 设置列标题
        self.result_tree.heading("index", text="序号")
        self.result_tree.heading("game", text="游戏名称")
        self.result_tree.heading("status", text="状态")
        
        # 设置列宽和属性
        self.result_tree.column("index", width=60, anchor=tk.CENTER, stretch=False)
        self.result_tree.column("game", width=600, anchor=tk.W, stretch=True)  # 游戏名称列可拉伸
        self.result_tree.column("status", width=120, anchor=tk.CENTER, stretch=False)
        
        # 增加行高和字体大小
        style = ttk.Style()
        style.configure("Treeview", 
                       rowheight=30,  # 增加行高
                       font=(font_family, 10))  # 设置字体大小
        
        style.configure("Treeview.Heading", 
                       font=(font_family, 10, "bold"))  # 表头字体
        
        # 添加滚动条
        scrollbar_y = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=self.result_tree.yview)
        scrollbar_x = ttk.Scrollbar(result_frame, orient=tk.HORIZONTAL, command=self.result_tree.xview)
        self.result_tree.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
        
        # 使用网格布局，使Treeview可扩展
        self.result_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar_y.grid(row=0, column=1, sticky="ns")
        scrollbar_x.grid(row=1, column=0, sticky="ew")
        
        # 创建信息框架
        info_frame = ttk.Frame(main_frame)
        info_frame.grid(row=3, column=0, sticky="ew")
        
        # 信息标签
        self.lbl_info = ttk.Label(info_frame, text="请加载愿望单文件并选择输出目录", wraplength=900)
        self.lbl_info.pack(fill=tk.X, expand=True)
    
    def load_wishlist(self):
        """加载愿望单文件"""
        path = filedialog.askopenfilename(
            title="选择愿望单文件",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        
        if path:
            global wishlist_path, wishlist_games, total_games
            wishlist_path = path
            wishlist_games = self.file_handler.load_wishlist(path)
            total_games = len(wishlist_games)
            
            if total_games > 0:
                self.update_status(f"已加载 {total_games} 个游戏")
                self.update_info(f"愿望单文件: {os.path.basename(path)}\n游戏总数: {total_games}")
                
                # 清空结果树
                self.clear_results()
                
                # 添加游戏到结果树
                for i, game in enumerate(wishlist_games, 1):
                    self.result_tree.insert("", tk.END, values=(i, game, "等待检查"))
                
                # 启用开始按钮
                if result_dir:
                    self.btn_start.config(state=tk.NORMAL)
            else:
                self.update_status("加载失败: 愿望单为空")
                self.update_info("错误: 愿望单文件为空或格式不正确")
    
    def select_output_dir(self):
        """选择输出目录"""
        global result_dir
        result_dir = filedialog.askdirectory(title="选择输出目录")
        
        if result_dir:
            self.update_status(f"已选择输出目录: {os.path.basename(result_dir)}")
            self.update_info(f"输出目录: {result_dir}")
            
            # 启用开始按钮
            if wishlist_games:
                self.btn_start.config(state=tk.NORMAL)
    
    def start_check(self):
        """开始检查"""
        global processing, paused, current_index
        
        # 检查Steam是否运行
        if not self.steam_controller.is_steam_running():
            messagebox.showerror("错误", "未检测到Steam运行，请先启动Steam")
            return
        
        # 检查红框是否显示
        if hint_window and hint_window.is_visible:
            # 开始检查时隐藏红框
            hint_window.hide()
            self.btn_toggle_hint.config(text="显示红框")
        
        # 检查是否有保存的进度
        if current_index > 0 and current_index < total_games:
            if messagebox.askyesno("继续检查", f"发现上次未完成的检查，是否从第 {current_index + 1} 个游戏继续？"):
                pass
            else:
                current_index = 0
                self.clear_results()
                for i, game in enumerate(wishlist_games, 1):
                    self.result_tree.insert("", tk.END, values=(i+1, game, "等待检查"))
        
        processing = True
        paused = False
        
        # 更新按钮状态
        self.btn_start.config(state=tk.DISABLED)
        self.btn_pause.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.NORMAL)
        self.btn_load.config(state=tk.DISABLED)
        self.btn_output.config(state=tk.DISABLED)
        
        # 更新状态
        self.update_status("正在检查...")
        self.update_info(f"当前进度: {current_index}/{total_games}")
        
        # 设置目标区域
        if hint_window:
            self.steam_controller.set_target_region(hint_window.get_position())
        
        # 创建线程进行检查
        self.check_thread = threading.Thread(target=self.check_games)
        self.check_thread.daemon = True
        self.check_thread.start()
    
    def check_games(self):
        """检查游戏"""
        global current_index, processing
        
        # 清空结果
        self.results = []
        
        # 加载之前的结果
        if current_index > 0:
            for i in range(current_index):
                item = self.result_tree.item(self.result_tree.get_children()[i])
                game = item["values"][1]
                status = item["values"][2] == "✓ 存在"
                self.results.append((game, status))
        
        try:
            while current_index < total_games and processing:
                if paused:
                    time.sleep(0.5)
                    continue
                
                game = wishlist_games[current_index]
                self.update_status(f"正在检查: {game}")
                
                # 更新当前游戏状态
                self.result_tree.set(self.result_tree.get_children()[current_index], "status", "检查中...")
                self.result_tree.see(self.result_tree.get_children()[current_index])
                
                # 搜索游戏 - 结果已经修正逻辑
                status = self.steam_controller.search_game(game)
                
                # 更新结果
                status_text = "✓ 存在" if status else "✗ 未找到"
                self.result_tree.set(self.result_tree.get_children()[current_index], "status", status_text)
                
                # 保存结果
                self.results.append((game, status))
                
                # 更新进度
                current_index += 1
                progress_percent = (current_index / total_games) * 100
                self.progress.config(value=progress_percent)
                self.update_info(f"当前进度: {current_index}/{total_games} ({progress_percent:.1f}%)")
                
                # 保存进度
                progress_data = {
                    "wishlist_path": wishlist_path,
                    "result_dir": result_dir,
                    "current_index": current_index,
                    "total_games": total_games,
                    "results": self.results
                }
                self.file_handler.save_progress(progress_data)
                
                # 短暂延迟，避免操作过快
                time.sleep(1)
            
            if processing:
                # 检查完成
                self.update_status("检查完成")
                self.update_info(f"检查完成！共检查 {total_games} 个游戏，其中 {sum(1 for game, status in self.results if not status)} 个游戏未找到")
                
                # 保存结果
                output_path = self.file_handler.save_results(self.results, result_dir)
                if output_path:
                    messagebox.showinfo("完成", f"检查结果已保存到:\n{output_path}")
                
                # 重置进度
                self.reset_progress()
        except Exception as e:
            self.update_status(f"检查出错: {str(e)}")
            print(f"检查出错: {e}", file=sys.stderr)
        
        # 更新按钮状态
        self.btn_start.config(state=tk.NORMAL)
        self.btn_pause.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.DISABLED)
        self.btn_load.config(state=tk.NORMAL)
        self.btn_output.config(state=tk.NORMAL)
    
    def toggle_pause(self):
        """暂停/继续检查"""
        global paused
        paused = not paused
        
        if paused:
            self.btn_pause.config(text="继续")
            self.update_status("已暂停")
        else:
            self.btn_pause.config(text="暂停")
            self.update_status("继续检查...")
    
    def stop_check(self):
        """停止检查"""
        global processing
        processing = False
        
        # 保存当前结果
        if self.results:
            output_path = self.file_handler.save_results(self.results, result_dir)
            if output_path:
                messagebox.showinfo("结果已保存", f"当前结果已保存到:\n{output_path}")
        
        self.update_status("已停止")
        self.update_info(f"检查已停止，当前进度: {current_index}/{total_games}")
    
    def toggle_hint_window(self):
        """显示/隐藏红框"""
        global hint_window
        
        if not hint_window:
            hint_window = PermanentHintWindow(self.root)
            self.btn_toggle_hint.config(text="隐藏红框")
        else:
            if hint_window.is_visible:
                hint_window.hide()
                self.btn_toggle_hint.config(text="显示红框")
            else:
                hint_window.show()
                self.btn_toggle_hint.config(text="隐藏红框")
    
    def check_progress(self):
        """检查是否有保存的进度"""
        global wishlist_path, result_dir, current_index, total_games, wishlist_games
        
        progress_data = self.file_handler.load_progress()
        
        if progress_data and "current_index" in progress_data and progress_data["current_index"] > 0:
            if messagebox.askyesno("发现未完成检查", f"发现上次未完成的检查，是否继续？\n进度: {progress_data['current_index']}/{progress_data['total_games']}"):
                wishlist_path = progress_data["wishlist_path"]
                result_dir = progress_data["result_dir"]
                current_index = progress_data["current_index"]
                total_games = progress_data["total_games"]
                self.results = progress_data["results"]
                
                # 加载愿望单
                wishlist_games = self.file_handler.load_wishlist(wishlist_path)
                
                if wishlist_games:
                    self.update_status(f"已加载上次进度: {current_index}/{total_games}")
                    self.update_info(f"愿望单文件: {os.path.basename(wishlist_path)}\n输出目录: {result_dir}\n当前进度: {current_index}/{total_games}")
                    
                    # 清空结果树
                    self.clear_results()
                    
                    # 添加游戏到结果树
                    for i, (game, status) in enumerate(self.results, 1):
                        status_text = "✓ 存在" if status else "✗ 未找到"
                        self.result_tree.insert("", tk.END, values=(i, game, status_text))
                    
                    # 添加剩余游戏
                    for i in range(current_index, total_games):
                        self.result_tree.insert("", tk.END, values=(i+1, wishlist_games[i], "等待检查"))
                    
                    # 更新进度条
                    progress_percent = (current_index / total_games) * 100
                    self.progress.config(value=progress_percent)
                    
                    # 启用开始按钮
                    self.btn_start.config(state=tk.NORMAL)
    
    def clear_results(self):
        """清空结果"""
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
    
    def update_status(self, text):
        """更新状态"""
        self.lbl_status.config(text=f"状态: {text}")
        self.root.update()
    
    def update_info(self, text):
        """更新信息"""
        self.lbl_info.config(text=text)
        self.root.update()
    
    def reset_progress(self):
        """重置进度"""
        global current_index
        current_index = 0
        self.progress.config(value=0)
        
        # 删除进度文件
        if os.path.exists(progress_file):
            try:
                os.remove(progress_file)
            except Exception as e:
                print(f"删除进度文件失败: {e}", file=sys.stderr)
    
    def on_closing(self):
        """窗口关闭事件处理"""
        global processing
        if processing:
            if messagebox.askokcancel("退出", "检查正在进行中，确定要退出吗？"):
                processing = False
                # 等待检查线程结束
                if hasattr(self, 'check_thread'):
                    self.check_thread.join(timeout=2)
                self.root.destroy()
        else:
            self.root.destroy()

# 主程序入口
def main():
    # 检查是否已经有实例在运行
    try:
        # 尝试创建互斥锁，防止多个实例
        if sys.platform.startswith("win"):
            import win32event
            import win32api
            import winerror
            
            mutex = win32event.CreateMutex(None, False, "SteamWishlistChecker")
            if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
                print("程序已经在运行中")
                return
    except:
        pass
    
    # 创建主窗口
    root = tk.Tk()
    root.option_add("*Font", (font_family, 10))
    
    # 设置DPI感知后的缩放
    try:
        # 获取系统DPI缩放
        dpi = ctypes.windll.user32.GetDpiForWindow(root.winfo_id())
        scale_factor = dpi / 96.0
        root.tk.call('tk', 'scaling', scale_factor)
    except:
        pass
    
    app = WishlistCheckerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
