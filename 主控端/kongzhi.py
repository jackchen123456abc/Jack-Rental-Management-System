import socket
import struct
import cv2
import numpy as np
import json

def recv_all(sock: socket.socket, n: int) -> bytes | None:
    data = bytearray(n)
    mv = memoryview(data)
    bytes_read = 0
    while bytes_read < n:
        packet = sock.recv_into(mv[bytes_read:], n - bytes_read)
        if packet == 0:
            return None
        bytes_read = bytes_read + packet
    return bytes(data)

def remote_control_client(target_ip: str = "127.0.0.1", port_video: int = 8000, port_control: int = 8001, display_w: int = 1920, display_h: int = 1080) -> None:
    remote_w = 1920
    remote_h = 1080
    scale_x = 1.0
    scale_y = 1.0
    control_sock = None
    window_name = "Remote Control"
    
    key_map = {
        8: "backspace",
        13: "enter",
        9: "tab",
        32: "space"
    }

    mouse_event_map = {
        cv2.EVENT_LBUTTONDOWN: ("mousedown", "left"),
        cv2.EVENT_LBUTTONUP: ("mouseup", "left"),
        cv2.EVENT_LBUTTONDBLCLK: ("doubleclick", "left"),
        cv2.EVENT_RBUTTONDOWN: ("mousedown", "right"),
        cv2.EVENT_RBUTTONUP: ("mouseup", "right"),
        cv2.EVENT_RBUTTONDBLCLK: ("doubleclick", "right"),
        cv2.EVENT_MBUTTONDOWN: ("mousedown", "middle"),
        cv2.EVENT_MBUTTONUP: ("mouseup", "middle"),
        cv2.EVENT_MBUTTONDBLCLK: ("doubleclick", "middle")
    }

    def send_command(cmd_dict: dict) -> None:
        if control_sock:
            try:
                msg = (json.dumps(cmd_dict) + "\n").encode("utf-8")
                control_sock.sendall(msg)
            except Exception:
                pass

    def update_scaling() -> None:
        nonlocal scale_x, scale_y
        if display_w > 0 and display_h > 0:
            scale_x = remote_w / display_w
            scale_y = remote_h / display_h

    def mouse_callback(event: int, x: int, y: int, flags: int, param: any) -> None:
        if display_w == 0 or display_h == 0:
            return
            
        real_x = int(x * scale_x)
        real_y = int(y * scale_y)

        if event == cv2.EVENT_MOUSEMOVE:
            send_command({"action": "move", "x": real_x, "y": real_y})
        elif event == cv2.EVENT_MOUSEWHEEL:
            clicks = flags >> 16
            send_command({"action": "scroll", "clicks": clicks, "x": real_x, "y": real_y})
        elif event == cv2.EVENT_MOUSEHWHEEL:
            clicks = flags >> 16
            send_command({"action": "hscroll", "clicks": clicks, "x": real_x, "y": real_y})
        elif event in mouse_event_map:
            action, button = mouse_event_map[event]
            send_command({"action": action, "x": real_x, "y": real_y, "button": button})

    def receive_video() -> None:
        nonlocal remote_w, remote_h
        video_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        video_sock.settimeout(5.0)
        video_sock.connect((target_ip, port_video))

        try:
            raw_len = recv_all(video_sock, 4)
            info_len = struct.unpack("!I", raw_len)[0]
            res_info = recv_all(video_sock, info_len).decode("utf-8")
            info = json.loads(res_info)
            remote_w = info["w"]
            remote_h = info["h"]
            update_scaling()
            print(f"[*] Connected! Remote resolution: {remote_w}x{remote_h}")
            video_sock.settimeout(None)

            while True:
                if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                    print("[*] Window closed by user, exiting...")
                    break

                raw_len = recv_all(video_sock, 4)
                if not raw_len:
                    print("[-] Video stream disconnected (Header lost)")
                    break
                    
                data_len = struct.unpack("!I", raw_len)[0]
                frame_data = recv_all(video_sock, data_len)
                
                if not frame_data:
                    print("[-] Video stream disconnected (Data lost)")
                    break

                frame = cv2.imdecode(np.frombuffer(frame_data, dtype=np.uint8), cv2.IMREAD_COLOR)
                if frame is None:
                    continue

                frame_resized = cv2.resize(frame, (display_w, display_h))
                cv2.imshow(window_name, frame_resized)

                key = cv2.waitKey(1) & 0xFF
                if key != 255:
                    if key in key_map:
                        send_command({"action": "key", "key": key_map[key]})
                    else:
                        try:
                            send_command({"action": "type", "text": chr(key)})
                        except ValueError:
                            pass
        finally:
            video_sock.close()

    try:
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, display_w, display_h)

        control_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        control_sock.settimeout(5.0)
        control_sock.connect((target_ip, port_control))
        control_sock.settimeout(None)

        cv2.setMouseCallback(window_name, mouse_callback)
        print(f"[*] Connecting to {target_ip} ...")
        
        receive_video()

    except ConnectionRefusedError:
        print(f"[!] Connection failed: {target_ip} refused connection.")
    except socket.timeout:
        print(f"[!] Connection timeout: {target_ip}.")
    except Exception as e:
        print(f"[!] Unknown error: {e}")
    finally:
        print("[*] Cleaning up resources...")
        if control_sock:
            try:
                control_sock.close()
            except Exception:
                pass
        cv2.destroyAllWindows()
        print("[*] Remote control client terminated.")

if __name__ == "__main__":
    remote_control_client()