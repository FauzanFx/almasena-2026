(function () {
  "use strict";

  const S = {
    missionSec: 0,
    lastLogSignature: "",
    lastQrResult: "",
    lastQrOverlay: null,
    isCamSwapped: false,
    pidChartData: [],

    // State Replay Mode
    isReplayMode: false,
    activeSessionId: "",
    replayData: [],
    replayDurationMs: 0,
    replayCurrentMs: 0,
    replayPlaying: false,
    replayTimer: null,
    lastFrameFetchTime: 0
  };

  // ── MISI TIMER CLOCK ──
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

  // ── KONTROL MODE MISI ──
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

  // ── PID ACTUATOR MODAL ──
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

  // ── DISARM (SAFETY CUTOFF) ──
  window.disarmROV = function () {
    fetch("/api/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: "disarm" })
    }).catch(err => console.error("Disarm Error:", err));

    appendLog("00:00", "DISARM COMMAND SENT — THRUSTERS DISABLED", "err");
  };

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

  // ── KAMERA PIP & SWAP ──
  window.swapCams = function () {
    S.isCamSwapped = !S.isCamSwapped;
    const mainCam = document.getElementById("main-cam");
    const pipCam = document.getElementById("pip-cam");
    const pipLabel = document.getElementById("pip-label");
    const ts = Date.now();

    if (S.isReplayMode) {
      updateReplayFrames(S.replayCurrentMs);
      return;
    }

    if (S.isCamSwapped) {
      if (mainCam) mainCam.src = `/video/bottom?t=${ts}`;
      if (pipCam) pipCam.src = `/video/front?t=${ts}`;
      if (pipLabel) pipLabel.textContent = "FWD CAM-01";
      appendLog("00:00", "Cam Swapped: BTM CAM is now Primary", "sys");
    } else {
      if (mainCam) mainCam.src = `/video/front?t=${ts}`;
      if (pipCam) pipCam.src = `/video/bottom?t=${ts}`;
      if (pipLabel) pipLabel.textContent = "BTM CAM-02";
      appendLog("00:00", "Cam Swapped: FWD CAM is now Primary", "sys");
    }
  };

  // ── QR BOUNDING BOX OVERLAY ──
  function renderQrOverlay(qrData) {
    const overlay = document.getElementById("qr-overlay");
    const label = document.getElementById("qr-overlay-label");
    const frame = document.getElementById("fpv-zone");
    const mainCam = document.getElementById("main-cam");
    const bbox = qrData.qr_bbox;
    const isPrimaryCamera = qrData.qr_camera === (S.isCamSwapped ? "bottom" : "front");

    if (!overlay || !label || !frame || !mainCam || !qrData.qr_data || !isPrimaryCamera ||
        !Array.isArray(bbox) || bbox.length !== 4) {
      if (overlay) overlay.style.display = "none";
      return;
    }

    const [x, y, width, height] = bbox.map(Number);
    if (![x, y, width, height].every(Number.isFinite) || width <= 0 || height <= 0) {
      overlay.style.display = "none";
      return;
    }

    const frameRect = frame.getBoundingClientRect();
    const imageRect = mainCam.getBoundingClientRect();
    const sourceWidth = mainCam.naturalWidth || 640;
    const sourceHeight = mainCam.naturalHeight || 360;
    const scale = Math.max(imageRect.width / sourceWidth, imageRect.height / sourceHeight);
    const drawnWidth = sourceWidth * scale;
    const drawnHeight = sourceHeight * scale;
    const cropX = (imageRect.width - drawnWidth) / 2;
    const cropY = (imageRect.height - drawnHeight) / 2;

    overlay.style.display = "block";
    overlay.style.left = `${imageRect.left - frameRect.left + cropX + x * drawnWidth}px`;
    overlay.style.top = `${imageRect.top - frameRect.top + cropY + y * drawnHeight}px`;
    overlay.style.width = `${width * drawnWidth}px`;
    overlay.style.height = `${height * drawnHeight}px`;
    label.textContent = `QR: ${qrData.qr_data}`;
  }

  // ── UPDATE UI TELEMETRI REALTIME (WS) ──
  function updateTelemetryUI(data) {
    if (!data) return;

    // Mode Otonom status
    if (data.autonomous_active !== undefined) {
      updateModeUI(Boolean(data.autonomous_active));
    }

    // Indikator Status Auto-Log / Recording Hybrid
    const btnAutoLog = document.getElementById("btn-autolog");
    if (btnAutoLog) {
      if (data.is_recording_active) {
        btnAutoLog.textContent = "⏺ REC: ACTIVE";
        btnAutoLog.style.borderColor = "var(--danger-bright)";
        btnAutoLog.style.color = "var(--danger-bright)";
      } else if (data.auto_log_enabled) {
        btnAutoLog.textContent = "⏺ REC: STANDBY";
        btnAutoLog.style.borderColor = "var(--warn-bright)";
        btnAutoLog.style.color = "var(--warn-bright)";
      } else {
        btnAutoLog.textContent = "⏺ Auto-Log: OFF";
        btnAutoLog.style.borderColor = "var(--border)";
        btnAutoLog.style.color = "var(--primary)";
      }
    }

    const pingMs = data.ping_ms !== undefined ? data.ping_ms : 0;
    const pingVal = document.getElementById("ping-val");
    const tbPing = document.getElementById("tb-ping");
    if (pingVal) pingVal.textContent = `${pingMs} ms`;
    if (tbPing) tbPing.textContent = `${pingMs}ms`;

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

    if (typeof data.altitude === "number" && !isNaN(data.altitude) &&
        typeof window.renderAltitude === "function") {
      window.renderAltitude(data.altitude);
    }

    const compassStrip = document.getElementById("compass-strip");
    const hdgVal = document.getElementById("hdg-val");
    const qsHdg = document.getElementById("qs-hdg");
    if (compassStrip) compassStrip.style.transform = `translateX(${-(heading / 360) * 400}px)`;
    if (hdgVal) hdgVal.textContent = `${String(Math.round(heading)).padStart(3, "0")}°`;
    if (qsHdg) qsHdg.textContent = `${String(Math.round(heading)).padStart(3, "0")}°`;

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

    const targetStm = data.target_stm32 !== undefined ? data.target_stm32 : 0;
    const currentStm = data.encoder_ticks !== undefined ? data.encoder_ticks : 0;
    updatePIDChart(targetStm, currentStm);

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

    const scannedQr = String(data.qr_data || "").trim();
    const qrResult = document.getElementById("qr-result");
    const qrConfirm = document.getElementById("qr-confirm");
    if (scannedQr) {
      if (qrResult) {
        qrResult.textContent = scannedQr;
        qrResult.style.color = "#34d399";
      }
      if (scannedQr !== S.lastQrResult) {
        S.lastQrResult = scannedQr;
        appendLog("QR", `QR BERHASIL DI-SCAN! Hasil: ${scannedQr}`, "info");

        if (qrConfirm) {
          qrConfirm.textContent = "QR berhasil dipindai. Gripper siap dioperasikan.";
          qrConfirm.style.display = "block";
        }

        const qrCamera = data.qr_camera;
        const shouldShowBottom = qrCamera === "bottom";
        if ((shouldShowBottom && !S.isCamSwapped) || (!shouldShowBottom && S.isCamSwapped)) {
          window.swapCams();
        }
      }
    }

    S.lastQrOverlay = {
      qr_data: scannedQr,
      qr_camera: data.qr_camera,
      qr_bbox: data.qr_bbox
    };
    renderQrOverlay(S.lastQrOverlay);

    // Injeksi trajectory realtime (hanya jika TIDAK dalam mode replay)
    if (!S.isReplayMode && typeof window.pushTrajectoryPoint === "function" &&
        (typeof data.pos_x === "number" || typeof data.depth_raw === "number")) {
      window.pushTrajectoryPoint({ x: data.pos_x, y: data.pos_y, depth: depth });
    }
  }

  window.addEventListener("resize", () => renderQrOverlay(S.lastQrOverlay || {}));

  // ── WEBSOCKET CONNECTION ──
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

  // ── FITUR SCREENSHOT & HYBRID AUTOLOG ──
  window.takeScreenshot = function () {
    fetch("/api/screenshot", { method: "POST" })
      .then(res => res.json())
      .then(data => {
        if (data.status === "ok") {
          appendLog("SNAP", `Screenshot Dual-Cam tersimpan di folder disk!`, "info");
        }
      })
      .catch(err => console.error("Error screenshot:", err));
  };

  window.toggleAutoLog = function () {
    fetch("/api/record/toggle_autolog", { method: "POST" })
      .then(res => res.json())
      .then(data => {
        if (data.status === "ok") {
          const statusStr = data.auto_log_enabled ? "STANDBY (ARM DIPERLUKAN)" : "OFF";
          appendLog("REC", `Auto-Log Record status: ${statusStr}`, "sys");
          loadReplaySessions();
        }
      })
      .catch(err => console.error("Error toggle autolog:", err));
  };

  // ── LOAD & SELECT REPLAY SESSIONS ──
  function loadReplaySessions() {
    fetch("/api/replay/sessions")
      .then(res => res.json())
      .then(data => {
        const selectEl = document.getElementById("replay-session-select");
        if (!selectEl || !data.sessions) return;

        const currentVal = selectEl.value;
        selectEl.innerHTML = '<option value="">-- [ LIVE MONITORING ] --</option>';

        data.sessions.forEach(s => {
          const opt = document.createElement("option");
          opt.value = s.session_id;
          const dur = s.meta.duration_sec ? `(${s.meta.duration_sec}s)` : "";
          opt.textContent = `${s.session_id} ${dur}`;
          selectEl.appendChild(opt);
        });

        selectEl.value = currentVal;
      })
      .catch(err => console.error("Gagal memuat sesi replay:", err));
  }

  window.onSelectReplaySession = function (sessionId) {
    if (!sessionId) {
      S.isReplayMode = false;
      S.activeSessionId = "";
      stopReplayPlayback();

      const badge = document.getElementById("replay-mode-badge");
      if (badge) {
        badge.textContent = "LIVE";
        badge.className = "font-mono text-rov-em";
      }

      const mainCam = document.getElementById("main-cam");
      const pipCam = document.getElementById("pip-cam");
      const ts = Date.now();
      if (mainCam) mainCam.src = S.isCamSwapped ? `/video/bottom?t=${ts}` : `/video/front?t=${ts}`;
      if (pipCam) pipCam.src = S.isCamSwapped ? `/video/front?t=${ts}` : `/video/bottom?t=${ts}`;

      if (typeof window.clearTrajectoryHistory === "function") {
        window.clearTrajectoryHistory();
      }
      appendLog("00:00", "Beralih ke Live Monitoring", "sys");
      return;
    }

    S.isReplayMode = true;
    S.activeSessionId = sessionId;
    stopReplayPlayback();

    const badge = document.getElementById("replay-mode-badge");
    if (badge) {
      badge.textContent = "REPLAY";
      badge.className = "font-mono text-rov-am";
    }

    appendLog("00:00", `Memuat data rekaman: ${sessionId}`, "sys");

    fetch(`/api/replay/session/${sessionId}`)
      .then(res => res.json())
      .then(res => {
        if (res.status !== "ok") return;

        S.replayData = res.trajectory || [];
        S.replayDurationMs = (res.meta && res.meta.duration_sec) ? res.meta.duration_sec * 1000 : 0;
        if (S.replayDurationMs === 0 && S.replayData.length > 0) {
          S.replayDurationMs = S.replayData[S.replayData.length - 1].elapsed_ms || 1000;
        }

        S.replayCurrentMs = 0;
        const seek = document.getElementById("replay-seek");
        if (seek) seek.value = 0;

        renderReplayFrameAt(0);
      });
  };

  // ── KONTROL PLAYBACK / SCRUBBING ──
  window.replayControl = function (action) {
    if (!S.isReplayMode) {
      appendLog("00:00", "Pilih sesi rekaman terlebih dahulu pada dropdown!", "warn");
      return;
    }

    if (action === "play") {
      if (S.replayPlaying) {
        stopReplayPlayback();
      } else {
        startReplayPlayback();
      }
    } else if (action === "prev") {
      S.replayCurrentMs = Math.max(0, S.replayCurrentMs - 2000);
      renderReplayFrameAt(S.replayCurrentMs);
    } else if (action === "next") {
      S.replayCurrentMs = Math.min(S.replayDurationMs, S.replayCurrentMs + 2000);
      renderReplayFrameAt(S.replayCurrentMs);
    }
  };

  window.replaySeek = function (val) {
    if (!S.isReplayMode || S.replayDurationMs === 0) return;
    S.replayCurrentMs = (val / 100) * S.replayDurationMs;
    renderReplayFrameAt(S.replayCurrentMs);
  };

  function startReplayPlayback() {
    S.replayPlaying = true;
    const btn = document.getElementById("btn-replay-play");
    if (btn) btn.textContent = "⏸";

    S.replayTimer = setInterval(() => {
      S.replayCurrentMs += 100;
      if (S.replayCurrentMs >= S.replayDurationMs) {
        S.replayCurrentMs = S.replayDurationMs;
        stopReplayPlayback();
      }
      renderReplayFrameAt(S.replayCurrentMs);
    }, 100);
  }

  function stopReplayPlayback() {
    S.replayPlaying = false;
    if (S.replayTimer) {
      clearInterval(S.replayTimer);
      S.replayTimer = null;
    }
    const btn = document.getElementById("btn-replay-play");
    if (btn) btn.textContent = "▶";
  }

  function renderReplayFrameAt(timeMs) {
    const seek = document.getElementById("replay-seek");
    if (seek && S.replayDurationMs > 0) {
      seek.value = (timeMs / S.replayDurationMs) * 100;
    }

    const curSec = Math.floor(timeMs / 1000);
    const totSec = Math.floor(S.replayDurationMs / 1000);
    const timeDisplay = document.getElementById("replay-time-display");
    if (timeDisplay) {
      const curStr = `${String(Math.floor(curSec / 60)).padStart(2, "0")}:${String(curSec % 60).padStart(2, "0")}`;
      const totStr = `${String(Math.floor(totSec / 60)).padStart(2, "0")}:${String(totSec % 60).padStart(2, "0")}`;
      timeDisplay.textContent = `${curStr} / ${totStr}`;
    }

    const slice = S.replayData.filter(p => p.elapsed_ms <= timeMs);
    const ptsH = slice.map(p => ({ x: p.x, y: p.y }));
    const ptsV = slice.map(p => ({ depth: p.depth }));
    if (typeof window.setTrajectoryHistory === "function") {
      window.setTrajectoryHistory(ptsH, ptsV);
    }

    const now = Date.now();
    if (now - S.lastFrameFetchTime > 60) {
      S.lastFrameFetchTime = now;
      updateReplayFrames(timeMs);
    }
  }

  function updateReplayFrames(timeMs) {
    if (!S.activeSessionId) return;

    const mainCam = document.getElementById("main-cam");
    const pipCam = document.getElementById("pip-cam");

    const primaryCamKey = S.isCamSwapped ? "bottom" : "front";
    const secondaryCamKey = S.isCamSwapped ? "front" : "bottom";

    if (mainCam) {
      mainCam.src = `/api/replay/frame?session=${S.activeSessionId}&cam=${primaryCamKey}&ms=${timeMs}`;
    }
    if (pipCam) {
      pipCam.src = `/api/replay/frame?session=${S.activeSessionId}&cam=${secondaryCamKey}&ms=${timeMs}`;
    }
  }

  // Inisialisasi awal
  appendLog("00:00", "GUI Init Complete", "sys");
  connectWebSocket();
  loadReplaySessions();

})();

