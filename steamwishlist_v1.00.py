from __future__ import annotations

import asyncio
import ctypes
import json
import os
import sys
import tempfile
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import psutil
import pyautogui
from PIL import ImageEnhance, ImageOps

try:
    import winrt.windows.globalization as wglo
    import winrt.windows.graphics.imaging as wgi
    import winrt.windows.media.ocr as wmo
    import winrt.windows.storage as ws
except Exception as exc:  # pragma: no cover - 仅用于缺依赖时给出友好提示
    wglo = None
    wgi = None
    wmo = None
    ws = None
    WINRT_IMPORT_ERROR = exc
else:
    WINRT_IMPORT_ERROR = None

APP_NAME = "SteamWishlistChecker"
APP_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
PROGRESS_FILE = APP_DIR / "progress.json"
REFERENCE_RESOLUTION = (1920, 1080)
BASE_WINDOW_SIZE = (1120, 780)
MIN_WINDOW_SIZE = (920, 680)
HINT_RECT_BASE_SIZE = (234, 31)
OCR_CAPTURE_BASE_HEIGHT = 320
OCR_NOT_FOUND_MARKERS = [
    "找不到您要找的游戏吗",
    "搜索steam商店",
    "didntfindwhatyourelookingfor",
    "didn'tfindwhatyou'relookingfor",
    "searchsteamstore",
]

font_family = "微软雅黑" if sys.platform.startswith("win") else "Heiti TC"
pyautogui.PAUSE = 0.05


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def get_window_dpi_scale(window: tk.Misc) -> float:
    try:
        dpi = ctypes.windll.user32.GetDpiForWindow(window.winfo_id())
        return max(dpi / 96.0, 1.0)
    except Exception:
        return 1.0


@dataclass(frozen=True)
class UiMetrics:
    screen_width: int
    screen_height: int
    dpi_scale: float
    logical_width: float
    logical_height: float
    resolution_scale: float
    pixel_scale: float
    font_scale: float
    hint_scale: float

    @classmethod
    def from_root(cls, root: tk.Misc) -> "UiMetrics":
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        dpi_scale = get_window_dpi_scale(root)
        logical_width = screen_width / dpi_scale
        logical_height = screen_height / dpi_scale
        resolution_scale = min(logical_width / REFERENCE_RESOLUTION[0], logical_height / REFERENCE_RESOLUTION[1])
        ui_scale = clamp(resolution_scale ** 0.9, 1.0, 1.35)
        pixel_scale = clamp(dpi_scale * ui_scale, 1.0, 2.4)
        font_scale = clamp(ui_scale, 1.0, 1.2)
        hint_scale = clamp(dpi_scale * resolution_scale, 1.0, 2.4)
        return cls(
            screen_width=screen_width,
            screen_height=screen_height,
            dpi_scale=dpi_scale,
            logical_width=logical_width,
            logical_height=logical_height,
            resolution_scale=resolution_scale,
            pixel_scale=pixel_scale,
            font_scale=font_scale,
            hint_scale=hint_scale,
        )

    def px(self, value: int) -> int:
        return max(1, int(round(value * self.pixel_scale)))

    def font(self, value: int) -> int:
        return max(9, int(round(value * self.font_scale)))

    def hint_px(self, value: int) -> int:
        return max(1, int(round(value * self.hint_scale)))


def resource_path(relative_path: str) -> str:
    """获取资源绝对路径，兼容 PyInstaller。"""
    try:
        base_path = Path(sys._MEIPASS)
    except Exception:
        base_path = Path(__file__).resolve().parent
    return str(base_path / relative_path)


def normalize_text(text: str) -> str:
    return "".join(text.lower().split())


@dataclass
class ProgressData:
    wishlist_path: str
    result_dir: str
    current_index: int
    total_games: int
    results: list[list[object]] = field(default_factory=list)


