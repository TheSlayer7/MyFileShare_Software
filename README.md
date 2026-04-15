# MyFileSharingSoftware

A peer-to-peer file transfer application for local area networks (LANs) using AES-256-CTR encryption and token-based authentication. This implementation serves as a case study in practical cryptography, network socket programming, and secure data transfer protocols.

---

## Overview

MyFileSharingSoftware enables direct file transfers between computers on the same LAN using an encrypted, authenticated protocol. No cloud storage, no central server, no internet connectivity required. The application automatically discovers peers on the network via UDP broadcast and establishes encrypted transfer sessions over TCP.

**Key Design Goals:**
- Zero-trust network model: encryption and authentication are mandatory
- Token-based user interaction: simple 6-character PIN replaces complex PKI
- Stateless key derivation: identical keys derived independently at sender and receiver
- Stream authentication: HMAC-SHA256 verifies encrypted data before finalization
- Pause/resume capability: partial transfers can be resumed without re-sending complete files

---

## Network Architecture

### Device Discovery (UDP Broadcast)

The application implements automatic peer discovery using UDP broadcast on port 49495:

1. **Broadcast Phase**: Each instance periodically broadcasts a heartbeat packet containing `FILE_SERVER_HERE|<hostname>` to the network broadcast address.
2. **Reception Phase**: All instances listen on the broadcast address and record the IP and arrival timestamp of any peer discovered.
3. **Staleness Pruning**: Peers that haven't sent a heartbeat in 120 seconds are automatically removed from the discovery list.

**Technical Details:**
- Broadcast address: `<broadcast>` (platform-specific; typically `255.255.255.255` or `/31` subnet broadcast)
- Port: UDP 49495
- Interval: 2-second heartbeat
- TTL (Time-To-Live): System default (typically 1 for local broadcasts)

This is a simple but effective mechanism because:
- No multicast group membership required
- Works on most corporate networks that allow broadcast
- Provides natural peer discovery without manual IP entry
- Token-based auth prevents unauthorized connections despite broadcast exposure

### File Transfer (TCP Stream)

File transfers occur over TCP port 49494 using a request-response protocol:

1. **Connection**: Sender initiates TCP connection to receiver's IP:49494.
2. **Authentication Handshake**: 
   - Receiver generates random 16-byte salt and sends it to sender
   - Both sides independently derive AES-256 key from token + salt using PBKDF2
   - Sender sends HMAC-SHA256(key, "AUTH_CHALLENGE") to prove token knowledge
   - Receiver validates; sends `AUTH_OK` or `AUTH_FAIL`
3. **Metadata Exchange**: Sender transmits file metadata (name, size, hash, flags).
4. **Transfer Negotiation**: 
   - Receiver asks user for approval (new transfer) or resume confirmation (partial file exists)
   - If approved, receiver sends `START|0` or `RESUME|<offset>`
5. **Encrypted Stream**: Sender streams encrypted file data in 8192-byte chunks.
6. **Integrity Verification**: 
   - Receiver computes HMAC-SHA256 over all ciphertext bytes
   - After stream ends, sender transmits final MAC
   - Receiver compares; sends `DONE` if match, `FAIL` if mismatch
7. **Post-Transfer**: Receiver verifies SHA-256 hash of decrypted data against declared hash.

**Connection Management:**
- Socket timeout: 20 seconds for both sender and receiver
- Graceful degradation: timeouts log warnings and close connection
- Retry semantics: application layer retry on user demand (resume)

### Protocol Error Handling

Failed authentication results in graduated response:
- **Attempt 1-2**: Log warning, close connection
- **Attempt 3+**: Lock IP for 60 seconds, reject all future connection attempts during lockout

Malformed metadata (invalid size, hash length, or field count) triggers immediate rejection with `REJECT|META` code.

---

## Cryptographic Architecture

### Encryption: AES-256-CTR

**Algorithm**: AES (Advanced Encryption Standard) in CTR (Counter) mode with 256-bit key

**Why CTR mode?**
- Stream cipher semantics: encrypt arbitrary-length data without padding
- Parallelizable: blocks can theoretically be encrypted out-of-order
- No IV reuse: nonce must be unique per message (enforced by random generation)

