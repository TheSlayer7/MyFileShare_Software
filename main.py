import socket
import os
import sys
import time
import hashlib
import hmac
import threading
import shutil
import secrets
import string
import platform
import subprocess
import tempfile
import json
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
CONTACTS_FILE = "contacts.json"
SOCKET_TIMEOUT = 20

class MyFileSharingApp(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        super().__init__()
        self.TkdndVersion = TkinterDnD._require(self)

        self.title("MyFileSharingSoftware")
        self.geometry("550x980") 
        self.resizable(False, False)
        
        self.shutdown_flag = threading.Event()
        self.cancel_transfer_flag = threading.Event()
        
        alphabet = string.ascii_uppercase + string.digits
        self.my_session_pin = ''.join(secrets.choice(alphabet) for _ in range(6))
        
        self.my_ip = self.get_local_ip()
        self.my_hostname = socket.gethostname()
        
        self.failed_attempts = {}
        self.discovered_peers = {} # {ip: timestamp}
        self.saved_contacts = self.load_contacts()
        
        self.save_dir = os.path.join(os.path.expanduser("~"), "Downloads", "MyFileSharing")
        os.makedirs(self.save_dir, exist_ok=True)
        
        self.transfer_approved = False
        self.prompt_event = threading.Event()

        self.setup_ui()
        self.protocol("WM_DELETE_WINDOW", self.hide_window)

        # Start Networking Threads
        threading.Thread(target=self.broadcast_presence, daemon=True).start()
        threading.Thread(target=self.start_tcp_server, daemon=True).start()
        threading.Thread(target=self.scan_for_server, daemon=True).start()
        threading.Thread(target=self.prune_stale_peers, daemon=True).start()

    def load_contacts(self):
        if os.path.exists(CONTACTS_FILE):
            try:
                with open(CONTACTS_FILE, "r") as f: return json.load(f)
            except: return []
        return []

    def save_contact_action(self):
        ip = self.ip_entry.get().strip()
        if ip and ip not in self.saved_contacts:
            self.saved_contacts.append(ip)
            with open(CONTACTS_FILE, "w") as f: json.dump(self.saved_contacts, f)
            self.update_peer_list()
            self.notify("Saved", f"IP {ip} saved to contacts.")

    def setup_ui(self):
        self.title_label = ctk.CTkLabel(self, text="MyFileSharingSoftware", font=("Arial", 28, "bold"))
        self.title_label.pack(pady=(20, 10))

        self.appearance_mode_optionemenu = ctk.CTkSegmentedButton(self, values=["Dark", "Light", "System"], command=self.on_appearance_change)
        self.appearance_mode_optionemenu.set("Dark")
        self.appearance_mode_optionemenu.pack(pady=5)

        self.my_info_frame = ctk.CTkFrame(self, corner_radius=10, border_width=1, border_color="#00A2FF")
        self.my_info_frame.pack(pady=15, padx=20, fill="x")
        
        self.device_label = ctk.CTkLabel(self.my_info_frame, text=f"DEVICE NAME: {self.my_hostname}", font=("Arial", 12, "bold"), text_color="#00A2FF")
        self.device_label.pack(pady=(5,0))
        self.info_inner = ctk.CTkFrame(self.my_info_frame, fg_color="transparent")
        self.info_inner.pack(pady=10)
        self.ip_token_label = ctk.CTkLabel(self.info_inner, text=f"IP: {self.my_ip}   |   TOKEN: ", font=("Arial", 16))
        self.ip_token_label.pack(side="left")
        self.token_value_label = ctk.CTkLabel(self.info_inner, text=self.my_session_pin, font=("Courier New", 24, "bold"), text_color="yellow")
        self.token_value_label.pack(side="left")

        self.target_frame = ctk.CTkFrame(self, corner_radius=10)
        self.target_frame.pack(pady=10, padx=20, fill="x")
        self.target_title = ctk.CTkLabel(self.target_frame, text="SEND TO ANOTHER DEVICE", font=("Arial", 12, "bold"), text_color="gray")
        self.target_title.pack(pady=(5,0))

        self.target_inputs = ctk.CTkFrame(self.target_frame, fg_color="transparent")
        self.target_inputs.pack(pady=10)

        self.ip_entry = ctk.CTkComboBox(self.target_inputs, values=self.saved_contacts, width=150)
        self.ip_entry.pack(side="left", padx=5)
        self.ip_entry.set("")
        
        self.save_btn = ctk.CTkButton(self.target_inputs, text="Save IP", command=self.save_contact_action, width=60)
        self.save_btn.pack(side="left", padx=2)

        self.pin_entry = ctk.CTkEntry(self.target_inputs, placeholder_text="6-Char Token", width=100, justify="center")
        self.pin_entry.pack(side="left", padx=5)

        self.drop_zone = ctk.CTkFrame(self, width=400, height=130, corner_radius=15, border_width=2, border_color="gray")
        self.drop_zone.pack(pady=20, padx=20, fill="x")
        self.drop_zone.pack_propagate(False) 
        self.drop_label = ctk.CTkLabel(self.drop_zone, text="📁\nDrag & Drop File/Folder Here\nor Click Below to Select", font=("Arial", 16))
        self.drop_label.pack(expand=True)
        self.drop_zone.drop_target_register(DND_FILES)
        self.drop_zone.dnd_bind('<<Drop>>', self.handle_file_drop)

        self.manual_btn = ctk.CTkButton(self, text="Select File(s) Manually", font=("Arial", 14), height=40, width=220, command=self.select_file)
        self.manual_btn.pack(pady=5)

        self.progress = ctk.CTkProgressBar(self, width=450)
        self.progress.set(0)
        self.progress.pack(pady=(15,5))

        self.speed_label = ctk.CTkLabel(self, text="Speed: 0.00 MB/s", font=("Arial", 12))
        self.speed_label.pack(pady=0)
        
        self.cancel_btn = ctk.CTkButton(self, text="Pause / Cancel Transfer", fg_color="#555555", hover_color="#8B0000", height=24, width=150, state="disabled", command=self.cancel_transfer)
        self.cancel_btn.pack(pady=5)

        self.log_box = ctk.CTkTextbox(self, height=90, state="disabled")
        self.log_box.pack(pady=10, padx=20, fill="x")

        self.settings_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.settings_frame.pack(pady=5)
        self.dir_label = ctk.CTkLabel(self.settings_frame, text=f"Save to: {self.truncate_path(self.save_dir)}", font=("Arial", 11), text_color="gray")
        self.dir_label.pack(side="left", padx=10)
        ctk.CTkButton(self.settings_frame, text="Change", width=60, height=24, command=self.change_save_dir).pack(side="left")

        self.bottom_btns = ctk.CTkFrame(self, fg_color="transparent")
        self.bottom_btns.pack(pady=10)
        ctk.CTkButton(self.bottom_btns, text="Open Received Folder", width=180, command=self.open_folder).pack(side="left", padx=10)
        ctk.CTkButton(self.bottom_btns, text="Shutdown", fg_color="#8B0000", hover_color="#FF0000", width=120, command=self.quit_app).pack(side="left", padx=10)

        self.apply_theme("Dark")

    def on_appearance_change(self, mode):
        ctk.set_appearance_mode(mode)
        self.apply_theme()

    def apply_theme(self, mode=None):
        current_mode = (mode or ctk.get_appearance_mode()).lower()
        is_light = current_mode == "light"

        if is_light:
            self.configure(fg_color="#EEF3F9")
            self.my_info_frame.configure(fg_color="#FFFFFF", border_color="#0B66C3")
            self.target_frame.configure(fg_color="#F7FAFF")
            self.drop_zone.configure(fg_color="#FFFFFF", border_color="#9DB4CF")
            self.log_box.configure(fg_color="#FFFFFF", text_color="#1C2A39", border_color="#B7C9DE", border_width=1)
            self.settings_frame.configure(fg_color="transparent")

            self.title_label.configure(text_color="#10243E")
            self.device_label.configure(text_color="#0B66C3")
            self.ip_token_label.configure(text_color="#1D3958")
            self.token_value_label.configure(text_color="#0C8A2F")
            self.target_title.configure(text_color="#486481")
            self.drop_label.configure(text_color="#294A6C")
            self.speed_label.configure(text_color="#294A6C")
            self.dir_label.configure(text_color="#526C88")
        else:
            self.configure(fg_color=["gray92", "gray10"])
            self.my_info_frame.configure(fg_color=["gray86", "gray16"], border_color="#00A2FF")
            self.target_frame.configure(fg_color=["gray88", "gray18"])
            self.drop_zone.configure(fg_color=["gray88", "gray18"], border_color="gray")
            self.log_box.configure(fg_color=["gray92", "gray14"], text_color=["gray15", "gray90"], border_width=0)

            self.title_label.configure(text_color=["gray10", "gray90"])
            self.device_label.configure(text_color="#00A2FF")
            self.ip_token_label.configure(text_color=["gray10", "gray90"])
            self.token_value_label.configure(text_color="yellow")
            self.target_title.configure(text_color="gray")
            self.drop_label.configure(text_color=["gray10", "gray90"])
            self.speed_label.configure(text_color=["gray20", "gray90"])
            self.dir_label.configure(text_color="gray")

    def cancel_transfer(self):
        self.cancel_transfer_flag.set()
        self.log("Interrupting transfer...")

    def update_peer_list(self):
        if self.shutdown_flag.is_set(): return
        active_ips = list(self.discovered_peers.keys())
        all_ips = list(set(self.saved_contacts + active_ips))
        self.ip_entry.configure(values=all_ips)

    def prune_stale_peers(self):
        while not self.shutdown_flag.is_set():
            now = time.time()
            changed = False
            for ip in list(self.discovered_peers.keys()):
                if now - self.discovered_peers[ip] > 120: 
                    del self.discovered_peers[ip]
                    changed = True
                    if not self.shutdown_flag.is_set():
                        self.log(f"Device {ip} went offline.")
            if changed and not self.shutdown_flag.is_set(): 
                self.after(0, self.update_peer_list)
            time.sleep(5)

    def truncate_path(self, path, max_length=40):
        return path if len(path) <= max_length else f"...{path[-(max_length-3):]}"

    def change_save_dir(self):
        new_dir = filedialog.askdirectory(initialdir=self.save_dir)
        if new_dir:
            self.save_dir = new_dir
            self.dir_label.configure(text=f"Save to: {self.truncate_path(self.save_dir)}")

    def update_ui_progress(self, pct, speed_text):
        if not self.shutdown_flag.is_set():
            self.progress.set(pct)
            self.speed_label.configure(text=speed_text)

    def log(self, message):
        if not self.shutdown_flag.is_set():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", f"[{time.strftime('%H:%M:%S')}] {message}\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")

    def log_info(self, message):
        self.log(f"[INFO] {message}")

    def log_warn(self, message):
        self.log(f"[WARN] {message}")

    def log_error(self, message):
        self.log(f"[ERROR] {message}")

    def notify(self, title, message):
        if not self.shutdown_flag.is_set():
            try: notification.notify(title=title, message=message, app_name='MyFileSharing', timeout=5)
            except: pass

    def recv_exact(self, sock, num_bytes):
        """Ensures exactly num_bytes are received from the socket."""
        data = b''
        while len(data) < num_bytes:
            packet = sock.recv(num_bytes - len(data))
            if not packet:
                break
            data += packet
        return data

    def get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except: return "127.0.0.1"

    def open_folder(self):
        if platform.system() == "Windows": os.startfile(self.save_dir)
        else: subprocess.Popen(["open" if platform.system() == "Darwin" else "xdg-open", self.save_dir])

    def calculate_hash(self, filepath):
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(8192): sha256.update(chunk)
        return sha256.hexdigest()

    def create_tray_icon(self):
        try: image = Image.open("icon.png") 
        except:
            image = Image.new('RGB', (64, 64), (0, 162, 255))
            d = ImageDraw.Draw(image)
            d.rectangle((16, 16, 48, 48), fill=(255, 255, 255))
        menu = pystray.Menu(item('Show App', self.show_window, default=True), item('Quit Completely', self.quit_app))
        self.tray_icon = pystray.Icon("MyFileSharing", image, "MyFileSharingSoftware", menu)
        self.tray_icon.run()

    def hide_window(self):
        self.withdraw()
        self.notify("Minimized", "Listening in background.")
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
        if hasattr(self, 'tray_icon'): 
            self.tray_icon.stop()
        os._exit(0)

    def broadcast_presence(self):
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while not self.shutdown_flag.is_set():
            try:
                udp_sock.sendto(f"FILE_SERVER_HERE|{self.my_hostname}".encode(), ("<broadcast>", UDP_PORT))
                time.sleep(2)
            except: break
        udp_sock.close()

    def scan_for_server(self):
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if sys.platform == "win32": udp.bind(("", UDP_PORT))
        else: udp.bind(("<broadcast>", UDP_PORT))
        udp.settimeout(2.0)
        while not self.shutdown_flag.is_set():
            try:
                data, addr = udp.recvfrom(1024)
                msg = data.decode().split("|")
                if msg[0] == "FILE_SERVER_HERE" and addr[0] != self.my_ip:
                    is_new = addr[0] not in self.discovered_peers
                    self.discovered_peers[addr[0]] = time.time()
                    if is_new and not self.shutdown_flag.is_set():
                        self.after(0, self.log, f"Found '{msg[1]}' at {addr[0]} \u2705")
                        self.after(0, self.update_peer_list)
            except socket.timeout: continue
            except: break
        udp.close()

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

    def ask_approval(self, prompt_title, prompt_msg):
        self.notify("Incoming File", prompt_msg)
        mb = messagebox.askyesno(prompt_title, prompt_msg)
        self.transfer_approved = mb
        self.prompt_event.set()

    def handle_client(self, conn, addr):
        ip = addr[0]
        try:
            conn.settimeout(SOCKET_TIMEOUT)
            if ip in self.failed_attempts:
                attempts, lockout_time = self.failed_attempts[ip]
                if time.time() < lockout_time:
                    conn.sendall(b"REJECT|LOCKED")
                    self.after(0, self.log_warn, f"Rejected connection from {ip}: temporary lockout active.")
                    conn.close()
                    return
                elif time.time() >= lockout_time and attempts >= 3:
                    del self.failed_attempts[ip]

            salt = os.urandom(16)
            conn.sendall(salt)
            kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480000)
            key = kdf.derive(self.my_session_pin.encode())

            client_auth = self.recv_exact(conn, 32)
            expected_auth = hmac.new(key, b"AUTH_CHALLENGE", hashlib.sha256).digest()
            if not hmac.compare_digest(client_auth, expected_auth):
                attempts = self.failed_attempts.get(ip, (0, 0))[0] + 1
                self.failed_attempts[ip] = (attempts, time.time() + 60 if attempts >= 3 else 0)
                conn.sendall(b"AUTH_FAIL")
                self.after(0, self.log_warn, f"Auth failed from {ip}. Attempt {attempts}/3.")
                conn.close()
                return

            if ip in self.failed_attempts: del self.failed_attempts[ip]
            conn.sendall(b"AUTH_OK")

            meta = conn.recv(1024).decode().split("|", 4)
            if not meta or len(meta) < 5:
                conn.sendall(b"REJECT|META")
                self.after(0, self.log_warn, f"Rejected malformed transfer metadata from {ip}.")
                return
            f_name, f_size, f_hash, is_f, s_name = meta[0], int(meta[1]), meta[2], meta[3], meta[4]

            part_file = os.path.join(self.save_dir, f"{f_hash}.part")
            offset = 0
            
            if os.path.exists(part_file):
                offset = os.path.getsize(part_file)
                if offset < f_size:
                    self.prompt_event.clear()
                    self.after(0, self.ask_approval, "Resume Transfer?", f"Resume receiving '{f_name}' from {s_name}? ({(offset/1e6):.1f}/{(f_size/1e6):.1f} MB already done)")
                    self.prompt_event.wait()
                else: offset = 0 
            else:
                self.prompt_event.clear()
                self.after(0, self.ask_approval, "Accept File?", f"Accept '{f_name}' ({(f_size/1e6):.2f} MB) from {s_name}?")
                self.prompt_event.wait() 

            if not self.transfer_approved:
                conn.sendall(b"REJECT|DECLINED")
                self.after(0, self.log_info, f"Declined transfer '{f_name}' from {s_name} ({ip}).")
                return 

            if offset > 0: conn.sendall(f"RESUME|{offset}".encode())
            else: conn.sendall(b"START|0")

            nonce = self.recv_exact(conn, 16)
            if len(nonce) != 16:
                self.after(0, self.log_error, f"Invalid nonce received from {s_name} ({ip}).")
                return
            decryptor = Cipher(algorithms.AES(key), modes.CTR(nonce)).decryptor()
            stream_mac = hmac.new(key, digestmod=hashlib.sha256)
            
            mode = "ab" if offset > 0 else "wb"
            self.after(0, self.log, f"Receiving {f_name} from {s_name} (Starting at {offset/1e6:.1f}MB)...")
            self.after(0, lambda: self.cancel_btn.configure(state="normal"))
            
            with open(part_file, mode) as f:
                rec, start_time = offset, time.time()
                while rec < f_size and not self.shutdown_flag.is_set():
                    data = conn.recv(min(8192, f_size - rec))
                    if not data: break 
                    
                    stream_mac.update(data)
                    f.write(decryptor.update(data))
                    rec += len(data)

                    elapsed = max(0.1, time.time() - start_time)
                    pct = rec / f_size if f_size > 0 else 1
                    speed = ((rec - offset) / 1e6) / elapsed
                    self.after(0, self.update_ui_progress, pct, f"Speed: {speed:.2f} MB/s")

            self.after(0, self.update_ui_progress, 0, "Speed: 0.00 MB/s")
            self.after(0, lambda: self.cancel_btn.configure(state="disabled"))

            if self.shutdown_flag.is_set(): return

            if rec < f_size:
                self.after(0, self.log_warn, "Transfer paused or connection dropped. Partial data kept for resume.")
                return

            sender_mac = self.recv_exact(conn, 32)
            if not sender_mac or not hmac.compare_digest(stream_mac.digest(), sender_mac):
                self.after(0, self.log_error, "SECURITY ALERT: Stream MAC mismatch. Transfer dropped as unsafe.")
                return
            
            # Tell the sender we successfully received and verified the MAC
            conn.sendall(b"DONE")

            if self.calculate_hash(part_file) == f_hash:
                save_base, save_ext = os.path.splitext(f_name)
                final_save_name = os.path.join(self.save_dir, f_name)
                counter = 1
                while os.path.exists(final_save_name):
                    final_save_name = os.path.join(self.save_dir, f"{save_base} ({counter}){save_ext}")
                    counter += 1
                
                os.rename(part_file, final_save_name)

                if is_f == "1":
                    fold = final_save_name.replace(".zip", "")
                    shutil.unpack_archive(final_save_name, fold)
                    os.remove(final_save_name)
                    
                self.after(0, self.log_info, f"Transfer completed successfully: {f_name}")
                self.after(0, self.notify, "Success", f"Received {f_name}")
            else:
                self.after(0, self.log_error, f"Hash mismatch for {f_name}. File rejected as corrupt.")

        except socket.timeout:
            if not self.shutdown_flag.is_set():
                self.after(0, self.log_warn, f"Connection with {ip} timed out.")
        except Exception as e: 
            if not self.shutdown_flag.is_set(): self.after(0, self.log_error, f"Receiver error from {ip}: {e}")
        finally: conn.close()

    def handle_file_drop(self, event):
        files = self.tk.splitlist(event.data)
        if not files: return
        if len(files) == 1: self.trigger_transfer(files[0])
        else:
            self.log(f"Zipping {len(files)} files for transfer...")
            threading.Thread(target=self._zip_and_transfer_multiple, args=(files,), daemon=True).start()

    def select_file(self):
        paths = filedialog.askopenfilenames()
        if not paths:
            path = filedialog.askdirectory()
            if path: self.trigger_transfer(path)
            return
        if len(paths) == 1: self.trigger_transfer(paths[0])
        else:
            self.log(f"Zipping {len(paths)} files for transfer...")
            threading.Thread(target=self._zip_and_transfer_multiple, args=(paths,), daemon=True).start()

    def _zip_and_transfer_multiple(self, files):
        tip, tpin = self.ip_entry.get().strip(), self.pin_entry.get().strip()
        if not tip or not tpin:
            self.after(0, self.log, "Error: Check IP and Token")
            return
        temp_dir = tempfile.mkdtemp()
        try:
            for f in files:
                if os.path.isfile(f): shutil.copy2(f, temp_dir)
                elif os.path.isdir(f): shutil.copytree(f, os.path.join(temp_dir, os.path.basename(f)))
            temp_zip = os.path.join(tempfile.gettempdir(), f"batch_transfer_{secrets.token_hex(4)}")
            send_path = shutil.make_archive(temp_zip, 'zip', temp_dir)
            self.send_logic(send_path, tip, tpin, is_batch=True)
        except Exception as e: self.after(0, self.log, f"Error packing files: {e}")
        finally: shutil.rmtree(temp_dir, ignore_errors=True)

    def trigger_transfer(self, file_path):
        tip, tpin = self.ip_entry.get().strip(), self.pin_entry.get().strip()
        if not tip or not tpin:
            self.log("Error: Check IP and Token")
            return
        threading.Thread(target=self.send_logic, args=(file_path, tip, tpin), daemon=True).start()

    def send_logic(self, file_path, target_ip, target_pin, is_batch=False):
        self.cancel_transfer_flag.clear()
        self.after(0, lambda: self.cancel_btn.configure(state="normal"))
        
        is_f = "1" if is_batch else "0"
        orig = "batch_transfer.zip" if is_batch else os.path.basename(file_path)
        send_path = file_path
        
        if os.path.isdir(file_path) and not is_batch:
            self.after(0, self.log, "Zipping folder...")
            temp_name = os.path.join(tempfile.gettempdir(), f"transfer_{secrets.token_hex(4)}")
            send_path = shutil.make_archive(temp_name, 'zip', file_path)
            is_f = "1"

        try:
            f_size, f_hash = os.path.getsize(send_path), self.calculate_hash(send_path)
            client = socket.socket()
            client.settimeout(SOCKET_TIMEOUT)
            self.after(0, self.log_info, f"Connecting to {target_ip}:{TCP_PORT}...")
            client.connect((target_ip, TCP_PORT))
            
            salt = client.recv(16)
            kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480000)
            key = kdf.derive(target_pin.encode())
            
            my_auth = hmac.new(key, b"AUTH_CHALLENGE", hashlib.sha256).digest()
            client.sendall(my_auth)
            auth_resp = client.recv(1024)
            if auth_resp == b"AUTH_FAIL":
                self.after(0, self.log_error, "Authentication failed: incorrect token.")
                client.close()
                return
            elif auth_resp != b"AUTH_OK":
                self.after(0, self.log_error, f"Unexpected auth response from target: {auth_resp!r}")
                return 

            name_to_send = orig if is_f == "0" else (orig if orig.endswith(".zip") else orig + ".zip")
            client.sendall(f"{name_to_send}|{f_size}|{f_hash}|{is_f}|{self.my_hostname}".encode())
            
            resp = client.recv(1024).decode().split("|")
            action = resp[0]
            if action == "REJECT":
                reason = resp[1] if len(resp) > 1 else "UNKNOWN"
                reason_map = {
                    "DECLINED": "recipient declined",
                    "LOCKED": "recipient is temporarily locked after failed token attempts",
                    "META": "recipient rejected malformed metadata",
                }
                self.after(0, self.log_warn, f"Transfer rejected by target: {reason_map.get(reason, reason)}.")
                return
            if action not in ("START", "RESUME"):
                self.after(0, self.log_error, f"Unexpected transfer response: {resp}")
                return
                
            offset = int(resp[1]) if action == "RESUME" else 0
            
            nonce = os.urandom(16)
            client.sendall(nonce)

            enc = Cipher(algorithms.AES(key), modes.CTR(nonce)).encryptor()
            stream_mac = hmac.new(key, digestmod=hashlib.sha256)

            self.after(0, self.log_info, f"Sending '{name_to_send}' to {target_ip} (starting at {offset/1e6:.1f} MB)...")
            with open(send_path, "rb") as f:
                f.seek(offset)
                sent, start = offset, time.time()
                while chunk := f.read(8192):
                    if self.cancel_transfer_flag.is_set() or self.shutdown_flag.is_set():
                        self.after(0, self.log_warn, "Transfer paused by user.")
                        break
                        
                    enc_chunk = enc.update(chunk)
                    stream_mac.update(enc_chunk)
                    client.sendall(enc_chunk)
                    
                    sent += len(chunk)
                    elapsed = max(0.1, time.time() - start)
                    pct = sent / f_size if f_size > 0 else 1
                    speed = ((sent - offset) / 1e6) / elapsed
                    self.after(0, self.update_ui_progress, pct, f"Speed: {speed:.2f} MB/s")

                if not self.cancel_transfer_flag.is_set() and not self.shutdown_flag.is_set():
                    final_chunk = enc.finalize()
                    if final_chunk:
                        stream_mac.update(final_chunk)
                        client.sendall(final_chunk)
                    client.sendall(stream_mac.digest())
                    
                    try:
                        ack = self.recv_exact(client, 4)
                        if ack == b"DONE":
                            self.after(0, self.log_info, "Sender confirmed delivery and integrity check passed.")
                        else:
                            self.after(0, self.log_warn, f"Transfer sent but ACK was unexpected: {ack!r}")
                    except socket.timeout:
                        self.after(0, self.log_warn, "Transfer sent but no ACK received before timeout.")

        except socket.timeout:
            if not self.shutdown_flag.is_set():
                self.after(0, self.log_warn, f"Connection to {target_ip} timed out.")
        except Exception as e: 
            if not self.shutdown_flag.is_set(): self.after(0, self.log_error, f"Sender failed: {e}")
        finally:
            if 'client' in locals():
                client.close()
            self.after(0, self.update_ui_progress, 0, "Speed: 0.00 MB/s")
            self.after(0, lambda: self.cancel_btn.configure(state="disabled"))
            if is_f == "1" and os.path.exists(send_path):
                os.remove(send_path)

if __name__ == "__main__":
    app = MyFileSharingApp()
    app.mainloop()