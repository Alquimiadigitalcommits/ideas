// E2E del modo automático: inicio → asistente (video, plataforma, estilo) → video listo → otra plataforma → editor.
// Uso: node e2e/auto.cjs <video_con_voz> <capturas> [url]
const { chromium } = require("playwright");
const path = require("path");

const [video, shots, url = "http://127.0.0.1:8765"] = process.argv.slice(2);
const shot = (page, name) => page.screenshot({ path: path.join(shots, name + ".png") });

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 }, deviceScaleFactor: 1, acceptDownloads: true });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

  await page.goto(url);
  await page.getByText("Crear video automático").waitFor();
  await page.waitForTimeout(500);
  await shot(page, "a0-inicio");
  await page.getByText("Crear video automático").click();

  // 1. video
  await page.locator('input[type="file"]').setInputFiles(video);
  await page.getByText("¿Dónde lo vas a publicar?").waitFor({ timeout: 60000 });
  await shot(page, "a1-plataforma");
  // 2. plataforma
  await page.locator(".wz-platform", { hasText: "TikTok" }).click();
  await page.getByRole("button", { name: "Siguiente →" }).click();
  // 3. estilo
  await page.getByText("¿Cómo quieres los subtítulos?").waitFor();
  await page.waitForTimeout(600);
  await page.locator(".wz-preset", { hasText: "Titular" }).click();
  await shot(page, "a2-estilo");
  const t0 = Date.now();
  await page.getByRole("button", { name: /Crear mi video/ }).click();
  await page.getByText("Creando tu video…").waitFor();
  await page.waitForTimeout(2500);
  await shot(page, "a3-progreso");
  await page.getByText("¡Tu video está listo!").waitFor({ timeout: 600000 });
  console.log(`✓ video automático en ${((Date.now() - t0) / 1000).toFixed(1)} s`);
  await page.waitForFunction(() => document.querySelector(".wz-video")?.readyState >= 1, null, { timeout: 20000 });
  const info = await page.evaluate(() => {
    const v = document.querySelector(".wz-video");
    return { dur: v.duration, w: v.videoWidth, h: v.videoHeight };
  });
  console.log(`✓ resultado reproducible: ${info.w}x${info.h}, ${info.dur.toFixed(2)} s`);
  console.log("  resumen:", (await page.locator(".wz-summary ul").innerText()).replace(/\n/g, " | "));
  await page.evaluate(() => { const v = document.querySelector(".wz-video"); v.currentTime = 1.0; });
  await page.waitForTimeout(800);
  await shot(page, "a4-listo");
  const dl = await Promise.all([page.waitForEvent("download"), page.getByText("⇩ Descargar video").click()]);
  console.log("✓ descarga:", dl[0].suggestedFilename());

  // otra plataforma (reutiliza la transcripción)
  await page.getByRole("button", { name: /Crear para otra plataforma/ }).click();
  await page.locator(".wz-platform", { hasText: "YouTube" }).first().click();
  await page.locator(".wz-platform", { hasText: "Horizontal" }).click();
  await page.getByRole("button", { name: "Siguiente →" }).click();
  const t1 = Date.now();
  await page.getByRole("button", { name: /Crear mi video/ }).click();
  await page.getByText("¡Tu video está listo!").waitFor({ timeout: 600000 });
  const w2 = await page.evaluate(async () => {
    const v = document.querySelector(".wz-video");
    await new Promise((r) => (v.readyState >= 1 ? r() : v.addEventListener("loadedmetadata", r, { once: true })));
    return `${v.videoWidth}x${v.videoHeight}`;
  });
  console.log(`✓ versión YouTube ${w2} en ${((Date.now() - t1) / 1000).toFixed(1)} s (sin volver a transcribir)`);

  // ajustar en el editor
  await page.getByRole("button", { name: /Ajustar en el editor/ }).click();
  await page.locator(".guide").waitFor({ timeout: 20000 });
  await page.locator(".caption-block").first().waitFor({ timeout: 20000 });
  console.log(`✓ editor: ${await page.locator(".caption-block").count()} subtítulos, ${await page.locator(".cut-region").count()} cortes;` +
    ` guía: ${(await page.locator(".guide").innerText()).replace(/\n/g, " ")}`);
  await page.evaluate(() => { document.querySelector("video.fg-video").currentTime = 2.3; });
  await page.waitForTimeout(900);
  await shot(page, "a5-editor");

  // computador sin transcripción disponible (simulado): explicación clara y subtítulos desactivados
  const p2 = await ctx.newPage();
  await p2.route("**/api/system", async (route) => {
    const r = await route.fetch();
    const j = await r.json();
    j.whisper = false;
    j.whisper_error = "Faltan componentes de Windows para la transcripción (Microsoft Visual C++ Redistributable). Vuelve a ejecutar el instalador.";
    await route.fulfill({ json: j });
  });
  await p2.goto(url);
  await p2.getByText("Subtítulos no disponibles").waitFor();
  await p2.getByText("Crear video automático").click();
  await p2.locator('input[type="file"]').setInputFiles(video);
  await p2.getByRole("button", { name: "Siguiente →" }).click();
  const disabled = await p2.locator(".wz-opt", { hasText: "Subtítulos automáticos" }).locator("input").isDisabled();
  console.log(`✓ sin transcripción: aviso visible y opción de subtítulos desactivada (${disabled})`);
  await shot(p2, "a6-sin-transcripcion");

  console.log(errors.length ? "ERRORES DE CONSOLA:\n" + errors.join("\n") : "✓ sin errores de consola");
  await browser.close();
  process.exit(errors.length || !disabled ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
