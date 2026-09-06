/* ==========================================================================
   js/main.js
   Gabungan dari main.js (logic telemetry asli) + ui-extras.js (UI tambahan).

   REVISI (data dummy dihilangkan, disiapkan untuk data REAL dari backend):
   1. TRAJECTORY MAP  -> tidak lagi menggambar jalur sinus palsu. Sekarang
      menunggu data asli lewat window.pushTrajectoryPoint(...) atau
      window.setTrajectoryHistory(...). Cari tag [BACKEND INTEGRATION] TRAJECTORY MAP.
   2. QR SIDE / STATUS VALID / ALTITUDE -> simulator dummy (DUMMY_SIDES,
      dummyTick, runDummyWsTick, dst) sudah DIHAPUS. Sekarang altitude &
      qr_side/qr_valid dibaca langsung dari payload WebSocket telemetry
      (data.altitude, data.qr_side, data.qr_valid). Cari tag
      [BACKEND INTEGRATION] QR SIDE & ALTITUDE.
   3. REPLAY CONTROLLER -> masih UI stub (belum terhubung ke data apapun,
      dummy maupun real). Cari tag [BACKEND INTEGRATION] REPLAY CONTROLLER
      untuk titik yang perlu disambungkan.

   Semua bagian lain (WebSocket telemetry, PID chart, QR bounding-box
   overlay di video, depth alarm, screenshot, auto-log, mode manual/auto)
   TIDAK diubah karena sudah memakai data real / sudah benar.
   ========================================================================== */

