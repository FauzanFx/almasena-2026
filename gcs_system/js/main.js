(function () {
  "use strict";

  const S = {
    missionSec: 0,
    lastLogSignature: "",
    lastQrResult: "",
    isCamSwapped: false,
    pidChartData: []
  };

  // 1. Mission Clock
  setInterval(() => {
    S.missionSec++;
    const clockEl = document.getElementById("tb-clock");
    if (clockEl) {
      const h = String(Math.floor(S.missionSec / 3600)).padStart(2, "0");
      const m = String(Math.floor((S.missionSec % 3600) / 60)).padStart(2, "0");
      const s = String(S.missionSec % 60).padStart(2, "0");
      clockEl.textContent = `${h}:${m}:${s}`;
    }
  }, 1000);

  // 2. System Logger
  function appendLog(ts, msg, type) {
    const logTerminal = document.getElementById("log-terminal");
    if (!logTerminal) return;

    const colors = {
      info: "rgba(52,211,153,.6)",
      warn: "rgba(245,158,11,.65)",
      err: "rgba(239,68,68,.7)",
      sys: "rgba(6,182,212,.55)",
    };

    const el = document.createElement("div");
    el.style.cssText = "display:flex;gap:5px;font-size:7px;letter-spacing:.04em;line-height:1.65;";
    el.innerHTML = `<span style="color:rgba(52,211,153,.28);flex-shrink:0;">${ts}</span><span style="color:${colors[type] || colors.info};">${msg}</span>`;

    logTerminal.appendChild(el);
    while (logTerminal.children.length > 30) {
      logTerminal.removeChild(logTerminal.firstChild);
    }
    logTerminal.scrollTop = logTerminal.scrollHeight;
  }

  /* ── MODE SELECTION (MANUAL VS AUTONOMOUS) ── */
  window.setMode = function (m) {
    const isAuto = (m === "auto");

    fetch("/api/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ autonomous_mode: isAuto })
    }).catch((err) => console.error("Error sending command:", err));

    updateModeUI(isAuto);
    appendLog("00:00", `Mode Command Sent: ${isAuto ? "AUTONOMOUS" : "MANUAL"}`, "sys");
  };

  function updateModeUI(isAuto) {
    const btnManual = document.getElementById("btn-manual");
    const btnAuto = document.getElementById("btn-auto");
    const modeBadge = document.getElementById("mode-badge");

    if (btnManual) btnManual.classList.toggle("active", !isAuto);
    if (btnAuto) btnAuto.classList.toggle("active", isAuto);
    if (modeBadge) modeBadge.textContent = isAuto ? "AUTONOMOUS" : "MANUAL";
  }

  /* ── PID SETTINGS MODAL CONTROLLER ── */
  window.togglePIDModal = function (show) {
    const modal = document.getElementById("pid-modal");
    if (modal) {
      if (show) {
        modal.classList.remove("hidden");
        appendLog("00:00", "Ballast PID Settings Window Opened", "sys");
      } else {
        modal.classList.add("hidden");
      }
    }
  };

  /* ── HARDWARE CONTROL (PID & ZEROING) ── */
  window.sendPID = function () {
    const kp = parseFloat(document.getElementById("pid-kp").value);
    const ki = parseFloat(document.getElementById("pid-ki").value);
    const kd = parseFloat(document.getElementById("pid-kd").value);

    fetch("/api/hardware", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: "set_pid", kp: kp, ki: ki, kd: kd })
    }).catch(err => console.error("PID Send Error:", err));

    appendLog("00:00", `Ballast PID Saved -> Kp:${kp}, Ki:${ki}, Kd:${kd}`, "warn");
  };

  window.sendZeroing = function () {
    fetch("/api/hardware", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: "zeroing" })
    }).catch(err => console.error("Zeroing Error:", err));

    appendLog("00:00", "Zeroing Encoder Command Dispatched", "warn");
  };

  /* ── LIVE PID RESPONSE GRAPH ── */
  function updatePIDChart(targetVal, currentVal) {
    const canvas = document.getElementById("pid-chart");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    S.pidChartData.push({ t: targetVal, c: currentVal });
    if (S.pidChartData.length > 60) S.pidChartData.shift();

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    ctx.strokeStyle = "rgba(6,182,212,0.15)";
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    for (let i = 0; i < canvas.width; i += 20) { ctx.moveTo(i, 0); ctx.lineTo(i, canvas.height); }
    for (let i = 0; i < canvas.height; i += 20) { ctx.moveTo(0, i); ctx.lineTo(canvas.width, i); }
    ctx.stroke();

    if (S.pidChartData.length < 2) return;

    let minVal = Math.min(...S.pidChartData.map(pt => Math.min(pt.t, pt.c)));
    let maxVal = Math.max(...S.pidChartData.map(pt => Math.max(pt.t, pt.c)));

    let range = maxVal - minVal;
    if (range === 0) range = 100;
    minVal -= range * 0.2;
    maxVal += range * 0.2;
    range = maxVal - minVal;

    const step = canvas.width / 59;

    // 1. PLOT TARGET (Garis Putus-putus Oranye)
    ctx.beginPath();
    ctx.strokeStyle = "rgba(245,158,11,0.8)";
    ctx.setLineDash([3, 3]);
    ctx.lineWidth = 1;
    S.pidChartData.forEach((pt, i) => {
      const x = i * step;
      const y = canvas.height - ((pt.t - minVal) / range) * canvas.height;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.setLineDash([]);

    // 2. PLOT ACTUAL (Garis Solid Cyan)
    ctx.beginPath();
    ctx.strokeStyle = "#22d3ee";
    ctx.lineWidth = 1.5;
    S.pidChartData.forEach((pt, i) => {
      const x = i * step;
      const y = canvas.height - ((pt.c - minVal) / range) * canvas.height;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }

  /* ── CAMERA STREAM SWAP HANDLER ── */
  window.swapCams = function () {
    S.isCamSwapped = !S.isCamSwapped;

    const mainCam = document.getElementById("main-cam");
    const pipCam = document.getElementById("pip-cam");
    const mainLabel = document.getElementById("cam-label-main");
    const pipLabel = document.getElementById("pip-label");

    const ts = Date.now();

    if (S.isCamSwapped) {
      if (mainCam) mainCam.src = `/video/bottom?t=${ts}`;
      if (pipCam) pipCam.src = `/video/front?t=${ts}`;
      if (mainLabel) mainLabel.textContent = "BTM CAM-02 (BOTTOM)";
      if (pipLabel) pipLabel.textContent = "FWD CAM-01";
      appendLog("00:00", "Cam Swapped: BTM CAM is now Primary", "sys");
    } else {
      if (mainCam) mainCam.src = `/video/front?t=${ts}`;
      if (pipCam) pipCam.src = `/video/bottom?t=${ts}`;
      if (mainLabel) mainLabel.textContent = "FWD CAM-01 (FORWARD)";
      if (pipLabel) pipLabel.textContent = "BTM CAM-02";
      appendLog("00:00", "Cam Swapped: FWD CAM is now Primary", "sys");
    }
  };

  /* ── TELEMETRY UI RENDERER ── */
  function updateTelemetryUI(data) {
    if (!data) return;

    if (data.autonomous_active !== undefined) {
      updateModeUI(Boolean(data.autonomous_active));
    }

    // Ping / Latency
    const pingMs = data.ping_ms !== undefined ? data.ping_ms : 0;
    const pingVal = document.getElementById("ping-val");
    const tbPing = document.getElementById("tb-ping");
    if (pingVal) pingVal.textContent = `${pingMs} ms`;
    if (tbPing) tbPing.textContent = `${pingMs}ms`;

    // Depth & Compass
    const depth = data.depth_raw !== undefined ? data.depth_raw : 0.0;
    const heading = data.heading !== undefined ? data.heading : 0.0;
    const roll = data.roll !== undefined ? data.roll : 0.0;
    const pitch = data.pitch !== undefined ? data.pitch : 0.0;

    const depthVal = document.getElementById("depth-val");
    const depthFill = document.getElementById("depth-fill");
    const qsDepth = document.getElementById("qs-depth");
    if (depthVal) depthVal.innerHTML = `${depth.toFixed(1)}<br/><span style="font-size:6px;color:rgba(6,182,212,.4);">m</span>`;
    if (depthFill) depthFill.style.height = `${Math.min(100, Math.max(0, (depth / 8) * 100))}%`;
    if (qsDepth) qsDepth.textContent = `${depth.toFixed(1)}m`;

    const compassStrip = document.getElementById("compass-strip");
    const hdgVal = document.getElementById("hdg-val");
    const qsHdg = document.getElementById("qs-hdg");
    if (compassStrip) compassStrip.style.transform = `translateX(${-(heading / 360) * 400}px)`;
    if (hdgVal) hdgVal.textContent = `${String(Math.round(heading)).padStart(3, "0")}°`;
    if (qsHdg) qsHdg.textContent = `${String(Math.round(heading)).padStart(3, "0")}°`;

    // IMU Roll & Pitch
    const rollVal = document.getElementById("roll-val");
    const pitchVal = document.getElementById("pitch-val");
    const rpReadout = document.getElementById("rp-readout");

    if (rollVal) rollVal.textContent = `${roll >= 0 ? "+" : ""}${roll.toFixed(1)}°`;
    if (pitchVal) pitchVal.textContent = `${pitch >= 0 ? "+" : ""}${pitch.toFixed(1)}°`;
    if (rpReadout) rpReadout.textContent = `R${roll >= 0 ? "+" : ""}${roll.toFixed(1)}° P${pitch >= 0 ? "+" : ""}${pitch.toFixed(1)}°`;

    const ahiSky = document.getElementById("ahi-sky");
    const ahiGnd = document.getElementById("ahi-gnd");
    const ahiLine = document.getElementById("ahi-line");
    const t = `rotate(${roll}deg) scaleX(1.7)`;
    if (ahiSky) ahiSky.style.transform = t;
    if (ahiGnd) ahiGnd.style.transform = t;
    if (ahiLine) ahiLine.style.transform = `translateY(calc(-50% + ${pitch * 2.5}px)) rotate(${roll}deg) scaleX(1.7)`;

    // Ballast Status
    const ballastPct = data.ballast_pct !== undefined ? data.ballast_pct : 0;
    const ballastStatus = data.ballast_status || "IDLE";
    const ballastVal = document.getElementById("ballast-val");
    const ballastBar = document.getElementById("ballast-bar");
    const ballastStatusEl = document.getElementById("ballast-status");
    const qsBallast = document.getElementById("qs-ballast");

    if (ballastVal) ballastVal.textContent = `${ballastPct}%`;
    if (ballastBar) ballastBar.style.width = `${ballastPct}%`;
    if (ballastStatusEl) ballastStatusEl.textContent = ballastStatus;
    if (qsBallast) qsBallast.textContent = `${ballastPct}%`;

    // Mapping Real Thrusters Input (-1000..1000 -> -100%..100%)
    const surgeCmd = data.surge_cmd !== undefined ? data.surge_cmd : 0;
    const pitchCmd = data.pitch_cmd !== undefined ? data.pitch_cmd : 0;
    const yawCmd = data.yaw_cmd !== undefined ? data.yaw_cmd : 0;
    const yawPct = Math.round((yawCmd / 1000.0) * 100);
    const fwdPct = Math.round((surgeCmd / 1000.0) * 100);
    const vertPct = Math.round((pitchCmd / 1000.0) * 100);

    const tbarFwd = document.getElementById("tbar-fwd");
    const tvalFwd = document.getElementById("tval-fwd");
    if (tbarFwd) tbarFwd.style.width = `${Math.abs(fwdPct)}%`;
    if (tvalFwd) tvalFwd.textContent = `${fwdPct >= 0 ? "+" : ""}${fwdPct}%`;

    const tbarVert = document.getElementById("tbar-vert");
    const tvalVert = document.getElementById("tval-vert");
    if (tbarVert) tbarVert.style.width = `${Math.abs(vertPct)}%`;
    if (tvalVert) tvalVert.textContent = `${vertPct >= 0 ? "+" : ""}${vertPct}%`;

    const tbarYaw = document.getElementById("tbar-yaw");
    const tvalYaw = document.getElementById("tval-yaw");
    if (tbarYaw) tbarYaw.style.width = `${Math.abs(yawPct)}%`;
    if (tvalYaw) tvalYaw.textContent = `${yawPct >= 0 ? "+" : ""}${yawPct}%`;

    // Render Grafik PID Response (Berjalan otomatis di background / modal)
    const targetStm = data.target_stm32 !== undefined ? data.target_stm32 : 0;
    const currentStm = data.encoder_ticks !== undefined ? data.encoder_ticks : 0;
    updatePIDChart(targetStm, currentStm);

    // Sync Mission Log Terminal
    if (data.ship_logs && Array.isArray(data.ship_logs) && data.ship_logs.length > 0) {
      const latestLog = data.ship_logs[data.ship_logs.length - 1];
      const sig = `${latestLog.ts}_${latestLog.msg}`;
      if (sig !== S.lastLogSignature) {
        const logTerminal = document.getElementById("log-terminal");
        if (logTerminal) {
          logTerminal.innerHTML = "";
          data.ship_logs.forEach((l) => appendLog(l.ts, l.msg, l.type));
        }
        S.lastLogSignature = sig;
      }
    }

    // QR is scanned on the Raspberry Pi and forwarded by main_gcs_alter.py.
    const scannedQr = String(data.qr_data || "").trim();
    const qrResult = document.getElementById("qr-result");
    if (scannedQr) {
      if (qrResult) {
        qrResult.textContent = scannedQr;
        qrResult.style.color = "#34d399";
      }
      if (scannedQr !== S.lastQrResult) {
        S.lastQrResult = scannedQr;
        appendLog("QR", `QR BERHASIL DI-SCAN! Hasil: ${scannedQr}`, "info");
      }
    }
  }

  // 5. WebSocket Client dengan Auto-Reconnect
  function connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = function () {
      appendLog("00:00", "Telemetry Tether Connected", "sys");
    };

    ws.onmessage = function (event) {
      try {
        const data = JSON.parse(event.data);
        updateTelemetryUI(data);
      } catch (err) {
        console.error("JSON Parse Error:", err);
      }
    };

    ws.onclose = function () {
      setTimeout(connectWebSocket, 2000);
    };
  }

  appendLog("00:00", "GUI Init Complete", "sys");
  connectWebSocket();
})();
