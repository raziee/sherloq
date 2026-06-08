const toolSelect = document.getElementById("tool-select");
const imageInput = document.getElementById("image-input");
const referenceWrap = document.getElementById("reference-wrap");
const referenceInput = document.getElementById("reference-input");
const paramsInput = document.getElementById("params-input");
const asyncInput = document.getElementById("async-input");
const runButton = document.getElementById("run-button");
const statusEl = document.getElementById("status");
const jsonOutput = document.getElementById("json-output");
const imageOutput = document.getElementById("image-output");

let tools = [];

async function loadTools() {
  const response = await fetch("/api/v1/tools");
  const payload = await response.json();
  tools = payload.tools || [];
  toolSelect.innerHTML = "";
  const groups = {};
  for (const tool of tools) {
    groups[tool.group] = groups[tool.group] || [];
    groups[tool.group].push(tool);
  }
  for (const [group, items] of Object.entries(groups)) {
    const optgroup = document.createElement("optgroup");
    optgroup.label = group;
    for (const tool of items) {
      const option = document.createElement("option");
      option.value = tool.id;
      option.textContent = tool.name;
      option.dataset.asyncDefault = tool.async_default ? "1" : "0";
      option.dataset.requiresReference = tool.id === "comparison" ? "1" : "0";
      optgroup.appendChild(option);
    }
    toolSelect.appendChild(optgroup);
  }
  updateToolUi();
}

function updateToolUi() {
  const selected = toolSelect.selectedOptions[0];
  if (!selected) return;
  referenceWrap.classList.toggle("hidden", selected.dataset.requiresReference !== "1");
  asyncInput.checked = selected.dataset.asyncDefault === "1";
}

toolSelect.addEventListener("change", updateToolUi);

function renderResult(payload) {
  const { images = {}, ...rest } = payload.result || payload;
  jsonOutput.textContent = JSON.stringify(rest, null, 2);
  imageOutput.innerHTML = "";
  for (const [name, data] of Object.entries(images)) {
    const card = document.createElement("div");
    card.className = "image-card";
    const title = document.createElement("strong");
    title.textContent = name;
    const img = document.createElement("img");
    img.alt = name;
    img.src = `data:image/png;base64,${data}`;
    card.appendChild(title);
    card.appendChild(img);
    imageOutput.appendChild(card);
  }
}

async function pollJob(jobId) {
  while (true) {
    const response = await fetch(`/api/v1/jobs/${jobId}`);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Job polling failed");
    }
    statusEl.textContent = `وضعیت کار: ${payload.status}`;
    if (payload.status === "completed") {
      renderResult(payload);
      return;
    }
    if (payload.status === "failed") {
      throw new Error(payload.error || "Job failed");
    }
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
}

runButton.addEventListener("click", async () => {
  const toolId = toolSelect.value;
  const file = imageInput.files[0];
  if (!toolId || !file) {
    statusEl.textContent = "لطفاً ابزار و تصویر را انتخاب کنید.";
    return;
  }

  const form = new FormData();
  form.append("image", file);
  form.append("params", paramsInput.value || "{}");
  form.append("image_format", "png");
  form.append("async_mode", asyncInput.checked ? "true" : "false");
  if (toolId === "comparison" && referenceInput.files[0]) {
    form.append("reference", referenceInput.files[0]);
  }

  statusEl.textContent = "در حال پردازش...";
  runButton.disabled = true;
  imageOutput.innerHTML = "";
  jsonOutput.textContent = "{}";

  try {
    const response = await fetch(`/api/v1/analyze/${toolId}`, {
      method: "POST",
      body: form,
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Request failed");
    }
    if (payload.job_id) {
      await pollJob(payload.job_id);
      statusEl.textContent = "تحلیل با موفقیت انجام شد.";
      return;
    }
    renderResult(payload);
    statusEl.textContent = `انجام شد در ${payload.elapsed_ms} میلی‌ثانیه`;
  } catch (error) {
    statusEl.textContent = error.message;
  } finally {
    runButton.disabled = false;
  }
});

loadTools().catch((error) => {
  statusEl.textContent = `خطا در بارگذاری ابزارها: ${error.message}`;
});