class FileHandler:
    @staticmethod
    def ensure_app_dir() -> None:
        APP_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def load_wishlist(path: str) -> list[str]:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return [line.strip() for line in handle if line.strip()]
        except Exception as exc:
            print(f"加载愿望单失败: {exc}", file=sys.stderr)
            return []

    @staticmethod
    def save_results(results: list[tuple[str, bool]], output_dir: str, prefix: str = "检查结果") -> str | None:
        try:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = Path(output_dir) / f"{prefix}_{timestamp}.txt"

            missing_count = sum(1 for _, status in results if not status)
            with output_path.open("w", encoding="utf-8") as handle:
                handle.write("Steam 愿望单检查结果\n")
                handle.write(f"检查时间: {datetime.now():%Y-%m-%d %H:%M:%S}\n")
                handle.write(f"总游戏数: {len(results)}\n")
                handle.write(f"未找到游戏数: {missing_count}\n")
                handle.write("=" * 60 + "\n\n")
                for index, (game, status) in enumerate(results, start=1):
                    status_text = "✓ 存在" if status else "✗ 未找到"
                    handle.write(f"{index:>4}. {game}    {status_text}\n")
            return str(output_path)
        except Exception as exc:
            print(f"保存结果失败: {exc}", file=sys.stderr)
            return None

    @staticmethod
    def save_progress(data: ProgressData) -> None:
        try:
            FileHandler.ensure_app_dir()
            with PROGRESS_FILE.open("w", encoding="utf-8") as handle:
                json.dump(data.__dict__, handle, ensure_ascii=False, indent=2)
        except Exception as exc:
            print(f"保存进度失败: {exc}", file=sys.stderr)

    @staticmethod
    def load_progress() -> ProgressData | None:
        try:
            if not PROGRESS_FILE.exists():
                return None
            with PROGRESS_FILE.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
            return ProgressData(
                wishlist_path=raw.get("wishlist_path", ""),
                result_dir=raw.get("result_dir", ""),
                current_index=int(raw.get("current_index", 0)),
                total_games=int(raw.get("total_games", 0)),
                results=raw.get("results", []),
            )
        except Exception as exc:
            print(f"加载进度失败: {exc}", file=sys.stderr)
            return None

    @staticmethod
    def clear_progress() -> None:
        try:
            if PROGRESS_FILE.exists():
                PROGRESS_FILE.unlink()
        except Exception as exc:
            print(f"清理进度失败: {exc}", file=sys.stderr)


class PermanentHintWindow:
    def __init__(self, master: tk.Tk, ui_metrics: UiMetrics):
        self.master = master
        self.ui_metrics = ui_metrics
        self.is_visible = True
        self.drag_start = (0, 0)

        self.padding = self.ui_metrics.hint_px(8)
        self.label_height = self.ui_metrics.hint_px(28)
        self.rect_width = self.ui_metrics.hint_px(HINT_RECT_BASE_SIZE[0])
        self.rect_height = self.ui_metrics.hint_px(HINT_RECT_BASE_SIZE[1])
        self.border_width = max(2, self.ui_metrics.hint_px(2))
        self.window_width = self.rect_width + self.padding * 2
        self.window_height = self.rect_height + self.label_height + self.padding * 3
        self.rect_left = self.padding
        self.rect_top = self.padding
        self.rect_right = self.rect_left + self.rect_width
        self.rect_bottom = self.rect_top + self.rect_height

        self.hint_window = tk.Toplevel(master)
        self.hint_window.attributes("-topmost", True)
        self.hint_window.attributes("-alpha", 0.84)
        self.hint_window.overrideredirect(True)

        screen_width = master.winfo_screenwidth()
        screen_height = master.winfo_screenheight()
        x = (screen_width - self.window_width) // 2
        y = (screen_height - self.window_height) // 2
        self.hint_window.geometry(f"{self.window_width}x{self.window_height}+{x}+{y}")

        self.canvas = tk.Canvas(
            self.hint_window,
            bg="#fff7f7",
            highlightthickness=0,
            bd=0,
            cursor="fleur",
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.create_rectangle(
            self.rect_left,
            self.rect_top,
            self.rect_right,
            self.rect_bottom,
            outline="#ff2d2d",
            width=self.border_width,
        )
        self.canvas.create_text(
            self.window_width // 2,
            self.rect_bottom + self.padding + self.label_height // 2,
            text="拖动红框对准 Steam 库搜索框",
            fill="#ff2d2d",
            font=(font_family, self.ui_metrics.font(10), "bold"),
        )
        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.drag_window)

    def start_drag(self, event: tk.Event) -> None:
        self.drag_start = (event.x, event.y)

    def drag_window(self, event: tk.Event) -> None:
        offset_x, offset_y = self.drag_start
        new_x = self.hint_window.winfo_x() - offset_x + event.x
        new_y = self.hint_window.winfo_y() - offset_y + event.y
        self.hint_window.geometry(f"+{new_x}+{new_y}")

    def show(self) -> None:
        if not self.is_visible:
            self.hint_window.deiconify()
            self.hint_window.lift()
            self.is_visible = True

    def hide(self) -> None:
        if self.is_visible:
            self.hint_window.withdraw()
            self.is_visible = False

    def destroy(self) -> None:
        if self.hint_window.winfo_exists():
            self.hint_window.destroy()
        self.is_visible = False

    def get_position(self) -> tuple[int, int, int, int]:
        self.hint_window.update_idletasks()
        x = self.hint_window.winfo_x()
        y = self.hint_window.winfo_y()
        return x + self.rect_left, y + self.rect_top, self.rect_width, self.rect_height


