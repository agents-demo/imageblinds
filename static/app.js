const stage = document.getElementById("stage");
const viewWindow = document.getElementById("view-window");
const cameraView = document.getElementById("camera-view");
const photoImg = document.getElementById("photo-img");
const photoBtn = document.getElementById("photo-btn");
const shutterBtn = document.getElementById("shutter-btn");
const micBtn = document.getElementById("mic-btn");
const resultPanel = document.getElementById("result-panel");
const resultBox = document.getElementById("result");
const errorPanel = document.getElementById("error-panel");
const errorBox = document.getElementById("error");
const certBanner = document.getElementById("cert-banner");
const fileInput = document.getElementById("file-input");
const settingsBtn = document.getElementById("settings-btn");
const settingsPanel = document.getElementById("settings-panel");
const langEnBtn = document.getElementById("lang-en");
const langZhBtn = document.getElementById("lang-zh");

if (location.protocol === "http:" && !["localhost", "127.0.0.1"].includes(location.hostname)) {
  certBanner.hidden = false;
}

function storedLang() {
  try {
    return localStorage.getItem("imageblinds.lang") === "zh" ? "zh" : "en";
  } catch {
    return "en";
  }
}

let lang = storedLang();

function applyLang() {
  langEnBtn.classList.toggle("active", lang === "en");
  langZhBtn.classList.toggle("active", lang === "zh");
  langEnBtn.setAttribute("aria-checked", lang === "en" ? "true" : "false");
  langZhBtn.setAttribute("aria-checked", lang === "zh" ? "true" : "false");
  if (recognition) recognition = null;
  pickVoice();
}

function setLang(next) {
  if (next !== "en" && next !== "zh") return;
  if (lang === next) {
    closeSettings();
    return;
  }
  lang = next;
  try {
    localStorage.setItem("imageblinds.lang", lang);
  } catch {}
  stopListening();
  applyLang();
  closeSettings();
}

function toggleSettings() {
  settingsPanel.hidden = !settingsPanel.hidden;
  settingsBtn.classList.toggle("open", !settingsPanel.hidden);
}

function closeSettings() {
  settingsPanel.hidden = true;
  settingsBtn.classList.remove("open");
}

let lastPointerdownAt = 0;

function onActivate(element, handler) {
  element.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    lastPointerdownAt = Date.now();
    handler(event);
  });
  element.addEventListener("click", (event) => {
    if (Date.now() - lastPointerdownAt < 400) return;
    handler(event);
  });
}

onActivate(settingsBtn, toggleSettings);
onActivate(langEnBtn, () => setLang("en"));
onActivate(langZhBtn, () => setLang("zh"));
document.addEventListener("pointerdown", (event) => {
  if (settingsPanel.hidden) return;
  if (!settingsPanel.contains(event.target) && !settingsBtn.contains(event.target)) closeSettings();
});
const configuredBase = (window.IMAGEBLINDS_API_BASE || "").trim();
const API_URL =
  configuredBase && configuredBase !== "__API_BASE__" ? configuredBase + "/api/analyze" : "/api/analyze";
const TTS_URL = API_URL.replace(/\/api\/analyze$/, "/api/tts");
const ASK_URL = API_URL.replace(/\/api\/analyze$/, "/api/ask");

const secureContext =
  window.isSecureContext || ["localhost", "127.0.0.1", "::1"].includes(location.hostname);

let state = "live";
let pictureMode = false;
let currentFile = null;
let lastDescription = "";
let cameraStream = null;
let cameraActive = false;
let errorTimer = null;

const MIN_ZOOM = 1;
const MAX_ZOOM = 8;
const CROP_MAX_SIDE = 3072;

const view = { zoom: 1, panX: 0, panY: 0 };
const activeTouches = new Map();
let gesture = null;
let analyzeSeq = 0;

const synth = window.speechSynthesis || null;
let voice = null;
let narrationAudio = null;
let analyzeController = null;
let askController = null;
let ttsController = null;

const SpeechRecognitionImpl = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
let listening = false;
let finalTranscript = "";
let suppressEndSend = false;