**Implementation:**
- Key size: 256 bits (32 bytes)
- Nonce size: 128 bits (16 bytes), generated fresh for each transfer
- Block size: 128 bits (16 bytes AES native)
- Chunk size: 8192 bytes (application layer for progress tracking)

### Key Derivation: PBKDF2-SHA256

**Process**:
```
1. Receiver generates salt = 16 random bytes
2. Sender and Receiver independently compute:
   key = PBKDF2(
     password = <6-char token>.encode(),
     salt = salt,
     iterations = 480,000,
     hash_function = SHA256,
     dklen = 32 (bytes)
   )
3. Both sides use identical key for AES and HMAC operations
```

**Rationale:**
- 480,000 iterations achieves ~100ms key derivation on modern hardware, making brute-force attacks computationally infeasible
- PBKDF2 is standardized (NIST Special Publication 800-132) and conservative
- Token is never transmitted; both sides derive the same key independently
- Salt is transmitted with nonce, providing per-transfer uniqueness

### Stream Authentication: HMAC-SHA256

After all file data is encrypted and transmitted, sender computes and transmits:
```
mac = HMAC-SHA256(key, <all ciphertext bytes>)
```

Receiver independently computes the same value by processing all received ciphertext bytes through HMAC-SHA256. If mismatch: transfer is rejected and partial file is deleted.

**Security Properties:**
- Detects both accidental corruption and deliberate tampering
- Computed over encrypted data, not plaintext (ensures attacker cannot modify encrypted stream undetected)
- Requires knowledge of key (which requires knowledge of token)

### Integrity Verification: SHA-256

Final verification: receiver computes SHA-256 hash of entire decrypted file and compares against hash declared in metadata. This provides:
- Detection of decryption errors (e.g., wrong nonce used)
- Detection of incomplete transfers or truncated data
- Metadata-declared hash serves as "expected value" for trust based on pre-transfer communication

---

## Protocol Details: Message Sequence

### Authentication Handshake

```
1. Sender -> Receiver: [TCP SYN]
2. Receiver -> Sender: 16 random bytes (salt)
3. Sender computes: key = PBKDF2(token, salt, 480k, SHA256, 32)
4. Sender computes: auth = HMAC(key, "AUTH_CHALLENGE")
5. Sender -> Receiver: auth (32 bytes)
6. Receiver computes: key = PBKDF2(token, salt, 480k, SHA256, 32)
7. Receiver computes: expected_auth = HMAC(key, "AUTH_CHALLENGE")
8. Receiver verifies: auth == expected_auth
9. Receiver -> Sender: b"AUTH_OK" or b"AUTH_FAIL"
   - If AUTH_FAIL: increment failed attempt counter for IP
   - If 3+ failures within 60 sec: lock IP for 60 sec
```

### Metadata Exchange (Post-Auth)

```
1. Sender -> Receiver: "<filename>|<filesize>|<sha256_hash>|<is_folder>|<hostname>"
   - filename: UTF-8 string (original or renamed for batch transfers)
   - filesize: decimal string (bytes)
   - sha256_hash: hex string (64 characters)
   - is_folder: "0" (file) or "1" (zipped folder)
   - hostname: UTF-8 string (sender's system hostname)
2. Receiver -> Sender: "START|0" or "RESUME|<offset>"
   - START: begin transfer from byte 0
   - RESUME: start from byte <offset> (partial file exists and user approved resume)
```

### Encrypted Transfer

```
1. Sender generates: nonce = 16 random bytes
2. Sender -> Receiver: nonce (16 bytes)
3. Sender and Receiver initialize:
   - encryptor = AES-CTR(key, nonce)
   - stream_mac = HMAC(key)
4. Sender reads file in 8192-byte chunks:
   For each chunk:
     a. encrypted_chunk = encryptor.update(chunk)
     b. stream_mac.update(encrypted_chunk)
     c. Sender -> Receiver: encrypted_chunk
5. Sender finalizes encryption:
   a. final = encryptor.finalize()
   b. stream_mac.update(final)
   c. Sender -> Receiver: final (may be empty or up to 15 bytes of padding)
6. Sender computes final MAC:
   a. mac = stream_mac.digest()
   b. Sender -> Receiver: mac (32 bytes, HMAC output)
```

### Verification & Completion

