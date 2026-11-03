// みんなのランキングに参加する端末の送信(希望した人だけ)。
// 送るのは「持っている銘柄」「買い増し候補」の国内株のコードの一覧だけ(株数・金額・口座・名前は送らない)。
// 置き場所は同期と同じ Firebase。Firebase の匿名ログインで端末ごとの番号(uid)をもらい、
// poll/{uid} の1件だけを書き換える(ルールで自分の分しか書けず、誰も読めない)。
// 集計は1日1回 GitHub Actions(tools/ranking_aggregate.py)がまとめて data/ranking.json に書き、アプリはそれを読む。
// 同期の暗号化とは別の仕組みで、送ったコードの一覧はアプリの管理者(Firebase のプロジェクトの持ち主)には見える。
(function () {
  "use strict";
  var CFG = window.HAITO_SYNC_CONFIG || null;
  var KEY = "haitoPoll";  // { on, asked(参加するか一度聞いた), uid, rt(refresh token), sent(送った中身のハッシュ), at(送った時刻) }
  var RESEND_MS = 7 * 86400000;  // 変わらなくても週に1回は送り直す(集計は90日送ってこない端末を外す)
  var token = null, tokenUntil = 0, timer = null, busy = false;

  function load() { try { return JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch (e) { return {}; } }
  function store(m) { try { localStorage.setItem(KEY, JSON.stringify(m)); } catch (e) {} }
  function configured() { return !!(CFG && CFG.apiKey && CFG.projectId); }
  function docUrl(uid) {
    var base = CFG.base || "https://firestore.googleapis.com/v1";
    return base + "/projects/" + encodeURIComponent(CFG.projectId) + "/databases/" + encodeURIComponent(CFG.databaseId || "(default)") +
      "/documents/poll/" + encodeURIComponent(uid);
  }
  // 匿名ログイン(初回)か、前にもらった番号の延長。1時間ほど使える鍵(idToken)を返す
  function signIn(m) {
    if (token && Date.now() < tokenUntil - 60000) return Promise.resolve(token);
    var req = m.rt
      ? fetch("https://securetoken.googleapis.com/v1/token?key=" + encodeURIComponent(CFG.apiKey), {
          method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: "grant_type=refresh_token&refresh_token=" + encodeURIComponent(m.rt) })
          .then(function (r) { if (!r.ok) throw new Error("refresh " + r.status); return r.json(); })
          .then(function (j) { return { idToken: j.id_token, refreshToken: j.refresh_token, localId: j.user_id, expiresIn: j.expires_in }; })
      : fetch("https://identitytoolkit.googleapis.com/v1/accounts:signUp?key=" + encodeURIComponent(CFG.apiKey), {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ returnSecureToken: true }) })
          .then(function (r) { if (!r.ok) throw new Error("signup " + r.status); return r.json(); });
    return req.then(function (j) {
      m.uid = j.localId; m.rt = j.refreshToken; store(m);
      token = j.idToken; tokenUntil = Date.now() + Number(j.expiresIn || 3600) * 1000;
      return token;
    });
  }
  function hash(s) { var h = 0; for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return s.length + ":" + h; }
  function arr(list) { return { arrayValue: { values: list.map(function (c) { return { stringValue: c }; }) } }; }

  // codes: { h: [持っているコード], w: [買い増し候補のコード] }
  function send(codes, force) {
    var m = load();
    if (!configured() || !m.on || busy) return Promise.resolve(false);
    var body = JSON.stringify(codes), hs = hash(body);
    if (!force && m.sent === hs && Date.now() - (m.at || 0) < RESEND_MS) return Promise.resolve(false);
    busy = true;
    return signIn(m).then(function (tk) {
      var doc = { fields: { h: arr(codes.h), w: arr(codes.w), t: { integerValue: String(Date.now()) } } };
      return fetch(docUrl(m.uid), { method: "PATCH", headers: { "Content-Type": "application/json", Authorization: "Bearer " + tk }, body: JSON.stringify(doc) });
    }).then(function (r) {
      if (!r.ok) throw new Error("http " + r.status);
      m = load(); m.sent = hs; m.at = Date.now(); store(m);
      return true;
    }).finally(function () { busy = false; });
  }
  function soon(getCodes) {
    if (!load().on) return;
    clearTimeout(timer);
    timer = setTimeout(function () { send(getCodes()).catch(function () {}); }, 4000);
  }
  // やめる: 送った分を消してから、この端末の番号も忘れる
  function leave() {
    var m = load();
    var done = function () { store({ on: false, asked: 1 }); token = null; };
    if (!configured() || !m.uid) { done(); return Promise.resolve(); }
    return signIn(m).then(function (tk) {
      return fetch(docUrl(m.uid), { method: "DELETE", headers: { Authorization: "Bearer " + tk } });
    }).then(done, function (e) { done(); throw e; });
  }
  function join(codes) {
    var m = load(); m.on = true; m.asked = 1; store(m);
    return send(codes, true);
  }

  window.HaitoPoll = {
    configured: configured, on: function () { return !!load().on; },
    asked: function () { return !!load().asked; },
    markAsked: function () { var m = load(); m.asked = 1; store(m); },
    join: join, leave: leave, send: send, soon: soon
  };
})();