function setState(mode) {
  state = mode;
  stage.classList.toggle("frozen", mode === "frozen");
  stage.classList.toggle("analyzing", mode === "analyzing");
  shutterBtn.setAttribute(
    "aria-label",
    mode === "frozen" ? "Analyze this picture" : "Capture and analyze"
  );
}

function setPictureMode(on) {
  pictureMode = on;
  photoBtn.classList.toggle("picture", on);
  photoBtn.setAttribute("aria-label", on ? "Back to the live camera" : "Upload a photo");
}

function setResult(text) {
  resultBox.textContent = text;
  resultBox.classList.remove("listening-text");
  resultPanel.hidden = false;
  stage.classList.add("has-result");
  micBtn.disabled = false;
  clampPan();
  applyTransform();
}

function hideResult() {
  resultPanel.hidden = true;
  stage.classList.remove("has-result");
  resultBox.classList.remove("listening-text");
  micBtn.disabled = true;
  stopListening();
  clampPan();
  applyTransform();
}

function pickVoice() {
  if (!synth) return;
  const voices = synth.getVoices();
  if (!voices.length) return;
  const prefix = lang === "zh" ? "zh" : "en";
  voice =
    voices.find((item) => item.lang && item.lang.toLowerCase().startsWith(prefix)) ||
    voices.find((item) => item.default) ||
    voices[0];
}

function fallbackSpeak(text) {
  if (!synth || !text) return;
  synth.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  if (voice) utterance.voice = voice;
  utterance.rate = 1;
  utterance.pitch = 1;
  synth.speak(utterance);
}

