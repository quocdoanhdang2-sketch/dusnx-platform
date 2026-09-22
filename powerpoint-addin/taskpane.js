Office.onReady(() => {
  document.getElementById("run").onclick = async () => {
    const out = document.getElementById("out");
    out.textContent = "Đang xử lý...";
    let selectedText = "";
    try {
      await PowerPoint.run(async (context) => {
        // PowerPoint JS APIs vary by requirement set. This MVP uses prompt text as primary context.
        // Add selected-slide extraction when your target Office version supports the needed API.
        await context.sync();
      });
      const payload = {
        platformUserId: document.getElementById("user").value,
        prompt: document.getElementById("prompt").value + (selectedText ? `\n${selectedText}` : ""),
        slideCount: Number(document.getElementById("slideCount").value || 5),
        linkedUserId: document.getElementById("linked").value,
      };
      const response = await fetch("http://localhost:8080/api/v1/presentations/generations", {
        method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(payload)
      });
      const job = await response.json();
      if (!response.ok) throw new Error(JSON.stringify(job));
      out.textContent = JSON.stringify(job, null, 2);
      while (true) {
        await new Promise(resolve => setTimeout(resolve, 700));
        const statusResponse = await fetch(`http://localhost:8080/api/v1/jobs/${job.jobId}`);
        const status = await statusResponse.json();
        out.textContent = JSON.stringify(status, null, 2);
        if (["completed", "failed"].includes(status.status)) break;
      }
    } catch (e) { out.textContent = String(e); }
  };
});
