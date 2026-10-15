// 証券会社の「配当金のお知らせ」PDF(電子交付書面)から、受け取った配当を読む。読み取りは端末の中だけで行う。
// 対応: SBIネオモバイル証券・SBI証券の「株式等(利益剰余金)配当金のお知らせ」(国内株)と
//       SBI証券の「外国株式等配当金等のご案内(兼)支払通知書」(米国株など。円に換算した税引前の額を使う)。
// お名前・口座番号などは読まない。PDFの文字は pdf.js(vendor/pdfjs)で取り出し、行ごとにまとめてから読む。
(function () {
  "use strict";
  var BASE = "vendor/pdfjs/";
  var loading = null;

  function loadPdfjs() {
    if (window.pdfjsLib) return Promise.resolve(window.pdfjsLib);
    if (loading) return loading;
    loading = new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = BASE + "pdf.min.js";
      s.onload = function () {
        if (!window.pdfjsLib) { reject(new Error("pdf.js")); return; }
        window.pdfjsLib.GlobalWorkerOptions.workerSrc = BASE + "pdf.worker.min.js";
        resolve(window.pdfjsLib);
      };
      s.onerror = function () { loading = null; reject(new Error("pdf.js")); };
      document.head.appendChild(s);
    });
    return loading;
  }

  // 文字のかたまりを、高さ(y)の近いものごとに1行にまとめる。行の中は左から右へ
  function linesOf(items) {
    var rows = [];
    items.forEach(function (it) {
      var str = String(it.str || "").normalize("NFKC").trim();
      if (!str) return;
      var y = it.transform[5], x = it.transform[4];
      var row = rows.filter(function (r) { return Math.abs(r.y - y) <= 2; })[0];
      if (!row) { row = { y: y, cells: [] }; rows.push(row); }
      row.cells.push({ x: x, s: str });
    });
    rows.sort(function (a, b) { return b.y - a.y; });
    return rows.map(function (r) {
      return r.cells.sort(function (a, b) { return a.x - b.x; }).map(function (c) { return c.s; }).join(" ").replace(/\s+/g, " ");
    });
  }
  function n(s) { return parseFloat(String(s).replace(/,/g, "")); }
  function ym(y, m) { return y + "/" + ("0" + m).slice(-2); }

  // 国内株: 「2021年12月 2日 20.0000000 3」(お支払日・配当単価・数量)→「(3176 )」→「60 9 3 0 48」(税引前・所得税・地方税・端数・受取)
  function parseDomestic(lines) {
    var out = [];
    for (var i = 0; i < lines.length; i++) {
      var m = lines[i].match(/(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s+([\d,]+\.\d+)\s+([\d,]+)\s*$/);
      if (!m) continue;
      var code = "", gross = null, j;
      for (j = i + 1; j < Math.min(lines.length, i + 4) && !code; j++) {
        var c = lines[j].match(/\(\s*([0-9][0-9A-Z]{3})\s*\)/);
        if (c) code = c[1];
      }
      for (var k = i + 1; k < Math.min(lines.length, i + 6); k++) {
        if (/^[\d,]+(\s+[\d,]+){2,}$/.test(lines[k])) { gross = n(lines[k].split(" ")[0]); break; }
      }
      if (!code || !(gross >= 0)) continue;
      out.push({ code: code, name: i > 0 && !/\d{4}\s*年/.test(lines[i - 1]) ? lines[i - 1] : "", ym: ym(m[1], m[2]),
                 date: m[1] + "-" + ("0" + m[2]).slice(-2) + "-" + ("0" + m[3]).slice(-2), per: n(m[4]), qty: n(m[5]), gross: gross });
    }
    return out;
  }
  // 外国株: 「2021/12/23 2021/12/24 2021/12/21 304-VIG 名前」(現地支払日・国内支払日・現地基準日・コード)→
  //         「2 1.55 0.15 0.00」(数量・外貨の配当)→ …「配当金等金額(円)」の下の「175 16 159」(円の税引前・外国源泉・国内課税所得)
  function parseForeign(lines) {
    var out = [];
    var starts = [];
    lines.forEach(function (l, i) { if (/^\d{4}\/\d{2}\/\d{2} \d{4}\/\d{2}\/\d{2} \d{4}\/\d{2}\/\d{2} \d+-[A-Z0-9.]+/.test(l)) starts.push(i); });
    starts.forEach(function (i, si) {
      var end = si + 1 < starts.length ? starts[si + 1] : lines.length;
      var m = lines[i].match(/^\d{4}\/\d{2}\/\d{2} (\d{4})\/(\d{2})\/(\d{2}) \d{4}\/\d{2}\/\d{2} \d+-([A-Z0-9.]+)\s*(.*)$/);
      var qty = null, gross = null, afterHead = false;
      for (var k = i + 1; k < end; k++) {
        var l = lines[k];
        if (qty === null && /^[\d,]+ [\d,]+\.\d+( [\d,.]+)*$/.test(l)) qty = n(l.split(" ")[0]);
        if (/配当金等金額\(円\)/.test(l)) { afterHead = true; continue; }
        if (afterHead && !/[\/外円]/.test(l) && /^[\d,]+( [\d,]+)+$/.test(l)) { gross = n(l.split(" ")[0]); break; }
      }
      if (!m || !(gross >= 0)) return;
      out.push({ code: m[4], name: m[5], ym: ym(m[1], +m[2]), date: m[1] + "-" + m[2] + "-" + m[3], qty: qty, gross: gross, fx: true });
    });
    return out;
  }
  function parseLines(lines) {
    var all = lines.join("\n");
    if (/外国株式等/.test(all) && /配当金等/.test(all)) return { kind: "foreign", rows: parseForeign(lines) };
    if (/配当金のお知らせ/.test(all)) return { kind: "domestic", rows: parseDomestic(lines) };
    return { kind: "", rows: [] };
  }

  function readFile(file) {
    return new Promise(function (resolve, reject) {
      var r = new FileReader();
      r.onload = function () { resolve(r.result); };
      r.onerror = function () { reject(r.error); };
      r.readAsArrayBuffer(file);
    });
  }
  function readPdf(pdfjs, buf) {
    return pdfjs.getDocument({ data: new Uint8Array(buf), cMapUrl: BASE + "cmaps/", cMapPacked: true, isEvalSupported: false }).promise.then(function (doc) {
      var pages = [];
      for (var i = 1; i <= doc.numPages; i++) pages.push(doc.getPage(i).then(function (p) { return p.getTextContent(); }));
      return Promise.all(pages).then(function (tcs) {
        var lines = [];
        tcs.forEach(function (tc) { lines = lines.concat(linesOf(tc.items)); });
        return parseLines(lines);
      });
    });
  }
  // files: File の配列。結果: { rows: [...], read: 読めた数, failed: [ファイル名] }
  function readAll(files) {
    return loadPdfjs().then(function (pdfjs) {
      var rows = [], read = 0, failed = [];
      return files.reduce(function (p, f) {
        return p.then(function () {
          return readFile(f).then(function (buf) { return readPdf(pdfjs, buf); }).then(function (r) {
            if (r.rows.length) { rows = rows.concat(r.rows); read++; } else failed.push(f.name);
          }, function () { failed.push(f.name); });
        });
      }, Promise.resolve()).then(function () { return { rows: rows, read: read, failed: failed }; });
    });
  }

  var api = { readAll: readAll, linesOf: linesOf, parseLines: parseLines };
  if (typeof window !== "undefined") window.HaitoPdfDividends = api;
  if (typeof module !== "undefined") module.exports = api;
})();
