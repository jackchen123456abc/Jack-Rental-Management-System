import socket
import threading
import struct
import cv2
import mss
import numpy as np
import pyautogui
import json
import zlib
import time
from pynput.mouse import Button, Controller
from pynput import keyboard as pynput_keyboard
from pynput import mouse as pynput_mouse
import ctypes
import os
import subprocess
import tkinter as tk

HOST = '0.0.0.0'
PORT_VIDEO = 8000
PORT_CONTROL = 8001
PORT_VIEW = 9527
JPEG_QUALITY = 50
RECV_BUFFER = 4096
QUALITY_VIEW = 60
SCALE_VIEW = 0.5
FPS_LIMIT = 15
PORT = 6000

ALL_PORTS = {
    6000: "Windows runner",
    8000: "System",
    8001: "System_reader",
    9527: "Windows_puter",
}

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0
mouse_ctrl = Controller()

BUTTON_MAP = {
    "left": Button.left,
    "right": Button.right,
    "middle": Button.middle
}

def open_firewall_ports():
    """启动时自动放行所有需要的 TCP 端口"""
    if os.name != 'nt':
        print("[防火墙] 非 Windows 系统，跳过自动放行")
        return

    print("[防火墙] 正在自动放行端口...")
    for port, desc in ALL_PORTS.items():
        rule_name = f"Jack租机-{desc}-{port}"
        try:
            subprocess.run(
                f'netsh advfirewall firewall delete rule name="{rule_name}"',
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5
            )
        except Exception:
            pass

        try:
            result = subprocess.run(
                f'netsh advfirewall firewall add rule name="{rule_name}" '
                f'dir=in action=allow protocol=TCP localport={port}',
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                print(f"  ✅ 端口 {port} ({desc}) 已放行")
            else:
                print(f"  ❌ 端口 {port} ({desc}) 放行失败: {result.stderr.strip()}")
                print(f"     ⚠️  请以管理员身份运行本程序！")
        except Exception as e:
            print(f"  ❌ 端口 {port} ({desc}) 放行异常: {e}")
    print("[防火墙] 端口放行处理完毕")

_lock_state = {
    "locked": False,
    "unlock_event": threading.Event(),
}
_lock_state_lock = threading.Lock()


def _block_black_screen(unlock_event):
    win = tk.Tk()
    win.title("")
    win.configure(bg="black", cursor="none")

    try:
        user32 = ctypes.windll.user32
        screen_w = user32.GetSystemMetrics(78)  
        screen_h = user32.GetSystemMetrics(79)  
        offset_x = user32.GetSystemMetrics(76) 
        offset_y = user32.GetSystemMetrics(77) 
    except Exception:
        screen_w = win.winfo_screenwidth()
        screen_h = win.winfo_screenheight()
        offset_x, offset_y = 0, 0

    win.geometry(f"{screen_w}x{screen_h}+{offset_x}+{offset_y}")
    win.attributes("-topmost", True)
    win.overrideredirect(True)
    for seq in [
        "<Key>", "<KeyRelease>", "<Button>", "<ButtonRelease>",
        "<Motion>", "<Enter>", "<Leave>", "<FocusIn>", "<FocusOut>",
        "<Alt-Tab>", "<Alt-F4>", "<Escape>"
    ]:
        win.bind(seq, lambda e: "break")

    win.protocol("WM_DELETE_WINDOW", lambda: None)
    win.focus_force()

    def poll_unlock():
        if unlock_event.is_set():
            try:
                win.destroy()
            except Exception:
                pass
        else:
            try:
                win.after(200, poll_unlock)
                win.attributes("-topmost", True)
                win.focus_force()
            except Exception:
                pass

    win.after(100, poll_unlock)
    win.mainloop()


def _start_input_blockers(unlock_event):
    def block_mouse_click(x, y, button, pressed):
        return False  # False = 阻止事件传递

    def block_mouse_scroll(x, y, dx, dy):
        return False

    def block_mouse_move(x, y):
        return False

    mouse_listener = pynput_mouse.Listener(
        on_click=block_mouse_click,
        on_scroll=block_mouse_scroll,
        on_move=block_mouse_move,
        suppress=True
    )
    def block_key_press(key):
        return False

    def block_key_release(key):
        return False

    kb_listener = pynput_keyboard.Listener(
        on_press=block_key_press,
        on_release=block_key_release,
        suppress=True
    )

    mouse_listener.start()
    kb_listener.start()
    unlock_event.wait()

    mouse_listener.stop()
    kb_listener.stop()


def perform_lock_screen():
    with _lock_state_lock:
        if _lock_state["locked"]:
            return
        _lock_state["locked"] = True
        _lock_state["unlock_event"].clear()

    unlock_event = _lock_state["unlock_event"]

    threading.Thread(target=_start_input_blockers, args=(unlock_event,), daemon=True).start()

    try:
        _block_black_screen(unlock_event)
    except Exception as e:
        print(f"[锁屏] 黑屏窗口异常: {e}")

    with _lock_state_lock:
        _lock_state["locked"] = False
    print("[锁屏] 已解锁，屏幕恢复正常")


def perform_unlock():
    """执行解锁：触发解锁事件，黑屏和键鼠屏蔽自动停止"""
    with _lock_state_lock:
        if _lock_state["locked"]:
            _lock_state["unlock_event"].set()
            _lock_state["locked"] = False
            return True
        return False

def get_button(cmd):
    return BUTTON_MAP.get(cmd.get("button", "left"), Button.left)

def set_position_and_get_button(cmd):
    mouse_ctrl.position = (cmd["x"], cmd["y"])
    return get_button(cmd)

def execute_move(cmd):
    pyautogui.moveTo(cmd["x"], cmd["y"])

def execute_click(cmd):
    btn = set_position_and_get_button(cmd)
    mouse_ctrl.click(btn, 1)

def execute_mousedown(cmd):
    btn = set_position_and_get_button(cmd)
    mouse_ctrl.press(btn)

def execute_mouseup(cmd):
    btn = set_position_and_get_button(cmd)
    mouse_ctrl.release(btn)

def execute_doubleclick(cmd):
    btn = set_position_and_get_button(cmd)
    mouse_ctrl.click(btn, 2)

def execute_scroll(cmd):
    pyautogui.scroll(cmd["clicks"], cmd["x"], cmd["y"])

def execute_hscroll(cmd):
    pyautogui.hscroll(cmd["clicks"], x=cmd["x"], y=cmd["y"])

def execute_type(cmd):
    pyautogui.typewrite(cmd["text"], interval=0.02)

def execute_key(cmd):
    pyautogui.press(cmd["key"])

COMMAND_MAP = {
    "move": execute_move,
    "click": execute_click,
    "mousedown": execute_mousedown,
    "mouseup": execute_mouseup,
    "doubleclick": execute_doubleclick,
    "scroll": execute_scroll,
    "hscroll": execute_hscroll,
    "type": execute_type,
    "key": execute_key
}

def execute_cmd(cmd):
    handler = COMMAND_MAP.get(cmd.get("action"))
    if handler:
        handler(cmd)

def control_handler(conn):
    buffer = ""
    while True:
        try:
            raw_data = conn.recv(RECV_BUFFER)
            if not raw_data:
                break
            buffer += raw_data.decode('utf-8', errors='ignore')
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                if line:
                    try:
                        cmd = json.loads(line)
                        execute_cmd(cmd)
                    except json.JSONDecodeError:
                        pass
        except Exception:
            break
    conn.close()

def video_stream(conn):
    with mss.MSS() as sct:
        monitor = sct.monitors[1]
        info = json.dumps({"w": monitor["width"], "h": monitor["height"]}).encode('utf-8')
        conn.sendall(struct.pack('!I', len(info)) + info)
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
        while True:
            try:
                frame = np.asarray(sct.grab(monitor))[:, :, :3]
                _, encoded = cv2.imencode('.jpg', frame, encode_param)
                data = encoded.tobytes()
                conn.sendall(struct.pack('!I', len(data)) + data)
            except:
                break
    conn.close()

def process_view_frame(sct):
    frame = np.asarray(sct.grab(sct.monitors[0]))[:, :, :3]
    if SCALE_VIEW != 1.0:
        h, w = frame.shape[:2]
        frame = cv2.resize(frame, (int(w * SCALE_VIEW), int(h * SCALE_VIEW)))
    _, jpeg_data = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, QUALITY_VIEW])
    return zlib.compress(jpeg_data.tobytes(), level=1)

