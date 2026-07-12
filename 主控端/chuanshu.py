import socket

def send_command_via_tcp(host: str, port: int = 6000, command: str = "", timeout: int = 5, wait_response: bool = True) -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((host, port))
            s.sendall((command + "\n").encode("utf-8"))
            if wait_response:
                result = s.recv(8192).decode("utf-8")
                return result
            return "OK"
    except socket.timeout:
        return "错误：连接超时"
    except ConnectionRefusedError:
        return "错误：目标拒绝连接"
    except Exception as e:
        return f"错误：{e}"

def send_lock_command(host: str, port: int = 6000) -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, port))
        sock.sendall(b"suoping\n")
        return sock
    except Exception as e:
        try:
            sock.close()
        except:
            pass
        return None


def send_unlock_to_socket(sock: socket.socket) -> str:
    if sock is None:
        return "错误：没有可用的锁屏连接"
    try:
        sock.settimeout(5)
        sock.sendall(b"jiesuo\n")
        sock.close()
        return "OK"
    except Exception as e:
        try:
            sock.close()
        except:
            pass
        return f"错误：{e}"

if __name__ == "__main__":
    pass