// ほかの端末との同期の中核。HAITO とチェックシート(../ir-check/)の両方から読み込む。
// 同期コード(端末で作るランダムな26文字)から、文書ID(SHA-256)と暗号鍵(PBKDF2→AES-GCM)を作る。
// 送るのは暗号文だけなので、接続先(Firebase)からは中身を読めない。コードを失くすと誰にも戻せない。
// 中身はこのサイトの localStorage のうち、HAITOの保有銘柄とチェックシートの採点・株価。
// 衝突は「最後に編集した端末が勝つ」。
(function () {
  "use strict";
  var CFG = window.HAITO_SYNC_CONFIG || null;
  var CODE_KEY = "haitoSyncCode", META_KEY = "haitoSyncMeta";
  var HAITO_KEY = "haitoDashboardV1";
  // 送る localStorage のキー → 送るときの名前
  var CHECK = { irCheckV1: "irCheck", irPrices: "irPrices" };
  // 端末ごとの表示の都合は送らない
  var LOCAL_ONLY = ["lastExport", "installDismissed", "installMoved"];
  var ALPHA = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"; // 見間違えやすい I L O 0 1 を除く

  var hooks = { onApplied: function () {}, onStatus: function () {}, toast: function () {}, onExternal: function () {} };
  var timer = null, busy = false, again = 0, retry = null, keyCache = null, started = false;
  var S = { error: "" };

  function get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function set(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) {} }
  function code() { return get(CODE_KEY) || ""; }
  function meta() { try { return JSON.parse(get(META_KEY) || "{}") || {}; } catch (e) { return {}; } }
  function setMeta(m) { set(META_KEY, JSON.stringify(m)); }
  function on() { return !!(CFG && code() && window.crypto && crypto.subtle); }
  function norm(c) { return String(c || "").toUpperCase().replace(/[^A-Z0-9]/g, ""); }
  function fmt(c) { return norm(c).replace(/(.{4})(?=.)/g, "$1-"); }
  function newCode() {
    var b = new Uint8Array(26), out = "";
    crypto.getRandomValues(b);
    for (var i = 0; i < b.length; i++) out += ALPHA[b[i] % ALPHA.length];
    return out;
  }
  function b64(buf) {
    var s = "", a = new Uint8Array(buf);
    for (var i = 0; i < a.length; i += 0x8000) s += String.fromCharCode.apply(null, a.subarray(i, i + 0x8000));
    return btoa(s);
  }
  function unb64(s) { var r = atob(s), a = new Uint8Array(r.length); for (var i = 0; i < r.length; i++) a[i] = r.charCodeAt(i); return a; }
  function hash(s) { var h = 0; for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return s.length + ":" + h; }

  function keys(c) {
    c = norm(c);
    if (keyCache && keyCache.code === c) return Promise.resolve(keyCache);
    var enc = new TextEncoder();
    var idP = crypto.subtle.digest("SHA-256", enc.encode("haito-sync-id:" + c)).then(function (h) {
      return Array.prototype.map.call(new Uint8Array(h), function (x) { return ("0" + x.toString(16)).slice(-2); }).join("");
    });
    var keyP = crypto.subtle.importKey("raw", enc.encode(c), "PBKDF2", false, ["deriveKey"]).then(function (base) {
      return crypto.subtle.deriveKey({ name: "PBKDF2", salt: enc.encode("haito-sync-key"), iterations: 150000, hash: "SHA-256" },
        base, { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
    });
    return Promise.all([idP, keyP]).then(function (r) { keyCache = { code: c, id: r[0], key: r[1] }; return keyCache; });
  }
  function url(id, extra) {
    var base = CFG.base || "https://firestore.googleapis.com/v1";
    return base + "/projects/" + encodeURIComponent(CFG.projectId) + "/databases/" + encodeURIComponent(CFG.databaseId || "(default)") +
      "/documents/vaults/" + id + "?key=" + encodeURIComponent(CFG.apiKey || "") + (extra || "");
  }

  // 同期する中身を localStorage から作る(どちらのアプリも保存してから呼ぶ)
  function payload() {
    var st = {};
    try { st = JSON.parse(get(HAITO_KEY) || "{}") || {}; } catch (e) { st = {}; }
    LOCAL_ONLY.forEach(function (k) { delete st[k]; });
    var out = { state: st };
    Object.keys(CHECK).forEach(function (k) {
      try { var v = get(k); if (v) out[CHECK[k]] = JSON.parse(v); } catch (e) {}
    });
    return JSON.stringify(out);
  }
  function applyPlain(plain) {
    var d = JSON.parse(plain), cur = {};
    try { cur = JSON.parse(get(HAITO_KEY) || "{}") || {}; } catch (e) { cur = {}; }
    var st = d.state || {};
    LOCAL_ONLY.forEach(function (k) { if (k in cur) st[k] = cur[k]; else delete st[k]; });
    set(HAITO_KEY, JSON.stringify(st));
    Object.keys(CHECK).forEach(function (k) {
      var v = d[CHECK[k]];
      set(k, v && typeof v === "object" ? JSON.stringify(v) : null);
    });
    hooks.onApplied();
  }

  function fetchVault(c) {
    return keys(c).then(function (k) {
      return fetch(url(k.id)).then(function (r) {
        if (r.status === 404) return null;
        if (!r.ok) throw new Error("http " + r.status);
        return r.json().then(function (doc) {
          var f = doc.fields || {};
          var iv = unb64(f.iv.stringValue), ct = unb64(f.ct.stringValue);
          return crypto.subtle.decrypt({ name: "AES-GCM", iv: iv }, k.key, ct).then(function (pt) {
            return { rev: doc.updateTime, t: Number(f.t.integerValue), data: new TextDecoder().decode(pt) };
          }, function () { throw new Error("decrypt"); });
        });
      });
    });
  }
  function putVault(c, plain, t, rev) {
    return keys(c).then(function (k) {
      var iv = crypto.getRandomValues(new Uint8Array(12));
      return crypto.subtle.encrypt({ name: "AES-GCM", iv: iv }, k.key, new TextEncoder().encode(plain)).then(function (ct) {
        var body = { fields: { v: { integerValue: "1" }, iv: { stringValue: b64(iv) }, ct: { stringValue: b64(ct) }, t: { integerValue: String(t) } } };
        var pre = rev ? "&currentDocument.updateTime=" + encodeURIComponent(rev) : "&currentDocument.exists=false";
        return fetch(url(k.id, pre), { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
          .then(function (r) {
            if (r.ok) return r.json().then(function (d) { return d.updateTime; });
            if (r.status === 400 || r.status === 409 || r.status === 412) return null; // 先に他の端末が書いた
            throw new Error("http " + r.status);
          });
      });
    });
  }

  // 1回の同期: 相手の方が新しく編集されていれば取り込み、こちらが新しければ送る
  function syncNow(manual) {
    if (!on()) return Promise.resolve();
    // 通信中に編集や「今すぐ同期」が重なったら、終わってからもう一度回す
    if (busy) { again = Math.max(again, manual ? 2 : 1); return Promise.resolve(); }
    clearTimeout(retry);
    if (!navigator.onLine) { S.error = "オフライン"; hooks.onStatus(); return Promise.resolve(); }
    busy = true;
    var c = code(), m = meta();
    var mine = payload(), h = hash(mine);
    var dirty = m.hash !== h;
    if (dirty && !m.editT) m.editT = Date.now(); // 閉じている間にもう一方のアプリで変えた分など
    return fetchVault(c).then(function (remote) {
      if (remote && remote.rev !== m.rev && (!dirty || remote.t >= m.editT)) {
        applyPlain(remote.data);
        setMeta({ rev: remote.rev, t: remote.t, hash: hash(payload()), at: Date.now() });
        if (dirty) hooks.toast("ほかの端末でより新しく編集された内容に合わせました");
        else if (manual) hooks.toast("ほかの端末の内容を取り込みました");
        return;
      }
      if (!dirty && remote) { setMeta(Object.assign(meta(), { at: Date.now() })); if (manual) hooks.toast("最新の状態です"); return; }
      var t = Math.max(m.editT || Date.now(), remote ? remote.t + 1 : 0);
      return putVault(c, mine, t, remote ? remote.rev : null).then(function (rev) {
        if (!rev) { again = Math.max(again, manual ? 2 : 1); return; } // 書き込みが重なった→もう一度
        // 通信中に重ねて編集されていたら、その編集時刻(lh/editT)は残して次の回に送る
        var m3 = meta(), next = { rev: rev, t: t, hash: h, at: Date.now() };
        if (m3.lh && m3.lh !== h) { next.lh = m3.lh; next.editT = m3.editT; }
        setMeta(next);
        if (manual) hooks.toast("ほかの端末へ送りました");
      });
    }).then(function () { S.error = ""; }, function (e) {
      S.error = e && e.message === "decrypt" ? "同期コードが合いません" : "つながりません";
      if (S.error === "つながりません") retry = setTimeout(function () { syncNow(false); }, 20000);
    }).then(function () {
      busy = false; hooks.onStatus();
      if (again) { var m2 = again === 2; again = 0; syncNow(m2); }
    });
  }
  // 中身が本当に変わったときだけ編集時刻を残す(描画のついでの保存は数えない)
  function noteEdit() {
    var m = meta(), h = hash(payload());
    if (h !== m.hash && h !== m.lh) { m.lh = h; m.editT = Date.now(); setMeta(m); }
  }
  function soon() {
    if (!on()) return;
    noteEdit();
    clearTimeout(timer);
    timer = setTimeout(function () { syncNow(false); }, 2500);
  }

  // この端末から始める: 今の内容で新しい置き場所を作る
  function startNew() {
    var c = newCode();
    return putVault(c, payload(), Date.now(), null).then(function (rev) {
      if (!rev) throw new Error("exists");
      set(CODE_KEY, c);
      setMeta({ rev: rev, t: Date.now(), hash: hash(payload()), at: Date.now() });
      S.error = "";
      return c;
    });
  }
  // コードでつなぐ: 相手の内容を読むだけ(置き換えるかは呼ぶ側が確かめてから adopt する)
  function peek(c) { return fetchVault(norm(c)); }
  function adopt(c, remote) {
    set(CODE_KEY, norm(c));
    applyPlain(remote.data);
    setMeta({ rev: remote.rev, t: remote.t, hash: hash(payload()), at: Date.now() });
    S.error = "";
  }
  function off() { set(CODE_KEY, null); set(META_KEY, null); keyCache = null; S.error = ""; }

  function init(h) {
    Object.keys(h || {}).forEach(function (k) { hooks[k] = h[k]; });
    if (started) return;
    started = true;
    // 同じ端末のもう一方のタブ(HAITO/チェックシート)が変えたとき: 画面を読み直し、自分の変更なら送る
    window.addEventListener("storage", function (e) {
      if (e.key === HAITO_KEY || CHECK[e.key]) { hooks.onExternal(e.key); soon(); }
      if (e.key === CODE_KEY || e.key === META_KEY) hooks.onStatus();
    });
    window.addEventListener("online", function () { syncNow(false); });
    document.addEventListener("visibilitychange", function () { if (!document.hidden) syncNow(false); });
    setInterval(function () { if (!document.hidden) syncNow(false); }, 60000);
    syncNow(false);
  }

  window.HaitoSync = {
    configured: function () { return !!CFG; }, on: on, code: code, meta: meta, status: S,
    norm: norm, fmt: fmt, startNew: startNew, peek: peek, adopt: adopt, off: off,
    syncNow: syncNow, soon: soon, init: init
  };
})();
