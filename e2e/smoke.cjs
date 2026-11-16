// Prueba de humo E2E: recorre la interfaz como un usuario contra el motor real.
// Uso: node e2e/smoke.cjs <video.mp4> <carpeta_capturas> [url]
const { chromium } = require("playwright");
const path = require("path");

const [video, shots, url = "http://127.0.0.1:8765"] = process.argv.slice(2);
const shot = (page, name) => page.screenshot({ path: path.join(shots, name + ".png") });

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await page.goto(url);
  console.log("H.264 en este navegador:", await page.evaluate(() =>
    document.createElement("video").canPlayType('video/mp4; codecs="avc1.42E01E, mp4a.40.2"') || "no"));

  await page.getByRole("button", { name: "+ Nuevo" }).click();
  await page.getByText("Importa un video").waitFor();
  await shot(page, "01-importar");
  await page.locator('input[type="file"]').setInputFiles(video);
  await page.locator("video.fg-video").waitFor({ timeout: 60000 });
  await page.waitForFunction(() => !document.querySelector(".job"), null, { timeout: 120000 });
  await page.waitForTimeout(800);
  console.log("✓ importado y preparado");

  await page.getByRole("button", { name: "Subtítulos", exact: true }).click();
  await page.getByRole("button", { name: /Transcribir/ }).click();
  await page.locator(".caption-list li").first().waitFor({ timeout: 180000 });
  const caps = await page.locator(".caption-list li").count();
  console.log("✓ subtítulos:", caps);

  // edición de un subtítulo
  const ta = page.locator(".caption-list textarea").first();
  await ta.fill("Hola a todos, bienvenidos");
  await ta.press("Enter");

  await page.getByRole("button", { name: "✨ Auto-editar" }).click();
  await page.locator(".cut-list li").first().waitFor({ timeout: 60000 });
  const cuts = await page.locator(".cut-list li").count();
  const stats = await page.locator(".stats").innerText();
  console.log("✓ cortes:", cuts, "|", stats.replace(/\n/g, " "));

  // recuperar un corte desde la lista
  await page.locator(".cut-list li").nth(1).getByRole("button", { name: "Recuperar" }).click();
  console.log("✓ corte recuperado; activos:", await page.locator(".cut-region.on").count());

  // formato 9:16 + estilo
  await page.getByRole("button", { name: "Formato" }).click();
  await page.getByRole("button", { name: /9:16/ }).click();
  await page.getByRole("button", { name: "Estilo" }).click();
  await page.getByRole("button", { name: /IMPACTO/ }).click();
  // posicionar el cabezal sobre una palabra para ver el subtítulo
  await page.evaluate(() => { const v = document.querySelector("video.fg-video"); v.currentTime = 2.3; });
  await page.waitForTimeout(800);
  await page.waitForFunction(() => document.querySelector(".save-state")?.textContent?.includes("Guardado"), null, { timeout: 10000 });
  await shot(page, "02-editor-9x16");
  console.log("✓ subtítulo visible:", await page.locator(".sub-overlay").innerText().catch(() => "(ninguno)"));

  await page.getByRole("button", { name: "Formato" }).click();
  await page.getByRole("button", { name: "Fondo desenfocado" }).click();
  await page.getByRole("button", { name: /16:9/ }).click();
  await page.waitForTimeout(600);
  await shot(page, "03-editor-16x9");
  await page.getByRole("button", { name: /9:16/ }).click();
  await page.getByRole("button", { name: "Recortar" }).click();

  // exportación real
  await page.getByRole("button", { name: "⇩ Exportar", exact: true }).click();
  await page.getByRole("button", { name: /TikTok/ }).click();
  await page.waitForTimeout(1000);
  await page.getByRole("button", { name: "⇩ Exportar MP4" }).click();
  await page.locator(".export-done").waitFor({ timeout: 300000 });
  console.log("✓", (await page.locator(".export-done").innerText()).replace(/\n/g, " "));
  await shot(page, "04-exportado");
  const files = await page.locator(".file-list a").allInnerTexts();
  console.log("archivos:", files.join(", "));

  // recarga: el proyecto debe persistir
  await page.reload();
  await page.locator(".cut-list li").first().waitFor({ timeout: 20000 });
  console.log("✓ tras recargar: cortes", await page.locator(".cut-list li").count(),
    "| recuperados", await page.locator(".cut-list li.off").count());

  console.log(errors.length ? "ERRORES DE CONSOLA:\n" + errors.join("\n") : "✓ sin errores de consola");
  await browser.close();
  process.exit(errors.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
