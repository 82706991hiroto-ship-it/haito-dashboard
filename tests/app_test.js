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
  expect(/JT[^]*?要注意[^]*?配当性向75%を目安/.test(risk), "JTの要注意の理由に配当性向75%目安の方針が出ていない");
  expect(!/CDS[^]*?直近で減配/.test(risk), "CDSが直近で減配になっている(記念配当を除けば増配)");
  await p.click('.tabbar .tab[data-tab="holdings"]');
  await p.waitForTimeout(800);
  const rows = await p.$$eval("#holdingsBody tr[data-id]", trs => trs.map(t => t.dataset.id + " " + t.querySelector(".sum-meta").textContent));
  const row = id => rows.find(r => r.startsWith(id + " ")) || "";
  expect(/増配 \+8\.8%/.test(row("h2169")), "CDSの増配率が +8.8% でない: " + row("h2169"));
  expect(!/減配/.test(row("h3176")), "三洋貿易が減配に見えている(分割の割り戻し漏れ): " + row("h3176"));
  expect(!errs.length, "画面のエラー: " + errs.join(" / "));
  await br.close();
  if (fails.length) { console.log("NG\n- " + fails.join("\n- ")); process.exit(1); }
  console.log("OK: 画面の計算の点検をすべて通過");
})();