def handle_view_client(conn, addr):
    frame_interval = 1.0 / FPS_LIMIT
    with mss.MSS() as sct:
        try:
            while True:
                start = time.time()
                data = process_view_frame(sct)
                conn.sendall(struct.pack('!I', len(data)) + data)
                elapsed = time.time() - start
                sleep_time = frame_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
        except:
            pass
        finally:
            conn.close()

def create_server(port):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, port))
    srv.listen(5)
    return srv

def lock_screen_handler(conn):
    buffer = ""
    try:
        conn.settimeout(10)
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                return
            buffer += chunk.decode("utf-8", errors="ignore")
            if "\n" in buffer:
                data, buffer = buffer.split("\n", 1)
                data = data.strip()
                break
        else:
            return

        if data == "guanji":
            conn.sendall(b"OK\n")
            conn.close()
            if os.name == 'nt':
                os.system("shutdown /s /t 0")
            else:
                os.system("shutdown -h now")

        elif data == "chongqi":
            conn.sendall(b"OK\n")
            conn.close()
            if os.name == 'nt':
                os.system("shutdown /r /t 0")
            else:
                os.system("shutdown -r now")

        elif data == "suoping":
            conn.sendall(b"LOCKED\n")
            conn.close()
            threading.Thread(target=perform_lock_screen, daemon=True).start()

        elif data == "jiesuo":
            unlocked = perform_unlock()
            if unlocked:
                conn.sendall(b"UNLOCKED\n")
            else:
                conn.sendall(b"NOT_LOCKED\n")
            conn.close()

        else:
            conn.sendall(b"UNKNOWN_COMMAND\n")
            conn.close()

    except Exception as e:
        print(f"[命令处理] 异常: {e}")
    finally:
        try:
            conn.close()
        except:
            pass


