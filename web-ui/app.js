const $ = (id) => document.getElementById(id);
const gateway = window.DUSNX_GATEWAY || "http://localhost:8080";

const show = (id, value) => {
  $(id).textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
};

$("send").onclick = async () => {
  $("output").textContent = "Đang xử lý...";
  const payload = {
    platform: $("platform").value,
    platformUserId: $("user").value,
    content: $("content").value,
    eventType: "message",
    feedbackValue: Number($("feedback").value || 0),
    linkedUserId: $("linked").value
  };
  try {
    const r = await fetch(`${gateway}/api/v1/events`, {
      method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(payload)
    });
    const text = await r.text();
    if (!r.ok) throw new Error(text);
    const data = JSON.parse(text);
    show("output", {
      intent: data.intent,
      selected_agent: data.selected_agent,
      next_action: data.next_action,
      confidence: data.confidence,
      state_version: data.state_snapshot?.state_version,
      runtime_mode: data.runtime_mode,
      agent_output: data.agent_output
    });
  } catch (e) {
    $("output").textContent = "Lỗi: " + e.message;
  }
};

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
      if (["completed", "failed"].includes(status.status)) break;
    }
  } catch (error) {
    show("jobOutput", `Lỗi: ${error.message}`);
  }
};