/* ============ BAGIAN 2: Canvas Trajectory & Utility ============ */
(function () {
  "use strict";

  const DEPTH_DANGER_THRESHOLD = 6.0;
  let audioCtx = null;
  let alarmPlaying = false;

  function updateDayDate() {
    const el = document.getElementById("info-daydate");
    if (!el) return;
    const now = new Date();
    const opts = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    const dateStr = now.toLocaleDateString('id-ID', opts);
    const timeStr = now.toLocaleTimeString('id-ID', { hour12: false });
    el.textContent = `${dateStr} · ${timeStr}`;
  }
  setInterval(updateDayDate, 1000);
  updateDayDate();

  let trajView = "h";
  let trajHistoryH = [];
  let trajHistoryV = [];

  function resizeTrajCanvas() {
    const canvas = document.getElementById("traj-canvas");
    const wrap = document.getElementById("traj-canvas-wrap");
    if (!canvas || !wrap) return;
    const rect = wrap.getBoundingClientRect();
    const newW = Math.max(40, Math.floor(rect.width));
    const newH = Math.max(40, Math.floor(rect.height));

    if (canvas.width !== newW || canvas.height !== newH) {
      canvas.width = newW;
      canvas.height = newH;
      drawTrajectory();
    }
  }

  function drawTrajGrid(ctx, w, h) {
    ctx.strokeStyle = "rgba(45,184,168,.15)";
    ctx.lineWidth = 0.5;
    for (let i = 0; i < w; i += 20) { ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i, h); ctx.stroke(); }
    for (let i = 0; i < h; i += 20) { ctx.beginPath(); ctx.moveTo(0, i); ctx.lineTo(w, i); ctx.stroke(); }
  }

  function drawTrajWaitingLabel(ctx, w, h) {
    ctx.font = "9px monospace";
    ctx.fillStyle = "rgba(148,166,157,.6)";
    ctx.textAlign = "center";
    ctx.fillText("WAITING FOR TRAJECTORY DATA", w / 2, h / 2);
    ctx.textAlign = "left";
  }

  // ── LABEL SUMBU (AXIS) STATIS: nama sumbu + satuan meter ──
  // Ditampilkan selalu (baik ada data maupun belum) supaya operator langsung
  // tahu sumbu mana yang mewakili apa dan dalam satuan apa (meter).
  function drawAxisNames(ctx, w, h, view) {
    ctx.font = "8px monospace";
    ctx.textBaseline = "alphabetic";

    const isLight = document.documentElement.getAttribute("data-theme") === "light";

    if (view === "h") {
      // Tampilan Horizontal (top-down): sumbu X (kanan) & sumbu Y (atas)
      const xyColor = isLight ? "#14201b" : "rgba(94,224,166,.85)";
      ctx.fillStyle = xyColor;
      ctx.textAlign = "right";
      ctx.fillText("X (m) →", w - 6, h - 6);

      ctx.save();
      ctx.translate(10, 14);
      ctx.textAlign = "left";
      ctx.fillStyle = xyColor;
      ctx.fillText("↑ Y (m)", 0, 0);
      ctx.restore();
    } else {
      // Tampilan Vertical (profil kedalaman): sumbu Z / Depth (m) di kiri
      ctx.fillStyle = isLight ? "#2b1c05" : "rgba(224,158,63,.9)";
      ctx.textAlign = "left";
      ctx.fillText("Z / DEPTH (m) ↓", 6, 14);

      ctx.fillStyle = isLight ? "#333d38" : "rgba(148,166,157,.75)";
      ctx.textAlign = "right";
      ctx.fillText("TIME →", w - 6, h - 6);
    }
    ctx.textAlign = "left";
  }

  function drawTrajectoryHorizontal(ctx, w, h) {
    drawTrajGrid(ctx, w, h);
    drawAxisNames(ctx, w, h, "h");

    if (trajHistoryH.length < 2) {
      drawTrajWaitingLabel(ctx, w, h);
      return;
    }

    const margin = 18;
    const xs = trajHistoryH.map(p => p.x);
    const ys = trajHistoryH.map(p => p.y);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const rangeX = (maxX - minX) || 1;
    const rangeY = (maxY - minY) || 1;

    const path = trajHistoryH.map(p => [
      margin + ((p.x - minX) / rangeX) * (w - margin * 2),
      margin + ((p.y - minY) / rangeY) * (h - margin * 2)
    ]);

    ctx.beginPath();
    ctx.strokeStyle = "#2db8a8";
    ctx.lineWidth = 2;
    path.forEach((p, i) => i === 0 ? ctx.moveTo(p[0], p[1]) : ctx.lineTo(p[0], p[1]));
    ctx.stroke();

    ctx.fillStyle = "#3ecf8e";
    ctx.beginPath(); ctx.arc(path[0][0], path[0][1], 4, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#e09e3f";
    const last = path[path.length - 1];
    ctx.beginPath(); ctx.arc(last[0], last[1], 4, 0, Math.PI * 2); ctx.fill();

    ctx.font = "9px monospace";
    ctx.fillStyle = "#3ecf8e"; ctx.fillText("S", path[0][0] - 3, path[0][1] - 8);
    ctx.fillStyle = "#e09e3f"; ctx.fillText("E", last[0] - 3, last[1] - 8);

    // ── Label nilai (jarak dalam meter) di ujung-ujung sumbu ──
    ctx.font = "7px monospace";
    ctx.fillStyle = "rgba(148,166,157,.85)";

    ctx.textAlign = "left";
    ctx.fillText(`X:${minX.toFixed(2)}m`, margin, h - 22);
    ctx.textAlign = "right";
    ctx.fillText(`X:${maxX.toFixed(2)}m`, w - margin, h - 22);

    ctx.textAlign = "left";
    ctx.fillText(`Y:${minY.toFixed(2)}m`, 4, margin + 20);
    ctx.fillText(`Y:${maxY.toFixed(2)}m`, 4, h - margin - 4);
    ctx.textAlign = "left";
  }

  function drawTrajectoryVertical(ctx, w, h) {
    drawTrajGrid(ctx, w, h);
    drawAxisNames(ctx, w, h, "v");

    if (trajHistoryV.length < 2) {
      drawTrajWaitingLabel(ctx, w, h);
      return;
    }

    const margin = 18;
    const floorY = h - margin * 0.6;
    const MAX_DEPTH_M = 8;
    const n = trajHistoryV.length;

    const path = trajHistoryV.map((p, i) => {
      const px = margin + ((w - margin * 2) * i) / (n - 1);
      const depthNorm = Math.min(1, Math.max(0, p.depth / MAX_DEPTH_M));
      const py = margin + depthNorm * (floorY - margin);
      return [px, py];
    });

    ctx.beginPath();
    ctx.strokeStyle = "rgba(224,158,63,.35)";
    ctx.setLineDash([2, 3]);
    ctx.lineWidth = 1;
    ctx.moveTo(0, floorY);
    ctx.lineTo(w, floorY);
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.beginPath();
    ctx.strokeStyle = "#2db8a8";
    ctx.lineWidth = 2;
    path.forEach((p, i) => i === 0 ? ctx.moveTo(p[0], p[1]) : ctx.lineTo(p[0], p[1]));
    ctx.stroke();

    ctx.fillStyle = "#3ecf8e";
    ctx.beginPath(); ctx.arc(path[0][0], path[0][1], 4, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#e09e3f";
    const last = path[path.length - 1];
    ctx.beginPath(); ctx.arc(last[0], last[1], 4, 0, Math.PI * 2); ctx.fill();

    ctx.font = "9px monospace";
    ctx.fillStyle = "#3ecf8e"; ctx.fillText("S", path[0][0] - 3, path[0][1] - 8);
    ctx.fillStyle = "#e09e3f"; ctx.fillText("E", last[0] - 3, last[1] - 8);

    ctx.font = "7px monospace";
    ctx.fillStyle = "rgba(224,158,63,.7)";
    ctx.textAlign = "left";
    ctx.fillText("FLOOR", 4, floorY - 3);

    // ── Skala kedalaman (Z) dalam meter: 0m di atas, MAX_DEPTH_M di bawah ──
    ctx.fillStyle = "rgba(148,166,157,.85)";
    ctx.fillText("0.00m", w - 34, margin + 8);
    ctx.fillText(`${MAX_DEPTH_M.toFixed(2)}m`, w - 34, floorY - 3);
  }

  function drawTrajectory() {
    const canvas = document.getElementById("traj-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const w = canvas.width, h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    if (trajView === "v") {
      drawTrajectoryVertical(ctx, w, h);
    } else {
      drawTrajectoryHorizontal(ctx, w, h);
    }
  }

  window.setTrajView = function (mode) {
    trajView = (mode === "v") ? "v" : "h";
    const btnH = document.getElementById("btn-traj-h");
    const btnV = document.getElementById("btn-traj-v");
    if (btnH) btnH.classList.toggle("active", trajView === "h");
    if (btnV) btnV.classList.toggle("active", trajView === "v");
    drawTrajectory();
  };

  window.pushTrajectoryPoint = function (point) {
    if (!point) return;
    if (typeof point.x === "number" && typeof point.y === "number") {
      trajHistoryH.push({ x: point.x, y: point.y });
      if (trajHistoryH.length > 500) trajHistoryH.shift();
    }
    if (typeof point.depth === "number") {
      trajHistoryV.push({ depth: point.depth });
      if (trajHistoryV.length > 500) trajHistoryV.shift();
    }
    drawTrajectory();
  };

  window.setTrajectoryHistory = function (pointsH, pointsV) {
    if (Array.isArray(pointsH)) trajHistoryH = pointsH;
    if (Array.isArray(pointsV)) trajHistoryV = pointsV;
    drawTrajectory();
  };

  window.clearTrajectoryHistory = function () {
    trajHistoryH = [];
    trajHistoryV = [];
    drawTrajectory();
  };

  resizeTrajCanvas();
  drawTrajectory();
  window.addEventListener("resize", () => { resizeTrajCanvas(); drawTrajectory(); });

  function beep() {
    try {
      if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.frequency.value = 880;
      osc.connect(gain); gain.connect(audioCtx.destination);
      gain.gain.setValueAtTime(0.15, audioCtx.currentTime);
      osc.start(); osc.stop(audioCtx.currentTime + 0.18);
    } catch (e) {}
  }

  function checkDepthAlarm() {
    const depthValEl = document.getElementById("depth-val");
    const banner = document.getElementById("depth-alarm-banner");
    if (!depthValEl || !banner) return;
    const depth = parseFloat(depthValEl.textContent) || 0;
    const danger = depth >= DEPTH_DANGER_THRESHOLD;
    banner.style.display = danger ? "block" : "none";
    if (danger && !alarmPlaying) { alarmPlaying = true; beep(); }
    if (!danger) alarmPlaying = false;
  }
  setInterval(checkDepthAlarm, 1000);

  function renderAltitude(altitude) {
    const altEl = document.getElementById("alt-val");
    const qsAlt = document.getElementById("qs-alt");
    if (typeof altitude !== "number" || isNaN(altitude)) return;
    if (altEl) altEl.textContent = `${altitude.toFixed(1)}m`;
    if (qsAlt) qsAlt.textContent = `${altitude.toFixed(1)}m`;
  }

  window.renderAltitude = renderAltitude;
  window.redrawTrajectory = drawTrajectory;

})();