def start_lock_service():
    try:
        srv_lock = create_server(PORT)
        print(f"  ✅ 锁屏/关机服务已启动 - 端口 {PORT}")
    except Exception as e:
        print(f"  ❌ 锁屏服务启动失败(端口{PORT}): {e}")
        return
    while True:
        conn, addr = srv_lock.accept()
        threading.Thread(target=lock_screen_handler, args=(conn,), daemon=True).start()

def accept_video_clients(srv):
    while True:
        conn, addr = srv.accept()
        threading.Thread(target=video_stream, args=(conn,), daemon=True).start()

def accept_control_clients(srv):
    while True:
        conn, addr = srv.accept()
        threading.Thread(target=control_handler, args=(conn,), daemon=True).start()

def accept_view_clients(srv):
    while True:
        conn, addr = srv.accept()
        threading.Thread(target=handle_view_client, args=(conn, addr), daemon=True).start()

def start_all_services():
    open_firewall_ports()
    print("=" * 45)

    try:
        srv_vid = create_server(PORT_VIDEO)
        print(f"  ✅ 视频流服务已启动 - 端口 {PORT_VIDEO}")
        threading.Thread(target=accept_video_clients, args=(srv_vid,), daemon=True).start()
    except Exception as e:
        print(f"  ❌ 视频流服务启动失败(端口{PORT_VIDEO}): {e}")

    try:
        srv_ctrl = create_server(PORT_CONTROL)
        print(f"  ✅ 控制服务已启动 - 端口 {PORT_CONTROL}")
        threading.Thread(target=accept_control_clients, args=(srv_ctrl,), daemon=True).start()
    except Exception as e:
        print(f"  ❌ 控制服务启动失败(端口{PORT_CONTROL}): {e}")

    try:
        srv_view = create_server(PORT_VIEW)
        print(f"  ✅ 查看服务已启动 - 端口 {PORT_VIEW}")
        threading.Thread(target=accept_view_clients, args=(srv_view,), daemon=True).start()
    except Exception as e:
        print(f"  ❌ 查看服务启动失败(端口{PORT_VIEW}): {e}")

    threading.Thread(target=start_lock_service, daemon=True).start()

    print("=" * 45)
    print("所有服务启动完毕，等待连接...")
    print("=" * 45)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    start_all_services()
if __name__ == "__main__":
    start_all_services()