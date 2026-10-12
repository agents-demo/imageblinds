const fileInput = document.getElementById("file-input");
const chooseBtn = document.getElementById("choose-btn");
const dropzone = document.getElementById("dropzone");
const previewPanel = document.getElementById("preview-panel");
const preview = document.getElementById("preview");
const fileName = document.getElementById("file-name");
const analyzeBtn = document.getElementById("analyze-btn");
const spinner = document.getElementById("spinner");
const resultPanel = document.getElementById("result-panel");
const resultBox = document.getElementById("result");
const errorPanel = document.getElementById("error-panel");
const errorBox = document.getElementById("error");

let selectedFile = null;

function showError(message) {
  errorBox.textContent = message;
  errorPanel.hidden = false;
}

function clearError() {
  errorPanel.hidden = true;
}

function setFile(file) {
  if (!file) return;
  selectedFile = file;
  if (preview.src) URL.revokeObjectURL(preview.src);
  preview.src = URL.createObjectURL(file);
  fileName.textContent = file.name;
  previewPanel.hidden = false;
  resultPanel.hidden = true;
  analyzeBtn.disabled = false;
  clearError();
}

chooseBtn.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", () => {
  if (fileInput.files && fileInput.files[0]) setFile(fileInput.files[0]);
});

dropzone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropzone.classList.add("dragging");
});

dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragging"));

dropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropzone.classList.remove("dragging");
  const file = event.dataTransfer.files && event.dataTransfer.files[0];
  if (file) setFile(file);
});

async function loadExample(name) {
  clearError();
  const response = await fetch(`/examples/${name}`);
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

async function analyze() {
  if (!selectedFile) {
    showError("Choose a photo first.");
    return;
  }
  clearError();
  resultPanel.hidden = true;
  analyzeBtn.disabled = true;
  spinner.hidden = false;

  const form = new FormData();
  form.append("file", selectedFile);

  try {
    const response = await fetch("/api/analyze", { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) {
      showError(data.error || data.detail || `Server error (${response.status}).`);
      return;
    }
    resultBox.textContent = data.description;
    resultPanel.hidden = false;
  } catch (err) {
    showError(`Could not reach the server: ${err.message}`);
  } finally {
    spinner.hidden = true;
    analyzeBtn.disabled = false;
  }
}

analyzeBtn.addEventListener("click", analyze);
