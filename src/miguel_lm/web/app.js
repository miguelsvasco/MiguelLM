/* MiguelLM web UI logic. Persona-free: all personal content (branding, boot
 * lines, the 3D head) is fetched from the server at runtime. */
(function () {
  "use strict";

  var TOKEN = window.MIGUELLM_TOKEN || "";
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

  /* ---------------- API helpers ---------------- */
  function authHeaders(extra) {
    var h = extra || {};
    if (TOKEN) h["Authorization"] = "Bearer " + TOKEN;
    return h;
  }
  function getJSON(path) {
    return fetch(path, { headers: authHeaders({}) }).then(function (r) {
      if (!r.ok) throw new Error(path + " -> " + r.status);
      return r.json();
    });
  }
  function postJSON(path, body) {
    return fetch(path, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    }).then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok) throw new Error(data.error || (path + " -> " + r.status));
        return data;
      });
    });
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
    function b64ToBytes(b64) {
      var bin = atob(b64);
      var bytes = new Uint8Array(bin.length);
      for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      return bytes;
    }
    // Returns a promise resolving to { analyser, ended } where ended is a promise.
    function playWavBase64(b64) {
      var c = ac();
      if (!c) return Promise.resolve(null);
      return c.decodeAudioData(b64ToBytes(b64).buffer.slice(0)).then(function (buffer) {
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
    return { playWavBase64: playWavBase64, blip: blip, beep: beep, ctx: ac };
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
      // morphs + transform + color tint + hyperspace speed
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
        console.warn("Head init failed", e);
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

    function loadHead() {
      if (!ok || !THREE.GLTFLoader) return;
      var loader = new THREE.GLTFLoader();
      if (TOKEN) loader.setRequestHeader({ Authorization: "Bearer " + TOKEN });
      loader.load(
        "/assets/head",
        function (gltf) {
          headGroup = new THREE.Group();
          var box = new THREE.Box3().setFromObject(gltf.scene);
          var size = box.getSize(new THREE.Vector3());
          var center = box.getCenter(new THREE.Vector3());
          var scale = 1.6 / (Math.max(size.x, size.y, size.z) || 1);
          gltf.scene.traverse(function (node) {
            if (!node.isMesh) return;
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
        },
        undefined,
        function (err) { console.warn("No 3D head:", err && err.message); }
      );
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
      // ease current toward target
      current.tilt += (target.tilt - current.tilt) * 0.06;
      current.speed += (target.speed - current.speed) * 0.06;
      current.bob += (target.bob - current.bob) * 0.06;

      // hyperspace
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

      // head pose + morphs
      if (headGroup) {
        headGroup.position.y = Math.sin(t) * current.bob;
        headGroup.rotation.y = Math.sin(t * 0.4) * 0.25 + current.tilt;
        headGroup.rotation.z = current.tilt * 0.4;
        var m = target.morph || {};
        ["smile", "frown", "browRaise"].forEach(function (k) {
          applyMorph(k, m[k] || 0);
        });
        // lip-sync
        var targetJaw = 0;
        if (speaking) {
          if (analyser) {
            analyser.getByteTimeDomainData(freqData);
            var sum = 0;
            for (var j = 0; j < freqData.length; j++) { var v = (freqData[j] - 128) / 128; sum += v * v; }
            targetJaw = Math.min(1, Math.sqrt(sum / freqData.length) * 4.5);
          } else {
            targetJaw = (Math.sin(t * 22) * 0.5 + 0.5) * 0.5; // synthetic when no audio
          }
        }
        jaw += (targetJaw - jaw) * 0.4;
        applyMorph("jawOpen", jaw);
      }

      renderer.render(scene, camera);
    }

    return { init: init, loadHead: loadHead, setEmotion: setEmotion, setSpeaking: setSpeaking };
  })();

  /* ---------------- DOM helpers ---------------- */
  var messagesEl = document.getElementById("messages");
  var thinkingEl = document.getElementById("thinking");
  var statusEl = document.getElementById("status");
  var statusText = document.getElementById("status-text");

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
    if (busy || !text.trim()) return;
    busy = true;
    addMessage("user", assistantPeerLabel.user, text);
    thinkingEl.classList.remove("hidden");
    setStatus("THINKING", "busy");
    Head.setEmotion("confused");

    postJSON("/chat", { text: text })
      .then(function (data) {
        thinkingEl.classList.add("hidden");
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
      .finally(function () { busy = false; });
  }

  // Labels come from /metadata (persona-free defaults until then).
  var assistantPeerLabel = { user: "YOU", bot: "MIGUELLM" };

  /* ---------------- Push-to-talk mic ---------------- */
  var Mic = (function () {
    var stream = null, ctx = null, processor = null, srcNode = null, chunks = [], rate = 16000, recording = false;
    var micBtn = document.getElementById("mic");

    function encodeWav(samples, sampleRate) {
      var buffer = new ArrayBuffer(44 + samples.length * 2);
      var view = new DataView(buffer);
      function str(off, s) { for (var i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i)); }
      str(0, "RIFF"); view.setUint32(4, 36 + samples.length * 2, true); str(8, "WAVE");
      str(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
      view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true);
      view.setUint16(32, 2, true); view.setUint16(34, 16, true);
      str(36, "data"); view.setUint32(40, samples.length * 2, true);
      var off = 44;
      for (var i = 0; i < samples.length; i++, off += 2) {
        var s = Math.max(-1, Math.min(1, samples[i]));
        view.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      }
      return buffer;
    }
    function bufToB64(buf) {
      var bytes = new Uint8Array(buf), bin = "";
      for (var i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
      return btoa(bin);
    }

    function start() {
      if (recording || busy) return;
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        addMessage("error", "SYSTEM", "Microphone not available in this browser.");
        return;
      }
      navigator.mediaDevices.getUserMedia({ audio: true }).then(function (s) {
        stream = s;
        var C = window.AudioContext || window.webkitAudioContext;
        ctx = new C();
        rate = ctx.sampleRate;
        srcNode = ctx.createMediaStreamSource(s);
        processor = ctx.createScriptProcessor(4096, 1, 1);
        chunks = [];
        processor.onaudioprocess = function (e) { chunks.push(new Float32Array(e.inputBuffer.getChannelData(0))); };
        srcNode.connect(processor);
        processor.connect(ctx.destination);
        recording = true;
        micBtn.classList.add("recording");
        setStatus("RECORDING", "busy");
      }).catch(function (err) {
        addMessage("error", "SYSTEM", "Mic error: " + err.message);
      });
    }

    function stop() {
      if (!recording) return;
      recording = false;
      micBtn.classList.remove("recording");
      setStatus("TRANSCRIBING", "busy");
      if (processor) processor.disconnect();
      if (srcNode) srcNode.disconnect();
      if (stream) stream.getTracks().forEach(function (t) { t.stop(); });
      var total = chunks.reduce(function (n, c) { return n + c.length; }, 0);
      var merged = new Float32Array(total), off = 0;
      chunks.forEach(function (c) { merged.set(c, off); off += c.length; });
      if (ctx) ctx.close();
      if (total < rate * 0.2) { setStatus("ONLINE", null); return; } // too short
      var b64 = bufToB64(encodeWav(merged, rate));
      postJSON("/transcribe", { wav_base64: b64, filename: "visitor.wav" })
        .then(function (data) {
          setStatus("ONLINE", null);
          var text = (data.text || "").trim();
          if (text) { document.getElementById("input").value = text; sendMessage(text); }
          else addMessage("system", "SYSTEM", "Didn't catch that.");
        })
        .catch(function (err) {
          setStatus("ERROR", "error");
          addMessage("error", "SYSTEM", "Transcription failed: " + err.message);
        });
    }

    if (micBtn) {
      micBtn.addEventListener("pointerdown", function (e) { e.preventDefault(); start(); });
      micBtn.addEventListener("pointerup", function (e) { e.preventDefault(); stop(); });
      micBtn.addEventListener("pointerleave", function () { if (recording) stop(); });
    }
    return {};
  })();

  /* ---------------- Boot sequence ---------------- */
  function runBoot(lines) {
    var bootEl = document.getElementById("boot");
    var textEl = document.getElementById("boot-text");
    var appEl = document.getElementById("app");
    var done = false;

    function finish() {
      if (done) return;
      done = true;
      bootEl.classList.add("fade-out");
      setTimeout(function () {
        bootEl.classList.add("hidden");
        appEl.classList.remove("hidden");
        appEl.classList.add("fade-in");
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
    return meta;
  }

  Head.init();
  getJSON("/metadata")
    .then(function (meta) {
      applyMetadata(meta);
      if (meta && meta.has_head) Head.loadHead();
      runBoot(meta && Array.isArray(meta.boot_lines) && meta.boot_lines.length ? meta.boot_lines : DEFAULT_BOOT);
    })
    .catch(function () {
      runBoot(DEFAULT_BOOT);
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
})();
