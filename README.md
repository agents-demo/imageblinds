# ImageBlinds

A small JS GUI: pick a `.jpg` photo, send it to an
[openjiuwen agent-core](https://github.com/openJiuwen-ai/agent-core) vision agent, and show
(and read aloud) the model's textual description of the image. Modeled after
[taketwo](https://github.com/agents-demo/taketwo) (multimodal `DeepAgent` reading images via
`read_file` with `enable_read_image_multimodal=True`).

## Setup

```bash
uv sync                      # installs deps incl. openjiuwen from git
cp .env.example .env         # then fill in API_BASE / API_KEY / VISION_MODEL_NAME
```

Requires Python 3.11–3.13.

## Run (localhost only)

```bash
uv run uvicorn imageblinds.server:app --reload
```

Open http://localhost:8000 — pick `chair.jpg` / `fridge.jpg` (or any JPG), press **Analyze**.
The result is shown and spoken aloud (Web Speech API; "Read aloud" repeats it).

## Phone + PWA install (one-time preparation)

The phone needs HTTPS with a **certificate it trusts** to install the app as a PWA
(Chrome refuses downloads and `fetch()` on untrusted pages, so the trust step is mandatory).

### 1. Generate the certificate (once)

```bash
mkdir -p certs
IP=<address the phone will reach>   # e.g. the machine's Wi-Fi IP; see the WSL note below
openssl req -x509 -newkey rsa:2048 -nodes -keyout certs/local.key -out certs/local.crt -days 825 \
  -subj "/CN=ImageBlinds" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign,digitalSignature,keyEncipherment" \
  -addext "extendedKeyUsage=serverAuth" \
  -addext "subjectAltName=IP:$IP,DNS:localhost"
```

- `certs/` is gitignored — the key never leaves this machine.
- The certificate doubles as the trust anchor, so it is the only file the phone installs.
- If the machine's IP changes, regenerate it with the new IP (and re-install on the phone).

**WSL note:** WSL2 is NAT'd, so the phone cannot reach the WSL IP. Forward the ports on
Windows once (an admin PowerShell):

```powershell
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=8000 connectaddress=<WSL-IP> connectport=8000
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=8080 connectaddress=<WSL-IP> connectport=8080
netsh advfirewall firewall add rule name=ImageBlinds dir=in action=allow protocol=TCP localport=8000
netsh advfirewall firewall add rule name=ImageBlindsHTTP dir=in action=allow protocol=TCP localport=8080
```

Then use the **Windows** Wi-Fi IP (`ipconfig` → `Wi-Fi ... IPv4 Address`) as `IP` above and
as the phone's address. Re-run the portproxy commands after WSL restarts (the WSL IP changes).

### 2. Install the certificate on the phone (once)

Get the file onto the phone — either way works:

- **USB**: copy `certs/local.crt` to the phone's Downloads folder via cable.
- **Download**: start the server (step 3) and open the plain-HTTP mirror
  `http://<IP>:8080/ca.crt` in the phone browser (no certificate warning there). The app page
  on port 8080 also shows a banner with this download link.

On Android (Samsung): Settings → **Biometrics and security → Other security settings →
Install from device storage → CA certificate** → pick the file. Verify it appears under
**View security certificates → User** tab ("ImageBlinds"). Then **fully close Chrome**
(recents → swipe away) and reopen it.

### 3. Start the servers (every run)

```bash
# HTTPS app server (PWA + phone)
uv run uvicorn imageblinds.server:app --host 0.0.0.0 --port 8000 \
  --ssl-certfile certs/local.crt --ssl-keyfile certs/local.key

# plain-HTTP mirror (certificate download + non-PWA access)
uv run uvicorn imageblinds.server:app --host 0.0.0.0 --port 8080
```

### 4. Install the app on the phone

Open `https://<IP>:8000` (with `https://`), verify the padlock is secure, then Chrome menu →
**Add to Home screen** / **Install app**. The app launches full-screen with its own icon;
analysis results are still spoken aloud.

## Run on your phone (same Wi-Fi network)

Start the server bound to all interfaces:

```bash
uv run uvicorn imageblinds.server:app --host 0.0.0.0 --port 8000
```

Find the machine's LAN IP (`hostname -I`) and browse `http://<IP>:8000` from the phone.
This is enough for the web page and voice output, but **installing the app as a PWA on the
phone requires HTTPS** — see the section above.

## Tests (offline, no model calls)

```bash
uv run pytest -q
uv run ruff check .
```
