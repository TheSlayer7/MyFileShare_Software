import socket
import os
import sys
import time
import hashlib
import threading
import shutil
import secrets
import string
import platform
import subprocess
import tempfile
import tkinter.messagebox as messagebox
import customtkinter as ctk
from customtkinter import filedialog
from tkinterdnd2 import TkinterDnD, DND_FILES
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw
from plyer import notification 

TCP_PORT = 49494
UDP_PORT = 49495

class MyFileSharingApp(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        super().__init__()
        self.TkdndVersion = TkinterDnD._require(self)

        self.title("MyFileSharingSoftware")
        self.geometry("550x920") 
        self.resizable(False, False)
        
        self.shutdown_flag = threading.Event()
        
        alphabet = string.ascii_uppercase + string.digits
        self.my_session_pin = ''.join(secrets.choice(alphabet) for _ in range(6))
        
        self.my_ip = self.get_local_ip()
        self.my_hostname = socket.gethostname()
        
        self.transfer_approved = False
        self.prompt_event = threading.Event()

        self.setup_ui()

        self.protocol("WM_DELETE_WINDOW", self.hide_window)

        threading.Thread(target=self.broadcast_presence, daemon=True).start()
        threading.Thread(target=self.start_tcp_server, daemon=True).start()

    def setup_ui(self):
        self.title_label = ctk.CTkLabel(self, text="MyFileSharingSoftware", font=("Arial", 28, "bold"))
        self.title_label.pack(pady=(20, 10))

        self.appearance_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.appearance_frame.pack(pady=5)
        self.appearance_mode_optionemenu = ctk.CTkSegmentedButton(self.appearance_frame, 
                                                               values=["Dark", "Light", "System"],
                                                               command=self.change_appearance_mode_event)
        self.appearance_mode_optionemenu.set("Dark")
        self.appearance_mode_optionemenu.pack()

        self.my_info_frame = ctk.CTkFrame(self, corner_radius=10, border_width=1, border_color="#00A2FF")
        self.my_info_frame.pack(pady=15, padx=20, fill="x")
        
        ctk.CTkLabel(self.my_info_frame, text=f"DEVICE NAME: {self.my_hostname}", font=("Arial", 12, "bold"), text_color="#00A2FF").pack(pady=(5,0))
        
        self.info_inner = ctk.CTkFrame(self.my_info_frame, fg_color="transparent")
        self.info_inner.pack(pady=10)
        
        self.info_text = ctk.CTkLabel(self.info_inner, text=f"IP: {self.my_ip}   |   TOKEN: ", font=("Arial", 16))
        self.info_text.pack(side="left")
        
        self.pin_label = ctk.CTkLabel(self.info_inner, text=self.my_session_pin, font=("Courier New", 24, "bold"), text_color="yellow")
        self.pin_label.pack(side="left")

        self.target_frame = ctk.CTkFrame(self, corner_radius=10)
        self.target_frame.pack(pady=10, padx=20, fill="x")
        
        ctk.CTkLabel(self.target_frame, text="SEND TO ANOTHER DEVICE", font=("Arial", 12, "bold"), text_color="gray").pack(pady=(5,0))

        self.target_inputs = ctk.CTkFrame(self.target_frame, fg_color="transparent")
        self.target_inputs.pack(pady=10)

        self.ip_entry = ctk.CTkEntry(self.target_inputs, placeholder_text="Target IP Address", width=180)
        self.ip_entry.pack(side="left", padx=5)
        
        self.scan_btn = ctk.CTkButton(self.target_inputs, text="Scan", command=self.start_scan_thread, width=60)
        self.scan_btn.pack(side="left", padx=5)

        self.pin_entry = ctk.CTkEntry(self.target_inputs, placeholder_text="6-Char Token", width=110, justify="center")
        self.pin_entry.pack(side="left", padx=5)

        self.drop_zone = ctk.CTkFrame(self, width=400, height=130, corner_radius=15, border_width=2, border_color="gray")
        self.drop_zone.pack(pady=20, padx=20, fill="x")
        self.drop_zone.pack_propagate(False) 

        self.drop_label = ctk.CTkLabel(self.drop_zone, text="📁\nDrag & Drop File/Folder Here\nor Click Below to Select", font=("Arial", 16))
        self.drop_label.pack(expand=True)

        self.drop_zone.drop_target_register(DND_FILES)
        self.drop_zone.dnd_bind('<<Drop>>', self.handle_file_drop)

        self.manual_btn = ctk.CTkButton(self, text="Select File/Folder Manually", font=("Arial", 14), 
                                      height=40, width=220, command=self.select_file)
        self.manual_btn.pack(pady=5)

        self.status_label = ctk.CTkLabel(self, text="Status: Online", text_color="green")
        self.status_label.pack(pady=(15, 0))

        self.progress = ctk.CTkProgressBar(self, width=450)
        self.progress.set(0)
        self.progress.pack(pady=10)

        self.speed_label = ctk.CTkLabel(self, text="Speed: 0.00 MB/s", font=("Arial", 12))
        self.speed_label.pack(pady=0)

        self.log_box = ctk.CTkTextbox(self, height=100, state="disabled")
        self.log_box.pack(pady=15, padx=20, fill="x")

        self.bottom_btns = ctk.CTkFrame(self, fg_color="transparent")
        self.bottom_btns.pack(pady=10)

        self.open_folder_btn = ctk.CTkButton(self.bottom_btns, text="Open Received Folder", width=180, command=self.open_folder)
        self.open_folder_btn.pack(side="left", padx=10)

        self.quit_btn = ctk.CTkButton(self.bottom_btns, text="Shutdown", fg_color="#8B0000", hover_color="#FF0000", width=120, command=self.quit_app)
        self.quit_btn.pack(side="left", padx=10)

    def change_appearance_mode_event(self, mode: str):
        ctk.set_appearance_mode(mode)

    def log(self, message):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def notify(self, title, message):
        try: notification.notify(title=title, message=message, app_name='MyFileSharing', timeout=5)
        except: pass

    def get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except: return "127.0.0.1"

    def open_folder(self):
        path = os.getcwd()
        if platform.system() == "Windows": os.startfile(path)
        else: subprocess.Popen(["open" if platform.system() == "Darwin" else "xdg-open", path])

    def calculate_hash(self, filepath):
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(8192): sha256.update(chunk)
        return sha256.hexdigest()

    def create_tray_icon(self):
        try:
            image = Image.open("icon.png") 
        except:
            image = Image.new('RGB', (64, 64), (0, 162, 255))
            d = ImageDraw.Draw(image)
            d.rectangle((16, 16, 48, 48), fill=(255, 255, 255))
        
        menu = pystray.Menu(
            item('Show App', self.show_window, default=True), 
            item('Quit Completely', self.quit_app)
        )
        self.tray_icon = pystray.Icon("MyFileSharing", image, "MyFileSharingSoftware", menu)
        self.tray_icon.run()

    def hide_window(self):
        self.withdraw()
        self.notify("Minimized", "App is still listening for files in the system tray.")
        if not hasattr(self, 'tray_thread'):
            self.tray_thread = threading.Thread(target=self.create_tray_icon, daemon=True)
            self.tray_thread.start()

    def show_window(self, icon=None, item=None):
        if hasattr(self, 'tray_icon'):
            self.tray_icon.stop()
            del self.tray_thread
        self.after(0, self.deiconify)

    def quit_app(self, icon=None, item=None):
        self.shutdown_flag.set()
        if hasattr(self, 'tray_icon'): self.tray_icon.stop()
        self.destroy()
        os._exit(0)

    def broadcast_presence(self):
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while not self.shutdown_flag.is_set():
            try:
                msg = f"FILE_SERVER_HERE|{self.my_hostname}"
                udp_sock.sendto(msg.encode(), ("<broadcast>", UDP_PORT))
                time.sleep(2)
            except: break
        udp_sock.close()

    def start_tcp_server(self):
        server = socket.socket()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", TCP_PORT)) 
        server.listen(5)
        server.settimeout(1.0)
        while not self.shutdown_flag.is_set():
            try:
                conn, addr = server.accept()
                threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True).start()
            except socket.timeout: continue
        server.close()

    def ask_approval(self, file_name, file_size, sender_name):
        self.notify("Incoming File", f"{sender_name} wants to send a file.")
        mb = messagebox.askyesno("Accept File?", f"Accept '{file_name}' ({(file_size/1e6):.2f} MB) from {sender_name}?")
        self.transfer_approved = mb
        self.prompt_event.set()

    def handle_client(self, conn, addr):
        ip = addr[0]
        try:
            salt = os.urandom(16)
            conn.sendall(salt)
            kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480000)
            key = kdf.derive(self.my_session_pin.encode())

            meta = conn.recv(1024).decode().split("|")
            if not meta: return
            
            f_name, f_size, f_hash, nonce_hex, is_f, s_name = meta[0], int(meta[1]), meta[2], meta[3], meta[4], meta[5]

            self.prompt_event.clear()
            self.after(0, self.ask_approval, f_name, f_size, s_name)
            self.prompt_event.wait() 

            if not self.transfer_approved:
                conn.sendall(b"REJECT")
                return 

            conn.sendall(b"OK")
            save_name = "recv_" + f_name
            decryptor = Cipher(algorithms.AES(key), modes.CTR(bytes.fromhex(nonce_hex))).decryptor()

            self.log(f"Receiving {f_name} from {s_name}...")
            with open(save_name, "wb") as f:
                rec = 0
                while rec < f_size:
                    data = conn.recv(min(8192, f_size - rec))
                    if not data: break
                    f.write(decryptor.update(data))
                    rec += len(data)
                f.write(decryptor.finalize())

            if self.calculate_hash(save_name) == f_hash:
                if is_f == "1":
                    fold = f_name.replace(".zip", "")
                    shutil.unpack_archive(save_name, fold)
                    os.remove(save_name)
                self.log("Transfer Success \u2705")
                self.notify("Success", f"Received {f_name}")
            else: self.log("Corruption Detected \u274c")

        except Exception as e: self.log(f"Error: {e}")
        finally: conn.close()

    def start_scan_thread(self):
        self.scan_btn.configure(state="disabled")
        threading.Thread(target=self.scan_for_server, daemon=True).start()

    def scan_for_server(self):
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if sys.platform == "win32": udp.bind(("", UDP_PORT))
        else: udp.bind(("<broadcast>", UDP_PORT))
        udp.settimeout(4.0)
        try:
            while True:
                data, addr = udp.recvfrom(1024)
                msg = data.decode().split("|")
                if msg[0] == "FILE_SERVER_HERE" and addr[0] != self.my_ip:
                    self.log(f"Found '{msg[1]}' at {addr[0]} \u2705")
                    self.ip_entry.delete(0, "end")
                    self.ip_entry.insert(0, addr[0])
                    break
        except: self.log("No other users found.")
        finally:
            udp.close()
            self.scan_btn.configure(state="normal")

    def handle_file_drop(self, event):
        p = event.data
        if p.startswith('{'): p = p[1:-1]
        self.trigger_transfer(p)

    def select_file(self):
        p = filedialog.askopenfilename() or filedialog.askdirectory()
        if p: self.trigger_transfer(p)

    def trigger_transfer(self, file_path):
        tip, tpin = self.ip_entry.get().strip(), self.pin_entry.get().strip()
        if not tip or not tpin:
            self.log("Error: Check IP and Token")
            return
        threading.Thread(target=self.send_logic, args=(file_path, tip, tpin), daemon=True).start()

    def send_logic(self, file_path, target_ip, target_pin):
        is_f, orig = "0", os.path.basename(file_path)
        send_path = file_path
        
        if os.path.isdir(file_path):
            self.log("Zipping folder...")
            temp_name = os.path.join(tempfile.gettempdir(), f"transfer_{secrets.token_hex(4)}")
            send_path = shutil.make_archive(temp_name, 'zip', file_path)
            is_f = "1"

        try:
            f_size, f_hash, nonce = os.path.getsize(send_path), self.calculate_hash(send_path), os.urandom(16)
            client = socket.socket()
            client.connect((target_ip, TCP_PORT))
            salt = client.recv(16)
            kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480000)
            key = kdf.derive(target_pin.encode())
            enc = Cipher(algorithms.AES(key), modes.CTR(nonce)).encryptor()

            name_to_send = orig if is_f == "0" else orig + ".zip"
            client.sendall(f"{name_to_send}|{f_size}|{f_hash}|{nonce.hex()}|{is_f}|{self.my_hostname}".encode())
            
            if client.recv(1024).decode() == "OK":
                self.log(f"Sending to {target_ip}...")
                with open(send_path, "rb") as f:
                    sent, start = 0, time.time()
                    while chunk := f.read(8192):
                        client.sendall(enc.update(chunk))
                        sent += len(chunk)
                        self.progress.set(sent/f_size)
                        self.speed_label.configure(text=f"{(sent/1e6)/(max(0.1, time.time()-start)):.2f} MB/s")
                    client.sendall(enc.finalize())
                self.log("Sent Successfully! \u2705")
            else: self.log("Rejected by target \u274c")
        except Exception as e: self.log(f"Failed: {e}")
        finally:
            client.close()
            self.progress.set(0)
            if is_f == "1": os.remove(send_path)

if __name__ == "__main__":
    app = MyFileSharingApp()
    app.mainloop()