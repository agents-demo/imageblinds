const stage = document.getElementById("stage");
const cameraView = document.getElementById("camera-view");
const photoImg = document.getElementById("photo-img");
const photoBtn = document.getElementById("photo-btn");
const shutterBtn = document.getElementById("shutter-btn");
const uploadPanel = document.getElementById("upload-panel");
const uploadContent = uploadPanel.querySelector(".overlay-content");
const resultOverlay = document.getElementById("result-overlay");
const resultBox = document.getElementById("result");
const errorPanel = document.getElementById("error-panel");
const errorBox = document.getElementById("error");
const speakBtn = document.getElementById("speak-btn");
const stopBtn = document.getElementById("stop-btn");
const certBanner = document.getElementById("cert-banner");
const fileInput = document.getElementById("file-input");
const chooseBtn = document.getElementById("choose-btn");
const backBtn = document.getElementById("back-btn");

if (location.protocol === "http:" && !["localhost", "127.0.0.1"].includes(location.hostname)) {
  certBanner.hidden = false;
}

const configuredBase = (window.IMAGEBLINDS_API_BASE || "").trim();
const API_URL =
  configuredBase && configuredBase !== "__API_BASE__" ? configuredBase + "/api/analyze" : "/api/analyze";

const isTouch =
  (window.matchMedia && window.matchMedia("(pointer: coarse)").matches) ||
  "ontouchstart" in window ||
  navigator.maxTouchPoints > 0;

let state = "live";
let currentFile = null;
let lastDescription = "";
let cameraStream = null;
let cameraActive = false;
let hadCamera = false;
let errorTimer = null;

const synth = window.speechSynthesis || null;
let voice = null;

function setState(mode) {
  state = mode;
  stage.classList.toggle("frozen", mode === "frozen");
  stage.classList.toggle("analyzing", mode === "analyzing");
  shutterBtn.setAttribute(
    "aria-label",
    mode === "frozen" ? "Return to the live camera" : "Capture and analyze"
  );
}

function pickVoice() {
  if (!synth) return;
  const voices = synth.getVoices();
  if (!voices.length) return;
  voice =
    voices.find((item) => item.lang && item.lang.toLowerCase().startsWith("en")) ||
    voices.find((item) => item.default) ||
    voices[0];
}

function speak(text) {
  if (!synth || !text) return;
  synth.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  if (voice) utterance.voice = voice;
  utterance.rate = 1;
  utterance.pitch = 1;
  synth.speak(utterance);
}

function stopSpeaking() {
  if (synth) synth.cancel();
}

if (synth) {
  synth.onvoiceschanged = pickVoice;
  pickVoice();
} else {
  speakBtn.hidden = true;
  stopBtn.hidden = true;
}

speakBtn.addEventListener("click", () => speak(lastDescription));
stopBtn.addEventListener("click", stopSpeaking);

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
  cameraView.hidden = true;
}

function clearPhoto() {
  if (photoImg.src) URL.revokeObjectURL(photoImg.src);
  photoImg.removeAttribute("src");
  photoImg.hidden = true;
  currentFile = null;
}

async function openCamera() {
  clearError();
  resultOverlay.hidden = true;
  uploadPanel.hidden = true;
  clearPhoto();
  cameraView.hidden = false;
  setState("analyzing");

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    showError("Camera is not available on this device.");
    openUpload();
    return;
  }
  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment" },
      audio: false,
    });
  } catch (err) {
    showError(`Could not open the camera: ${err.message}`);
    openUpload();
    return;
  }
  cameraActive = true;
  hadCamera = true;
  cameraView.srcObject = cameraStream;
  setState("live");
}

function openUpload() {
  clearError();
  stopCamera();
  resultOverlay.hidden = true;
  clearPhoto();
  uploadPanel.hidden = false;
  setState("menu");
}

function setFile(file) {
  if (!file) return;
  clearError();
  stopCamera();
  if (photoImg.src) URL.revokeObjectURL(photoImg.src);
  photoImg.src = URL.createObjectURL(file);
  photoImg.hidden = false;
  uploadPanel.hidden = true;
  resultOverlay.hidden = true;
  currentFile = file;
  setState("frozen");
  analyze();
}

function captureFrame() {
  return new Promise((resolve, reject) => {
    if (!cameraView.videoWidth || !cameraView.videoHeight) {
      reject(new Error("The camera is still starting. Try again."));
      return;
    }
    const canvas = document.createElement("canvas");
    canvas.width = cameraView.videoWidth;
    canvas.height = cameraView.videoHeight;
    canvas.getContext("2d").drawImage(cameraView, 0, 0);
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
  let file = null;
  if (cameraActive) {
    try {
      file = await captureFrame();
    } catch (err) {
      showError(err.message);
      setState("live");
      return;
    }
    if (photoImg.src) URL.revokeObjectURL(photoImg.src);
    photoImg.src = URL.createObjectURL(file);
    photoImg.hidden = false;
    stopCamera();
    currentFile = file;
  }
  if (!currentFile) {
    setState("live");
    return;
  }
  setState("frozen");
  await analyze();
}

function resumeLive() {
  resultOverlay.hidden = true;
  stopSpeaking();
  if (isTouch || hadCamera) openCamera();
  else openUpload();
}

async function analyze() {
  if (!currentFile) return;
  clearError();
  resultOverlay.hidden = true;
  setState("analyzing");

  const form = new FormData();
  form.append("file", currentFile);

  try {
    const response = await fetch(API_URL, { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || data.detail || `Server error (${response.status}).`);
    }
    lastDescription = data.description;
    resultBox.textContent = lastDescription;
    resultOverlay.hidden = false;
    setState("frozen");
    speak(lastDescription);
  } catch (err) {
    showError(err.message);
    resumeLive();
  }
}

shutterBtn.addEventListener("click", () => {
  if (state === "live") freezeAndAnalyze();
  else if (state === "frozen") resumeLive();
});

photoBtn.addEventListener("click", openUpload);
backBtn.addEventListener("click", resumeLive);
chooseBtn.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", () => {
  if (fileInput.files && fileInput.files[0]) setFile(fileInput.files[0]);
});

document.addEventListener("dragover", (event) => {
  if (uploadPanel.hidden) return;
  event.preventDefault();
  uploadContent.classList.add("dragging");
});

document.addEventListener("dragleave", (event) => {
  if (!uploadPanel.contains(event.relatedTarget)) uploadContent.classList.remove("dragging");
});

document.addEventListener("drop", (event) => {
  if (uploadPanel.hidden) return;
  event.preventDefault();
  uploadContent.classList.remove("dragging");
  const file = event.dataTransfer.files && event.dataTransfer.files[0];
  if (file) setFile(file);
});

async function loadExample(name) {
  clearError();
  const response = await fetch(`./examples/${name}`);
  if (!response.ok) {
    showError(`Could not load example ${name}.`);
    return;
  }
  const blob = await response.blob();
  setFile(new File([blob], name, { type: blob.type || "image/jpeg" }));
}

document.querySelectorAll(".example-btn").forEach((button) => {
  button.addEventListener("click", () => loadExample(button.dataset.example));
});

if (isTouch) openCamera();
else openUpload();

if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost")) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("./sw.js").catch(() => {});
  });
}