class WindowsOcrRecognizer:
    def __init__(self) -> None:
        self._engine = None
        self._engine_thread_id = None
        self._temp_dir = Path(tempfile.gettempdir()) / APP_NAME
        self._temp_dir.mkdir(parents=True, exist_ok=True)

    def _create_engine(self):
        if WINRT_IMPORT_ERROR is not None:
            raise RuntimeError(f"缺少 Windows OCR 依赖: {WINRT_IMPORT_ERROR}")

        engine = wmo.OcrEngine.try_create_from_user_profile_languages()
        if engine is not None:
            return engine

        for tag in ("zh-CN", "en-US"):
            try:
                engine = wmo.OcrEngine.try_create_from_language(wglo.Language(tag))
            except Exception:
                engine = None
            if engine is not None:
                return engine

        raise RuntimeError("Windows 原生 OCR 不可用，请先在系统可选功能中安装中文或英文 OCR 语言包。")

    def _get_engine(self):
        current_thread = threading.get_ident()
        if self._engine is None or self._engine_thread_id != current_thread:
            self._engine = self._create_engine()
            self._engine_thread_id = current_thread
        return self._engine

    @staticmethod
    def preprocess_image(image):
        enlarged = image.resize((image.width * 2, image.height * 2))
        grayscale = ImageOps.grayscale(enlarged)
        contrasted = ImageOps.autocontrast(grayscale)
        sharpened = ImageEnhance.Sharpness(contrasted).enhance(2.2)
        return sharpened

    async def _recognize_file_async(self, image_path: Path) -> str:
        engine = self._get_engine()
        file = await ws.StorageFile.get_file_from_path_async(str(image_path))
        stream = await file.open_async(ws.FileAccessMode.READ)
        decoder = await wgi.BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()
        if bitmap.bitmap_pixel_format != wgi.BitmapPixelFormat.BGRA8:
            bitmap = wgi.SoftwareBitmap.convert(bitmap, wgi.BitmapPixelFormat.BGRA8)
        result = await engine.recognize_async(bitmap)
        return (result.text or "").strip()

    def recognize_text(self, image) -> str:
        processed = self.preprocess_image(image)
        temp_path = self._temp_dir / f"ocr_capture_{threading.get_ident()}_{int(time.time() * 1000)}.png"
        processed.save(temp_path)
        try:
            return asyncio.run(self._recognize_file_async(temp_path))
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass


