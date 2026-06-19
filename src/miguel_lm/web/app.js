/* MiguelLM desktop UI logic. Runs inside a pywebview window: all networking goes
 * through the Python bridge (window.pywebview.api.*), which uses the configured
 * token. No fetch, no token, no auth handling in the page. Persona-free. */
(function () {
  "use strict";

  // Surface JS/load errors into the page so they're visible without devtools.
  function showError(msg) {
    try {
      var el = document.getElementById("messages");
      if (!el) return;
      var d = document.createElement("div");
      d.className = "msg error";
      d.innerHTML = '<div class="who">SYSTEM</div>';
      var b = document.createElement("div");
      b.className = "bubble";
      b.textContent = String(msg);
      d.appendChild(b);
      el.appendChild(d);
    } catch (e) {}
  }
  window.addEventListener("error", function (e) { showError("JS error: " + (e.message || e.error)); });
  window.addEventListener("unhandledrejection", function (e) { showError("Promise error: " + (e.reason && e.reason.message || e.reason)); });

  var EMOTIONS = ["normal", "happy", "sad", "grumpy", "love", "scared", "confused", "mischievous", "thinking"];
  var DEFAULT_BOOT = [
    "ROBCO INDUSTRIES (TM) TERMLINK PROTOCOL",
    "",
    "INITIALIZING MIGUELLM...",
    "> LOADING NEURAL INTERFACE ......... OK",
    "> MOUNTING PERSONA MATRIX .......... OK",
    "> CALIBRATING VOICE SYNTHESIZER .... OK",
    "> SPINNING UP HYPERSPACE RIG ....... OK",
    "> ESTABLISHING UPLINK .............. OK",
    "",
    "WELCOME",
  ];

  /* ---------------- Python bridge ---------------- */
  var API = null;
  function whenBridgeReady() {
    return new Promise(function (resolve) {
      if (window.pywebview && window.pywebview.api) return resolve(window.pywebview.api);
      window.addEventListener("pywebviewready", function () { resolve(window.pywebview.api); });
    });
  }

  function b64ToArrayBuffer(b64) {
    var bin = atob(b64);
    var bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return bytes.buffer;
  }

  /* ---------------- Audio (playback + SFX + lip-sync) ---------------- */
  var Audio = (function () {
    var ctx = null;
    function ac() {
      if (!ctx) {
        var C = window.AudioContext || window.webkitAudioContext;
        if (C) ctx = new C();
      }
      if (ctx && ctx.state === "suspended") ctx.resume();
      return ctx;
    }
    function playWavBase64(b64) {
      var c = ac();
      if (!c) return Promise.resolve(null);
      return c.decodeAudioData(b64ToArrayBuffer(b64)).then(function (buffer) {
        var src = c.createBufferSource();
        src.buffer = buffer;
        var analyser = c.createAnalyser();
        analyser.fftSize = 256;
        src.connect(analyser);
        analyser.connect(c.destination);
        var ended = new Promise(function (res) { src.onended = res; });
        src.start();
        return { analyser: analyser, ended: ended, duration: buffer.duration };
      });
    }
    function blip() {
      var c = ac();
      if (!c) return;
      var o = c.createOscillator(), g = c.createGain();
      o.type = "square";
      o.frequency.value = 1400 + Math.random() * 400;
      g.gain.value = 0.012;
      o.connect(g); g.connect(c.destination);
      o.start();
      g.gain.exponentialRampToValueAtTime(0.0001, c.currentTime + 0.03);
      o.stop(c.currentTime + 0.035);
    }
    function beep(freq, dur) {
      var c = ac();
      if (!c) return;
      var o = c.createOscillator(), g = c.createGain();
      o.type = "sine"; o.frequency.value = freq;
      g.gain.value = 0.05;
      o.connect(g); g.connect(c.destination);
      o.start();
      g.gain.exponentialRampToValueAtTime(0.0001, c.currentTime + dur);
      o.stop(c.currentTime + dur + 0.01);
    }
    return { playWavBase64: playWavBase64, blip: blip, beep: beep };
  })();

  /* ---------------- Emotion avatar ----------------
   * Static green portraits, one per emotion, each with an idle and a "talking"
   * (mouth-open) frame. While speaking we swap idle<->talking by audio amplitude
   * so the mouth appears to move. All frames are base64 PNGs from the backend. */
  var Head = (function () {
    var img = document.getElementById("head-avatar");
    var fallback = document.getElementById("head-fallback");
    var frames = {};            // emotion -> { idle: dataURI, talking: dataURI }
    var loaded = false;
    var currentEmotion = "normal";
    var speaking = false, analyser = null, freqData = null;
    var mouthOpen = false, lastSwap = 0, raf = null;

    function init() { /* nothing until avatars arrive; the fallback ring shows meanwhile */ }

    function loadAvatars(map) {
      if (!map || typeof map !== "object" || !Object.keys(map).length) {
        showError("No avatars available (backend returned none).");
        return;
      }
      frames = {};
      Object.keys(map).forEach(function (emotion) {
        var v = map[emotion] || {};
        var idle = v.idle ? "data:image/png;base64," + v.idle : null;
        var talking = v.talking ? "data:image/png;base64," + v.talking : idle;
        frames[emotion] = { idle: idle, talking: talking };
        // Warm the browser cache so idle<->talking swaps don't flicker.
        [idle, talking].forEach(function (uri) { if (uri) { var p = new Image(); p.src = uri; } });
      });
      loaded = true;
      if (img) img.classList.remove("hidden");
      if (fallback) fallback.classList.add("hidden");
      render();
    }

    function framesFor(name) {
      return frames[name] || frames.normal || frames[Object.keys(frames)[0]] || null;
    }

    function render() {
      if (!loaded || !img) return;
      var f = framesFor(currentEmotion);
      if (!f) return;
      var uri = (speaking && mouthOpen && f.talking) ? f.talking : f.idle;
      if (uri && img.getAttribute("src") !== uri) img.setAttribute("src", uri);
    }

    function setEmotion(name) {
      currentEmotion = name || "normal";
      var tag = document.getElementById("emotion-tag");
      if (tag) tag.textContent = name ? "[ " + name + " ]" : "";
      render();
    }

    function setSpeaking(on, an) {
      speaking = !!on;
      analyser = (on && an) ? an : null;
      if (analyser) freqData = new Uint8Array(analyser.fftSize);
      if (img) img.classList.toggle("speaking", speaking);
      if (speaking) {
        if (!raf) raf = requestAnimationFrame(flap);
      } else {
        if (raf) { cancelAnimationFrame(raf); raf = null; }
        mouthOpen = false;
        render();
      }
    }

    function flap(ts) {
      if (!speaking) { raf = null; return; }
      raf = requestAnimationFrame(flap);
      if (analyser) {
        analyser.getByteTimeDomainData(freqData);
        var sum = 0;
        for (var i = 0; i < freqData.length; i++) { var v = (freqData[i] - 128) / 128; sum += v * v; }
        mouthOpen = Math.sqrt(sum / freqData.length) > 0.06;
      } else if (ts - lastSwap > 110) {
        // No analyser (audio missing): just flap on a timer for some life.
        mouthOpen = !mouthOpen;
        lastSwap = ts;
      }
      render();
    }

    return { init: init, loadAvatars: loadAvatars, setEmotion: setEmotion, setSpeaking: setSpeaking };
  })();

  /* ---------------- DOM helpers ---------------- */
  var messagesEl = document.getElementById("messages");
  var thinkingEl = document.getElementById("thinking");
  var statusEl = document.getElementById("status");
  var statusText = document.getElementById("status-text");
  var assistantPeerLabel = { user: "YOU", bot: "MIGUELLM" };

  function setStatus(text, kind) {
    statusText.textContent = text;
    statusEl.className = "status" + (kind ? " " + kind : "");
  }
  function addMessage(kind, who, text) {
    var wrap = document.createElement("div");
    wrap.className = "msg " + kind;
    var whoEl = document.createElement("div");
    whoEl.className = "who";
    whoEl.textContent = who;
    var bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = text || "";
    wrap.appendChild(whoEl);
    wrap.appendChild(bubble);
    messagesEl.appendChild(wrap);
    scrollDown();
    return bubble;
  }
  function scrollDown() { messagesEl.scrollTop = messagesEl.scrollHeight; }

  /* ---------------- Typewriter synced to audio ---------------- */
  function typewrite(bubble, text, durationMs) {
    return new Promise(function (resolve) {
      var caret = document.createElement("span");
      caret.className = "type-caret";
      bubble.textContent = "";
      bubble.appendChild(caret);
      var i = 0;
      var per = Math.max(12, Math.min(60, durationMs ? durationMs / Math.max(1, text.length) : 28));
      var timer = setInterval(function () {
        if (i >= text.length) {
          clearInterval(timer);
          if (caret.parentNode) caret.parentNode.removeChild(caret);
          resolve();
          return;
        }
        caret.insertAdjacentText("beforebegin", text[i]);
        if (i % 2 === 0 && text[i].trim()) Audio.blip();
        i++;
        scrollDown();
      }, per);
    });
  }

  /* ---------------- Chat flow ---------------- */
  var busy = false;
  function sendMessage(text) {
    if (busy || !text.trim() || !API) return;
    busy = true;
    addMessage("user", assistantPeerLabel.user, text);
    thinkingEl.classList.remove("hidden");
    setStatus("THINKING", "busy");
    Head.setEmotion("thinking");

    Promise.resolve(API.chat(text))
      .then(function (data) {
        thinkingEl.classList.add("hidden");
        if (!data || data.error) throw new Error((data && data.error) || "no response");
        var resp = data.response || {};
        var spoken = resp.spoken_text || "...";
        var emotion = resp.emotion || "normal";
        var bubble = addMessage("bot", assistantPeerLabel.bot, "");
        Head.setEmotion(emotion);
        setStatus("SPEAKING", "busy");

        var play = data.audio_wav_base64
          ? Audio.playWavBase64(data.audio_wav_base64).catch(function () { return null; })
          : Promise.resolve(null);

        return play.then(function (clip) {
          Head.setSpeaking(true, clip ? clip.analyser : null);
          var dur = clip ? clip.duration * 1000 : null;
          var done = typewrite(bubble, spoken, dur);
          var audioDone = clip ? clip.ended : Promise.resolve();
          return Promise.all([done, audioDone]).then(function () {
            Head.setSpeaking(false, null);
            Head.setEmotion(emotion);
            setStatus("ONLINE", null);
          });
        });
      })
      .catch(function (err) {
        thinkingEl.classList.add("hidden");
        addMessage("error", "SYSTEM", "Dialogue failed: " + err.message);
        setStatus("ERROR", "error");
        Head.setEmotion("grumpy");
      })
      .then(function () { busy = false; });
  }

  /* ---------------- Push-to-talk (Python-side recording) ---------------- */
  function startListen() {
    if (busy || !API) return;
    var micBtn = document.getElementById("mic");
    micBtn.classList.add("recording");
    setStatus("RECORDING", "busy");
    Promise.resolve(API.listen())
      .then(function (res) {
        micBtn.classList.remove("recording");
        setStatus("ONLINE", null);
        if (!res || res.error) { addMessage("error", "SYSTEM", "Voice failed: " + ((res && res.error) || "?")); return; }
        var text = (res.text || "").trim();
        if (text) { document.getElementById("input").value = text; sendMessage(text); }
        else addMessage("system", "SYSTEM", "Didn't catch that.");
      })
      .catch(function (err) {
        micBtn.classList.remove("recording");
        setStatus("ERROR", "error");
        addMessage("error", "SYSTEM", "Voice failed: " + err.message);
      });
  }

  /* ---------------- Boot sequence ---------------- */
  function runBoot(lines) {
    var bootEl = document.getElementById("boot");
    var textEl = document.getElementById("boot-text");
    var appEl = document.getElementById("app");
    bootEl.classList.remove("hidden");
    var done = false;

    function finish() {
      if (done) return;
      done = true;
      bootEl.classList.add("fade-out");
      setTimeout(function () {
        bootEl.classList.add("hidden");
        appEl.classList.remove("hidden");
        appEl.classList.add("fade-in");
        window.dispatchEvent(new Event("resize"));
        document.getElementById("input").focus();
      }, 480);
    }

    document.addEventListener("keydown", function once() {
      document.removeEventListener("keydown", once);
      finish();
    });
    bootEl.addEventListener("click", finish);

    var li = 0, ci = 0, out = "";
    var cursor = '<span class="boot-cursor">&nbsp;</span>';
    Audio.beep(660, 0.12);
    (function step() {
      if (done) return;
      if (li >= lines.length) { setTimeout(finish, 600); return; }
      var line = lines[li];
      if (ci < line.length) {
        out += line[ci];
        ci++;
        textEl.innerHTML = out + cursor;
        setTimeout(step, 12 + Math.random() * 18);
      } else {
        out += "\n";
        li++; ci = 0;
        if (line.indexOf("OK") !== -1) Audio.beep(880, 0.05);
        textEl.innerHTML = out + cursor;
        setTimeout(step, 90);
      }
    })();
  }

  /* ---------------- Init ---------------- */
  function applyMetadata(meta) {
    var app = (meta && meta.app) || {};
    if (app.name) {
      document.getElementById("brand-name").textContent = String(app.name).toUpperCase();
      assistantPeerLabel.bot = String(app.assistant_label || app.name).toUpperCase();
    }
    if (app.subtitle) document.getElementById("brand-sub").textContent = app.subtitle;
    if (app.intro_text) addMessage("bot", assistantPeerLabel.bot, app.intro_text);
  }

  Head.init();
  whenBridgeReady().then(function (api) {
    API = api;
    return Promise.resolve(api.metadata()).catch(function () { return {}; });
  }).then(function (meta) {
    meta = meta || {};
    if (meta.error) meta = {};
    applyMetadata(meta);
    if (meta.has_avatars && API) {
      Promise.resolve(API.avatars()).then(function (map) {
        Head.loadAvatars(map);
      }).catch(function (e) { showError("Fetching avatars failed: " + (e && e.message || e)); });
    } else if (!meta.has_avatars) {
      showError("Backend reports no avatars (has_avatars=false).");
    }
    runBoot(Array.isArray(meta.boot_lines) && meta.boot_lines.length ? meta.boot_lines : DEFAULT_BOOT);
  });

  // Composer
  document.getElementById("composer").addEventListener("submit", function (e) {
    e.preventDefault();
    var input = document.getElementById("input");
    var text = input.value.trim();
    if (!text) return;
    input.value = "";
    sendMessage(text);
  });

  var micBtn = document.getElementById("mic");
  if (micBtn) micBtn.addEventListener("click", startListen);
})();
