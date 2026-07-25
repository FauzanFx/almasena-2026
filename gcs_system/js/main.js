(function () {
  "use strict";

  /* ── State ── */
  const S = {
    mode: "manual",
    leak: false,
    camSwapped: false,
    heading: 45,
    depth: 3.2,
    roll: 1.2,
    pitch: -0.8,
    ping: 45,
    batt: { pct: 92, v: 14.8 },
    temp: 32.0,
    thrusters: { fwd: 62, vert: 18, lat: -5 },
    missionSec: 0,
    logEntries: [],
    logIdx: 0,
  };

  /* ── DOM refs ── */
  const $ = (id) => document.getElementById(id);
  const compassStrip = $("compass-strip");
  const hdgVal = $("hdg-val");
  const ahiSky = $("ahi-sky");
  const ahiGnd = $("ahi-gnd");
  const ahiLine = $("ahi-line");
  const rpReadout = $("rp-readout");
  const depthFill = $("depth-fill");
  const depthValEl = $("depth-val");
  const pingLed = $("ping-led");
  const pingVal = $("ping-val");
  const battLed = $("batt-led");
  const battVal = $("batt-val");
  const battBar = $("batt-bar");
  const tempLed = $("temp-led");
  const tempVal = $("temp-val");
  const imuVal = $("imu-val");
  const leakBtn = $("leak-btn");
  const leakIco = $("leak-ico");
  const leakValEl = $("leak-val");
  const logTerminal = $("log-terminal");
  const tbPing = $("tb-ping");
  const tbClock = $("tb-clock");
  const modeBadge = $("mode-badge");
  const tbLeakAlert = $("tb-leak-alert");
  const camLabelMain = $("cam-label-main");
  const pipLabel = $("pip-label");
  const qsDepth = $("qs-depth");
  const qsHdg = $("qs-hdg");
  const qsBatt = $("qs-batt");

  /* ── Helpers ── */
  const pad = (n, l = 2) => String(Math.floor(n)).padStart(l, "0");
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const sign = (v) => (v >= 0 ? "+" : "");

  /* ── Build compass ticks ── */
  (function buildCompass() {
    const ticks = [
      "N", "18", "36", "54", "72",
      "E", "108", "126", "144", "162",
      "S", "198", "216", "234", "252",
      "W", "288", "306", "324", "342",
      "N", "18", "36", "54",
    ];
    ticks.forEach((t) => {
      const el = document.createElement("span");
      const isMajor = ["N", "E", "S", "W"].includes(t);
      el.textContent = t;
      el.style.cssText = `width:20px;text-align:center;font-size:${isMajor ? "9" : "7.5"}px;color:${isMajor ? "#22d3ee" : "rgba(6,182,212,.5)"};font-family:'Share Tech Mono',monospace;`;
      compassStrip.appendChild(el);
    });
  })();

  /* ── Mission Clock ── */
  setInterval(() => {
    S.missionSec++;
    tbClock.textContent = `${pad(Math.floor(S.missionSec / 3600))}:${pad(Math.floor((S.missionSec % 3600) / 60))}:${pad(S.missionSec % 60)}`;
  }, 1000);

  /* ── Logging System ── */
  function appendLog(ts, msg, type, animate = true) {
    const colors = {
      info: "rgba(52,211,153,.6)",
      warn: "rgba(245,158,11,.65)",
      err: "rgba(239,68,68,.7)",
      sys: "rgba(6,182,212,.55)",
    };
    const el = document.createElement("div");
    el.style.cssText = `display:flex;gap:5px;font-size:7px;letter-spacing:.04em;line-height:1.65;${animate ? "animation:log-slide .3s ease;" : ""}`;
    el.innerHTML = `<span style="color:rgba(52,211,153,.28);flex-shrink:0;font-family:'Share Tech Mono',monospace;">${ts}</span><span style="color:${colors[type] || colors.info};overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${msg}</span>`;
    logTerminal.appendChild(el);
    while (logTerminal.children.length > 28) {
      logTerminal.removeChild(logTerminal.firstChild);
    }
    logTerminal.scrollTop = logTerminal.scrollHeight;
  }

  function addLog(msg, type = "info") {
    const m = pad(Math.floor(S.missionSec / 60));
    const sc = pad(S.missionSec % 60);
    appendLog(`${m}:${sc}`, msg, type);
  }

  /* ── Mode toggle ── */
  window.setMode = function (m) {
    S.mode = m;
    ["manual", "depth", "heading"].forEach((id) => {
      const btn = $("btn-" + id);
      const sub = $("msub-" + id);
      btn.classList.toggle("active", id === m);
      btn.style.color = id === m ? "#34d399" : "rgba(52,211,153,.4)";
      if (sub) {
        sub.style.color =
          id === m ? "rgba(52,211,153,.5)" : "rgba(52,211,153,.25)";
      }
    });
    const labels = {
      manual: "MANUAL",
      depth: "DEPTH HOLD",
      heading: "HDG HOLD",
    };
    const msgs = {
      manual: "Manual mode active",
      depth: "Depth hold engaged",
      heading: "Heading hold engaged",
    };
    modeBadge.textContent = labels[m];
    addLog(msgs[m], "sys");
  };

  /* ── Leak toggle ── */
  window.toggleLeak = function () {
    S.leak = !S.leak;
    if (S.leak) {
      leakBtn.classList.remove("leak-safe");
      leakBtn.classList.add("leak-danger");
      leakIco.setAttribute("stroke", "#ef4444");
      leakValEl.textContent = "⚡ LEAK DET.";
      leakValEl.style.color = "#ef4444";
      tbLeakAlert.classList.remove("hidden");
      addLog("CRITICAL: LEAK DETECTED!", "err");
    } else {
      leakBtn.classList.remove("leak-danger");
      leakBtn.classList.add("leak-safe");
      leakIco.setAttribute("stroke", "#34d399");
      leakValEl.textContent = "✓ SAFE";
      leakValEl.style.color = "#34d399";
      tbLeakAlert.classList.add("hidden");
      addLog("Leak sensor cleared", "sys");
    }
  };

  /* ── Cam swap: swap the src between main-cam and pip-cam ── */
  window.swapCams = function () {
    S.camSwapped = !S.camSwapped;

    const mainCam = $("main-cam");
    const pipCam = $("pip-cam");

    const tempSrc = mainCam.src;
    mainCam.src = pipCam.src;
    pipCam.src = tempSrc;

    if (S.camSwapped) {
      pipLabel.textContent = "FWD CAM-01";
      camLabelMain.textContent = "BTM CAM-02";
      addLog("Camera swap: BTM primary", "sys");
    } else {
      pipLabel.textContent = "BTM CAM-02";
      camLabelMain.textContent = "FWD CAM-01";
      addLog("Camera swap: FWD primary", "sys");
    }
  };

  /* ════════════════════════════════════════════════════
     KONEKSI KE VIRTUAL ROV (WEBSOCKETS DUAL-CHANNEL)
  ════════════════════════════════════════════════════ */
  
  // Jalur 1: Untuk Telemetri (Menerima Data)
  const wsTelemetry = new WebSocket('ws://localhost:8000/ws/telemetry');
  
  wsTelemetry.onopen = function () {
    addLog("Telemetry Tether Connected", "sys");
    $("tb-leak-alert").classList.add("hidden");
  };

  wsTelemetry.onmessage = function (event) {
    const data = JSON.parse(event.data);
    updateTelemetry(data);
  };

  wsTelemetry.onerror = function (error) {
    addLog("TELEMETRY ERROR: Pastikan python server menyala", "err");
  };

  // Jalur 2: Untuk Kontrol (Mengirim Perintah)
  const wsControl = new WebSocket('ws://localhost:8000/ws/control');

  wsControl.onopen = function () {
    addLog("Control Tether Connected", "sys");
  };

  wsControl.onerror = function (error) {
    addLog("CONTROL ERROR: Koneksi ke thruster terputus", "err");
  };

  function updateTelemetry(data) {
    // 1. Update variabel state
    S.depth = data.depth;
    S.heading = data.heading;
    S.roll = data.roll;
    S.pitch = data.pitch;
    S.ping = data.ping;
    S.batt.pct = data.batt_pct;
    S.temp = data.temp;

    // 2. Update Tampilan Depth
    const depthPct = clamp((S.depth / 8) * 100, 0, 100);
    depthFill.style.height = depthPct + "%";
    depthValEl.innerHTML = `${S.depth.toFixed(1)}<br/><span style="font-size:6px;color:rgba(6,182,212,.4);">m</span>`;
    qsDepth.textContent = S.depth.toFixed(1) + "m";

    // 3. Update Tampilan Heading (Kompas)
    const offset = -(S.heading / 360) * (24 * 20);
    compassStrip.style.transform = `translateX(${offset}px)`;
    hdgVal.textContent = pad(Math.round(S.heading), 3) + "°";
    qsHdg.textContent = pad(Math.round(S.heading), 3) + "°";

    // 4. Update Artificial Horizon (Roll & Pitch)
    const pitchOffset = S.pitch * 2.5;
    const t = `rotate(${S.roll}deg) scaleX(1.7)`;
    ahiSky.style.transform = t;
    ahiGnd.style.transform = t;
    ahiLine.style.transform = `translateY(calc(-50% + ${pitchOffset}px)) rotate(${S.roll}deg) scaleX(1.7)`;
    rpReadout.textContent = `R${sign(S.roll)}${S.roll.toFixed(1)}° P${sign(S.pitch)}${S.pitch.toFixed(1)}°`;
    imuVal.textContent = `${sign(S.roll)}${S.roll.toFixed(1)}° / ${sign(S.pitch)}${S.pitch.toFixed(1)}°`;

    // 5. Update Baterai, Ping, & Temp
    battVal.textContent = `${S.batt.pct}%`;
    battBar.style.width = S.batt.pct + "%";

    const isGood = S.ping < 65;
    const isWarn = S.ping < 100;
    const pingColor = isGood ? "#34d399" : isWarn ? "#f59e0b" : "#ef4444";
    pingVal.textContent = S.ping + " ms";
    pingVal.style.color = pingColor;
    pingLed.style.background = pingColor;
    pingLed.style.boxShadow = `0 0 6px ${pingColor}`;
    pingLed.className = `led-dot mt-0.5${!isGood ? " led-pulse" : ""}`;
    tbPing.textContent = S.ping + "ms";
    tbPing.style.color = pingColor;

    tempVal.textContent = S.temp.toFixed(1) + " °C";
  }

  /* ── Initial active mode style ── */
  setMode("manual");

  /* ════════════════════════════════════════════════════
     KONTROL KEYBOARD (VIRTUAL JOYSTICK)
  ════════════════════════════════════════════════════ */
  const keys = {
    w: false,
    a: false,
    s: false,
    d: false,
    ArrowUp: false,
    ArrowDown: false,
  };

  // Deteksi saat tombol ditekan
  window.addEventListener("keydown", (e) => {
    if (keys.hasOwnProperty(e.key) && !keys[e.key]) {
      keys[e.key] = true;
      updateThrusters();
    }
  });

  // Deteksi saat tombol dilepas
  window.addEventListener("keyup", (e) => {
    if (keys.hasOwnProperty(e.key)) {
      keys[e.key] = false;
      updateThrusters();
    }
  });

  // Fungsi untuk kalkulasi gaya dorong dan kirim ke Python
  function updateThrusters() {
    // Kunci kontrol agar hanya bisa digerakkan saat mode MANUAL
    if (S.mode !== "manual") return;

    // Kalkulasi Power: W/S (Maju/Mundur), A/D (Kiri/Kanan), Arrow (Naik/Turun)
    S.thrusters.fwd = (keys.w ? 60 : 0) - (keys.s ? 60 : 0);
    S.thrusters.lat = (keys.d ? 40 : 0) - (keys.a ? 40 : 0);
    S.thrusters.vert = (keys.ArrowUp ? 50 : 0) - (keys.ArrowDown ? 50 : 0);

    // 1. Update Tampilan Bar & Angka di GUI
    $("tbar-fwd").style.width = Math.abs(S.thrusters.fwd) + "%";
    $("tbar-vert").style.width = Math.abs(S.thrusters.vert) + "%";
    $("tbar-lat").style.width = Math.abs(S.thrusters.lat) + "%";

    $("tval-fwd").textContent = sign(S.thrusters.fwd) + S.thrusters.fwd + "%";
    $("tval-vert").textContent = sign(S.thrusters.vert) + S.thrusters.vert + "%";
    $("tval-lat").textContent = sign(S.thrusters.lat) + S.thrusters.lat + "%";

    // 2. Tembakkan Perintah ke ROV (via WebSocket Kontrol)
    if (wsControl.readyState === WebSocket.OPEN) {
      wsControl.send(
        JSON.stringify({
          gerak: S.thrusters.fwd > 0 ? "Maju" : (S.thrusters.fwd < 0 ? "Mundur" : (S.thrusters.lat > 0 ? "Kanan" : (S.thrusters.lat < 0 ? "Kiri" : "Diam"))),
          fwd: S.thrusters.fwd,
          lat: S.thrusters.lat,
          vert: S.thrusters.vert,
        })
      );
    }
  }

  addLog("System boot complete", "sys");
})();