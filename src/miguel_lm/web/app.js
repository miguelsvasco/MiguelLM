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

  var EMOTIONS = ["warm", "amused", "confused", "serious", "speaking"];
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

  /* ---------------- 3D head in hyperspace ---------------- */
  var Head = (function () {
    var THREE = window.THREE;
    var renderer, scene, camera, stars, headGroup, morphMeshes = [], morphDict = {};
    var ok = false, raf = null;
    var speaking = false, analyser = null, freqData = null;
    var current = emotionParams("warm");
    var target = emotionParams("warm");
    var jaw = 0;
    var canvas = document.getElementById("head-canvas");
    var fallback = document.getElementById("head-fallback");

    function emotionParams(name) {
      var map = {
        warm:     { morph: { smile: 0.35 },                 tilt: 0.05,  speed: 0.4, hue: 0x2cff70, bob: 0.06 },
        amused:   { morph: { smile: 0.8, browRaise: 0.3 },  tilt: 0.18,  speed: 0.8, hue: 0x6dffa0, bob: 0.12 },
        confused: { morph: { browRaise: 0.7 },              tilt: -0.22, speed: 0.5, hue: 0x9ffcff, bob: 0.05 },
        serious:  { morph: { frown: 0.4 },                  tilt: 0.0,   speed: 0.25, hue: 0xff6b6b, bob: 0.02 },
        speaking: { morph: {},                              tilt: 0.04,  speed: 0.9, hue: 0x2cff70, bob: 0.08 },
      };
      return map[name] || map.warm;
    }

    function init() {
      if (!THREE) { degrade(); return; }
      try {
        renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        scene = new THREE.Scene();
        camera = new THREE.PerspectiveCamera(50, 1, 0.1, 1000);
        camera.position.set(0, 0, 3.2);
        buildStars();
        resize();
        window.addEventListener("resize", resize);
        ok = true;
        animate();
      } catch (e) {
        showError("WebGL init failed (no 3D head): " + (e && e.message ? e.message : e));
        degrade();
      }
    }

    function buildStars() {
      var N = 1200;
      var geo = new THREE.BufferGeometry();
      var pos = new Float32Array(N * 3);
      for (var i = 0; i < N; i++) {
        pos[i * 3] = (Math.random() - 0.5) * 12;
        pos[i * 3 + 1] = (Math.random() - 0.5) * 12;
        pos[i * 3 + 2] = -Math.random() * 40;
      }
      geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
      var mat = new THREE.PointsMaterial({ color: 0x2cff70, size: 0.05, transparent: true, opacity: 0.85 });
      stars = new THREE.Points(geo, mat);
      scene.add(stars);
    }

    function loadHeadFromBase64(b64) {
      if (!ok) { showError("3D head: WebGL/THREE not available in this webview."); return; }
      if (!THREE.GLTFLoader) { showError("3D head: GLTFLoader script did not load."); return; }
      if (!b64) { showError("3D head: backend returned no model."); return; }
      var loader = new THREE.GLTFLoader();
      try {
        loader.parse(b64ToArrayBuffer(b64), "", onHead, function (err) {
          showError("3D head parse failed: " + (err && err.message ? err.message : err));
        });
      } catch (e) { showError("3D head parse threw: " + e.message); }
    }

    function onHead(gltf) {
      headGroup = new THREE.Group();
      var box = new THREE.Box3().setFromObject(gltf.scene);
      var size = box.getSize(new THREE.Vector3());
      var center = box.getCenter(new THREE.Vector3());
      var scale = 1.6 / (Math.max(size.x, size.y, size.z) || 1);
      // Collect meshes FIRST — never mutate the tree during traverse(), or the
      // wireframe children we add get re-traversed (infinite recursion).
      var meshes = [];
      gltf.scene.traverse(function (node) { if (node.isMesh) meshes.push(node); });
      meshes.forEach(function (node) {
        var geom = node.geometry;
        node.material = new THREE.MeshBasicMaterial({ color: 0x0c2c14, transparent: true, opacity: 0.28 });
        node.material.morphTargets = true;
        if (node.morphTargetDictionary) morphDict = node.morphTargetDictionary;
        morphMeshes.push(node);
        var wire = new THREE.Mesh(geom, new THREE.MeshBasicMaterial({ color: 0x2cff70, wireframe: true }));
        wire.material.morphTargets = true;
        node.add(wire);
        morphMeshes.push(wire);
      });
      gltf.scene.position.sub(center.multiplyScalar(scale));
      gltf.scene.scale.setScalar(scale);
      headGroup.add(gltf.scene);
      scene.add(headGroup);
    }

    function degrade() {
      if (canvas) canvas.classList.add("hidden");
      if (fallback) fallback.classList.remove("hidden");
    }

    function resize() {
      if (!ok) return;
      var w = canvas.clientWidth || 1, h = canvas.clientHeight || 1;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    }

    function setEmotion(name) {
      target = emotionParams(name);
      var tag = document.getElementById("emotion-tag");
      if (tag) tag.textContent = name ? "[ " + name + " ]" : "";
    }
    function setSpeaking(on, an) { speaking = on; analyser = an || null; if (an) freqData = new Uint8Array(an.fftSize); }

    function applyMorph(name, value) {
      if (!(name in morphDict)) return;
      var idx = morphDict[name];
      morphMeshes.forEach(function (m) {
        if (m.morphTargetInfluences) m.morphTargetInfluences[idx] = value;
      });
    }

    var t = 0;
    function animate() {
      raf = requestAnimationFrame(animate);
      t += 0.016;
      current.tilt += (target.tilt - current.tilt) * 0.06;
      current.speed += (target.speed - current.speed) * 0.06;
      current.bob += (target.bob - current.bob) * 0.06;

      if (stars) {
        var p = stars.geometry.attributes.position.array;
        var spd = current.speed * 0.5 + (speaking ? 0.2 : 0);
        for (var i = 2; i < p.length; i += 3) {
          p[i] += spd;
          if (p[i] > 3) { p[i] = -40; }
        }
        stars.geometry.attributes.position.needsUpdate = true;
        stars.material.color.setHex(target.hue);
      }

      if (headGroup) {
        headGroup.position.y = Math.sin(t) * current.bob;
        headGroup.rotation.y = Math.sin(t * 0.4) * 0.25 + current.tilt;
        headGroup.rotation.z = current.tilt * 0.4;
        var m = target.morph || {};
        ["smile", "frown", "browRaise"].forEach(function (k) { applyMorph(k, m[k] || 0); });
        var targetJaw = 0;
        if (speaking) {
          if (analyser) {
            analyser.getByteTimeDomainData(freqData);
            var sum = 0;
            for (var j = 0; j < freqData.length; j++) { var v = (freqData[j] - 128) / 128; sum += v * v; }
            targetJaw = Math.min(1, Math.sqrt(sum / freqData.length) * 4.5);
          } else {
            targetJaw = (Math.sin(t * 22) * 0.5 + 0.5) * 0.5;
          }
        }
        jaw += (targetJaw - jaw) * 0.4;
        applyMorph("jawOpen", jaw);
      }

      renderer.render(scene, camera);
    }

    return { init: init, loadHeadFromBase64: loadHeadFromBase64, setEmotion: setEmotion, setSpeaking: setSpeaking };
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
    Head.setEmotion("confused");

    Promise.resolve(API.chat(text))
      .then(function (data) {
        thinkingEl.classList.add("hidden");
        if (!data || data.error) throw new Error((data && data.error) || "no response");
        var resp = data.response || {};
        var spoken = resp.spoken_text || "...";
        var emotion = resp.emotion || "warm";
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
            Head.setEmotion(emotion === "speaking" ? "warm" : emotion);
            setStatus("ONLINE", null);
          });
        });
      })
      .catch(function (err) {
        thinkingEl.classList.add("hidden");
        addMessage("error", "SYSTEM", "Dialogue failed: " + err.message);
        setStatus("ERROR", "error");
        Head.setEmotion("serious");
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
    if (meta.has_head && API) {
      Promise.resolve(API.head_model_b64()).then(function (b64) {
        Head.loadHeadFromBase64(b64);
      }).catch(function (e) { showError("Fetching 3D head failed: " + (e && e.message || e)); });
    } else if (!meta.has_head) {
      showError("Backend reports no head model (has_head=false).");
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