async function speak(text) {
  if (!text) return;
  stopSpeaking();
  const controller = new AbortController();
  ttsController = controller;
  try {
    const response = await fetch(`${TTS_URL}?text=${encodeURIComponent(text)}&lang=${encodeURIComponent(lang)}`, {
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`TTS error (${response.status}).`);
    const blob = await response.blob();
    if (blob.size === 0) throw new Error("TTS returned no audio.");
    narrationAudio = new Audio(URL.createObjectURL(blob));
    narrationAudio.onended = () => {
      if (narrationAudio) {
        URL.revokeObjectURL(narrationAudio.src);
        narrationAudio = null;
      }
    };
    await narrationAudio.play();
  } catch (err) {
    if (err.name === "AbortError") return;
    fallbackSpeak(text);
  } finally {
    if (ttsController === controller) ttsController = null;
  }
}

function stopSpeaking() {
  if (ttsController) {
    ttsController.abort();
    ttsController = null;
  }
  if (synth) synth.cancel();
  if (narrationAudio) {
    narrationAudio.pause();
    URL.revokeObjectURL(narrationAudio.src);
    narrationAudio = null;
  }
}

if (synth) {
  synth.onvoiceschanged = pickVoice;
  pickVoice();
}

function buildRecognition() {
  const instance = new SpeechRecognitionImpl();
  instance.lang = lang === "zh" ? "zh-CN" : "en-US";
  instance.interimResults = true;
  instance.continuous = false;
  instance.onresult = (event) => {
    let interim = "";
    finalTranscript = "";
    for (const entry of event.results) {
      if (entry.isFinal) finalTranscript += entry[0].transcript;
      else interim += entry[0].transcript;
    }
    const transcript = finalTranscript || interim;
    if (transcript.trim()) {
      resultBox.textContent = transcript;
      resultBox.classList.add("listening-text");
      resultPanel.hidden = false;
      stage.classList.add("has-result");
    }
  };
  instance.onerror = (event) => {
    if (event.error === "aborted" || event.error === "no-speech") return;
    showError(`Voice input failed: ${event.error}.`);
    stopListening();
    setResult(lastDescription);
  };
  instance.onend = () => {
    const suppressed = suppressEndSend;
    suppressEndSend = false;
    const transcript = finalTranscript.trim();
    stopListening();
    if (suppressed) return;
    if (transcript) askQuestion(transcript);
    else setResult(lastDescription);
  };
  return instance;
}

function startListening() {
  if (listening) return;
  if (!SpeechRecognitionImpl) {
    showError("Voice input is not supported on this browser.");
    return;
  }
  clearError();
  stopSpeaking();
  finalTranscript = "";
  suppressEndSend = false;
  recognition = recognition || buildRecognition();
  try {
    recognition.start();
  } catch {
    recognition = buildRecognition();
    try {
      recognition.start();
    } catch (err) {
      showError(`Could not start voice input: ${err.message}`);
      return;
    }
  }
  listening = true;
  micBtn.classList.add("listening");
  micBtn.setAttribute("aria-label", "Stop voice input");
  resultBox.textContent = "Listening…";
  resultBox.classList.add("listening-text");
  resultPanel.hidden = false;
  stage.classList.add("has-result");
}

function stopListening() {
  if (!listening && !recognition) return;
  suppressEndSend = true;
  if (recognition) {
    try {
      recognition.abort();
    } catch {}
  }
  listening = false;
  micBtn.classList.remove("listening");
  micBtn.setAttribute("aria-label", "Ask a voice follow-up question");
}

async function askQuestion(question) {
  if (!currentFile || !question) return;
  clearError();
  setResult(`You asked: ${question}`);
  micBtn.disabled = true;
  const controller = new AbortController();
  askController = controller;
  const form = new FormData();
  form.append("file", currentFile);
  form.append("question", question);
  form.append("lang", lang);

  try {
    const response = await fetch(ASK_URL, {
      method: "POST",
      body: form,
      signal: controller.signal,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || data.detail || `Server error (${response.status}).`);
    }
    lastDescription = data.answer;
    setResult(lastDescription);
    speak(lastDescription);
  } catch (err) {
    if (err.name === "AbortError") return;
    setResult(lastDescription);
    showError(err.message);
  } finally {
    if (askController === controller) askController = null;
  }
}

micBtn.addEventListener("click", () => {
  if (listening) {
    const transcript = finalTranscript.trim();
    stopListening();
    if (transcript) askQuestion(transcript);
    else setResult(lastDescription);
  } else {
    startListening();
  }
});

function showError(message) {
  errorBox.textContent = message;
  errorPanel.hidden = false;
  speak(message);
  clearTimeout(errorTimer);
  errorTimer = setTimeout(() => {
    errorPanel.hidden = true;
  }, 7000);
}

function clearError() {
  clearTimeout(errorTimer);
  errorPanel.hidden = true;
  stopSpeaking();
}

function stopCamera() {
  cameraActive = false;
  if (cameraStream) {
    cameraStream.getTracks().forEach((track) => track.stop());
    cameraStream = null;
  }
  cameraView.srcObject = null;
}

function clearPhoto() {
  if (photoImg.src) URL.revokeObjectURL(photoImg.src);
  photoImg.removeAttribute("src");
  photoImg.hidden = true;
  currentFile = null;
}

function activeMedia() {
  return state === "live" ? cameraView : photoImg;
}

function mediaSize() {
  if (activeMedia() === cameraView) {
    return { width: cameraView.videoWidth, height: cameraView.videoHeight };
  }
  return { width: photoImg.naturalWidth, height: photoImg.naturalHeight };
}

function applyTransform() {
  const media = activeMedia();
  if (!media) return;
  media.style.transform = `translate3d(${view.panX}px, ${view.panY}px, 0) scale(${view.zoom})`;
}

function resetView() {
  view.zoom = 1;
  view.panX = 0;
  view.panY = 0;
  applyTransform();
}

function containRect(contentWidth, contentHeight, viewWidth, viewHeight) {
  const scale = Math.min(viewWidth / contentWidth, viewHeight / contentHeight);
  const width = contentWidth * scale;
  const height = contentHeight * scale;
  return { x: (viewWidth - width) / 2, y: (viewHeight - height) / 2, width, height, scale };
}

function clampPan() {
  const viewWidth = viewWindow.clientWidth;
  const viewHeight = viewWindow.clientHeight;
  const { width: contentWidth, height: contentHeight } = mediaSize();
  if (!contentWidth || !contentHeight || !viewWidth || !viewHeight) return;
  const rect = containRect(contentWidth, contentHeight, viewWidth, viewHeight);
  const contentW = rect.width * view.zoom;
  const contentH = rect.height * view.zoom;
  const contentX = rect.x * view.zoom + view.panX;
  const contentY = rect.y * view.zoom + view.panY;
  if (contentW <= viewWidth) {
    view.panX = (viewWidth - contentW) / 2 - rect.x * view.zoom;
  } else {
    view.panX = Math.min(
      -rect.x * view.zoom,
      Math.max(viewWidth - contentW - rect.x * view.zoom, view.panX)
    );
  }
  if (contentH <= viewHeight) {
    view.panY = (viewHeight - contentH) / 2 - rect.y * view.zoom;
  } else {
    view.panY = Math.min(
      -rect.y * view.zoom,
      Math.max(viewHeight - contentH - rect.y * view.zoom, view.panY)
    );
  }
}

function visibleCrop(contentWidth, contentHeight) {
  const viewWidth = viewWindow.clientWidth;
  const viewHeight = viewWindow.clientHeight;
  const rect = containRect(contentWidth, contentHeight, viewWidth, viewHeight);
  const zoom = view.zoom;
  const vx0 = Math.max((0 - view.panX) / zoom, rect.x);
  const vy0 = Math.max((0 - view.panY) / zoom, rect.y);
  const vx1 = Math.min((viewWidth - view.panX) / zoom, rect.x + rect.width);
  const vy1 = Math.min((viewHeight - view.panY) / zoom, rect.y + rect.height);
  const sx = Math.max(0, Math.round((vx0 - rect.x) / rect.scale));
  const sy = Math.max(0, Math.round((vy0 - rect.y) / rect.scale));
  const sw = Math.max(1, Math.min(contentWidth - sx, Math.round((vx1 - vx0) / rect.scale)));
  const sh = Math.max(1, Math.min(contentHeight - sy, Math.round((vy1 - vy0) / rect.scale)));
  const full = sw >= contentWidth - 1 && sh >= contentHeight - 1;
  const scale = Math.min(1, CROP_MAX_SIDE / Math.max(sw, sh));
  return {
    sx,
    sy,
    sw,
    sh,
    dw: Math.max(1, Math.round(sw * scale)),
    dh: Math.max(1, Math.round(sh * scale)),
    full,
  };
}

function cropElement(media, crop) {
  return new Promise((resolve, reject) => {
    const canvas = document.createElement("canvas");
    canvas.width = crop.dw;
    canvas.height = crop.dh;
    canvas
      .getContext("2d")
      .drawImage(media, crop.sx, crop.sy, crop.sw, crop.sh, 0, 0, crop.dw, crop.dh);
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("Could not crop the photo."))),
      "image/jpeg",
      0.9
    );
  });
}

