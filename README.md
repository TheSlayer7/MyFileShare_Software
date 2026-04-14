# 📁 MyFileSharingSoftware

> ⚠️ **Educational Project** — Built as a fun learning exercise to understand how secure file transfer, encryption, and local area networking work under the hood. Not intended for production use.

A lightweight, encrypted peer-to-peer LAN file sharing desktop app built in Python. Transfer files and folders between devices on the same network using AES-256 encryption — no internet connection, no third-party servers, no cloud.

---

## 🎯 What This Project Explores

- How **TCP sockets** work for reliable data transfer between two machines
- How **UDP broadcasting** enables automatic device discovery on a local network
- How **AES-256-CTR encryption** works when applied to a real data stream
- How **PBKDF2 key derivation** turns a short token into a strong cryptographic key
- How **SHA-256 hashing** verifies file integrity after a transfer completes
- How **multithreading** keeps a GUI responsive during long-running operations
- How to build a **system tray application** in Python

---

## ✨ Features

- 🔒 **AES-256-CTR encryption** — all file data is encrypted before leaving your machine
- 🔑 **PBKDF2 key derivation** — the session token is never sent over the network
- ✅ **SHA-256 integrity verification** — detects corruption or tampering post-transfer
- 🧪 **Stream MAC verification** — encrypted stream is authenticated before finalizing a transfer
- 📡 **UDP device discovery** — automatically scan your LAN to find other users
- 📂 **Folder support** — folders are zipped, sent encrypted, and unpacked on arrival
- 🖱️ **Drag & Drop** — drag files directly into the app window
- 🔔 **System tray** — minimize to tray and keep listening for incoming files
- 🌗 **Dark / Light / System theme** — switchable at any time
- 🎨 **Improved Light mode contrast** — cleaner cards, better text contrast, and clearer token display
- 📊 **Live progress & speed meter** — real-time transfer speed displayed in MB/s
- 🧾 **Clear transfer logs** — `[INFO]`, `[WARN]`, and `[ERROR]` entries with actionable messages

---

## 🚀 Getting Started

### Prerequisites

Make sure you have the following installed before continuing:

