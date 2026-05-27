import numpy as np
import cv2
import tkinter as tk
from tkinter import Toplevel
import threading
import pygetwindow as gw
import keyboard
import mss
import win32api
import win32con
import time

# -------------------【终极速度配置】-------------------
GAME_WINDOW_TITLE = "钢琴块2"
START_HOTKEY = 'f10'
STOP_HOTKEY = 'f12'
EMERGENCY_STOP_HOTKEY = 'esc'

# 颜色检测（极简到极致）
GRAY_TOLERANCE = 6
MIN_BLACK_PIXELS = 50

# 区域配置（宽高固定，提前缓存）
AREA_WIDTH = 180
AREA_HEIGHT = 100
AREA_GAP = 20       # 区域之间的水平间隔（像素）
AREA_COLORS = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
AREA_ALPHA = 0.3

# 全局开关（零延迟）
is_running = False
LOOP_DELAY = 0        # 让出GIL，不增加实质延迟，降低CPU占用

# 提前初始化（避免循环内创建）
sct = mss.mss()
tk_root = None
# 缓存区域（窗口对象, canvas对象, 列号, 初始x, 初始y）
AREA_CACHE = []

# -------------------【点击统计日志】-------------------
click_counts = [0, 0, 0, 0]       # 各区域累计点击次数
session_counts = [0, 0, 0, 0]     # 本次运行累计点击次数
last_click_time = 0               # 最后一次点击时间戳

# 日志打印控制（避免刷屏）
LOG_INTERVAL = 0.2  # 秒，日志刷新间隔
last_log_time = 0

def print_live_log():
    """打印实时点击日志，数字实时变化"""
    global last_log_time
    now = time.time()
    if now - last_log_time < LOG_INTERVAL:
        return
    last_log_time = now

    line = " | ".join(
        f"区域{i+1}: {click_counts[i]:>4}"
        for i in range(4)
    )
    print(f"\r🎹 {line}", end="", flush=True)

def print_summary(title="📊 点击统计"):
    """打印各区域点击统计汇总"""
    total = sum(session_counts)
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"{'='*50}")
    for i in range(4):
        pct = (session_counts[i] / total * 100) if total > 0 else 0
        bar = "█" * int(pct / 5)
        print(f"  区域 {i+1}: {session_counts[i]:>5} 次  ({pct:>5.1f}%)  {bar}")
    print(f"{'-'*50}")
    print(f"  合计: {total:>5} 次")
    print(f"{'='*50}")

def reset_session_counts():
    """重置本次运行计数"""
    global session_counts
    session_counts = [0, 0, 0, 0]

# -------------------【底层鼠标操作（最快！）】-------------------
def mouse_click(x, y):
    """直接调用Windows API发送点击消息，无任何延迟"""
    win32api.SetCursorPos((x, y))
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


# -------------------【区域创建（精简版）】-------------------
def create_draggable_area(column_idx):
    global tk_root
    win = Toplevel(tk_root)
    win.attributes('-topmost', True, '-alpha', AREA_ALPHA, '-toolwindow', True, '-transparentcolor', 'black')
    win.config(bg='black', bd=0)

    game_center_x, game_center_y = get_game_window_center()
    total_width = AREA_WIDTH * 4 + AREA_GAP * 3
    start_x = game_center_x - total_width // 2 + column_idx * (AREA_WIDTH + AREA_GAP)
    start_y = game_center_y + 180

    win.geometry(f"{AREA_WIDTH}x{AREA_HEIGHT}+{start_x}+{start_y}")

    canvas = tk.Canvas(win, bg='black', highlightthickness=0)
    canvas.pack(fill=tk.BOTH, expand=True)
    color = "#%02x%02x%02x" % AREA_COLORS[column_idx]
    canvas.create_rectangle(0, 0, AREA_WIDTH, AREA_HEIGHT, outline=color, width=1)

    drag_data = {'drag': False, 'ox': 0, 'oy': 0}

    def on_down(_): drag_data.update({'drag': True, 'ox': _.x, 'oy': _.y})

    def on_move(_):
        if drag_data['drag']:
            x = win.winfo_x() + (_.x - drag_data['ox'])
            y = win.winfo_y() + (_.y - drag_data['oy'])
            win.geometry(f"+{x}+{y}")

    def on_up(_): drag_data['drag'] = False

    canvas.bind('<Button-1>', on_down)
    canvas.bind('<B1-Motion>', on_move)
    canvas.bind('<ButtonRelease-1>', on_up)
    return (win, canvas, column_idx, start_x, start_y)


def get_game_window_center():
    try:
        game_windows = gw.getWindowsWithTitle(GAME_WINDOW_TITLE)
        if not game_windows:
            raise Exception(f'未找到「{GAME_WINDOW_TITLE}」窗口！请先打开游戏再运行脚本')
        game_win = game_windows[0]
        game_win.activate()
        return game_win.left + game_win.width // 2, game_win.top + game_win.height // 2
    except Exception as e:
        print(f"❌ 窗口错误：{e}")
        exit()