```
1. Receiver computes:
   a. final_mac = stream_mac.digest()
   b. Verify: final_mac == received_mac
2. If MAC mismatch:
   Receiver -> Sender: b"FAIL"
   Receiver deletes partial file
   Transfer ABORTED
3. If MAC match:
   Receiver decrypts all data into file
   Receiver computes SHA256 of decrypted file
   Receiver compares against declared hash
4. If hash match:
   Receiver -> Sender: b"DONE"
   Rename partial file to final name
   Transfer COMPLETE
5. If hash mismatch:
   Receiver -> Sender: b"FAIL"
   Receiver deletes file
   Transfer ABORTED
```

---

## Session State and Pause/Resume

### Pause Semantics

When sender clicks "Pause":
- pause_transfer_flag is set
- File read loop detects flag and breaks early
- Finalization block detects pause and does NOT send MAC
- Receiver does not send ACK; remains waiting for MAC bytes
- Partial file remains saved on receiver disk with `.part` suffix keyed by file hash

Next transfer attempt:
- Receiver detects partial `.part` file exists
- Receiver prompts user: "Resume transfer?" with current progress
- If user accepts: sends `RESUME|<current_size>`
- Sender seeks to offset and continues reading/encrypting from that point
- If user declines: partial file deleted, new transfer starts from byte 0

### Cancel Semantics

When sender clicks "Cancel":
- cancel_transfer_flag is set
- File read loop breaks early
- Finalization block detects cancel and does NOT send MAC
- Batch zip file (if any) is deleted from temp directory
- Receiver partial file is NOT cleaned up by sender (receiver manages with timeout pruning or manual delete)

---

## Installation & Execution

### Prerequisites

- Python 3.10 or newer
- pip or uv package manager
- For Linux: tkdnd library (`sudo apt install tkdnd` on Debian/Ubuntu)

### Install with uv (Recommended)

```bash
uv venv
uv pip install -r requirements.txt
uv run main.py
```

### Install with Traditional venv

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

**macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

The application starts in Dark mode by default. Theme can be changed via the segmented button at the top of the window.

---

## Usage

### Receiving Files

1. Launch the application. Your device's IP address and a random 6-character token appear at the top.
2. Share IP and token with sender via out-of-band channel (chat, email, verbally, etc.).
3. When sender initiates transfer, a dialog appears asking to accept or decline.
4. If accepted, transfer progress appears in the log with real-time speed.
5. On completion, file appears in `~/Downloads/MyFileSharing/` (or custom save directory).

### Sending Files

1. Select target IP (discovered via UDP broadcast or manually entered).
2. Enter recipient's 6-character token (from their screen).
3. Drag file/folder into drop zone or click "Select File(s) Manually".
4. Wait for recipient to accept.
5. Monitor progress in log; use Pause to suspend (resume at recipient prompt) or Cancel to abort.

### Batch Operations

Multiple files/folders can be selected. The application automatically zips them into a single encrypted file, transfers the archive, and unpacks on the receiving end. Original folder structure is preserved.

---

## Troubleshooting

### Transfer Timeouts or Failures

**Symptom**: Connection hangs or times out at 20 seconds.

**Causes**:
- Network latency or packet loss on compromised Wi-Fi
- Firewall rules blocking TCP 49494 or UDP 49495
- NAT/Port forwarding not configured (if devices are on different subnets)

**Solution**:
- Verify both devices are on same LAN (ping target device)
- Check firewall: `ufw allow 49494/tcp` and `ufw allow 49495/udp` on Linux
- If using corporate network, request IT to unblock ports or test on personal hotspot

### Authentication Failures

**Symptom**: Repeated "Auth failed from X.X.X.X" (3 attempts) followed by temporary lockout.

**Causes**:
- Incorrect 6-character token entered on sender side
- Token changed between sender launching and metadata arriving
- Token miscopied or sender/receiver out of sync

**Solution**:
- Verify token on receiver screen (exact match, case-sensitive)
- Have receiver generate new token by restarting application
- Sender re-enters new token in UI before initiating transfer

### Stream MAC Mismatch

**Symptom**: Transfer data streamed successfully but receiver reports "SECURITY ALERT: Stream MAC mismatch."

**Causes**:
- Bit flip or corruption in encrypted bytes during transmission (rare over TCP)
- Implementation bug in encryptor/decryptor (AES-256-CTR mode)
- Attacker modified encrypted stream in-transit (active network attack)

