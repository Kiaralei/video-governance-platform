const state = {
  queue: [],
  pipelineJobs: [],
  selectedTaskId: null,
  selectedContentId: null,
};

const $ = (selector) => document.querySelector(selector);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "请求失败");
  }
  return data;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function decisionText(value) {
  if (value === "pass") return "通过";
  if (value === "block") return "拦截";
  if (value === "VIOLATION") return "疑似违规";
  if (value === "NO_VIOLATION") return "未见违规";
  if (value === "UNCERTAIN") return "不确定";
  return "需人工判断";
}

function jobStatusText(value) {
  const labels = {
    queued: "排队中",
    processing: "处理中",
    completed: "已完成",
    failed: "失败",
  };
  return labels[value] ?? value;
}

function stageText(value) {
  const labels = {
    queued: "等待机审",
    evidence_extraction: "证据提取",
    machine_review: "机审判断",
    human_review_queued: "已流转人审",
    failed: "处理失败",
  };
  return labels[value] ?? value;
}

function recommendationPill(value) {
  if (!value) return `<span class="pill">暂无强建议</span>`;
  return `<span class="pill ${value}">机审建议：${decisionText(value)}</span>`;
}

function percent(value) {
  return `${Math.round((value ?? 0) * 100)}%`;
}

function formatBytes(value) {
  if (!value) return "";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function renderVideoMeta(meta = {}) {
  const resolution = meta.width && meta.height ? `${meta.width}x${meta.height}` : "";
  const duration = meta.duration_ms ? `${Math.round(meta.duration_ms / 1000)} 秒` : "";
  const rows = [
    ["来源类型", meta.source_type],
    ["资产状态", meta.asset_status],
    ["时长", duration],
    ["分辨率", resolution],
    ["编码", meta.video_codec],
    ["文件大小", formatBytes(meta.file_size_bytes)],
    ["SHA256", meta.sha256 ? `${meta.sha256.slice(0, 18)}...` : ""],
    ["存储 URI", meta.storage_uri],
    ["来源", meta.local_path || meta.file_path || meta.source_url || meta.source],
  ].filter(([, value]) => value);
  if (!rows.length) return `<p class="muted">暂无视频特征。</p>`;
  return rows
    .map(([label, value]) => `<div class="evidence-item"><strong>${label}</strong><br>${escapeHtml(value)}</div>`)
    .join("");
}

function renderAvailability(availability = {}) {
  const rows = [
    ["视频源", availability.video_source?.available],
    ["ffprobe", availability.ffprobe?.available],
    ["ffmpeg", availability.ffmpeg?.available],
    ["关键帧", availability.frame_extraction?.available],
    ["ASR", availability.asr?.available],
    ["OCR", availability.ocr?.available],
    ["目标检测", availability.object_detection?.available],
    ["场景识别", availability.scene_classification?.available],
  ];
  return rows
    .map(([label, value]) => `<span class="pill">${label}：${value ? "可用" : "降级"}</span>`)
    .join("");
}

function renderModelInvocations(invocations = []) {
  if (!invocations.length) return `<p class="muted">暂无模型调用记录。</p>`;
  return invocations
    .map(
      (item) => `
        <div class="evidence-item">
          <strong>${escapeHtml(item.modality)}</strong><br>
          ${escapeHtml(item.status)}
          ${item.provider ? ` · ${escapeHtml(item.provider)}` : ""}
          ${item.model_version ? ` · ${escapeHtml(item.model_version)}` : ""}
          ${item.warnings ? `<br><span class="muted">${escapeHtml(item.warnings.join ? item.warnings.join("；") : item.warnings)}</span>` : ""}
          ${item.error ? `<br><span class="muted">${escapeHtml(item.error)}</span>` : ""}
        </div>
      `
    )
    .join("");
}

function renderObjectDetections(objects = []) {
  if (!objects.length) return `<p class="muted">暂无目标检测结果。</p>`;
  return objects
    .map(
      (item) => `
        <div class="evidence-item">
          <strong>${escapeHtml(item.label)}</strong><br>
          ${escapeHtml(item.frame_id)} · ${percent(item.confidence)}
        </div>
      `
    )
    .join("");
}

function renderExtractionNotes(notes = []) {
  if (!notes.length) return `<p class="muted">没有降级说明。</p>`;
  return notes.map((note) => `<div class="evidence-item">${escapeHtml(note)}</div>`).join("");
}

async function loadConfig() {
  const config = await api("/api/v1/config");
  $("#tenant").textContent = config.tenant_id;
  $("#jurisdiction").textContent = config.jurisdiction;
}

async function loadSummary() {
  const summary = await api("/api/v1/dashboard/summary");
  $("#metricTotal").textContent = summary.total_content;
  $("#metricPending").textContent = summary.queue.pending;
  $("#metricQueued").textContent = summary.pipeline.queued;
  $("#metricProcessing").textContent = summary.pipeline.processing;
  $("#metricPass").textContent = summary.decisions.pass;
  $("#metricBlock").textContent = summary.decisions.block;
}

async function loadPipelineJobs() {
  const jobs = await api("/api/v1/pipeline/jobs?offset=0&limit=50");
  state.pipelineJobs = jobs.items;
  $("#machineCount").textContent = `${jobs.total} 条流水线任务`;
  renderPipelineList();
}

function renderPipelineList() {
  const list = $("#machineList");
  if (!state.pipelineJobs.length) {
    list.innerHTML = `<div class="empty-state">暂无机审流水线任务。</div>`;
    return;
  }
  list.innerHTML = state.pipelineJobs
    .map(
      (job) => `
        <button class="task-card ${job.content_id === state.selectedContentId ? "active" : ""}" data-content-id="${job.content_id}">
          <div class="task-title">${escapeHtml(job.title)}</div>
          <div class="pill-row">
            <span class="pill">${jobStatusText(job.status)}</span>
            <span class="pill">${stageText(job.stage)}</span>
            ${job.status === "completed" ? recommendationPill(job.recommendation) : ""}
          </div>
          <p class="muted">${escapeHtml(job.creator_id)} · ${escapeHtml(job.updated_at)}</p>
        </button>
      `
    )
    .join("");
  list.querySelectorAll("[data-content-id]").forEach((button) => {
    button.addEventListener("click", () => openPipelineJob(button.dataset.contentId));
  });
}

async function openPipelineJob(contentId) {
  state.selectedContentId = contentId;
  renderPipelineList();
  const job = state.pipelineJobs.find((item) => item.content_id === contentId);
  if (!job) return;
  if (job.status === "completed" && job.machine_review_id) {
    const review = await api(`/api/v1/machine/reviews/${contentId}`);
    renderMachineReview(job, review);
    return;
  }
  renderPipelineStatus(job);
}

function renderPipelineStatus(job) {
  $("#machinePanel").innerHTML = `
    <div class="panel-block">
      <h3>流水线状态</h3>
      <h2>${escapeHtml(job.title)}</h2>
      <p>${escapeHtml(job.description)}</p>
      <div class="pill-row" style="margin-top: 12px;">
        <span class="pill">${jobStatusText(job.status)}</span>
        <span class="pill">${stageText(job.stage)}</span>
        <span class="pill">尝试 ${job.attempts}/${job.max_attempts}</span>
      </div>
      ${job.error ? `<div class="evidence-item"><strong>错误</strong><br>${escapeHtml(job.error)}</div>` : ""}
    </div>
    <div class="panel-block">
      <h3>为什么这样设计</h3>
      <p class="muted">摄取接口只负责快速入库和排队，耗时的证据提取与机审由后台 worker 处理。这样大量输入不会把 HTTP 请求线程长时间占住。</p>
    </div>
  `;
}

function renderMachineReview(job, review) {
  const verdicts = review.verdicts ?? [];
  const ruleHits = review.evidence?.pre_filter_results?.rule_hits ?? [];
  const asr = review.evidence?.asr_transcript ?? [];
  const ocr = review.evidence?.ocr_results ?? [];
  const videoMeta = review.evidence?.video_meta ?? {};
  const availability = review.evidence?.modality_availability ?? {};
  const extractionNotes = review.evidence?.extraction_notes ?? [];
  const modelInvocations = review.evidence?.modality_model_invocations ?? [];
  const objectDetections = review.evidence?.object_detections ?? [];
  const reviewSource = review.evidence?.machine_review_source ?? "local_rules";
  $("#machinePanel").innerHTML = `
    <div class="case-grid">
      <div>
        <div class="panel-block">
          <h3>内容信息</h3>
          <h2>${escapeHtml(review.title)}</h2>
          <p>${escapeHtml(review.description)}</p>
          <div class="pill-row" style="margin-top: 12px;">
            <span class="pill">创作者：${escapeHtml(review.creator_id)}</span>
            <span class="pill">流水线：${jobStatusText(job.status)}</span>
            <span class="pill">最终裁定：${decisionText(review.final_decision)}</span>
          </div>
        </div>
        <div class="panel-block">
          <h3>证据摘要</h3>
          ${asr.map((item) => `<div class="evidence-item"><strong>语音转写</strong><br>${escapeHtml(item.text)}</div>`).join("")}
          ${ocr.map((item) => `<div class="evidence-item"><strong>画面文字</strong><br>${escapeHtml(item.text)}</div>`).join("")}
          ${renderObjectDetections(objectDetections)}
          ${ruleHits.length ? ruleHits.map((item) => `<div class="evidence-item"><strong>规则命中</strong><br>${escapeHtml(item.rule_id)}</div>`).join("") : `<p class="muted">未命中关键词规则。</p>`}
        </div>
        <div class="panel-block">
          <h3>视频特征</h3>
          <div class="pill-row">${renderAvailability(availability)}</div>
          ${renderVideoMeta(videoMeta)}
          ${renderModelInvocations(modelInvocations)}
          ${renderExtractionNotes(extractionNotes)}
        </div>
      </div>
      <aside class="decision-box">
        <div class="panel-block">
          <h3>机审结论</h3>
          <div class="pill-row">
            ${recommendationPill(review.recommendation)}
            <span class="pill">置信度 ${percent(review.confidence)}</span>
            <span class="pill">来源：${reviewSource === "llm" ? "LLM" : "本地规则"}</span>
          </div>
          <p style="margin-top: 10px;">${escapeHtml(review.rationale)}</p>
        </div>
        <div class="panel-block">
          <h3>维度判断</h3>
          ${verdicts.map((v) => `
            <div class="evidence-item">
              <strong>${escapeHtml(v.dimension_id)}</strong><br>
              ${decisionText(v.decision)} · ${percent(v.confidence)}<br>
              <span class="muted">证据引用：${escapeHtml((v.evidence_refs ?? []).join("、"))}</span>
            </div>
          `).join("")}
        </div>
        ${review.task_id ? `<button data-open-task="${review.task_id}">进入人审任务</button>` : ""}
      </aside>
    </div>
  `;
  const openTaskButton = $("#machinePanel").querySelector("[data-open-task]");
  if (openTaskButton) {
    openTaskButton.addEventListener("click", (event) => {
      document.querySelector('[data-view="queue"]').click();
      openCase(event.currentTarget.dataset.openTask);
    });
  }
}

async function loadQueue() {
  const queue = await api("/api/v1/review/human/queue?offset=0&limit=50");
  state.queue = queue.items;
  $("#queueCount").textContent = `${queue.total} 条待审`;
  renderQueue();
}

function renderQueue() {
  const list = $("#queueList");
  if (!state.queue.length) {
    list.innerHTML = `<div class="empty-state">暂无待审任务。</div>`;
    return;
  }
  list.innerHTML = state.queue
    .map(
      (task) => `
        <button class="task-card ${task.task_id === state.selectedTaskId ? "active" : ""}" data-task-id="${task.task_id}">
          <div class="task-title">${escapeHtml(task.title)}</div>
          <div class="pill-row">
            ${recommendationPill(task.machine_recommendation)}
            <span class="pill">置信度 ${percent(task.machine_confidence)}</span>
          </div>
          <p class="muted">${escapeHtml(task.creator_id)} · ${escapeHtml(task.created_at)}</p>
        </button>
      `
    )
    .join("");
  list.querySelectorAll("[data-task-id]").forEach((button) => {
    button.addEventListener("click", () => openCase(button.dataset.taskId));
  });
}

async function openCase(taskId) {
  state.selectedTaskId = taskId;
  renderQueue();
  const data = await api(`/api/v1/review/human/${taskId}`);
  await api(`/api/v1/review/human/${taskId}/claim`, {
    method: "POST",
    body: JSON.stringify({ reviewer_id: "reviewer_demo" }),
  }).catch(() => null);
  renderCase(data);
}

function renderCase(data) {
  const asr = data.evidence.asr_transcript ?? [];
  const ocr = data.evidence.ocr_results ?? [];
  const rules = data.evidence.pre_filter_results?.rule_hits ?? [];
  const verdicts = data.machine_review.verdicts ?? [];
  const videoMeta = data.evidence.video_meta ?? {};
  const availability = data.evidence.modality_availability ?? {};
  const extractionNotes = data.evidence.extraction_notes ?? [];
  const modelInvocations = data.evidence.modality_model_invocations ?? [];
  const objectDetections = data.evidence.object_detections ?? [];
  const reviewSource = data.evidence.machine_review_source ?? "local_rules";
  $("#casePanel").innerHTML = `
    <div class="case-grid">
      <div>
        <div class="panel-block">
          <h3>内容信息</h3>
          <h2>${escapeHtml(data.content.title)}</h2>
          <p>${escapeHtml(data.content.description)}</p>
          <div class="pill-row" style="margin-top: 12px;">
            <span class="pill">创作者：${escapeHtml(data.content.creator_id)}</span>
            <span class="pill">法域：${escapeHtml(data.content.jurisdiction)}</span>
          </div>
        </div>
        <div class="panel-block">
          <h3>证据包</h3>
          ${asr.map((item) => `<div class="evidence-item"><strong>语音转写</strong><br>${escapeHtml(item.text)}</div>`).join("")}
          ${ocr.map((item) => `<div class="evidence-item"><strong>画面文字</strong><br>${escapeHtml(item.text)}</div>`).join("")}
          ${renderObjectDetections(objectDetections)}
          ${rules.length ? rules.map((item) => `<div class="evidence-item"><strong>规则命中</strong><br>${escapeHtml(item.rule_id)}</div>`).join("") : `<p class="muted">未命中关键词规则。</p>`}
        </div>
        <div class="panel-block">
          <h3>视频特征</h3>
          <div class="pill-row">${renderAvailability(availability)}</div>
          ${renderVideoMeta(videoMeta)}
          ${renderModelInvocations(modelInvocations)}
          ${renderExtractionNotes(extractionNotes)}
        </div>
        <div class="panel-block">
          <h3>机审结果</h3>
          <div class="pill-row">
            ${recommendationPill(data.machine_review.recommendation)}
            <span class="pill">置信度 ${percent(data.machine_review.confidence)}</span>
            <span class="pill">来源：${reviewSource === "llm" ? "LLM" : "本地规则"}</span>
          </div>
          <p style="margin-top: 10px;">${escapeHtml(data.machine_review.rationale)}</p>
          ${verdicts.map((v) => `<div class="evidence-item"><strong>${escapeHtml(v.dimension_id)}</strong><br>${decisionText(v.decision)} · ${percent(v.confidence)}</div>`).join("")}
        </div>
      </div>
      <aside class="decision-box">
        <div class="panel-block">
          <h3>人审最终裁定</h3>
          <p class="muted">当前 MVP 只允许提交“通过”或“拦截”。</p>
          <textarea id="decisionReason" placeholder="提交前必须填写裁定理由。"></textarea>
          <div class="decision-actions" style="margin-top: 12px;">
            <button class="pass-btn" data-decision="pass">通过</button>
            <button class="block-btn" data-decision="block">拦截</button>
          </div>
        </div>
      </aside>
    </div>
  `;
  $("#casePanel").querySelectorAll("[data-decision]").forEach((button) => {
    button.addEventListener("click", () => submitDecision(data.task.task_id, button.dataset.decision));
  });
}

async function submitDecision(taskId, decision) {
  const reason = $("#decisionReason").value.trim();
  if (!reason) {
    alert("请先填写裁定理由。");
    return;
  }
  await api(`/api/v1/review/human/${taskId}/decide`, {
    method: "POST",
    body: JSON.stringify({ decision, reason, reviewer_id: "reviewer_demo" }),
  });
  state.selectedTaskId = null;
  $("#casePanel").innerHTML = `<div class="empty-state">裁定已提交。</div>`;
  await refreshAll();
}

async function loadAudit() {
  const audit = await api("/api/v1/audit");
  $("#auditList").innerHTML = audit.items.length
    ? audit.items
        .map(
          (item) => `
          <div class="audit-entry">
            <strong>${escapeHtml(actionText(item.action))}</strong>
            <div>
              <div>${escapeHtml(item.actor)} · ${escapeHtml(item.created_at)}</div>
              <code>${escapeHtml(item.entry_hash)}</code>
            </div>
          </div>
        `
        )
        .join("")
    : `<div class="empty-state">暂无审计事件。</div>`;
}

function actionText(action) {
  const labels = {
    content_queued: "内容入队",
    pipeline_started: "流水线启动",
    evidence_extracted: "证据提取完成",
    machine_review_completed: "机审完成",
    human_review_task_created: "人审任务创建",
    task_claimed: "任务领取",
    human_decision_submitted: "人审裁定提交",
    pipeline_failed: "流水线失败",
  };
  return labels[action] ?? action;
}

async function refreshAll() {
  await Promise.all([loadSummary(), loadPipelineJobs(), loadQueue(), loadAudit()]);
}

document.querySelectorAll(".nav-item").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
    document.querySelectorAll(".view").forEach((view) => view.classList.remove("active-view"));
    button.classList.add("active");
    $(`#${button.dataset.view}View`).classList.add("active-view");
  });
});