def create_all_draggable_areas():
    global tk_root, AREA_CACHE
    tk_root = tk.Tk()
    tk_root.withdraw()
    AREA_CACHE.clear()
    for i in range(4):
        win, canvas, col_idx, x, y = create_draggable_area(i)
        AREA_CACHE.append((win, canvas, col_idx, x, y))
    print("🚀 超极速版启动！")
    print(f"操作：F10启动/暂停 | F12停止 | ESC紧急退出")
    print("⚠️  请手动关闭鼠标加速（控制面板→鼠标→指针选项→取消提高指针精确度）")
    print("\n📋 各区域点击次数将实时显示...\n")
    tk_root.mainloop()


# -------------------【超极速合并检测（砍掉OpenCV遍历）】-------------------
def detect_and_click_all():
    """
    超极速策略：
    1. 合并截图（1次mss.grab代替4次）
    2. 跳过cv2.cvtColor，直接取B通道作为近似灰度
    3. 跳过cv2.threshold，用numpy布尔掩码直接统计黑像素
    4. 局部变量缓存，避免全局查找
    """
    # 局部缓存（避免每次循环查找全局属性）
    _w = AREA_WIDTH
    _h = AREA_HEIGHT
    _tol = GRAY_TOLERANCE
    _min_px = MIN_BLACK_PIXELS

    # 获取4个canvas绝对坐标
    coords = []
    for _, canvas, _, _, _ in AREA_CACHE:
        coords.append((canvas.winfo_rootx(), canvas.winfo_rooty()))

    if not coords:
        return

    # 计算包围盒
    min_x = min(c[0] for c in coords)
    min_y = min(c[1] for c in coords)
    max_x = max(c[0] + _w for c in coords)
    max_y = max(c[1] + _h for c in coords)

    # 【核心】一次截图覆盖全部区域
    monitor = {"left": min_x, "top": min_y, "width": max_x - min_x, "height": max_y - min_y}
    big_img = np.array(sct.grab(monitor))

    # 【优化1】跳过cv2.cvtColor，直接取B通道作为近似灰度
    # 钢琴块2黑块=(0,0,0)，背景=白色/浅色，B通道足够判断
    big_gray = big_img[:, :, 0]

    # 逐个区域切片检测
    for idx, (x, y) in enumerate(coords):
        ox = x - min_x
        oy = y - min_y
        slice_gray = big_gray[oy:oy+_h, ox:ox+_w]

        # 【优化2】跳过cv2.threshold，纯numpy布尔统计黑像素
        # np.count_nonzero 比 np.sum 稍快，且省去创建二值图
        if np.count_nonzero(slice_gray < _tol) >= _min_px:
            center_x = x + _w // 2
            center_y = y + _h // 2
            mouse_click(center_x, center_y)

            click_counts[idx] += 1
            session_counts[idx] += 1
            last_click_time = time.time()
            print_live_log()
            break  # 只处理第一个检测到的黑块


# -------------------【主逻辑（零冗余）】-------------------
def main_script():
    global is_running, last_click_time

    def toggle_running():
        global is_running
        is_running = not is_running
        if is_running:
            reset_session_counts()
            print("\n▶️ 启动 — 开始实时记录点击日志")
        else:
            print("\n⏸️ 暂停 — 本次运行统计如下：")
            print_summary("⏸️ 暂停统计")
            print("\n（按 F10 继续运行，点击计数将重新累计）")

    def stop_script():
        global is_running
        is_running = False
        print("\n🛑 停止 — 最终统计如下：")
        print_summary("🛑 停止统计")
        print("\n（按 F10 可重新启动）")

    def emergency_stop():
        global is_running
        is_running = False
        print("\n🆘 紧急退出 — 最终统计如下：")
        print_summary("🆘 紧急退出统计")
        exit()

    keyboard.add_hotkey(START_HOTKEY, toggle_running)
    keyboard.add_hotkey(STOP_HOTKEY, stop_script)
    keyboard.add_hotkey(EMERGENCY_STOP_HOTKEY, emergency_stop)

    try:
        while True:
            if is_running:
                detect_and_click_all()
            time.sleep(LOOP_DELAY)
    finally:
        sct.close()
        keyboard.unhook_all()
        for win, canvas, _, _, _ in AREA_CACHE:
            if win.winfo_exists():
                win.destroy()
        if tk_root is not None:
            tk_root.quit()


if __name__ == "__main__":
    area_thread = threading.Thread(target=create_all_draggable_areas, daemon=True)
    area_thread.start()
    time.sleep(0.05)
    main_script()