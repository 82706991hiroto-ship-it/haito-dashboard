// 画面を開かずに確かめられる部分の点検(node だけで動く)。
//   node tests/unit_test.js
// - Yahooの参考指標から株価・予想配当を読む parseQuoteBlock(HAITO とチェックシートの両方。同じ結果になること)
// - 端末間の同期で2台が食い違ったときの足し合わせ(sync-core.js の mergeKeep)
const fs = require("fs"), path = require("path"), assert = require("assert");
const ROOT = path.join(__dirname, "..");
let failed = 0;
function test(name, fn) { try { fn(); console.log("ok  " + name); } catch (e) { failed++; console.log("NG  " + name + "\n    " + String(e.message).split("\n")[0]); } }

function loadParse(file) {
  const s = fs.readFileSync(file, "utf8"), a = s.indexOf("  function parseQuoteBlock(t) {"), b = s.indexOf("\n  }\n", a) + 4;
  return new Function(s.slice(a, b) + "; return parseQuoteBlock;")();
}
const parsers = [["HAITO", path.join(ROOT, "index.html")]];
const irCheck = path.join(ROOT, "..", "ir-check", "index.html");
if (fs.existsSync(irCheck)) parsers.push(["チェックシート", irCheck]);

parsers.forEach(([who, file]) => {
  const parse = loadParse(file);
  test(who + ": PER×EPSと利回りが合えば PER×EPS の株価", () => {
    const q = parse("発行済株式数 100株 配当利回り（会社予想） 2.92% 1株配当（会社予想） 32.00円 PER（会社予想） (連)12.50倍 EPS（会社予想） (連)87.68 BPS（実績） 900");
    assert.strictEqual(q.price, 1096); assert.strictEqual(q.fdiv, 32); assert.strictEqual(q.feps, 87.68);
  });
  test(who + ": PER×EPSが利回りと食い違えば使わない(三菱HCキャピタル 実際は1,348.5円)", () => {
    const q = parse("発行済株式数 1,466,912,244株 11/12 配当利回り（会社予想） 3.78% 15:30 1株配当（会社予想） 51.00円 2027/03 PER（会社予想） (連)12.09倍 15:30 PBR（実績） (連)0.96倍 EPS（会社予想） (連)90.62 2027/03 BPS（実績） (連)1,389.19");
    assert.ok(Math.abs(q.price - 1348.5) <= 3, "price " + q.price); assert.strictEqual(q.fdiv, 51);
  });
  test(who + ": 食い違うときは、利回りと合う最低購入代金÷単元株数を使う", () => {
    const q = parse("発行済株式数 1株 配当利回り（会社予想） 3.78% 1株配当（会社予想） 51.00円 PER（会社予想） (連)12.09倍 EPS（会社予想） (連)90.62 BPS（実績） 1 最低購入代金 134,850 単元株数 100株");
    assert.strictEqual(q.price, 1348.5);
  });
  test(who + ": 赤字でPERが無いときは 配当÷利回り", () => {
    const q = parse("発行済株式数 1株 配当利回り（会社予想） 4.00% 1株配当（会社予想） 40.00円 PER（会社予想） ---倍 EPS（会社予想） (連)-12.5 BPS（実績） 800 あいうえおかきくけこ");
    assert.strictEqual(q.price, 1000); assert.strictEqual(q.feps, -12.5);
  });
  test(who + ": 関係ない文は読まない", () => { assert.strictEqual(parse("今日は良い天気です。株価は上がるでしょうか。それとも下がるでしょうか。分かりません。"), null); });
});

// ---- 同期の足し合わせ ----
global.window = global;
global.localStorage = { getItem() { return null; }, setItem() {}, removeItem() {} };
global.document = { addEventListener() {} };
require(path.join(ROOT, "sync-core.js"));
const merge = (w, l, ids) => JSON.parse(window.HaitoSync._merge(JSON.stringify(w), JSON.stringify(l), ids));

test("同期: 予想配当は入れた日時の新しいほう(どちらが勝っても同じ)", () => {
  const ids = { holdings: ["a"], irPrices: ["7203"] };
  const oldCheck = { state: { holdings: [{ id: "a", code: "7203", div: 90, fdivDate: "2026/10/20" }] }, irPrices: { "7203": { p: 3000, d: "2026-10-30", f: 90, fd: "2026-10-20T09:00:00" } } };
  const newManual = { state: { holdings: [{ id: "a", code: "7203", div: 100, divAt: "2026-10-25T10:00:00", divBy: "手入力" }] }, irPrices: { "7203": { p: 2900, d: "2026-10-25", f: 100, fd: "2026-10-25T10:00:00" } } };
  [merge(oldCheck, newManual, ids), merge(newManual, oldCheck, ids)].forEach((r) => {
    assert.strictEqual(r.state.holdings[0].div, 100); assert.strictEqual(r.state.holdings[0].divBy, "手入力");
    assert.strictEqual(r.irPrices["7203"].p, 3000); assert.strictEqual(r.irPrices["7203"].f, 100);
  });
});
test("同期: 負けた側で足した銘柄は残り、負けた側で消した銘柄は消える", () => {
  const ids = { holdings: ["a", "b"] };
  const w = { state: { holdings: [{ id: "a", code: "1" }, { id: "b", code: "2" }] } };
  const l = { state: { holdings: [{ id: "a", code: "1" }, { id: "c", code: "3" }] } };  // b を消して c を足した
  assert.deepStrictEqual(merge(w, l, ids).state.holdings.map((h) => h.id).sort(), ["a", "c"]);
});
test("同期: 買い増し候補の株価は新しいほう、前回の株価も一緒に", () => {
  const ids = { watch: ["w"] };
  const w = { state: { watch: [{ id: "w", code: "8593", price: 1348, priceDate: "2026/11/05" }] } };
  const l = { state: { watch: [{ id: "w", code: "8593", price: 1200, priceDate: "2026/11/16", prevPrice: 1348, prevPriceDate: "2026/11/05" }] } };
  const r = merge(w, l, ids).state.watch[0];
  assert.strictEqual(r.price, 1200); assert.strictEqual(r.prevPrice, 1348);
});
test("同期: 受け取った配当の記録は足し合わせ、同じ入金は二重にしない", () => {
  const p1 = { code: "8058", ym: "2026/06", date: "2026-06-25", gross: 5500, qty: 100 };
  const p2 = { code: "2914", ym: "2026/09", date: "2026-09-01", gross: 9700, qty: 100 };
  const r = merge({ state: { payouts: [p1] } }, { state: { payouts: [p1, p2] } }, {});
  assert.strictEqual(r.state.payouts.length, 2);
});

if (failed) { console.log("\n" + failed + " 件の点検に失敗"); process.exit(1); }
console.log("\nOK: 部品の点検をすべて通過");