$("#refreshBtn").addEventListener("click", refreshAll);
$("#seedBtn").addEventListener("click", async () => {
  await api("/api/v1/dev/seed", { method: "POST", body: "{}" });
  await refreshAll();
});

$("#uploadForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
  await api("/api/v1/content/upload", { method: "POST", body: JSON.stringify(payload) });
  document.querySelector('[data-view="machine"]').click();
  await refreshAll();
});

$("#batchUploadForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const raw = new FormData(event.currentTarget).get("items_json");
  let items;
  try {
    items = JSON.parse(raw);
  } catch (error) {
    $("#batchUploadResult").textContent = "JSON 格式不正确";
    return;
  }
  if (!Array.isArray(items)) {
    $("#batchUploadResult").textContent = "请输入 JSON 数组";
    return;
  }
  const result = await api("/api/v1/content/batch", {
    method: "POST",
    body: JSON.stringify({ items }),
  });
  $("#batchUploadResult").textContent = `已接收 ${result.accepted} 条，失败 ${result.failed} 条`;
  document.querySelector('[data-view="machine"]').click();
  await refreshAll();
});

loadConfig().then(refreshAll).catch((error) => {
  document.body.innerHTML = `<pre>${escapeHtml(error.message)}</pre>`;
});

setInterval(() => {
  refreshAll().catch(() => undefined);
}, 3000);
