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

## Run on your phone (same Wi-Fi network)

Start the server bound to all interfaces:

```bash
uv run uvicorn imageblinds.server:app --host 0.0.0.0 --port 8000
```

Find the machine's LAN IP (`hostname -I`) and browse `http://<IP>:8000` from the phone.
This is enough for the web page and voice output, but **installing the app as a PWA on the
phone requires HTTPS** — continue with the next section.

## HTTPS + install as an app (PWA) on the phone

1. Generate a local CA and a server certificate (only once):

   ```bash
   openssl req -x509 -newkey rsa:2048 -nodes -keyout certs/ca.key -out certs/ca.crt -days 3650 \
     -subj "/CN=ImageBlinds Local CA" \
     -addext "basicConstraints=critical,CA:TRUE" \
     -addext "keyUsage=critical,keyCertSign,cRLSign"
   IP=$(hostname -I | awk '{print $1}')
   openssl req -newkey rsa:2048 -nodes -keyout certs/server.key -out certs/server.csr \
     -subj "/CN=$IP"
   printf "subjectAltName=IP:%s,DNS:localhost\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nbasicConstraints=CA:FALSE\n" "$IP" > certs/san.ext
   openssl x509 -req -in certs/server.csr -CA certs/ca.crt -CAkey certs/ca.key -CAcreateserial \
     -out certs/server.crt -days 825 -extfile certs/san.ext
   cat certs/server.crt certs/ca.crt > certs/fullchain.pem
   ```

   (`certs/` is gitignored — the keys never leave this machine. The cert is bound to the
   current LAN IP; regenerate the server cert if the IP changes.)

2. Install the CA on the phone once:
   - Download `ca.crt`: start the server and open `http://<IP>:8000/ca.crt`, or copy the
     file by any means.
   - Android: Settings → Security → More/Encryption & credentials → Install a certificate →
     CA certificate → pick `ca.crt`.

3. Run with HTTPS:

   ```bash
   uv run uvicorn imageblinds.server:app --host 0.0.0.0 --port 8000 \
     --ssl-certfile certs/fullchain.pem --ssl-keyfile certs/server.key
   ```

4. On the phone open `https://<IP>:8000`, then Chrome menu → **Add to Home screen** /
   **Install app**. The app launches full-screen with its own icon; analysis results are
   still spoken aloud.

## Tests (offline, no model calls)

```bash
uv run pytest -q
uv run ruff check .
```
