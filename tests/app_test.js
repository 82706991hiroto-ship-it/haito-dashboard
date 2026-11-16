// 画面の計算の点検(HAITO)。公式の書類で確かめた銘柄で、表示される数字と判定を照合する。
// ローカル: haito-dashboard と ir-check を同じフォルダに置き、その親で python3 -m http.server 8765 を動かしてから
//   NODE_PATH=$(npm root -g) node tests/app_test.js
// GitHub Actions(.github/workflows/app-test.yml)でも push のたびに動く。
const { chromium } = require("playwright");
const BASE = process.env.BASE || "http://127.0.0.1:8765";
const H = (code, name, sector, div, extra) => Object.assign({ id: "h" + code, code, name, sector, account: "特定", shares: 100, cost: 1000, div, prevDiv: "", price: 2000, priceDate: "2026/10/08", months: [3, 9] }, extra || {});
const holdings = [
  H("2169", "CDS", "サービス業", 74),            // 記念配当10円を除くと 68→74円の増配
  H("8593", "三菱HCキャピタル", "その他金融業", 46), // 連結の配当性向は約41%(有報の配当性向欄91%は単体)
  H("2914", "JT", "食料品", 234),                 // 配当性向75%目安の方針。高い配当性向で要注意
  H("3176", "三洋貿易", "卸売業", 28.5, { priceDate: "2026/10/08" }), // 2026-07-01に1株→2株。分割後の値
  H("8766", "東京海上", "保険業", 14.53),          // 連結(日本基準)の配当性向は約42%。IFRSの参考値で78%と出ていた
];
const fails = [];
function expect(cond, msg) { if (!cond) fails.push(msg); }
(async () => {
  const br = await chromium.launch();
  const ctx = await br.newContext({ viewport: { width: 390, height: 844 } });
  await ctx.addInitScript(h => localStorage.setItem("haitoDashboardV1", JSON.stringify({ holdings: h })), holdings);
  const p = await ctx.newPage();
  const errs = [];
  p.on("pageerror", e => errs.push(e.message));
  await p.goto(BASE + "/haito-dashboard/index.html#analysis");
  await p.waitForTimeout(3000);
  const risk = await p.textContent("#riskBody");
  expect(!/三菱HCキャピタル[^]*?配当性向が高い/.test(risk.split("判定のしかた")[0]), "三菱HCキャピタルが配当性向で要注意になっている(連結は約41%のはず)");
  expect(!/東京海上[^]*?配当性向/.test(risk.split("判定のしかた")[0]), "東京海上が配当性向で要注意になっている(連結は約42%のはず)");
  expect(/JT[^]*?要注意[^]*?配当性向75%を目安/.test(risk), "JTの要注意の理由に配当性向75%目安の方針が出ていない");
  expect(!/CDS[^]*?直近で減配/.test(risk), "CDSが直近で減配になっている(記念配当を除けば増配)");
  await p.click('.tabbar .tab[data-tab="holdings"]');
  await p.waitForTimeout(800);
  const rows = await p.$$eval("#holdingsBody tr[data-id]", trs => trs.map(t => t.dataset.id + " " + t.querySelector(".sum-meta").textContent));
  const row = id => rows.find(r => r.startsWith(id + " ")) || "";
  expect(/増配 \+8\.8%/.test(row("h2169")), "CDSの増配率が +8.8% でない: " + row("h2169"));
  expect(!/減配/.test(row("h3176")), "三洋貿易が減配に見えている(分割の割り戻し漏れ): " + row("h3176"));
  expect(!errs.length, "画面のエラー: " + errs.join(" / "));

  // 株式分割の見張り: 予想配当と株価がどちらも約4分の1なら、減配ではなく分割を疑い、登録すると株数と過去の配当を直す
  // 内蔵データにまだ分割が入っていない銘柄で試す(毎週の更新で公式の分割が入ると、その銘柄では疑いが出なくなるため、銘柄は毎回データから選ぶ)
  const src = require("fs").readFileSync(require("path").join(__dirname, "..", "data.js"), "utf8");
  const mapOf = name => JSON.parse(src.match(new RegExp("var " + name + " = (\\{.*?\\});"))[1]);
  const INFO = mapOf("CODE_INFO_MAP"), SPLITS = mapOf("SPLIT_MAP");
  const sc = Object.keys(INFO).sort().find(c => /^[1-9][0-9]{3}$/.test(c) && !SPLITS[c] && Array.isArray(INFO[c][3]) && INFO[c][3].length >= 6 &&
    INFO[c][3][0] >= 20 && (INFO[c][2] || []).length === 2 && INFO[c][3].slice(0, 5).every((v, i, a) => i === 0 || a[i - 1] >= v));
  const sName = INFO[sc][0].normalize("NFKC"), sDiv = INFO[sc][3][0], sPrice = Math.round(sDiv / 0.035);
  const ctx2 = await br.newContext({ viewport: { width: 390, height: 844 } });
  await ctx2.addInitScript(a => {
    if (sessionStorage.getItem("t")) return;
    sessionStorage.setItem("t", "1");
    localStorage.clear();
    // 保有と内蔵データは分割前の値、チェックシートで入れた値は分割後(配当も株価も4分の1)
    localStorage.setItem("haitoDashboardV1", JSON.stringify({ holdings: [{ id: "s1", code: a.code, name: a.name, sector: a.sector, account: "特定",
      shares: 100, cost: 2000, div: a.div, prevDiv: "", price: a.price, priceDate: "2026/09/20", months: a.months }] }));
    localStorage.setItem("irPrices", JSON.stringify({ [a.code]: { p: Math.round(a.price / 4), d: "2099-01-01", f: Math.round(a.div / 4 * 100) / 100 } }));
  }, { code: sc, name: sName, sector: INFO[sc][1], div: sDiv, price: sPrice, months: INFO[sc][2] });
  const q = await ctx2.newPage();
  const errs2 = [];
  q.on("pageerror", e => errs2.push(e.message));
  q.on("dialog", d => d.accept());
  await q.goto(BASE + "/haito-dashboard/index.html#home");
  await q.waitForTimeout(2500);
  const season = await q.textContent("#seasonBody");
  expect(/株式分割かもしれません[^]*?約4分の1/.test(season), "予想配当・株価が4分の1なのに分割の疑いが出ていない");
  await q.click('#seasonBody [data-sp="reg"][data-n="4"]');
  await q.waitForTimeout(800);
  const h1 = await q.evaluate(() => JSON.parse(localStorage.getItem("haitoDashboardV1")).holdings[0]);
  expect(h1.shares === 400 && h1.cost === 500, "分割の登録で株数・取得単価が直っていない: " + h1.shares + "株・" + h1.cost + "円");
  await q.click('.tabbar .tab[data-tab="analysis"]');
  await q.waitForTimeout(800);
  expect(!new RegExp(sName + "[^]*?減配予想").test((await q.textContent("#riskBody")).split("判定のしかた")[0]), "分割を登録したのに減配予想になっている");
  expect(!errs2.length, "画面のエラー(分割): " + errs2.join(" / "));
  await br.close();
  if (fails.length) { console.log("NG\n- " + fails.join("\n- ")); process.exit(1); }
  console.log("OK: 画面の計算の点検をすべて通過");
})();
