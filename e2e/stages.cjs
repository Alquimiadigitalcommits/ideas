// E2E de las etapas 2-5: deshacer, rostro, transiciones, previsualización exacta, música, animación,
// exportación y proyecto portable. Uso: node e2e/stages.cjs <video_con_rostro_y_voz> <musica> <capturas> [url]
const { chromium } = require("playwright");
const path = require("path");
const fs = require("fs");

const [video, music, shots, url = "http://127.0.0.1:8765"] = process.argv.slice(2);
const shot = (page, name) => page.screenshot({ path: path.join(shots, name + ".png") });
const tab = (page, name) => page.locator(".tabs button", { hasText: new RegExp(`^${name}$`) }).click();
const idle = (page, t = 240000) => page.waitForFunction(() => !document.querySelector(".job"), null, { timeout: t });
const api = (page, p) => page.evaluate((u) => fetch(u).then((r) => r.json()), p);

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, acceptDownloads: true });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("dialog", (d) => d.accept());
  await page.goto(url);
  await page.getByRole("button", { name: /Editar manualmente/ }).click();

  await page.getByRole("button", { name: "+ Nuevo" }).click();
  await page.locator('input[type="file"][accept*=".mp4"]').setInputFiles(video);
  await page.locator("video.fg-video").waitFor({ timeout: 60000 });
  await idle(page);
  const pid = await page.evaluate(() => localStorage.getItem("sve.project"));
  console.log("✓ importado", pid);

  await tab(page, "Subtítulos");
  await page.getByRole("button", { name: /Transcribir/ }).click();
  await page.locator(".caption-list li").first().waitFor({ timeout: 180000 });
  await idle(page);

  // auto-edición + deshacer/rehacer
  await page.locator(".tabs button", { hasText: /^Cortes$/ }).click();
  await page.getByRole("button", { name: /Detectar y cortar silencios/ }).click();
  await page.locator(".cut-region").first().waitFor({ timeout: 60000 });
  await idle(page);
  await page.waitForTimeout(500);
  const nCuts = await page.locator(".cut-region").count();
  await page.locator("body").click({ position: { x: 700, y: 300 } });
  await page.keyboard.press("Control+z");
  await page.waitForTimeout(300);
  const afterUndo = await page.locator(".cut-region").count();
  await page.keyboard.press("Control+Shift+z");
  await page.waitForTimeout(300);
  const afterRedo = await page.locator(".cut-region").count();
  console.log(`✓ deshacer auto-edición: ${nCuts} → ${afterUndo} → ${afterRedo}`);
  if (afterUndo !== 0 || afterRedo !== nCuts) throw new Error("deshacer/rehacer no funcionó");

  // formato 9:16 + seguimiento de rostro
  await tab(page, "Formato");
  await page.getByRole("button", { name: /9:16/ }).click();
  await page.getByRole("button", { name: /Detectar y seguir el rostro/ }).click();
  await page.getByText(/Seguimiento activo/).waitFor({ timeout: 120000 });
  const pos = async (t) => {
    await page.evaluate((tt) => { document.querySelector("video.fg-video").currentTime = tt; }, t);
    await page.waitForTimeout(400);
    return page.evaluate(() => document.querySelector("video.fg-video").style.objectPosition);
  };
  const p1 = await pos(1.5), p2 = await pos(19);
  console.log(`✓ rostro: object-position ${p1} → ${p2}`);
  await shot(page, "s1-rostro-inicio");

  // transiciones
  await tab(page, "Transiciones");
  await page.locator(".trans-btn", { hasText: "Fundido a negro" }).first().click();
  await page.locator(".join-marker").nth(1).click();
  await page.waitForTimeout(300);
  await page.getByRole("button", { name: /Previsualización exacta de esta unión/ }).click();
  await page.locator(".modal video").waitFor({ timeout: 120000 });
  await page.waitForFunction(() => document.querySelector(".modal video").readyState >= 2, null, { timeout: 20000 });
  const pdur = await page.evaluate(() => document.querySelector(".modal video").duration);
  console.log(`✓ previsualización exacta renderizada: ${pdur.toFixed(2)} s`);
  await page.waitForTimeout(700);
  await shot(page, "s2-previsualizacion");
  await page.getByRole("button", { name: "Cerrar ✕" }).click();

  // división con S y transición individual flash
  await page.evaluate(() => { document.querySelector("video.fg-video").currentTime = 6.5; });
  await page.waitForTimeout(300);
  await page.locator("body").click({ position: { x: 700, y: 300 } });
  await page.keyboard.press("s");
  await page.locator(".split-marker").first().click();
  await page.getByText("Usar la transición general").click();
  await page.locator(".section").filter({ hasText: "Unión seleccionada" }).locator(".trans-btn", { hasText: "Flash" }).click();
  await shot(page, "s3-transiciones");
  console.log("✓ división + flash individual; uniones:", await page.locator(".join-marker").count());

  // estilo animado
  await tab(page, "Estilo");
  await page.locator(".preset", { hasText: /NEÓN POP/ }).click();

  // audio
  await tab(page, "Audio");
  await page.locator('input[type="file"][accept*=".mp3"]').setInputFiles(music);
  await page.locator(".music-card").waitFor({ timeout: 20000 });
  await page.getByText("Reducción de ruido").click();
  await page.waitForFunction(() => document.querySelector(".save-state")?.textContent?.includes("Guardado"), null, { timeout: 10000 });
  await page.evaluate(() => { document.querySelector("video.fg-video").currentTime = 2.2; });
  await page.waitForTimeout(600);
  await shot(page, "s4-audio");
  console.log("✓ música:", (await page.locator(".music-card b").innerText()));

  // exportar
  await page.getByRole("button", { name: "⇩ Exportar", exact: true }).click();
  await page.getByRole("button", { name: "⇩ Exportar MP4" }).click();
  await page.locator(".export-done").waitFor({ timeout: 400000 });
  const jobs = await api(page, `/api/projects/${pid}/jobs`);
  const ex = jobs.find((j) => j.kind === "export" && j.status === "done");
  console.log(`✓ exportado: ${ex.result.width}x${ex.result.height}, ${ex.result.duration} s, ${ex.result.segments} segmentos, ` +
    `${ex.result.transitions} transiciones, piso de ruido ${ex.result.noise_floor_db} dB`);
  fs.writeFileSync(path.join(shots, "export.json"), JSON.stringify(ex.result));

  // proyecto portable: descargar e importar
  const dl = await Promise.all([page.waitForEvent("download"), page.getByText("Guardar copia del proyecto (.json)").click()]);
  const f = path.join(shots, "proyecto.json");
  await dl[0].saveAs(f);
  await page.locator('input[type="file"][accept*=".json"]').setInputFiles(f);
  await page.waitForFunction(() => document.querySelector(".project-name")?.value?.includes("importado"), null, { timeout: 20000 });
  console.log("✓ proyecto importado:", await page.locator(".project-name").inputValue());

  console.log(errors.length ? "ERRORES DE CONSOLA:\n" + errors.join("\n") : "✓ sin errores de consola");
  await browser.close();
  process.exit(errors.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