- **Python 3.10 or newer** — [Download here](https://www.python.org/downloads/)
- **pip** (comes bundled with Python)
- **Git** — [Download here](https://git-scm.com/downloads)

---

### Step 1 — Clone the repository

Open a terminal or command prompt and run:

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
cd YOUR_REPO_NAME
```

---

### Step 2 — Create a virtual environment (Recommended)

A virtual environment keeps this project's dependencies isolated from your system Python installation and prevents version conflicts.

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

You should see `(venv)` appear at the start of your terminal prompt confirming it is active.

---

### Step 3 — Install dependencies

```bash
pip install customtkinter tkinterdnd2 cryptography pystray Pillow plyer
```

Or install from the requirements file:

```bash
pip install -r requirements.txt
```

---

### Step 4 — Run the app

**Windows:**
```bash
python main.py
```

**macOS / Linux:**
```bash
python3 main.py
```

> 💡 **Tip:** Launch the app on **two devices connected to the same Wi-Fi or LAN network** to transfer files between them. It will not work over the internet.

---

## 📖 Usage Guide

### 📥 Receiving a File

1. Launch the app. Your **IP Address** and a secure **6-Character Token** will be displayed in the top panel.
2. Share your **IP address** and **Token** with the person who wants to send you a file.
3. When they initiate a transfer, a popup will appear asking if you want to accept — click **Yes**.
4. Once completed, click **Open Received Folder** at the bottom to view your received file.

---

### 📤 Sending a File

1. Make sure the receiving device has the app open and is on the **same Wi-Fi or local network**.
2. Under the **SEND TO ANOTHER DEVICE** section:
   - Select a discovered or saved receiver IP address, or type one manually.
   - Enter the receiver's **6-Character Token** — ask them to read it off their screen.
3. **Drag and drop** a file or folder into the drop zone, or click **Select File/Folder Manually**.
4. The transfer will begin automatically as soon as the receiver accepts the prompt.

---

## 🧭 Logging and Status Messages

The app now logs transfer state with explicit severity markers:

- `[INFO]` for normal connection/progress/completion updates
- `[WARN]` for recoverable issues (timeouts, pause, user reject, temporary lockouts)
- `[ERROR]` for integrity or protocol failures (auth failure, malformed response, hash mismatch)

Common reject reasons now include details, for example:

- recipient declined the transfer
- recipient temporarily locked after multiple failed token attempts
- recipient rejected malformed metadata

---

## 🔐 How the Encryption Works

```
[Receiver]  Generates a random 16-byte salt → sends it to sender
[Both]      Independently derive AES-256 key using PBKDF2(token + salt, 480,000 iterations)
[Sender]    Encrypts file in 8192-byte chunks using AES-256-CTR with a random nonce
[Network]   Only encrypted bytes travel over TCP — unreadable to any interceptor
[Receiver]  Decrypts the stream, then verifies SHA-256 hash matches the original
```

The **session token is never transmitted over the network**. Both sides independently arrive at the same AES-256 key — this is what makes the transfer secure. Anyone intercepting the traffic would only see an encrypted data stream and a salt, which are completely useless without the token.

---

## ⚠️ Troubleshooting & Limitations

### 🚨 "Stream MAC mismatch" / Security Alert
This means the encrypted stream integrity check failed, and the receiver intentionally dropped the transfer.

Try the following:
- Retry the transfer once (temporary network interruptions can break a stream)
- Ensure both devices are running the latest version of this app
- Verify the receiver token is correct
- Avoid unstable or heavily filtered networks

### 🔥 Firewall Prompts
The first time you run this app, **Windows Defender** or your OS firewall may ask for network permissions. You **must allow access on private networks** for the app to send and receive files.

### 🌐 Slow Speeds or Connection Failures on Public / University Wi-Fi
Many enterprise or university networks use **AP Isolation (Client Isolation)** and aggressive P2P throttling. If you cannot connect or experience very slow speeds, your network is actively blocking direct LAN communication.

> **Fix:** Enable your phone's or computer's **Mobile Hotspot** and connect both devices to it. You don't need active cellular data — it simply creates a clean, unthrottled local network for the app to work on.

### 🐧 Linux — tkinterdnd2 Issues
On some Linux distributions, `tkinterdnd2` may require `tkdnd` to be installed separately:
```bash
sudo apt install tkdnd
```

---

## 🛡️ Security Note

This tool is designed for convenience on **trusted local networks**. Transfers are encrypted with AES-256, however this project has **not** been professionally audited. Do not use it as a replacement for enterprise-grade secure file transfer solutions, and avoid using it on untrusted or public networks.

---

## 📦 Dependencies & Licenses

| Library | Version | License | Repository |
|---|---|---|---|
| [customtkinter](https://github.com/TomSchimansky/CustomTkinter) | ≥ 5.2.0 | [MIT](https://github.com/TomSchimansky/CustomTkinter/blob/master/LICENSE) | [GitHub](https://github.com/TomSchimansky/CustomTkinter) |
| [tkinterdnd2](https://github.com/pmgagne/tkinterdnd2) | ≥ 0.3.0 | [MIT](https://github.com/pmgagne/tkinterdnd2/blob/master/LICENSE) | [GitHub](https://github.com/pmgagne/tkinterdnd2) |
| [cryptography](https://cryptography.io) | ≥ 41.0.0 | [Apache 2.0 / BSD](https://github.com/pyca/cryptography/blob/main/LICENSE) | [GitHub](https://github.com/pyca/cryptography) |
| [pystray](https://github.com/moses-palmer/pystray) | ≥ 0.19.0 | [LGPLv3](https://www.gnu.org/licenses/gpl-3.0.en.html) | [GitHub](https://github.com/moses-palmer/pystray) |
| [plyer](https://github.com/kivy/plyer) | ≥ 2.1.0 | [MIT](https://github.com/kivy/plyer/blob/master/LICENSE) | [GitHub](https://github.com/kivy/plyer) |
| [Pillow](https://python-pillow.org/) | ≥ 10.0.0 | [HPND](https://github.com/python-pillow/Pillow/blob/main/LICENSE) | [GitHub](https://github.com/python-pillow/Pillow) |

### License Notes

- **pystray** is licensed under [LGPLv3](https://www.gnu.org/licenses/lgpl-3.0.html). It is used here as an unmodified library import, which is fully permitted under the LGPL terms.
- **Pillow** uses the [HPND License](https://github.com/python-pillow/Pillow/blob/main/LICENSE) — one of the oldest and most permissive open source licenses available, predating even MIT.
- **cryptography** uses [Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0) for most components and [BSD-3-Clause](https://opensource.org/licenses/BSD-3-Clause) for others — both fully permissive.
- All other dependencies are under the [MIT License](https://opensource.org/licenses/MIT).

---

## 🙏 Credits & Attributions

- **AES-256 encryption** — implemented via the [cryptography](https://cryptography.io) library by the [Python Cryptographic Authority (PyCA)](https://github.com/pyca)
- **GUI framework** — [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) by [Tom Schimansky](https://github.com/TomSchimansky)
- **Drag & Drop support** — [tkinterdnd2](https://github.com/pmgagne/tkinterdnd2) by [Pierre-Marie Gagne](https://github.com/pmgagne)
- **System tray support** — [pystray](https://github.com/moses-palmer/pystray) by [Moses Palmér](https://github.com/moses-palmer)
- **Desktop notifications** — [plyer](https://github.com/kivy/plyer) by the [Kivy team](https://github.com/kivy)
- **Image handling** — [Pillow](https://python-pillow.org/) by [Alex Clark and contributors](https://github.com/python-pillow/Pillow/graphs/contributors), originally by Fredrik Lundh

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for full details.

---

## ❗ Disclaimer

This is a personal educational project built to explore socket programming, cryptography, and GUI development in Python. It has **not** been audited for security and is **not** recommended for transferring sensitive data in real-world or untrusted environments. Use on trusted local networks only.