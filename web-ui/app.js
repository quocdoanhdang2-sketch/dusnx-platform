const $ = (id) => document.getElementById(id);
const gateway = window.DUSNX_GATEWAY || "http://localhost:8080";
let nextTimelineCursor = null;

const show = (id, value) => {
  $(id).textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
};

const text = (tag, value, className) => {
  const element = document.createElement(tag);
  if (className) element.className = className;
  element.textContent = value ?? "—";
  return element;
};

const timelineUrl = (cursor) => {
  const platform = encodeURIComponent($("platform").value);
  const user = encodeURIComponent($("user").value.trim());
  const params = new URLSearchParams({limit: "25"});
  const linked = $("linked").value.trim();
  if (linked) params.set("linkedUserId", linked);
  if (cursor) params.set("before", cursor);
  return `${gateway}/api/v1/history/${platform}/${user}?${params}`;
};

const addField = (container, label, value) => {
  if (value === null || value === undefined || value === "") return;
  const row = text("div", "", "timeline-field");
  row.append(text("strong", `${label}: `), text("span", String(value)));
  container.append(row);
};

const renderTimelineItem = (item) => {
  const card = text("article", "", `timeline-item platform-${item.platform || "unknown"}`);
  const header = text("div", "", "timeline-header");
  header.append(
    text("span", item.platform || "unknown", "platform-badge"),
    text("time", item.event_time_utc || "Không có thời điểm")
  );
  card.append(header, text("p", item.content || "(record cũ không có nội dung)", "timeline-content"));
  const details = text("div", "", "timeline-details");
  addField(details, "event", item.event_type);
  addField(details, "intent", item.intent);
  addField(details, "agent", item.selected_agent);
  addField(details, "next action (đề xuất)", item.next_action);
  addField(details, "confidence", item.confidence);
  addField(details, "routing", item.routing_source);
  addField(details, "feedback đã biết", item.known_feedback_value);
  addField(details, "state version", item.state_version);
  addField(details, "runtime", item.runtime_mode);
  addField(details, "model", item.model_version);
  if (item.state_reset !== null && item.state_reset !== undefined)
    addField(details, "state reset", item.state_reset ? `có — ${item.reset_reason || "không có lý do"}` : "không");
  card.append(details);
  return card;
};

const loadTimeline = async ({append = false} = {}) => {
  const list = $("timeline");
  const status = $("timelineStatus");
  if (!$("user").value.trim()) {
    status.textContent = "Nhập platform user ID trước khi tải timeline.";
    return;
  }
  status.textContent = "Đang tải timeline…";
  $("reloadTimeline").disabled = true;
  $("loadOlder").disabled = true;
  try {
    const response = await fetch(timelineUrl(append ? nextTimelineCursor : null));
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || body.title || JSON.stringify(body));
    if (!append) list.replaceChildren();
    for (const item of body.items) list.append(renderTimelineItem(item));
    nextTimelineCursor = body.next_cursor;
    $("loadOlder").hidden = !body.has_more;
    const total = list.childElementCount;
    status.textContent = total === 0
      ? "Chưa có event cho identity này."
      : `Đang hiển thị ${total} event, mới nhất trước.`;
  } catch (error) {
    status.textContent = `Không tải được timeline: ${error.message}`;
  } finally {
    $("reloadTimeline").disabled = false;
    $("loadOlder").disabled = false;
  }
};

$("send").onclick = async () => {
  $("output").textContent = "Đang xử lý…";
  const payload = {
    platform: $("platform").value,
    platformUserId: $("user").value,
    content: $("content").value,
    eventType: "message",
    feedbackValue: Number($("feedback").value || 0),
    linkedUserId: $("linked").value
  };
  try {
    const response = await fetch(`${gateway}/api/v1/events`, {
      method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(payload)
    });
    const body = await response.json();
    if (!response.ok) throw new Error(JSON.stringify(body));
    show("output", {
      intent: body.intent,
      selected_agent: body.selected_agent,
      next_action_proposal: body.next_action,
      confidence: body.confidence,
      state_version: body.state_snapshot?.state_version,
      runtime_mode: body.runtime_mode,
      routing_source: body.routing_source,
      agent_output: body.agent_output
    });
    await loadTimeline();
  } catch (error) {
    $("output").textContent = `Lỗi: ${error.message}`;
  }
};

$("reloadTimeline").onclick = () => loadTimeline();
$("loadOlder").onclick = () => loadTimeline({append: true});

$("generateSlides").onclick = async () => {
  show("jobOutput", "Đang tạo job...");
  try {
    const response = await fetch(`${gateway}/api/v1/presentations/generations`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        platformUserId: $("user").value,
        linkedUserId: $("linked").value,
        prompt: $("slidePrompt").value,
        slideCount: Number($("slideCount").value || 5)
      })
    });
    const job = await response.json();
    if (!response.ok) throw new Error(JSON.stringify(job));
    show("jobOutput", job);
    while (true) {
      await new Promise(resolve => setTimeout(resolve, 600));
      const statusResponse = await fetch(`${gateway}/api/v1/jobs/${job.jobId}`);
      const status = await statusResponse.json();
      show("jobOutput", status);
      if (["completed", "failed"].includes(status.status)) {
        if (status.status === "completed") await loadTimeline();
        break;
      }
    }
  } catch (error) {
    show("jobOutput", `Lỗi: ${error.message}`);
  }
};

if (typeof module !== "undefined") {
  module.exports = {renderTimelineItem, timelineUrl};
}