class SteamController:
    def __init__(self, ui_metrics: UiMetrics) -> None:
        self.steam_process_name = "steamwebhelper.exe"
        self.target_region: tuple[int, int, int, int] | None = None
        self.ui_metrics = ui_metrics
        self.ocr = WindowsOcrRecognizer()
        self.search_wait_seconds = 2.2
        self.ocr_capture_height = self.ui_metrics.px(OCR_CAPTURE_BASE_HEIGHT)

    def is_steam_running(self) -> bool:
        for proc in psutil.process_iter(["name"]):
            try:
                name = proc.info.get("name") or ""
            except (psutil.Error, OSError):
                continue
            if name.lower() == self.steam_process_name:
                return True
        return False

    def set_target_region(self, region: tuple[int, int, int, int]) -> None:
        self.target_region = region

    def _recognize_search_panel(self) -> str:
        if not self.target_region:
            raise RuntimeError("尚未设置搜索区域")

        region_x, region_y, region_width, region_height = self.target_region
        padding = self.ui_metrics.hint_px(10)
        ocr_x = max(region_x - padding, 0)
        ocr_y = max(region_y + region_height + padding, 0)
        desired_width = max(region_width + padding * 4, int(region_width * 2.2))
        available_width = max(self.ui_metrics.screen_width - ocr_x - padding, region_width)
        available_height = max(self.ui_metrics.screen_height - ocr_y - padding, self.ui_metrics.hint_px(120))
        ocr_width = min(desired_width, available_width)
        ocr_height = min(self.ocr_capture_height, available_height)
        ocr_region = (ocr_x, ocr_y, ocr_width, ocr_height)
        screenshot = pyautogui.screenshot(region=ocr_region)
        return self.ocr.recognize_text(screenshot)

    def _type_with_clipboard(self, text: str) -> None:
        """通过剪贴板粘贴文本，避免 pyautogui.write() 无法处理特殊字符的问题。

        使用 ctypes 直接操作 Windows 剪贴板，线程安全，不会阻塞 Tk 主循环。
        """
        import ctypes
        from ctypes import wintypes

        GMEM_MOVEABLE = 0x0002
        CF_UNICODETEXT = 13
        clipboard_handle_t = getattr(wintypes, "HANDLE", ctypes.c_void_p)

        OpenClipboard = ctypes.windll.user32.OpenClipboard
        OpenClipboard.argtypes = [wintypes.HWND]
        OpenClipboard.restype = wintypes.BOOL
        CloseClipboard = ctypes.windll.user32.CloseClipboard
        EmptyClipboard = ctypes.windll.user32.EmptyClipboard
        SetClipboardData = ctypes.windll.user32.SetClipboardData
        SetClipboardData.argtypes = [wintypes.UINT, clipboard_handle_t]
        SetClipboardData.restype = clipboard_handle_t
        GetClipboardData = ctypes.windll.user32.GetClipboardData
        GetClipboardData.argtypes = [wintypes.UINT]
        GetClipboardData.restype = clipboard_handle_t
        GlobalAlloc = ctypes.windll.kernel32.GlobalAlloc
        GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        GlobalAlloc.restype = wintypes.HGLOBAL
        GlobalLock = ctypes.windll.kernel32.GlobalLock
        GlobalLock.argtypes = [wintypes.HGLOBAL]
        GlobalLock.restype = wintypes.LPVOID
        GlobalUnlock = ctypes.windll.kernel32.GlobalUnlock
        GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        GlobalSize = ctypes.windll.kernel32.GlobalSize
        GlobalSize.argtypes = [wintypes.HGLOBAL]
        GlobalSize.restype = ctypes.c_size_t
        memcpy = ctypes.cdll.msvcrt.memcpy
        memcpy.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
        memcpy.restype = ctypes.c_void_p

        # 保存原剪贴板内容
        saved_handle = None
        saved_data = b""
        if OpenClipboard(None):
            try:
                h = GetClipboardData(CF_UNICODETEXT)
                if h:
                    saved_handle = h
                    size = GlobalSize(h)
                    ptr = GlobalLock(h)
                    saved_data = ctypes.string_at(ptr, size)
                    GlobalUnlock(h)
            except Exception:
                pass
            CloseClipboard()

        # 设置新文本到剪贴板
        if OpenClipboard(None):
            try:
                EmptyClipboard()
                data_bytes = text.encode("utf-16-le") + b"\x00\x00"
                size = len(data_bytes)
                h_mem = GlobalAlloc(GMEM_MOVEABLE, size)
                p_mem = GlobalLock(h_mem)
                memcpy(p_mem, data_bytes, size)
                GlobalUnlock(h_mem)
                SetClipboardData(CF_UNICODETEXT, h_mem)
            finally:
                CloseClipboard()

        # Ctrl+V 粘贴
        pyautogui.hotkey("ctrl", "v")

        # 恢复原剪贴板内容
        if saved_handle is not None or saved_data:
            if OpenClipboard(None):
                try:
                    EmptyClipboard()
                    if saved_data:
                        h_mem = GlobalAlloc(GMEM_MOVEABLE, len(saved_data))
                        p_mem = GlobalLock(h_mem)
                        memcpy(p_mem, saved_data, len(saved_data))
                        GlobalUnlock(h_mem)
                        SetClipboardData(CF_UNICODETEXT, h_mem)
                except Exception:
                    pass
                finally:
                    CloseClipboard()

    def _contains_not_found_marker(self, text: str) -> bool:
        normalized = normalize_text(text)
        return any(marker in normalized for marker in OCR_NOT_FOUND_MARKERS)

    def search_game(self, game_name: str) -> bool:
        if not self.target_region:
            raise RuntimeError("请先设置红框位置")

        region_x, region_y, region_width, region_height = self.target_region
        search_x = region_x + region_width // 2
        search_y = region_y + region_height // 2

        try:
            pyautogui.moveTo(search_x, search_y, duration=0.2)
            pyautogui.click()
            time.sleep(0.15)
            pyautogui.hotkey("ctrl", "a")
            pyautogui.press("backspace")
            time.sleep(0.1)
            self._type_with_clipboard(game_name)
            pyautogui.press("enter")

            ocr_text = ""
            for _ in range(2):
                time.sleep(self.search_wait_seconds)
                ocr_text = self._recognize_search_panel()
                if ocr_text.strip():
                    break

            if self._contains_not_found_marker(ocr_text):
                return False
            if ocr_text.strip():
                return True

            raise RuntimeError("OCR 没有识别到任何文本，请检查红框位置或增大搜索结果区域")
        finally:
            try:
                pyautogui.hotkey("ctrl", "a")
                pyautogui.press("backspace")
            except Exception:
                pass


class WishlistCheckerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.ui_metrics = UiMetrics.from_root(root)
        self.root.title("Steam 愿望单检查工具（轻量版）")
        self.configure_window()

        try:
            self.root.iconbitmap(resource_path("icon.ico"))
        except Exception:
            pass

        self.file_handler = FileHandler()
        self.steam_controller = SteamController(self.ui_metrics)
        self.hint_window: PermanentHintWindow | None = None
        self.check_thread: threading.Thread | None = None

        self.wishlist_path = ""
        self.result_dir = ""
        self.wishlist_games: list[str] = []
        self.results: list[tuple[str, bool]] = []
        self.current_index = 0
        self.total_games = 0
        self.processing = False
        self.paused = False
        self.stop_requested = False
        self.resume_prompt_needed = False

        self.init_ui()
        self.check_progress()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.bind("<Configure>", self.on_root_configure)

    def configure_window(self) -> None:
        window_width = int(clamp(self.ui_metrics.px(BASE_WINDOW_SIZE[0]), MIN_WINDOW_SIZE[0], self.ui_metrics.screen_width * 0.88))
        window_height = int(clamp(self.ui_metrics.px(BASE_WINDOW_SIZE[1]), MIN_WINDOW_SIZE[1], self.ui_metrics.screen_height * 0.88))
        min_width = int(clamp(self.ui_metrics.px(MIN_WINDOW_SIZE[0]), MIN_WINDOW_SIZE[0], window_width))
        min_height = int(clamp(self.ui_metrics.px(MIN_WINDOW_SIZE[1]), MIN_WINDOW_SIZE[1], window_height))
        x = max((self.ui_metrics.screen_width - window_width) // 2, 0)
        y = max((self.ui_metrics.screen_height - window_height) // 2, 0)
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.root.minsize(min_width, min_height)

    def configure_styles(self) -> None:
        base_font = self.ui_metrics.font(11)
        title_font = self.ui_metrics.font(12)
        self.root.option_add("*Font", (font_family, base_font))

        style = ttk.Style(self.root)
        style.configure(
            "App.TButton",
            font=(font_family, base_font, "bold"),
            padding=(self.ui_metrics.px(16), self.ui_metrics.px(9)),
        )
        style.configure("App.TLabel", font=(font_family, base_font))
        style.configure("Status.TLabel", font=(font_family, title_font, "bold"))
        style.configure("Treeview", rowheight=self.ui_metrics.px(36), font=(font_family, base_font))
        style.configure("Treeview.Heading", font=(font_family, base_font, "bold"))
        style.configure("App.Horizontal.TProgressbar", thickness=self.ui_metrics.px(16))

    def call_on_ui(self, func, wait: bool = False):
        if threading.current_thread() is threading.main_thread():
            return func()

        finished = threading.Event()
        payload: dict[str, object] = {}

        def wrapper():
            try:
                payload["value"] = func()
            except Exception as exc:  # pragma: no cover - GUI 主线程异常透传
                payload["error"] = exc
            finally:
                finished.set()

        self.root.after(0, wrapper)
        if wait:
            finished.wait()
            if "error" in payload:
                raise payload["error"]
            return payload.get("value")
        return None

    def init_ui(self) -> None:
        self.configure_styles()
        main_padding = self.ui_metrics.px(16)
        section_gap = self.ui_metrics.px(12)
        button_gap = self.ui_metrics.px(8)

        main_frame = ttk.Frame(self.root, padding=main_padding)
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)

        toolbar = ttk.Frame(main_frame)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, section_gap))

        self.btn_load = ttk.Button(toolbar, text="加载愿望单", command=self.load_wishlist, style="App.TButton")
        self.btn_load.pack(side=tk.LEFT, padx=(0, button_gap))

        self.btn_output = ttk.Button(toolbar, text="选择输出目录", command=self.select_output_dir, style="App.TButton")
        self.btn_output.pack(side=tk.LEFT, padx=(0, button_gap))

        self.btn_start = ttk.Button(toolbar, text="开始检查", command=self.start_check, state=tk.DISABLED, style="App.TButton")
        self.btn_start.pack(side=tk.LEFT, padx=(0, button_gap))

        self.btn_pause = ttk.Button(toolbar, text="暂停", command=self.toggle_pause, state=tk.DISABLED, style="App.TButton")
        self.btn_pause.pack(side=tk.LEFT, padx=(0, button_gap))

        self.btn_stop = ttk.Button(toolbar, text="停止", command=self.stop_check, state=tk.DISABLED, style="App.TButton")
        self.btn_stop.pack(side=tk.LEFT, padx=(0, button_gap))

        self.btn_toggle_hint = ttk.Button(toolbar, text="显示红框", command=self.toggle_hint_window, style="App.TButton")
        self.btn_toggle_hint.pack(side=tk.LEFT)

        status_frame = ttk.Frame(main_frame)
        status_frame.grid(row=1, column=0, sticky="ew", pady=(0, section_gap))
        status_frame.columnconfigure(1, weight=1)

        self.lbl_status = ttk.Label(status_frame, text="状态: 就绪", style="Status.TLabel")
        self.lbl_status.grid(row=0, column=0, sticky="w")

        self.progress = ttk.Progressbar(status_frame, orient=tk.HORIZONTAL, mode="determinate", style="App.Horizontal.TProgressbar")
        self.progress.grid(row=0, column=1, sticky="ew", padx=(self.ui_metrics.px(14), 0))

        result_frame = ttk.Frame(main_frame)
        result_frame.grid(row=2, column=0, sticky="nsew", pady=(0, section_gap))
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(0, weight=1)

        columns = ("index", "game", "status")
        self.result_tree = ttk.Treeview(result_frame, columns=columns, show="headings")
        self.result_tree.heading("index", text="序号")
        self.result_tree.heading("game", text="游戏名称")
        self.result_tree.heading("status", text="状态")
        self.result_tree.column("index", width=self.ui_metrics.px(84), anchor=tk.CENTER, stretch=False)
        self.result_tree.column("game", width=self.ui_metrics.px(700), anchor=tk.W, stretch=True)
        self.result_tree.column("status", width=self.ui_metrics.px(140), anchor=tk.CENTER, stretch=False)

        scrollbar_y = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=self.result_tree.yview)
        scrollbar_x = ttk.Scrollbar(result_frame, orient=tk.HORIZONTAL, command=self.result_tree.xview)
        self.result_tree.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

        self.result_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar_y.grid(row=0, column=1, sticky="ns")
        scrollbar_x.grid(row=1, column=0, sticky="ew")

        info_frame = ttk.Frame(main_frame)
        info_frame.grid(row=3, column=0, sticky="ew")
        self.lbl_info = ttk.Label(
            info_frame,
            text="请先导出愿望单，选择输出目录，再放置红框。",
            wraplength=self.ui_metrics.px(940),
            justify=tk.LEFT,
            style="App.TLabel",
        )
        self.lbl_info.pack(fill=tk.X, expand=True)

    def on_root_configure(self, event: tk.Event) -> None:
        if event.widget is self.root and hasattr(self, "lbl_info"):
            wraplength = max(event.width - self.ui_metrics.px(72), self.ui_metrics.px(520))
            self.lbl_info.config(wraplength=wraplength)

    def refresh_start_button(self) -> None:
        if self.processing:
            self.btn_start.config(state=tk.DISABLED)
            return
        self.btn_start.config(state=tk.NORMAL if self.wishlist_games and self.result_dir else tk.DISABLED)

    def refresh_result_tree(self) -> None:
        self.clear_results()
        cached_results = {game: status for game, status in self.results[: self.current_index]}
        for index, game in enumerate(self.wishlist_games, start=1):
            if game in cached_results:
                status_text = "✓ 存在" if cached_results[game] else "✗ 未找到"
            else:
                status_text = "等待检查"
            self.result_tree.insert("", tk.END, values=(index, game, status_text))

    def clear_results(self) -> None:
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)

    def update_status(self, text: str) -> None:
        self.lbl_status.config(text=f"状态: {text}")
        self.root.update_idletasks()

    def update_info(self, text: str) -> None:
        self.lbl_info.config(text=text)
        self.root.update_idletasks()

    def set_row_status(self, index: int, status_text: str) -> None:
        children = self.result_tree.get_children()
        if 0 <= index < len(children):
            item = children[index]
            self.result_tree.set(item, "status", status_text)
            self.result_tree.see(item)

    def set_running_controls(self, running: bool) -> None:
        self.btn_load.config(state=tk.DISABLED if running else tk.NORMAL)
        self.btn_output.config(state=tk.DISABLED if running else tk.NORMAL)
        self.btn_pause.config(state=tk.NORMAL if running else tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL if running else tk.DISABLED)
        if not running:
            self.btn_pause.config(text="暂停")
        self.refresh_start_button()

    def load_wishlist(self) -> None:
        path = filedialog.askopenfilename(
            title="选择愿望单文件",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
        )
        if not path:
            return

        games = self.file_handler.load_wishlist(path)
        if not games:
            self.update_status("加载失败")
            self.update_info("愿望单文件为空，或者文件编码无法识别。")
            return

        self.wishlist_path = path
        self.wishlist_games = games
        self.total_games = len(games)
        self.current_index = 0
        self.results = []
        self.resume_prompt_needed = False
        self.progress.config(value=0)
        self.file_handler.clear_progress()

        self.refresh_result_tree()
        self.update_status(f"已加载 {self.total_games} 个游戏")
        self.update_info(f"愿望单文件: {Path(path).name}\n游戏总数: {self.total_games}")
        self.refresh_start_button()

    def select_output_dir(self) -> None:
        path = filedialog.askdirectory(title="选择输出目录")
        if not path:
            return

        self.result_dir = path
        self.update_status(f"已选择输出目录: {Path(path).name}")
        self.update_info(f"输出目录: {path}")
        self.refresh_start_button()

    def toggle_hint_window(self) -> None:
        if self.hint_window is None:
            self.hint_window = PermanentHintWindow(self.root, self.ui_metrics)
            self.btn_toggle_hint.config(text="隐藏红框")
            return

        if self.hint_window.is_visible:
            self.hint_window.hide()
            self.btn_toggle_hint.config(text="显示红框")
        else:
            self.hint_window.show()
            self.btn_toggle_hint.config(text="隐藏红框")

    def reset_progress_state(self) -> None:
        self.current_index = 0
        self.results = []
        self.progress.config(value=0)
        self.resume_prompt_needed = False
        self.file_handler.clear_progress()
        self.refresh_result_tree()

    def check_progress(self) -> None:
        progress_data = self.file_handler.load_progress()
        if progress_data is None:
            return

        wishlist_path = Path(progress_data.wishlist_path)
        if not wishlist_path.exists():
            self.file_handler.clear_progress()
            return

        wishlist_games = self.file_handler.load_wishlist(str(wishlist_path))
        if not wishlist_games:
            self.file_handler.clear_progress()
            return

        self.wishlist_path = str(wishlist_path)
        self.result_dir = progress_data.result_dir
        self.wishlist_games = wishlist_games
        self.total_games = len(wishlist_games)
        self.current_index = min(progress_data.current_index, self.total_games)
        self.results = [(game, bool(status)) for game, status in progress_data.results[: self.current_index]]
        self.resume_prompt_needed = self.current_index > 0

        self.refresh_result_tree()
        if self.total_games:
            self.progress.config(value=(self.current_index / self.total_games) * 100)
        self.update_status(f"已恢复到 {self.current_index}/{self.total_games}")
        self.update_info(
            f"愿望单文件: {Path(self.wishlist_path).name}\n"
            f"输出目录: {self.result_dir or '未设置'}\n"
            f"当前进度: {self.current_index}/{self.total_games}"
        )
        self.refresh_start_button()

    def save_progress_snapshot(self) -> None:
        progress = ProgressData(
            wishlist_path=self.wishlist_path,
            result_dir=self.result_dir,
            current_index=self.current_index,
            total_games=self.total_games,
            results=[[game, status] for game, status in self.results],
        )
        self.file_handler.save_progress(progress)

    def start_check(self) -> None:
        if not self.wishlist_games:
            messagebox.showerror("错误", "请先加载愿望单文件")
            return
        if not self.result_dir:
            messagebox.showerror("错误", "请先选择输出目录")
            return
        if self.hint_window is None:
            messagebox.showerror("错误", "请先点击“显示红框”，把搜索框放进红框里")
            return
        if not self.steam_controller.is_steam_running():
            messagebox.showerror("错误", "未检测到 Steam，请先启动 Steam 客户端")
            return

        if self.resume_prompt_needed and 0 < self.current_index < self.total_games:
            should_resume = messagebox.askyesno(
                "继续检查",
                f"检测到上次进度 {self.current_index}/{self.total_games}。\n是否从上次位置继续？",
            )
            if not should_resume:
                self.reset_progress_state()
            self.resume_prompt_needed = False

        target_region = self.hint_window.get_position()
        self.steam_controller.set_target_region(target_region)
        if self.hint_window.is_visible:
            self.hint_window.hide()
            self.btn_toggle_hint.config(text="显示红框")

        self.processing = True
        self.paused = False
        self.stop_requested = False
        self.update_status("正在检查...")
        self.update_info(f"当前进度: {self.current_index}/{self.total_games}")
        self.set_running_controls(True)

        self.check_thread = threading.Thread(target=self.check_games, daemon=True)
        self.check_thread.start()

    def check_games(self) -> None:
        try:
            self.results = self.results[: self.current_index]
            while self.current_index < self.total_games and self.processing:
                if self.paused:
                    time.sleep(0.2)
                    continue

                index = self.current_index
                game = self.wishlist_games[index]
                self.call_on_ui(lambda: self.update_status(f"正在检查: {game}"))
                self.call_on_ui(lambda: self.set_row_status(index, "检查中..."))

                status = self.steam_controller.search_game(game)
                self.results.append((game, status))
                self.current_index += 1
                progress_percent = (self.current_index / self.total_games) * 100 if self.total_games else 0

                self.call_on_ui(lambda: self.set_row_status(index, "✓ 存在" if status else "✗ 未找到"))
                self.call_on_ui(lambda: self.progress.config(value=progress_percent))
                self.call_on_ui(
                    lambda: self.update_info(
                        f"当前进度: {self.current_index}/{self.total_games} ({progress_percent:.1f}%)"
                    )
                )
                self.save_progress_snapshot()
                time.sleep(0.6)

            if self.processing and self.current_index >= self.total_games:
                output_path = self.file_handler.save_results(self.results, self.result_dir)
                self.file_handler.clear_progress()
                completed = len(self.results)
                missing_count = sum(1 for _, status in self.results if not status)
                self.call_on_ui(lambda: self.progress.config(value=100))
                self.call_on_ui(lambda: self.update_status("检查完成"))
                self.call_on_ui(
                    lambda: self.update_info(
                        f"检查完成，共检查 {completed} 个游戏，其中 {missing_count} 个未找到。"
                    )
                )
                if output_path:
                    self.call_on_ui(
                        lambda: messagebox.showinfo("完成", f"检查结果已保存到:\n{output_path}"),
                        wait=True,
                    )
                self.current_index = 0
                self.resume_prompt_needed = False
            elif self.stop_requested:
                output_path = None
                if self.results:
                    output_path = self.file_handler.save_results(self.results, self.result_dir, prefix="中断结果")
                self.call_on_ui(lambda: self.update_status("已停止"))
                self.call_on_ui(
                    lambda: self.update_info(f"已停止，当前进度: {self.current_index}/{self.total_games}")
                )
                if output_path:
                    self.call_on_ui(
                        lambda: messagebox.showinfo("已停止", f"当前结果已保存到:\n{output_path}"),
                        wait=True,
                    )
        except Exception as exc:
            self.call_on_ui(lambda: self.update_status("检查出错"))
            self.call_on_ui(lambda: self.update_info(str(exc)))
            self.call_on_ui(lambda: messagebox.showerror("检查失败", str(exc)), wait=True)
        finally:
            self.processing = False
            self.paused = False
            self.stop_requested = False
            self.call_on_ui(lambda: self.set_running_controls(False))

    def toggle_pause(self) -> None:
        if not self.processing:
            return
        self.paused = not self.paused
        if self.paused:
            self.btn_pause.config(text="继续")
            self.update_status("已暂停")
        else:
            self.btn_pause.config(text="暂停")
            self.update_status("继续检查...")

    def stop_check(self) -> None:
        if not self.processing:
            return
        self.stop_requested = True
        self.processing = False
        self.update_status("正在停止...")

    def on_closing(self) -> None:
        if self.processing:
            should_close = messagebox.askokcancel("退出", "检查仍在进行中，确定要退出吗？")
            if not should_close:
                return
            self.stop_requested = False
            self.processing = False
            if self.check_thread and self.check_thread.is_alive():
                self.check_thread.join(timeout=2)

        if self.hint_window is not None:
            self.hint_window.destroy()
        self.root.destroy()


# 设置 DPI 感知，改善高分屏显示
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception as exc:
    print(f"DPI 感知设置失败: {exc}", file=sys.stderr)


def main() -> None:
    root = tk.Tk()

    try:
        root.tk.call("tk", "scaling", get_window_dpi_scale(root))
    except Exception:
        pass

    WishlistCheckerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
