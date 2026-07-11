// sound.js - shared Web Audio SFX engine for all pages
(function () {
  'use strict';
  var _ctx = null;
  function ctx() {
    if (!_ctx) _ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (_ctx.state === 'suspended') _ctx.resume();
    return _ctx;
  }

  function tone(freq, type, start, dur, gain, c) {
    var o = c.createOscillator(), g = c.createGain();
    o.type = type; o.frequency.value = freq;
    g.gain.setValueAtTime(0, start);
    g.gain.linearRampToValueAtTime(gain, start + 0.012);
    g.gain.exponentialRampToValueAtTime(0.001, start + dur);
    o.connect(g); g.connect(c.destination);
    o.start(start); o.stop(start + dur + 0.01);
  }

  // low-passed osc tone, used for dull/blocked/error timbres
  function toneLP(freq, type, start, dur, gain, cutoff, c) {
    var o = c.createOscillator(), g = c.createGain(), filt = c.createBiquadFilter();
    filt.type = 'lowpass'; filt.frequency.value = cutoff;
    o.type = type; o.frequency.value = freq;
    g.gain.setValueAtTime(gain, start);
    g.gain.exponentialRampToValueAtTime(0.001, start + dur);
    o.connect(filt); filt.connect(g); g.connect(c.destination);
    o.start(start); o.stop(start + dur + 0.01);
  }

  function noise(start, dur, gainVal, centerFreq, q, c) {
    var len = Math.ceil(c.sampleRate * (dur + 0.01));
    var buf = c.createBuffer(1, len, c.sampleRate);
    var d = buf.getChannelData(0);
    for (var i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    var src = c.createBufferSource(), filt = c.createBiquadFilter(), g = c.createGain();
    filt.type = 'bandpass'; filt.frequency.value = centerFreq; filt.Q.value = q || 1.5;
    g.gain.setValueAtTime(gainVal, start);
    g.gain.exponentialRampToValueAtTime(0.001, start + dur);
    src.buffer = buf; src.connect(filt); filt.connect(g); g.connect(c.destination);
    src.start(start);
  }

  function sweep(f0, f1, type, start, dur, gainVal, c) {
    var o = c.createOscillator(), g = c.createGain();
    o.type = type;
    o.frequency.setValueAtTime(f0, start);
    o.frequency.exponentialRampToValueAtTime(f1, start + dur);
    g.gain.setValueAtTime(gainVal, start);
    g.gain.exponentialRampToValueAtTime(0.001, start + dur);
    o.connect(g); g.connect(c.destination);
    o.start(start); o.stop(start + dur + 0.01);
  }

  var SOUNDS = {
    // ── gameplay ──────────────────────────────────────────────
    stone: function () {
      var c = ctx(), t = c.currentTime;
      noise(t, 0.08, 0.5, 580, 2.0, c);
      tone(720, 'sine', t, 0.055, 0.13, c);
    },
    stone_opp: function () {
      var c = ctx(), t = c.currentTime;
      noise(t, 0.09, 0.42, 420, 2.0, c);
      tone(500, 'sine', t, 0.06, 0.1, c);
    },
    correct: function () {
      var c = ctx(), t = c.currentTime;
      var freqs = [523.25, 659.25, 783.99, 1046.5];
      freqs.forEach(function (f, i) {
        var o = c.createOscillator(), g = c.createGain();
        o.type = 'triangle'; o.frequency.value = f;
        var st = t + i * 0.08;
        g.gain.setValueAtTime(0, st);
        g.gain.linearRampToValueAtTime(0.27, st + 0.015);
        g.gain.setValueAtTime(0.27, st + 0.06);
        g.gain.exponentialRampToValueAtTime(0.001, st + 0.55);
        o.connect(g); g.connect(c.destination);
        o.start(st); o.stop(st + 0.6);
      });
    },
    // restored original dull two-tone failure buzz (sawtooth + square, low-passed)
    wrong: function () {
      var c = ctx(), t = c.currentTime;
      [[180, 'sawtooth'], [90, 'square']].forEach(function (p, i) {
        var o = c.createOscillator(), g = c.createGain(), filt = c.createBiquadFilter();
        filt.type = 'lowpass'; filt.frequency.value = 400;
        o.type = p[1]; o.frequency.value = p[0];
        var st = t + i * 0.15;
        g.gain.setValueAtTime(0.2, st);
        g.gain.exponentialRampToValueAtTime(0.001, st + 0.35);
        o.connect(filt); filt.connect(g); g.connect(c.destination);
        o.start(st); o.stop(st + 0.35);
      });
    },
    next: function () {
      var c = ctx(), t = c.currentTime;
      sweep(560, 1100, 'sine', t, 0.13, 0.1, c);
      sweep(280, 560, 'sine', t + 0.05, 0.11, 0.07, c);
    },
    hint: function () {
      var c = ctx(), t = c.currentTime;
      tone(1047, 'sine', t, 0.14, 0.17, c);
      tone(1319, 'sine', t + 0.1, 0.13, 0.14, c);
    },
    // ── RPG / progression ─────────────────────────────────────
    xp: function () {
      var c = ctx(), t = c.currentTime;
      tone(880, 'triangle', t, 0.12, 0.13, c);
      tone(1100, 'triangle', t + 0.07, 0.14, 0.11, c);
    },
    xp_combo: function () {
      var c = ctx(), t = c.currentTime;
      [880, 1100, 1320].forEach(function (f, i) { tone(f, 'triangle', t + i * 0.065, 0.2, 0.13, c); });
    },
    streak3: function () {
      var c = ctx(), t = c.currentTime;
      [659, 784, 1047].forEach(function (f, i) { tone(f, 'triangle', t + i * 0.085, 0.26, 0.21, c); });
    },
    streak5: function () {
      var c = ctx(), t = c.currentTime;
      [659, 784, 880, 1047, 1175].forEach(function (f, i) { tone(f, 'sine', t + i * 0.075, 0.28, 0.19, c); });
    },
    streak7: function () {
      var c = ctx(), t = c.currentTime;
      [523, 587, 659, 698, 784, 880, 1047].forEach(function (f, i) { tone(f, 'sine', t + i * 0.07, 0.35, 0.18, c); });
    },
    rankup: function () {
      var c = ctx(), t = c.currentTime;
      [293.66, 369.99, 440].forEach(function (f) {
        var o = c.createOscillator(), g = c.createGain();
        o.type = 'sine'; o.frequency.value = f;
        g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(0.17, t + 0.05);
        g.gain.setValueAtTime(0.17, t + 0.3); g.gain.exponentialRampToValueAtTime(0.001, t + 1.2);
        o.connect(g); g.connect(c.destination); o.start(t); o.stop(t + 1.25);
      });
      tone(587.33, 'sine', t + 0.4, 0.75, 0.14, c);
      tone(880, 'sine', t + 0.72, 0.55, 0.12, c);
    },
    quest_tick: function () {
      var c = ctx(), t = c.currentTime;
      tone(1180, 'sine', t, 0.065, 0.12, c);
    },
    quest_complete: function () {
      var c = ctx(), t = c.currentTime;
      var seq = [[440, 0.13], [554, 0.13], [659, 0.13], [880, 0.45]];
      var dt = 0;
      seq.forEach(function (p) { tone(p[0], 'triangle', t + dt, p[1] + 0.22, 0.23, c); dt += p[1]; });
      [659, 830, 987].forEach(function (f) {
        var o = c.createOscillator(), g = c.createGain();
        o.type = 'sine'; o.frequency.value = f;
        var st = t + dt - 0.1;
        g.gain.setValueAtTime(0, st); g.gain.linearRampToValueAtTime(0.15, st + 0.06);
        g.gain.exponentialRampToValueAtTime(0.001, st + 0.95);
        o.connect(g); g.connect(c.destination); o.start(st); o.stop(st + 1.0);
      });
    },
    map_move: function () {
      var c = ctx(), t = c.currentTime;
      noise(t, 0.02, 0.055, 900, 1.2, c);
      tone(320, 'triangle', t, 0.075, 0.04, c);
      tone(430, 'triangle', t + 0.055, 0.085, 0.05, c);
      tone(1040, 'sine', t + 0.1, 0.12, 0.03, c);
    },
    map_replay: function () {
      var c = ctx(), t = c.currentTime;
      noise(t, 0.02, 0.05, 1100, 1.6, c);
      tone(300, 'triangle', t, 0.07, 0.035, c);
      tone(392, 'triangle', t + 0.05, 0.08, 0.045, c);
      tone(1175, 'sine', t + 0.095, 0.16, 0.03, c);
      tone(1568, 'sine', t + 0.14, 0.12, 0.018, c);
    },
    map_quest_focus: function () {
      var c = ctx(), t = c.currentTime;
      [523.25, 659.25, 783.99].forEach(function (f, i) {
        tone(f, 'triangle', t + i * 0.085, 0.24, 0.075, c);
      });
      tone(1046.5, 'sine', t + 0.19, 0.34, 0.03, c);
    },
    map_locked: function () {
      var c = ctx(), t = c.currentTime;
      noise(t, 0.025, 0.045, 420, 1.0, c);
      toneLP(180, 'square', t, 0.09, 0.055, 320, c);
      toneLP(145, 'triangle', t + 0.095, 0.11, 0.05, 300, c);
    },
    map_start: function () {
      var c = ctx(), t = c.currentTime;
      tone(440, 'triangle', t, 0.13, 0.05, c);
      tone(659.25, 'triangle', t + 0.08, 0.18, 0.065, c);
      tone(880, 'sine', t + 0.14, 0.24, 0.045, c);
    },
    // accept a guild quest: short rising brass-like fanfare
    accept_quest: function () {
      var c = ctx(), t = c.currentTime;
      tone(392, 'sawtooth', t, 0.16, 0.12, c);
      tone(587.33, 'sawtooth', t + 0.11, 0.26, 0.12, c);
      tone(587.33, 'triangle', t + 0.11, 0.26, 0.06, c);
    },
    // claim reward: bright chest "ka-ching" + scattered coin pings
    claim: function () {
      var c = ctx(), t = c.currentTime;
      [784, 1047, 1319].forEach(function (f) { tone(f, 'triangle', t, 0.5, 0.16, c); });
      [1568, 1760, 2093, 1865].forEach(function (f, i) {
        tone(f, 'sine', t + 0.18 + i * 0.07, 0.18, 0.09, c);
      });
    },
    evolve: function () {
      var c = ctx(), t = c.currentTime;
      sweep(200, 1800, 'sine', t, 0.7, 0.16, c);
      sweep(150, 1200, 'triangle', t + 0.05, 0.65, 0.1, c);
      [400, 600, 900, 1300].forEach(function (f, i) { tone(f, 'sine', t + 0.6 + i * 0.065, 0.28, 0.09, c); });
    },
    purchase: function () {
      var c = ctx(), t = c.currentTime;
      tone(880, 'triangle', t, 0.12, 0.2, c);
      tone(1320, 'triangle', t + 0.1, 0.15, 0.18, c);
    },
    equip: function () {
      var c = ctx(), t = c.currentTime;
      noise(t, 0.04, 0.42, 1800, 1.2, c);
      sweep(400, 200, 'sawtooth', t, 0.12, 0.1, c);
      tone(440, 'sine', t + 0.07, 0.18, 0.09, c);
    },
    unequip: function () {
      var c = ctx(), t = c.currentTime;
      noise(t, 0.04, 0.32, 1400, 1.2, c);
      sweep(260, 180, 'sine', t, 0.14, 0.09, c);
    },
    // ── match flow ────────────────────────────────────────────
    game_start: function () {
      var c = ctx(), t = c.currentTime;
      var o = c.createOscillator(), g = c.createGain();
      o.type = 'sine'; o.frequency.value = 293.66;
      g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(0.3, t + 0.025);
      g.gain.exponentialRampToValueAtTime(0.001, t + 1.8);
      o.connect(g); g.connect(c.destination); o.start(t); o.stop(t + 1.85);
      tone(440, 'sine', t + 0.02, 1.5, 0.07, c);
    },
    win: function () {
      var c = ctx(), t = c.currentTime;
      [523, 659, 784, 1047, 1319].forEach(function (f, i) {
        var o = c.createOscillator(), g = c.createGain();
        o.type = 'sine'; o.frequency.value = f;
        var st = t + i * 0.12;
        g.gain.setValueAtTime(0, st); g.gain.linearRampToValueAtTime(0.19, st + 0.02);
        g.gain.exponentialRampToValueAtTime(0.001, st + 0.7);
        o.connect(g); g.connect(c.destination); o.start(st); o.stop(st + 0.75);
      });
    },
    lose: function () {
      var c = ctx(), t = c.currentTime;
      [330, 262, 220, 175].forEach(function (f, i) { tone(f, 'sine', t + i * 0.15, 0.4, 0.18, c); });
      sweep(250, 130, 'sawtooth', t + 0.3, 0.5, 0.09, c);
    },
    pass: function () {
      var c = ctx(), t = c.currentTime;
      sweep(620, 400, 'sine', t, 0.22, 0.15, c);
    },
    invite: function () {
      var c = ctx(), t = c.currentTime;
      tone(660, 'sine', t, 0.15, 0.18, c);
      tone(880, 'sine', t + 0.13, 0.15, 0.15, c);
    },
    message: function () {
      var c = ctx(), t = c.currentTime;
      tone(880, 'sine', t, 0.1, 0.12, c);
      tone(1100, 'sine', t + 0.085, 0.1, 0.1, c);
    },
    // ── countdown ticks (byo-yomi) ────────────────────────────
    tick_normal: function () {
      var c = ctx(), t = c.currentTime;
      tone(760, 'sine', t, 0.05, 0.12, c);
    },
    tick_urgent: function () {
      var c = ctx(), t = c.currentTime;
      tone(1180, 'sine', t, 0.07, 0.17, c);
    },
    // ── generic UI (button delegation) ────────────────────────
    // light but clearly audible default tap for any button
    ui_tap: function () {
      var c = ctx(), t = c.currentTime;
      tone(1000, 'sine', t, 0.04, 0.14, c);
      tone(1500, 'sine', t, 0.025, 0.08, c);
    },
    ui_nav: function () {
      var c = ctx(), t = c.currentTime;
      sweep(520, 920, 'sine', t, 0.1, 0.08, c);
    },
    ui_tab: function () {
      var c = ctx(), t = c.currentTime;
      tone(900, 'sine', t, 0.03, 0.06, c);
      tone(1200, 'sine', t + 0.04, 0.03, 0.05, c);
    },
    ui_open: function () {
      var c = ctx(), t = c.currentTime;
      sweep(420, 820, 'sine', t, 0.14, 0.09, c);
    },
    ui_close: function () {
      var c = ctx(), t = c.currentTime;
      sweep(820, 420, 'sine', t, 0.14, 0.09, c);
    },
    ui_toggle: function () {
      var c = ctx(), t = c.currentTime;
      tone(700, 'triangle', t, 0.05, 0.1, c);
    },
    ui_danger: function () {
      var c = ctx(), t = c.currentTime;
      sweep(220, 110, 'sawtooth', t, 0.24, 0.14, c);
      toneLP(150, 'square', t + 0.02, 0.2, 0.1, 300, c);
    },
    ui_blocked: function () {
      var c = ctx(), t = c.currentTime;
      toneLP(140, 'square', t, 0.09, 0.16, 220, c);
    }
  };

  window.SFX = {
    get muted() { return localStorage.getItem('sfx_muted') === '1'; },
    set muted(v) { localStorage.setItem('sfx_muted', v ? '1' : '0'); },
    play: function (name) {
      if (this.muted) return;
      try { var fn = SOUNDS[name]; if (fn) fn(); } catch (e) {}
    },
    toggle: function () {
      this.muted = !this.muted;
      return !this.muted;
    }
  };

  // ── Global click delegation ───────────────────────────────────
  // Guarantees every button makes a sound. Resolution order:
  //   1. data-sfx="none"          → silent (element plays its own SFX elsewhere)
  //   2. blocked/locked/disabled  → ui_blocked
  //   3. data-sfx="<name>"        → that specific sound
  //   4. fallback                 → ui_tap (ultra-light)
  var BTN_SELECTOR = 'button, [role="button"], [data-sfx], [onclick], .btn, .qc-btn, input[type="button"], input[type="submit"]';
  function isBlocked(el) {
    if (el.disabled) return true;
    if (el.getAttribute && el.getAttribute('aria-disabled') === 'true') return true;
    var cl = el.classList;
    return !!(cl && (cl.contains('locked') || cl.contains('disabled') || cl.contains('is-locked')));
  }
  document.addEventListener('click', function (e) {
    if (SFX.muted) return;
    var el = e.target && e.target.closest ? e.target.closest(BTN_SELECTOR) : null;
    if (!el) return;
    var tag = el.getAttribute('data-sfx');
    if (tag === 'none') return;
    if (isBlocked(el)) { SFX.play('ui_blocked'); return; }
    if (tag) { SFX.play(tag); return; }
    SFX.play('ui_tap');
  }, true);
})();
