"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  let auth = "", selected = null, lease = "", revision = 0, objectURL = null;
  let controls = [], pollBusy = false;
  function requestId() {
    // getRandomValues also works for the network-free, in-memory demo document.
    return Array.from(crypto.getRandomValues(new Uint8Array(16)), value => value.toString(16).padStart(2, "0")).join("");
  }
  function log(message) {
    const lines = $("activity").textContent.split("\n").slice(-40);
    lines.push(new Date().toLocaleTimeString() + "  " + message);
    $("activity").textContent = lines.join("\n");
  }
  async function api(path, method = "GET", body, image = false) {
    const headers = { Authorization: "Bearer " + auth };
    if (lease) headers["X-Control-Token"] = lease;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const response = await fetch(path, {method, headers, body: body === undefined ? undefined : JSON.stringify(body), cache:"no-store"});
    if (!response.ok) {
      const result = await response.json().catch(() => ({}));
      throw new Error(result.code || (result.detail && result.detail.code) || "REQUEST_FAILED");
    }
    return image ? response.blob() : response.json();
  }
  const path = () => "/api/operator/runs/" + selected;
  function buttons(state) {
    const owned = state === "HUMAN" && Boolean(lease);
    $("claim").disabled = state !== "PAUSED";
    for (const id of ["renew","resume","act","refresh-screen","control"]) $(id).disabled = !owned;
    $("cancel").disabled = !selected || state === "FINISHED";
    $("state").textContent = state;
  }
  async function loadScreen() {
    if (!lease) return;
    const blob = await api(path() + "/screenshot?revision=" + revision, "GET", undefined, true);
    if (objectURL) URL.revokeObjectURL(objectURL);
    objectURL = URL.createObjectURL(blob);
    $("screen").src = objectURL; $("screen").hidden = false; $("screen-placeholder").hidden = true;
    controls = (await api(path() + "/controls?revision=" + revision)).controls;
    $("control").replaceChildren();
    controls.forEach((control, index) => {
      const option = document.createElement("option"); option.value = String(index);
      option.textContent = control.label + " / " + control.kind + (control.risk === "forbidden" ? " / BLOCKED" : "");
      option.disabled = control.risk === "forbidden" || !control.enabled;
      $("control").append(option);
    });
    const allowed = controls.findIndex(item => item.enabled && item.risk !== "forbidden");
    $("control").value = String(allowed);
    $("act").disabled = allowed < 0;
  }
  async function show(run) {
    if (selected !== run.run_id) lease = "";
    selected = run.run_id;
    if (run.control.state !== "HUMAN" || run.control.revision !== revision) lease = "";
    revision = run.control.revision;
    const context = run.control.intervention;
    $("context").textContent = context ? context.code + ": automation is paused at a checked boundary." : "Automation owns this session, or the run has finished.";
    $("details").replaceChildren();
    for (const [label, value] of [["Run",run.run_id],["Session",run.session_id],["Capability",run.capability],["Step",run.step],["Lease",run.control.lease_remaining_seconds + " seconds"]]) {
      const dt = document.createElement("dt"), dd = document.createElement("dd");
      dt.textContent = label; dd.textContent = String(value); $("details").append(dt,dd);
    }
    buttons(run.control.state);
    if (!lease) { $("screen").hidden = true; $("screen-placeholder").hidden = false; }
  }
  async function refresh() {
    if (!auth || pollBusy) return;
    pollBusy = true;
    try {
      const result = await api("/api/operator/interventions");
      $("queue").replaceChildren();
      if (!result.interventions.length) {
        const empty = document.createElement("p"); empty.className = "empty";
        empty.textContent = "No interventions waiting. Automation is clear to continue."; $("queue").append(empty);
      }
      result.interventions.forEach(run => {
        const button = document.createElement("button"); button.className = "run-item";
        button.textContent = run.control.intervention.code;
        const small = document.createElement("small"); small.textContent = run.run_id.slice(0,12) + " / step " + run.step;
        button.append(small); button.addEventListener("click", () => guarded(() => show(run))); $("queue").append(button);
      });
      if (selected) await show(await api(path()));
      $("connection-status").textContent = "Connected. " + result.interventions.length + " live intervention(s).";
    } finally { pollBusy = false; }
  }
  async function guarded(operation) { try { await operation(); } catch (error) { log(error.message); } }
  $("connect").onclick = () => guarded(async () => {
    auth = $("token").value.trim(); $("token").value = "";
    lease = ""; selected = null;
    await refresh(); $("refresh").disabled = false; log("Operator connection established.");
  });
  $("refresh").onclick = () => guarded(refresh);
  $("claim").onclick = () => guarded(async () => {
    const result = await api(path() + "/claim", "POST", {revision});
    lease = result.control_token; revision = result.revision;
    buttons("HUMAN"); await loadScreen(); log("Human control claimed on the same live session.");
  });
  $("renew").onclick = () => guarded(async () => { await api(path()+"/renew","POST",{revision}); log("Control lease renewed."); });
  $("resume").onclick = () => guarded(async () => {
    await api(path()+"/resume","POST",{revision}); lease = "";
    log("Control returned. Automation will recheck the live state."); await refresh();
  });
  $("cancel").onclick = () => guarded(async () => {
    await api(path()+"/cancel","POST",{}); lease = ""; log("Run cancelled; browser closed."); await refresh();
  });
  $("refresh-screen").onclick = () => guarded(loadScreen);
  $("act").onclick = () => guarded(async () => {
    const selectedControl = controls[Number($("control").value)];
    if (!selectedControl || selectedControl.risk === "forbidden") return;
    const action = {kind:selectedControl.kind,target:selectedControl.key};
    if (action.kind === "fill") action.parameter = "member_id";
    if (action.kind === "extract") action.output = selectedControl.key;
    await api(path()+"/actions","POST",{revision,request_id:requestId(),action});
    log("Applied reviewed control: " + selectedControl.key + "."); await loadScreen();
  });
  setInterval(() => guarded(refresh), 3000);
  window.addEventListener("beforeunload", () => { auth = lease = ""; if (objectURL) URL.revokeObjectURL(objectURL); });
})();
