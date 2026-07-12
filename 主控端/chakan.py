import socket
import zlib
from typing import Optional
import cv2
import numpy as np

ESC_KEY = 27
Q_KEY = 113

def recv_all(sock: socket.socket, n: int) -> Optional[bytes]:
    data = bytearray(n)
    view = memoryview(data)
    received = 0
    while received < n:
        packet_size = sock.recv_into(view[received:])
        if packet_size == 0:
            return None
        received += packet_size
    return bytes(data)

def view_remote_screen(remote_ip: str, port: int = 9527, window_name: str = "Remote View") -> None:
    print(f"[*] 正在尝试连接目标 {remote_ip}:{port} ...")
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(5)
        
        try:
            sock.connect((remote_ip, port))
        except (ConnectionRefusedError, socket.timeout, Exception) as e:
            error_msg = "目标拒绝连接" if isinstance(e, ConnectionRefusedError) else "连接超时" if isinstance(e, socket.timeout) else f"未知错误: {e}"
            print(f"[!] 连接失败：{error_msg}")
            return

        sock.settimeout(None)
        print(f"[+] 成功连接目标！正在接收屏幕画面...")
        print(f"[*] 操作提示：按 ESC 或 q 键断开连接并退出")
        
        try:
            while True:
                raw_length = recv_all(sock, 4)
                if not raw_length:
                    print("[-] 目标已断开连接。")
                    break
                    
                length = int.from_bytes(raw_length, byteorder='big')
                
                frame_data = recv_all(sock, length)
                if not frame_data:
                    print("[-] 目标已断开连接。")
                    break

                jpeg_data = zlib.decompress(frame_data)
                nparr = np.frombuffer(jpeg_data, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                if frame is not None:
                    cv2.imshow(window_name, frame)

                key = cv2.waitKey(1) & 0xFF
                if key in (ESC_KEY, Q_KEY):
                    print("[*] 用户主动退出。")
                    break
                    
                if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                    break

        except zlib.error:
            print("[!] 数据解压失败，可能收到了损坏的数据包。")
        except Exception as e:
            print(f"[!] 运行过程中发生错误: {e}")
        finally:
            cv2.destroyAllWindows()
            print("[*] 查看器已关闭，连接已断开。")

if __name__ == "__main__":
    TARGET_IP = "192.168.1.100"
    view_remote_screen(
        remote_ip=TARGET_IP, 
        port=9527, 
        window_name=f"Monitoring {TARGET_IP}"
    )