(function() {
  'use strict';

  /* ── State ── */
  const S = {
    mode: 'manual',
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
    depthDir: 1,
    rollDir: 1,
    missionSec: 720,
    logEntries: [],
    logIdx: 0,
  };

  const logPool = [
    ['Pitch nominal','info'],
    ['Bearing stable','info'],
    ['Depth hold locked','info'],
    ['Battery OK','info'],
    ['Ping stable','info'],
    ['CAM-01 FWD stable','sys'],
    ['CAM-02 BTM stable','sys'],
    ['Task B waypoint sighted','info'],
    ['Gripper deployed','info'],
    ['Sample collected','info'],
    ['Holding position','info'],
    ['IMU nominal','sys'],
    ['Thruster-4 OK','sys'],
    ['Ascending 0.2m','warn'],
    ['Manual input detected','warn'],
    ['Hovering at 3.2m','info'],
  ];

  /* ── DOM refs ── */
  const $ = id => document.getElementById(id);
  const compassStrip = $('compass-strip');
  const hdgVal       = $('hdg-val');
  const ahiSky       = $('ahi-sky');
  const ahiGnd       = $('ahi-gnd');
  const ahiLine      = $('ahi-line');
  const rpReadout    = $('rp-readout');
  const depthFill    = $('depth-fill');
  const depthValEl   = $('depth-val');
  const pingLed      = $('ping-led');
  const pingVal      = $('ping-val');
  const battLed      = $('batt-led');
  const battVal      = $('batt-val');
  const battBar      = $('batt-bar');
  const tempLed      = $('temp-led');
  const tempVal      = $('temp-val');
  const imuVal       = $('imu-val');
  const leakBtn      = $('leak-btn');
  const leakIco      = $('leak-ico');
  const leakValEl    = $('leak-val');
  const logTerminal  = $('log-terminal');
  const tbPing       = $('tb-ping');
  const tbClock      = $('tb-clock');
  const modeBadge    = $('mode-badge');
  const tbLeakAlert  = $('tb-leak-alert');
  const camLabelMain = $('cam-label-main');
  const pipLabel     = $('pip-label');
  const pipContent   = $('pip-content');
  const qsDepth      = $('qs-depth');
  const qsHdg        = $('qs-hdg');
  const qsBatt       = $('qs-batt');

  /* ── Helpers ── */
  const pad = (n, l=2) => String(Math.floor(n)).padStart(l, '0');
  const rnd = (a, b) => Math.random() * (b - a) + a;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const sign = v => v >= 0 ? '+' : '';

  /* ── Build compass ticks ── */
  (function buildCompass() {
    const ticks = ['N','18','36','54','72','E','108','126','144','162','S','198','216','234','252','W','288','306','324','342','N','18','36','54'];
    ticks.forEach(t => {
      const el = document.createElement('span');
      const isMajor = ['N','E','S','W'].includes(t);
      el.textContent = t;
      el.style.cssText = `width:20px;text-align:center;font-size:${isMajor?'9':'7.5'}px;color:${isMajor?'#22d3ee':'rgba(6,182,212,.5)'};font-family:'Share Tech Mono',monospace;`;
      compassStrip.appendChild(el);
    });
  })();

  /* ── Add initial log entries ── */
  const initLogs = [
    ['00:00', 'System boot complete', 'sys'],
    ['00:01', 'ROV-ALPHA connected', 'sys'],
    ['00:02', 'CAM-01 FWD online', 'sys'],
    ['00:03', 'CAM-02 BTM online', 'sys'],
    ['00:05', 'Depth hold engaged', 'info'],
    ['00:08', 'Descent 0 → 3.2m OK', 'info'],
    ['00:12', 'Task waypoint A reached', 'info'],
  ];
  initLogs.forEach(([ts, msg, type]) => appendLog(ts, msg, type, false));

  function appendLog(ts, msg, type, animate=true) {
    const colors = { info:'rgba(52,211,153,.6)', warn:'rgba(245,158,11,.65)', err:'rgba(239,68,68,.7)', sys:'rgba(6,182,212,.55)' };
    const el = document.createElement('div');
    el.style.cssText = `display:flex;gap:5px;font-size:7px;letter-spacing:.04em;line-height:1.65;${animate?'animation:log-slide .3s ease;':''}`;
    el.innerHTML = `<span style="color:rgba(52,211,153,.28);flex-shrink:0;font-family:'Share Tech Mono',monospace;">${ts}</span><span style="color:${colors[type]||colors.info};overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${msg}</span>`;
    logTerminal.appendChild(el);
    // keep max 28 entries
    while (logTerminal.children.length > 28) logTerminal.removeChild(logTerminal.firstChild);
    logTerminal.scrollTop = logTerminal.scrollHeight;
  }

  function addLog(msg, type='info') {
    S.missionSec += Math.floor(rnd(1, 4));
    const m = pad(Math.floor(S.missionSec / 60));
    const sc = pad(S.missionSec % 60);
    appendLog(`${m}:${sc}`, msg, type);
  }

  /* ── Mode toggle ── */
  window.setMode = function(m) {
    S.mode = m;
    ['manual','depth','heading'].forEach(id => {
      const btn = $('btn-' + id);
      const sub = $('msub-' + id);
      btn.classList.toggle('active', id === m);
      btn.style.color = id === m ? '#34d399' : 'rgba(52,211,153,.4)';
      if (sub) sub.style.color = id === m ? 'rgba(52,211,153,.5)' : 'rgba(52,211,153,.25)';
    });
    const labels = { manual:'MANUAL', depth:'DEPTH HOLD', heading:'HDG HOLD' };
    const msgs   = { manual:'Manual mode active', depth:'Depth hold engaged', heading:'Heading hold engaged' };
    modeBadge.textContent = labels[m];
    addLog(msgs[m], 'sys');
  };

  /* ── Leak toggle ── */
  window.toggleLeak = function() {
    S.leak = !S.leak;
    if (S.leak) {
      leakBtn.classList.remove('leak-safe');
      leakBtn.classList.add('leak-danger');
      leakIco.setAttribute('stroke', '#ef4444');
      leakValEl.textContent = '⚡ LEAK DET.';
      leakValEl.style.color = '#ef4444';
      tbLeakAlert.classList.remove('hidden');
      addLog('CRITICAL: LEAK DETECTED!', 'err');
    } else {
      leakBtn.classList.remove('leak-danger');
      leakBtn.classList.add('leak-safe');
      leakIco.setAttribute('stroke', '#34d399');
      leakValEl.textContent = '✓ SAFE';
      leakValEl.style.color = '#34d399';
      tbLeakAlert.classList.add('hidden');
      addLog('Leak sensor cleared', 'sys');
    }
  };

  /* ── Cam swap ── */
  window.swapCams = function() {
    S.camSwapped = !S.camSwapped;
    if (S.camSwapped) {
      // Main = bottom cam look, PiP = ocean
      pipLabel.textContent = 'FWD CAM-01';
      camLabelMain.textContent = 'BTM CAM-02';
      pipContent.className = 'absolute inset-0 ocean-bg';
      pipContent.innerHTML = `
        <div style="position:absolute;top:0;left:22%;width:30px;height:70%;background:linear-gradient(180deg,rgba(56,189,248,.1) 0%,transparent 70%);transform:rotate(-8deg);transform-origin:top;"></div>
        <div style="position:absolute;inset:0;background-image:linear-gradient(rgba(6,182,212,.06) 1px,transparent 1px),linear-gradient(90deg,rgba(6,182,212,.06) 1px,transparent 1px);background-size:18px 18px;background-color:transparent;"></div>`;
      addLog('Camera swap: BTM primary', 'sys');
    } else {
      pipLabel.textContent = 'BTM CAM-02';
      camLabelMain.textContent = 'FWD CAM-01';
      pipContent.className = 'absolute inset-0 bottomcam-bg';
      pipContent.innerHTML = `
        <div style="position:absolute;left:9%;right:9%;top:40%;height:18px;background:#2d3748;border-top:1px solid #4a5568;border-bottom:1px solid #1a202c;transform:rotate(-1.5deg);"></div>
        <div style="position:absolute;left:0;width:12%;top:38%;height:22px;background:#2d3748;border-top:1px solid #4a5568;border-bottom:1px solid #1a202c;"></div>
        <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:22px;height:22px;border:1px solid rgba(245,158,11,.4);border-radius:50%;"></div>
        <div style="position:absolute;top:50%;left:calc(50% - 16px);width:32px;height:1px;background:rgba(245,158,11,.35);"></div>
        <div style="position:absolute;left:50%;top:calc(50% - 16px);width:1px;height:32px;background:rgba(245,158,11,.35);"></div>`;
      addLog('Camera swap: FWD primary', 'sys');
    }
  };

  /* ════════════════════════════════════════════════════
     LIVE DATA INTERVALS (SIMULATION)
  ════════════════════════════════════════════════════ */
  
  // 1. KITA BUNGKUS SEMUA DATA PALSU KE DALAM FUNGSI INI
  function startSimulation() {
    /* Mission clock */
    let elapsed = 0;
    setInterval(() => {
      elapsed++;
      tbClock.textContent = `${pad(Math.floor(elapsed/3600))}:${pad(Math.floor((elapsed%3600)/60))}:${pad(elapsed%60)}`;
    }, 1000);

    /* Heading drift */
    setInterval(() => {
      S.heading = (S.heading + rnd(-.35, .8) + 360) % 360;
      const offset = -(S.heading / 360) * (24 * 20);
      compassStrip.style.transform = `translateX(${offset}px)`;
      hdgVal.textContent = pad(Math.round(S.heading), 3) + '°';
      qsHdg.textContent = pad(Math.round(S.heading), 3) + '°';
    }, 1100);

    /* Depth */
    setInterval(() => {
      S.depth += rnd(-.06, .13) * S.depthDir;
      if (S.depth > 5.8) S.depthDir = -1;
      if (S.depth < 0.9) S.depthDir = 1;
      S.depth = clamp(S.depth, .5, 6.5);
      const pct = clamp((S.depth / 8) * 100, 0, 100);
      depthFill.style.height = pct + '%';
      depthFill.className = S.depth > 5 ? 'depth-fill-red' : S.depth > 3.5 ? 'depth-fill-amber' : 'depth-fill-cyan';
      depthFill.style.position = 'absolute';
      depthFill.style.bottom = '0';
      depthFill.style.left = '0';
      depthFill.style.right = '0';
      depthFill.style.borderRadius = '0 0 2px 2px';
      depthFill.style.transition = 'height 1.8s ease';
      const dColor = S.depth > 5 ? '#ef4444' : S.depth > 3.5 ? '#f59e0b' : '#22d3ee';
      depthValEl.innerHTML = `${S.depth.toFixed(1)}<br/><span style="font-size:6px;color:rgba(6,182,212,.4);">m</span>`;
      depthValEl.style.color = dColor;
      qsDepth.textContent = S.depth.toFixed(1) + 'm';
      qsDepth.style.color = dColor;
    }, 2100);

    /* Roll/pitch → AHI */
    setInterval(() => {
      S.roll += rnd(-.65, .65) * S.rollDir;
      if (Math.abs(S.roll) > 8) S.rollDir *= -1;
      S.roll = clamp(S.roll, -11, 11);
      S.pitch += rnd(-.35, .35);
      S.pitch = clamp(S.pitch, -6, 6);

      const rollRad = S.roll;
      const pitchOffset = S.pitch * 2.5;
      const t = `rotate(${rollRad}deg) scaleX(1.7)`;
      ahiSky.style.transform = t;
      ahiGnd.style.transform = t;
      ahiLine.style.transform = `translateY(calc(-50% + ${pitchOffset}px)) rotate(${rollRad}deg) scaleX(1.7)`;
      rpReadout.textContent = `R${sign(S.roll)}${S.roll.toFixed(1)}° P${sign(S.pitch)}${S.pitch.toFixed(1)}°`;
      imuVal.textContent = `${sign(S.roll)}${S.roll.toFixed(1)}° / ${sign(S.pitch)}${S.pitch.toFixed(1)}°`;
    }, 1200);

    /* Ping */
    setInterval(() => {
      S.ping = Math.floor(rnd(36, 70));
      const isGood = S.ping < 65;
      const isWarn = S.ping < 100;
      const color = isGood ? '#34d399' : isWarn ? '#f59e0b' : '#ef4444';
      pingVal.textContent = S.ping + ' ms';
      pingVal.style.color = color;
      pingLed.style.background = color;
      pingLed.style.boxShadow = `0 0 6px ${color}`;
      pingLed.className = `led-dot mt-0.5${!isGood ? ' led-pulse' : ''}`;
      tbPing.textContent = S.ping + 'ms';
      tbPing.style.color = color;
    }, 2600);

    /* Battery */
    setInterval(() => {
      S.batt.pct = Math.max(60, S.batt.pct - rnd(0, .05));
      S.batt.v = Math.max(12.5, (S.batt.pct / 100) * 16.8);
      const pct = Math.round(S.batt.pct);
      const color = pct > 50 ? '#34d399' : pct > 25 ? '#f59e0b' : '#ef4444';
      battVal.textContent = `${S.batt.v.toFixed(1)}V (${pct}%)`;
      battVal.style.color = color;
      battBar.style.width = pct + '%';
      battBar.style.background = `linear-gradient(90deg,#059669,${color})`;
      battLed.style.background = color;
      battLed.style.boxShadow = `0 0 6px ${color}`;
      qsBatt.textContent = pct + '%';
      qsBatt.style.color = color;
    }, 5000);

    /* Temp */
    setInterval(() => {
      S.temp = clamp(S.temp + rnd(-.18, .18), 29, 39);
      const color = S.temp > 36 ? '#ef4444' : S.temp > 33 ? '#f59e0b' : '#22d3ee';
      tempVal.textContent = S.temp.toFixed(1) + ' °C';
      tempVal.style.color = color;
      tempLed.style.background = color;
      tempLed.style.boxShadow = `0 0 6px ${color}`;
    }, 3100);

    /* Thrusters */
    setInterval(() => {
      const fwd  = Math.floor(rnd(48, 84));
      const vert = Math.floor(rnd(0, 28)) * (Math.random() > .5 ? 1 : -1);
      const lat  = Math.floor(rnd(0, 16)) * (Math.random() > .4 ? 1 : -1);

      $('tbar-fwd').style.width  = Math.abs(fwd)  + '%';
      $('tbar-vert').style.width = Math.abs(vert) + '%';
      $('tbar-lat').style.width  = Math.abs(lat)  + '%';

      $('tval-fwd').textContent  = sign(fwd)  + fwd  + '%';
      $('tval-vert').textContent = sign(vert) + vert + '%';
      $('tval-lat').textContent  = sign(lat)  + lat  + '%';
    }, 1900);

    /* Auto log */
    setInterval(() => {
      const [msg, type] = logPool[S.logIdx % logPool.length];
      addLog(msg, type);
      S.logIdx++;
    }, 3800);
  }

  // 2. TEMPAT UNTUK DATA ASLI NANTINYA (Saat ini masih kosong)
  function updateTelemetry(data) {
    // Nanti kodingan dari MQTT/WebSockets masuk ke sini
    // Contoh: 
    // S.roll = data.roll;
    // S.pitch = data.pitch;
  }

  /* ── Initial active mode style ── */
  setMode('manual');
  
  // 3. JALANKAN SIMULASINYA SEKARANG

})();