**Solution**:
- Retry transfer (TCP should detect and retry lost packets; issue is application layer)
- Ensure network is not under active attack (check for man-in-the-middle)
- If problem persists, log a bug with network capture (tcpdump)

### Sender/Receiver Both Require Human Approval

**Symptom**: Device is locked behind firewall; has no inbound connectivity.

**Explanation**: 
UDP broadcast reaches sender, but TCP connection from sender to receiver cannot be established inbound on receiver's WAN interface. This is expected behavior on most corporate networks.

**Solution**:
- Test on same building's Wi-Fi, not split across WAN
- Use personal hotspot for testing across buildings
- AP isolation or aggressive filtering is active; request network exemption

---

## Security Considerations

**Design Scope**: LAN-only; single token shared between participants; no multi-party confidentiality.

**Threat Model:**
- **Passive Eavesdropping**: Mitigated by AES-256-CTR encryption
- **Active Tampering**: Mitigated by HMAC-SHA256 stream authentication
- **Replay Attacks**: Each transfer uses fresh nonce; same token with different nonce/salt produces different ciphertext
- **Brute Force**: 6-character token (47 billion combinations) + 480k PBKDF2 iterations makes dictionary attack infeasible
- **Token Interception**: Token never transmitted; derived independently at both ends
- **Decryption Error**: Final SHA-256 hash detects garbled plaintext post-decryption

**Not Mitigated:**
- If token is compromised (shared with attacker), all transfers are at risk
- If network is physically compromised (attacker on same LAN), attacker can perform man-in-the-middle on UDP discovery
- No perfect forward secrecy: compromise of a single token retroactively exposes all past transfers on that token instance

---

## Dependencies

| Library | Purpose | License |
|---------|---------|---------|
| customtkinter | GUI framework with modern styling | [MIT](https://spdx.org/licenses/MIT.html) |
| tkinterdnd2 | Drag-and-drop file support | [MIT](https://spdx.org/licenses/MIT.html) |
| cryptography (PyCA) | AES-256-CTR, PBKDF2, SHA-256, HMAC | [Apache-2.0](https://spdx.org/licenses/Apache-2.0.html) / [BSD-3-Clause](https://spdx.org/licenses/BSD-3-Clause.html) |
| pystray | System tray integration | [LGPL-3.0-only](https://spdx.org/licenses/LGPL-3.0-only.html) |
| plyer | Cross-platform notifications | [MIT](https://spdx.org/licenses/MIT.html) |
| Pillow | Image rendering for tray icon | [HPND](https://spdx.org/licenses/HPND.html) |

All dependencies are permissive open-source licenses compatible with MIT.

For third-party license compliance details (including full Apache-2.0 and BSD-3-Clause text for `cryptography`), see [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

---

## Design Notes

**Why PBKDF2 over bcrypt/Argon2?**
PBKDF2 is NIST-standardized and conservative. Bcrypt/Argon2 are stronger but more modern; PBKDF2 with 480k iterations provides adequate security for LAN trust model.

**Why AES-CTR over GCM?**
GCM provides authenticated encryption (AEAD), eliminating separate HMAC step. CTR + HMAC is by necessity in current implementation but separates encryption from authentication semantics for clarity. GCM would be more efficient (single pass over data).

**Why only 6-character token?**
User memorability and verbal/SMS communication. 6 alphanumeric characters = ~47 billion combinations. With 480k PBKDF2 iterations, dictionary attack takes >10 seconds per attempt on modern hardware; with account lockout, infeasible. Not suitable for internet/untrusted networks.

**Why UDP broadcast for discovery?**
Multicast would be more efficient but requires group subscription. Broadcast works on most corporate networks that block multicast. Stateless and no special socket options required.

**Why partial file resume?**
Large files (>1 GB) are common. Transient network issues are common. Resume-from-offset is essential UX for real-world deployments.

---

## License

MIT License. See [LICENSE](LICENSE) for full text.

Third-party dependency license notices are included in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

---

## Disclaimer

This is an educational project exploring socket programming, cryptography, and GUI design in Python. It has not undergone professional security audit. Do not use for sensitive data in untrusted environments. For enterprise secure file transfer, use audited solutions (e.g., rsync over SSH, commercial MFT appliances).