function distance(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function midpoint(a, b) {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}

function beginGesture() {
  const points = [...activeTouches.values()];
  if (!points.length) {
    gesture = null;
    return;
  }
  gesture = {
    mode: points.length >= 2 ? "pinch" : "pan",
    startZoom: view.zoom,
    startPanX: view.panX,
    startPanY: view.panY,
    startDist: points.length >= 2 ? distance(points[0], points[1]) : 0,
    startMid: points.length >= 2 ? midpoint(points[0], points[1]) : null,
    moved: false,
    last: points[points.length - 1],
  };
}

function onTouchStart(event) {
  if (state === "analyzing") return;
  for (const touch of event.changedTouches) {
    activeTouches.set(touch.identifier, { x: touch.clientX, y: touch.clientY });
  }
  beginGesture();
}

function onTouchMove(event) {
  event.preventDefault();
  if (!gesture) return;
  for (const touch of event.changedTouches) {
    const point = activeTouches.get(touch.identifier);
    if (point) {
      point.x = touch.clientX;
      point.y = touch.clientY;
    }
  }
  const points = [...activeTouches.values()];
  if (gesture.mode === "pinch" && points.length >= 2) {
    const dist = distance(points[0], points[1]);
    if (dist > 0 && gesture.startDist > 0) {
      const zoom = Math.min(
        MAX_ZOOM,
        Math.max(MIN_ZOOM, gesture.startZoom * (dist / gesture.startDist))
      );
      view.zoom = zoom;
      view.panX = gesture.startMid.x - (gesture.startMid.x - gesture.startPanX) * (zoom / gesture.startZoom);
      view.panY = gesture.startMid.y - (gesture.startMid.y - gesture.startPanY) * (zoom / gesture.startZoom);
      gesture.moved = true;
    }
  } else if (points.length === 1) {
    const point = points[0];
    if (gesture.last) {
      view.panX += point.x - gesture.last.x;
      view.panY += point.y - gesture.last.y;
      gesture.moved = true;
    }
    gesture.last = { x: point.x, y: point.y };
    gesture.mode = "pan";
  }
  clampPan();
  applyTransform();
}

function onTouchEnd(event) {
  for (const touch of event.changedTouches) {
    activeTouches.delete(touch.identifier);
  }
  if (!activeTouches.size) {
    const moved = gesture ? gesture.moved : false;
    gesture = null;
    if (moved) finishGesture();
  } else {
    beginGesture();
  }
}

function finishGesture() {
  clampPan();
  applyTransform();
}

async function openStream(constraints) {
  try {
    return await navigator.mediaDevices.getUserMedia({ video: constraints, audio: false });
  } catch (err) {
    if (err.name !== "OverconstrainedError") throw err;
    return null;
  }
}

function storedCameraId() {
  try {
    return localStorage.getItem("imageblinds.cameraId.v2") || "";
  } catch {
    return "";
  }
}

function rememberCameraId(stream) {
  try {
    const id = stream.getVideoTracks()[0].getSettings().deviceId;
    if (id) localStorage.setItem("imageblinds.cameraId.v2", id);
  } catch {}
}

const HIGH_RES_ENV_VIDEO = {
  facingMode: { exact: "environment" },
  width: { min: 1920, ideal: 3840 },
  height: { min: 1080, ideal: 2160 },
  aspectRatio: { ideal: 16 / 9 },
};

async function openCamera() {
  setPictureMode(false);
  clearError();
  hideResult();
  clearPhoto();
  cameraView.hidden = false;
  setState("analyzing");

  if (!secureContext) {
    showError("The camera needs HTTPS (or localhost). Open the https:// address of this app.");
    setState("live");
    resetView();
    return;
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    showError("Camera is not available on this device.");
    setState("live");
    resetView();
    return;
  }
  try {
    cameraStream = null;
    const savedId = storedCameraId();
    if (savedId) {
      cameraStream = await openStream({ deviceId: { exact: savedId }, ...HIGH_RES_ENV_VIDEO });
    }
    if (!cameraStream) cameraStream = await openStream(HIGH_RES_ENV_VIDEO);
    if (!cameraStream) cameraStream = await openStream({ facingMode: "environment" });
    if (!cameraStream) {
      cameraStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    }
    rememberCameraId(cameraStream);
  } catch (err) {
    showError(`Could not open the camera: ${err.message}`);
    setState("live");
    resetView();
    return;
  }
  cameraActive = true;
  cameraView.srcObject = cameraStream;
  await cameraView.play().catch(() => {});
  setState("live");
  resetView();
}

function setFile(file) {
  if (!file) return;
  analyzeSeq++;
  if (analyzeController) {
    analyzeController.abort();
    analyzeController = null;
  }
  if (askController) {
    askController.abort();
    askController = null;
  }
  clearError();
  stopCamera();
  if (photoImg.src) URL.revokeObjectURL(photoImg.src);
  photoImg.src = URL.createObjectURL(file);
  photoImg.hidden = false;
  hideResult();
  stopSpeaking();
  currentFile = file;
  setPictureMode(true);
  setState("frozen");
  resetView();
}

function captureFrame() {
  return new Promise((resolve, reject) => {
    if (!cameraView.videoWidth || !cameraView.videoHeight) {
      reject(new Error("The camera is still starting. Try again."));
      return;
    }
    const crop = visibleCrop(cameraView.videoWidth, cameraView.videoHeight);
    const canvas = document.createElement("canvas");
    if (crop.full) {
      canvas.width = cameraView.videoWidth;
      canvas.height = cameraView.videoHeight;
      canvas.getContext("2d").drawImage(cameraView, 0, 0);
    } else {
      canvas.width = crop.dw;
      canvas.height = crop.dh;
      canvas
        .getContext("2d")
        .drawImage(cameraView, crop.sx, crop.sy, crop.sw, crop.sh, 0, 0, crop.dw, crop.dh);
    }
    canvas.toBlob(
      (blob) => {
        if (blob) resolve(new File([blob], "camera.jpg", { type: "image/jpeg" }));
        else reject(new Error("Could not capture the camera frame."));
      },
      "image/jpeg",
      0.9
    );
  });
}

async function freezeAndAnalyze() {
  clearError();
  setState("analyzing");
  try {
    const file = await captureFrame();
    resetView();
    if (photoImg.src) URL.revokeObjectURL(photoImg.src);
    photoImg.src = URL.createObjectURL(file);
    photoImg.hidden = false;
    stopCamera();
    currentFile = file;
    setPictureMode(true);
  } catch (err) {
    showError(err.message);
    setState("live");
    return;
  }
  setState("frozen");
  await analyze();
}

function resumeLive() {
  hideResult();
  stopSpeaking();
applyLang();

openCamera();
}

function cancelToLive() {
  analyzeSeq++;
  if (analyzeController) {
    analyzeController.abort();
    analyzeController = null;
  }
  if (askController) {
    askController.abort();
    askController = null;
  }
  stopListening();
  resumeLive();
}

function cancelToPicture() {
  analyzeSeq++;
  if (analyzeController) {
    analyzeController.abort();
    analyzeController = null;
  }
  if (askController) {
    askController.abort();
    askController = null;
  }
  stopListening();
  setState("frozen");
}

async function analyze() {
  if (!currentFile) return;
  clearError();
  setState("analyzing");

  let file = currentFile;
  const photoWidth = photoImg.naturalWidth;
  const photoHeight = photoImg.naturalHeight;
  if (photoWidth && photoHeight) {
    const crop = visibleCrop(photoWidth, photoHeight);
    if (!crop.full) {
      try {
        const blob = await cropElement(photoImg, crop);
        file = new File([blob], "crop.jpg", { type: "image/jpeg" });
      } catch (err) {
        setState("frozen");
        showError(err.message);
        return;
      }
    }
  }

  const seq = ++analyzeSeq;
  if (analyzeController) analyzeController.abort();
  const controller = new AbortController();
  analyzeController = controller;
  const form = new FormData();
  form.append("file", file);
  form.append("lang", lang);

  try {
    const response = await fetch(API_URL, {
      method: "POST",
      body: form,
      signal: controller.signal,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || data.detail || `Server error (${response.status}).`);
    }
    if (seq !== analyzeSeq) return;
    lastDescription = data.description;
    setResult(lastDescription);
    setState("frozen");
    speak(lastDescription);
  } catch (err) {
    if (seq !== analyzeSeq) return;
    if (pictureMode) setState("frozen");
    else resumeLive();
    showError(err.message);
  } finally {
    if (analyzeController === controller) analyzeController = null;
  }
}

shutterBtn.addEventListener("click", () => {
  if (analyzeController || askController || listening) {
    if (pictureMode) cancelToPicture();
    else cancelToLive();
    return;
  }
  if (state === "analyzing") return;
  if (pictureMode) analyze();
  else if (cameraActive) freezeAndAnalyze();
  else openCamera();
});

photoBtn.addEventListener("click", () => {
  if (pictureMode) cancelToLive();
  else fileInput.click();
});

fileInput.addEventListener("change", () => {
  if (fileInput.files && fileInput.files[0]) setFile(fileInput.files[0]);
});

viewWindow.addEventListener("touchstart", onTouchStart, { passive: true });
viewWindow.addEventListener("touchmove", onTouchMove, { passive: false });
viewWindow.addEventListener("touchend", onTouchEnd);
viewWindow.addEventListener("touchcancel", onTouchEnd);

document.addEventListener("gesturestart", (event) => event.preventDefault());
document.addEventListener("gesturechange", (event) => event.preventDefault());
document.addEventListener("gestureend", (event) => event.preventDefault());

window.addEventListener("resize", () => {
  clampPan();
  applyTransform();
});

document.addEventListener("dragover", (event) => {
  if (state === "analyzing") return;
  event.preventDefault();
});

document.addEventListener("drop", (event) => {
  event.preventDefault();
  const file = event.dataTransfer.files && event.dataTransfer.files[0];
  if (file) setFile(file);
});

openCamera();

if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost")) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("./sw.js").catch(() => {});
  });
}
