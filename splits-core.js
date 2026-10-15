// 株式分割の「この端末で登録した分」。HAITO とチェックシート(../ir-check/)の両方から読み込む。
// 内蔵データの分割は EDINET(有報・半期報告書)に載ってから毎月の自動更新で入るので、それまでの間、
// 予想配当や株価の取り込みで分割に気づいたら、利用者が確かめたうえでここに登録して過去の1株配当を割り戻す。
// 公式のデータに同じ分割が入ったら(または新しい期の有報に替わったら)、ここの登録は自動で使われなくなる。
(function () {
  "use strict";
  var KEY = "haitoSplitsV1";
  var RATIOS = [2, 3, 4, 5, 10];

  function load() { try { return JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch (e) { return {}; } }
  function store(all) { try { localStorage.setItem(KEY, JSON.stringify(all)); } catch (e) {} }
  function norm(c) { return String(c || "").trim().toUpperCase(); }
  function days(a, b) { return (new Date(a + "T00:00:00") - new Date(b + "T00:00:00")) / 86400000; }
  function today() { var d = new Date(); return d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2) + "-" + ("0" + d.getDate()).slice(-2); }

  // 公式の分割(HAITOの SPLIT_MAP、チェックシートの r.splits)と同じものか。
  // 効力発生日は登録した日(気づいた日)の少し前のことが多いので、前200日〜後60日を同じとみる
  function sameSplit(e, date, n) {
    if (Number(n) !== Number(e.n) || !date) return false;
    var d = days(String(date).slice(0, 10), e.d);
    return d >= -200 && d <= 60;
  }
  // ctx: { fy: いまのデータの決算期末, official: [[効力発生日, 比率], …] }
  function pending(e, ctx) {
    ctx = ctx || {};
    if (ctx.fy && e.fy && String(ctx.fy) > String(e.fy)) return false;  // 新しい期の有報に替わった
    return !(ctx.official || []).some(function (o) { return sameSplit(e, o[0], o[1]); });
  }
  function entries(code) { return (load()[norm(code)] || []).slice(); }
  function factor(code, ctx) {
    return entries(code).reduce(function (f, e) { return pending(e, ctx) ? f * Number(e.n) : f; }, 1);
  }
  function add(code, e) {
    var all = load(), c = norm(code);
    var list = (all[c] || []).filter(function (x) { return x.d !== e.d; });
    list.push({ n: Number(e.n), d: e.d || today(), p: e.p > 0 ? e.p : undefined, fy: e.fy || undefined, src: e.src || "", at: today() });
    all[c] = list;
    store(all);
    return list[list.length - 1];
  }
  function remove(code, d) {
    var all = load(), c = norm(code);
    all[c] = (all[c] || []).filter(function (x) { return x.d !== d; });
    if (!all[c].length) delete all[c];
    store(all);
  }
  // 有報の数字(チェックシートの fin)を分割後の1株あたりに直した写し
  function adjustFin(code, rec) {
    if (!rec) return rec;
    var f = entries(code).reduce(function (m, e) {
      var hit = (rec.splits || []).some(function (d) { return sameSplit(e, d, e.n); });
      return !hit && pending(e, { fy: rec.fy }) ? m * Number(e.n) : m;
    }, 1);
    if (f === 1) return rec;
    var r = Object.assign({}, rec);
    function div(v) { return v == null ? v : Math.round(v / f * 100) / 100; }
    ["div", "dl", "dlo", "eps"].forEach(function (k) { if (Array.isArray(r[k])) r[k] = r[k].map(div); });
    if (r.bps) r.bps = div(r.bps);
    r.localSplit = f;
    return r;
  }

  // 予想配当・株価から、株式分割を疑うか。
  // o: { last: 前期の1株配当(分割前), fdiv: いまの予想配当, price: いまの株価, prevPrice: 前に入れた株価, prevDate: その日付,
  //      feps: 予想1株利益, lastEps: 前期の1株利益(分割前) }
  // まず株価で比率を決める(分割では株価も同じ割合で下がる。増配・減配は配当だけが動く)。
  // 前の株価が無い・もう分割後の値のときは、1株利益も同じ割合で小さくなっているかで見る(利益は年ごとに動くので幅を広く)。
  // どちらでも決まらないときだけ、配当の比率から候補を出す(本当の大きな減配と見分けられないので、確かめてもらう)
  function guess(o) {
    var last = Number(o.last), fdiv = Number(o.fdiv);
    if (!(last > 0) || !(fdiv > 0) || fdiv >= last * 0.75) return null;
    function nearest(r, tol) {
      var best = null;
      RATIOS.forEach(function (n) { var d = Math.abs(r * n - 1); if (d <= tol && (!best || d < best.d)) best = { n: n, d: d }; });
      return best && best.n;
    }
    function out(n, by) { return { n: n, alts: [], by: by, growth: fdiv * n / last - 1 }; }
    var fe = Number(o.feps), le = Number(o.lastEps);
    var epsN = fe > 0 && le > 0 && fe / le < 0.6 ? nearest(fe / le, 0.35) : null;
    var p = Number(o.price), pp = Number(o.prevPrice);
    var fresh = !o.prevDate || days(today(), String(o.prevDate).slice(0, 10).replace(/\//g, "-")) <= 400;
    if (p > 0 && pp > 0 && fresh) {
      var pn = nearest(p / pp, 0.15);
      if (pn) return out(pn, "price");
      // 株価はほぼそのまま: 本当の減配か、前の株価がもう分割後の値。1株利益も同じ割合で小さければ分割とみる
      if (p / pp > 0.75 && p / pp < 1.33) return epsN && fdiv * epsN / last >= 0.7 ? out(epsN, "eps") : null;
    }
    if (epsN && fdiv * epsN / last >= 0.7) return out(epsN, "eps");
    var c = RATIOS.filter(function (n) { var g = fdiv * n / last; return g >= 0.85 && g <= 1.6; })
      .sort(function (a, b) { return Math.abs(fdiv * a / last - 1.1) - Math.abs(fdiv * b / last - 1.1); });
    if (!c.length) return null;
    return { n: c[0], alts: c.slice(1), by: "div", growth: fdiv * c[0] / last - 1 };
  }

  window.HaitoSplits = { KEY: KEY, load: load, entries: entries, pending: pending, sameSplit: sameSplit, factor: factor,
                         add: add, remove: remove, adjustFin: adjustFin, guess: guess, today: today };
})();