/* ============ BAGIAN 1: Telemetry & Kontrol Utama (UNCHANGED, sudah pakai data real) ============ */
(function () {
  "use strict";

  const S = {
    missionSec: 0,
    lastLogSignature: "",
    lastQrResult: "",
    lastQrOverlay: null,
    isCamSwapped: false,
    pidChartData: []
  };

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

  /* ---------------------------------------------------------------------
     QR BOUNDING-BOX OVERLAY DI ATAS VIDEO (REAL, sudah pakai data asli
     dari WebSocket: data.qr_data, data.qr_bbox, data.qr_camera).
     JANGAN DIUBAH — ini bukan bagian dummy.
     --------------------------------------------------------------------- */
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

  function updateTelemetryUI(data) {
    if (!data) return;

    if (data.autonomous_active !== undefined) {
      updateModeUI(Boolean(data.autonomous_active));
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

    /* ===================================================================
       [BACKEND INTEGRATION] QR SIDE & ALTITUDE
       Field yang diharapkan dari payload WebSocket /ws/telemetry:
         - data.altitude : number  (meter, tinggi ROV dari dasar kolam)
         - data.qr_side  : "A" | "B" | "C" | "D"
         - data.qr_valid : boolean
       Selama backend belum mengirim field ini, kartu ALT (FLOOR) dan
       QR SIDE / STATUS akan tetap menampilkan placeholder default
       ("--.-m", "SIDE: -", "STATUS: -") sesuai HTML.
       =================================================================== */
    if (typeof data.altitude === "number" && !isNaN(data.altitude) &&
        typeof window.renderAltitude === "function") {
      window.renderAltitude(data.altitude);
    }
    if (data.qr_side !== undefined && data.qr_valid !== undefined &&
        typeof window.renderQrSideValid === "function") {
      window.renderQrSideValid(data.qr_side, Boolean(data.qr_valid));
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
    if (scannedQr) {
      if (qrResult) {
        qrResult.textContent = scannedQr;
        qrResult.style.color = "#34d399";
      }
      if (scannedQr !== S.lastQrResult) {
        S.lastQrResult = scannedQr;
        appendLog("QR", `QR BERHASIL DI-SCAN! Hasil: ${scannedQr}`, "info");

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

    /* -------------------------------------------------------------------
       [BACKEND INTEGRATION] TRAJECTORY MAP — sumber data opsional #1
       Jika backend mengirim posisi ROV per-tick di dalam payload telemetry
       yang sama (mis. data.pos_x, data.pos_y dalam meter relatif titik
       start), baris di bawah ini otomatis akan menambah titik ke
       Trajectory Map horizontal & vertikal setiap kali telemetry masuk.
       Jika backend TIDAK mengirim field ini, baris ini tidak melakukan
       apa-apa dan tidak akan error — silakan sesuaikan nama field bila
       berbeda, atau panggil window.pushTrajectoryPoint(...) /
       window.setTrajectoryHistory(...) secara manual dari tempat lain.
       ------------------------------------------------------------------- */
    if (typeof window.pushTrajectoryPoint === "function" &&
        (typeof data.pos_x === "number" || typeof data.depth_raw === "number")) {
      window.pushTrajectoryPoint({ x: data.pos_x, y: data.pos_y, depth: depth });
    }
  }

  window.addEventListener("resize", () => renderQrOverlay(S.lastQrOverlay || {}));

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


/* ============ BAGIAN 2: UI Tambahan (trajectory, replay, QR side, alarm, dsb) ============ */
(function () {
  "use strict";

  // NOTE: placeholder ambang bahaya kedalaman — konfirmasi ke tim safety/mekanik
  // nilai real-nya, atau ganti agar bisa dikirim dari backend (mis. via
  // data.depth_danger_threshold pada payload telemetry) jika perlu dinamis.
  const DEPTH_DANGER_THRESHOLD = 6.0; // meter
  let autoLogOn = false;
  let autoLogTimer = null;
  let audioCtx = null;
  let alarmPlaying = false;
  let replayPlaying = false;

  /* ── Day/Date (Top Info Bar) — REAL, pakai jam sistem browser, JANGAN DIUBAH ── */
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

  /* =======================================================================
     [BACKEND INTEGRATION] TRAJECTORY MAP
     -----------------------------------------------------------------------
     Data dummy (jalur sinus palsu) SUDAH DIHAPUS. Sekarang canvas hanya
     menggambar grid + label "WAITING FOR TRAJECTORY DATA" sampai backend
     mengirim titik jalur asli.

     Cara mengisi data real, pilih salah satu:

     1) Dorong satu titik setiap kali ada telemetry baru (real-time trail):
          window.pushTrajectoryPoint({ x: 1.2, y: 0.8, depth: 2.4 });
        - x, y  -> dipakai untuk mode HORIZONTAL (top-down). Satuan bebas
                   (meter / normalized), yang penting konsisten antar titik.
        - depth -> dipakai untuk mode VERTICAL (profil kedalaman), satuan meter.

     2) Atau kirim seluruh histori jalur sekaligus (mis. saat load replay
        / mission sudah selesai):
          window.setTrajectoryHistory(
            [{x:0,y:0}, {x:1,y:0.4}, ...],      // untuk mode horizontal
            [{depth:0.5}, {depth:1.2}, ...]     // untuk mode vertical
          );

     3) window.clearTrajectoryHistory() untuk mengosongkan saat mission baru
        dimulai / reset.

     updateTelemetryUI() di Bagian 1 sudah mencoba memanggil
     pushTrajectoryPoint() otomatis jika field data.pos_x / data.pos_y /
     data.depth_raw ada di payload WebSocket — sesuaikan nama field di sana
     jika kontrak backend berbeda.
     ======================================================================= */
  let trajView = "h"; // "h" = horizontal (top-down), "v" = vertical (profil kedalaman)
  let trajHistoryH = []; // titik real horizontal: [{x, y}, ...]
  let trajHistoryV = []; // titik real vertical (kedalaman): [{depth}, ...] berurutan waktu

  function resizeTrajCanvas() {
    const canvas = document.getElementById("traj-canvas");
    const wrap = document.getElementById("traj-canvas-wrap");
    if (!canvas || !wrap) return;
    const rect = wrap.getBoundingClientRect();
    canvas.width = Math.max(40, Math.floor(rect.width));
    canvas.height = Math.max(40, Math.floor(rect.height));
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

  // Mode Horizontal: top-down (X-Y) — sekarang pakai trajHistoryH (data real).
  function drawTrajectoryHorizontal(ctx, w, h) {
    drawTrajGrid(ctx, w, h);

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
  }

  // Mode Vertical: profil kedalaman ROV — sekarang pakai trajHistoryV (data real),
  // garis putus-putus tetap sebagai referensi dasar kolam (FLOOR).
  function drawTrajectoryVertical(ctx, w, h) {
    drawTrajGrid(ctx, w, h);

    if (trajHistoryV.length < 2) {
      drawTrajWaitingLabel(ctx, w, h);
      return;
    }

    const margin = 18;
    const floorY = h - margin * 0.6;
    // NOTE: skala kedalaman maksimum dibuat konsisten dengan normalisasi
    // depth-fill di Bagian 1 (depth / 8). Sesuaikan bila kedalaman
    // kolam/misi real berbeda.
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
    ctx.fillText("FLOOR", 4, floorY - 3);
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

  // Dipanggil dari tombol HORZ / VERT di card Trajectory Map (index.html)
  window.setTrajView = function (mode) {
    trajView = (mode === "v") ? "v" : "h";
    const btnH = document.getElementById("btn-traj-h");
    const btnV = document.getElementById("btn-traj-v");
    if (btnH) btnH.classList.toggle("active", trajView === "h");
    if (btnV) btnV.classList.toggle("active", trajView === "v");
    drawTrajectory();
  };

  // --- API publik untuk backend: isi titik trajectory REAL di sini ---
  window.pushTrajectoryPoint = function (point) {
    // point: { x, y, depth }
    // x/y  -> untuk peta horizontal (top-down)
    // depth -> untuk peta vertical (profil kedalaman), satuan meter
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
  setInterval(resizeTrajCanvas, 250); // jaga-jaga bila ukuran panel berubah tanpa event resize
  window.addEventListener("resize", () => { resizeTrajCanvas(); drawTrajectory(); });

  /* =======================================================================
     [BACKEND INTEGRATION] REPLAY CONTROLLER
     -----------------------------------------------------------------------
     Masih berupa UI stub (tombol & slider sudah jalan secara visual, tapi
     belum terhubung ke data replay apapun). Yang perlu disambungkan:
       - replayControl('prev' | 'play' | 'next') : saat ini 'play' hanya
         mengganti ikon tombol ▶ / ⏸. Hubungkan ke endpoint/command backend
         untuk mulai/berhenti/loncat frame replay kamera & trajectory.
       - replaySeek(val) : val = 0-100 (persen posisi slider). Hubungkan ke
         seek posisi waktu pada sesi rekaman yang dipilih.
     ======================================================================= */
  window.replayControl = function (action) {
    const btn = document.getElementById("btn-replay-play");
    if (action === "play") {
      replayPlaying = !replayPlaying;
      if (btn) btn.textContent = replayPlaying ? "⏸" : "▶";
    }
    // TODO(backend): kirim command replay ('prev' | 'play' | 'next') ke server di sini.
  };
  window.replaySeek = function (val) {
    // TODO(backend): kirim posisi seek (val, 0-100%) ke server / player replay di sini.
  };

  /* ── Screenshot & Auto-Logging — REAL (screenshot client-side dari <img> video), JANGAN DIUBAH ── */
  window.takeScreenshot = function () {
    try {
      const img = document.getElementById("main-cam");
      const canvas = document.createElement("canvas");
      canvas.width = img.naturalWidth || 640;
      canvas.height = img.naturalHeight || 360;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      const link = document.createElement("a");
      link.download = `screenshot_${Date.now()}.png`;
      link.href = canvas.toDataURL("image/png");
      link.click();
    } catch (e) {
      console.warn("Screenshot capture blocked (CORS on video stream):", e);
    }
  };

  window.toggleAutoLog = function () {
    autoLogOn = !autoLogOn;
    const btn = document.getElementById("btn-autolog");
    if (btn) btn.textContent = autoLogOn ? "⏺ Auto-Log: ON" : "⏺ Auto-Log: OFF";
    if (autoLogOn) {
      autoLogTimer = setInterval(window.takeScreenshot, 10000);
    } else if (autoLogTimer) {
      clearInterval(autoLogTimer);
    }
  };

  /* ── Depth Danger Alarm — REAL (baca depth-val di DOM), JANGAN DIUBAH ── */
  function beep() {
    try {
      if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.frequency.value = 880;
      osc.connect(gain); gain.connect(audioCtx.destination);
      gain.gain.setValueAtTime(0.15, audioCtx.currentTime);
      osc.start(); osc.stop(audioCtx.currentTime + 0.18);
    } catch (e) { /* audio not available */ }
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

  /* =======================================================================
     [BACKEND INTEGRATION] QR SIDE & ALTITUDE — render functions
     -----------------------------------------------------------------------
     Simulator dummy (DUMMY_SIDES, dummyTick, runDummyWsTick,
     renderDummyQrResult, setInterval fabrikasi data) SUDAH DIHAPUS.

     Dua fungsi di bawah ini di-expose ke window supaya bisa dipanggil dari
     updateTelemetryUI() di Bagian 1, yang sudah otomatis memanggilnya saat
     payload WebSocket berisi data.altitude / data.qr_side / data.qr_valid.
     Kartu ALT (FLOOR) dan QR SIDE/STATUS akan tetap menampilkan placeholder
     default ("--.-m", "SIDE: -", "STATUS: -") sampai data real pertama
     kali diterima — tidak ada lagi data fiktif yang tampil.
     ======================================================================= */
  function renderAltitude(altitude) {
    const altEl = document.getElementById("alt-val");
    const qsAlt = document.getElementById("qs-alt");
    if (typeof altitude !== "number" || isNaN(altitude)) return;
    if (altEl) altEl.textContent = `${altitude.toFixed(1)}m`;
    if (qsAlt) qsAlt.textContent = `${altitude.toFixed(1)}m`;
  }

  function renderQrSideValid(qr_side, qr_valid) {
    const qrSideEl = document.getElementById("qr-side");
    const qrValidEl = document.getElementById("qr-valid");
    if (qrSideEl) {
      qrSideEl.textContent = `SIDE: ${qr_side}`;
      qrSideEl.classList.remove("qr-pill-side");
      void qrSideEl.offsetWidth;
      qrSideEl.classList.add("qr-pill-side");
    }
    if (qrValidEl) {
      qrValidEl.textContent = qr_valid ? "STATUS: VALID" : "STATUS: INVALID";
      qrValidEl.classList.remove("qr-pill-valid", "qr-pill-invalid");
      qrValidEl.classList.add(qr_valid ? "qr-pill-valid" : "qr-pill-invalid");
    }
  }

  window.renderAltitude = renderAltitude;
  window.renderQrSideValid = renderQrSideValid;

})();