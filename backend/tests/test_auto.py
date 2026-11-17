"""Modo automático, diagnóstico de transcripción (Windows), fuentes incluidas y vista previa perezosa."""
import pytest

from app import config
from app.engine import transcribe
from tests.conftest import stream_durations
from tests.test_api import client, wait


def _project(path, prepare=False):
    pid = client.post("/api/projects", json={"name": "Auto"}).json()["id"]
    r = client.post(f"/api/projects/{pid}/import-path", json={"path": str(path), "prepare": prepare})
    assert r.status_code == 200
    return pid, r.json()


def test_import_without_prepare_starts_no_job(tone_video):
    pid, job = _project(tone_video, prepare=False)
    assert job is None
    assert client.get(f"/api/projects/{pid}/jobs").json() == []


def test_auto_creates_vertical_video_with_subtitles(speech_video):
    pid, _ = _project(speech_video)
    style = client.get(f"/api/projects/{pid}").json()["doc"]["subtitle_style"]
    style.update(font_family="Outfit", uppercase=True, max_words=3, animation="pop")
    j = wait(client.post(f"/api/projects/{pid}/auto", json={
        "platform": "tiktok", "pace": "dinamico", "subtitle_style": style, "whisper_model": "tiny"}).json()["id"], 300)
    assert j["status"] == "done", j
    r = j["result"]
    assert r["steps"] == ["analizar", "transcribir", "silencios", "encuadre", "exportar"]
    assert r["words"] > 10 and r["cuts"] >= 4 and r["removed_seconds"] > 5
    ex = r["export"]
    assert (ex["width"], ex["height"]) == (1080, 1920) and ex["cues"] > 3
    out = config.project_dir(pid) / "exports" / ex["video"]
    d = stream_durations(out)
    assert abs(float(d["video"]["duration"]) - float(d["audio"]["duration"])) < 0.03
    assert (out.parent / ex["video"].replace(".mp4", ".ass")).read_text().count("Outfit") == 1
    doc = client.get(f"/api/projects/{pid}").json()["doc"]
    assert doc["format"]["aspect"] == "9:16" and doc["audio"]["denoise"] and doc["format"]["jump_zoom"] > 0
    assert doc["proxy_ready"]
    # H.264 en MP4 ≤1080p: el navegador lo reproduce, no hace falta generar proxy
    assert not (config.project_dir(pid) / "proxy.mp4").exists()
    assert client.get(f"/api/projects/{pid}/media/preview").status_code == 200

    # otra plataforma con el mismo video: reutiliza la transcripción
    j2 = wait(client.post(f"/api/projects/{pid}/auto", json={"platform": "youtube", "whisper_model": "tiny"}).json()["id"], 300)
    assert j2["status"] == "done" and "transcribir" not in j2["result"]["steps"]
    assert j2["result"]["export"]["width"] == 1920 and j2["result"]["export"]["cues"] > 3


def test_auto_follows_face(face_video):
    pid, _ = _project(face_video)
    j = wait(client.post(f"/api/projects/{pid}/auto", json={"platform": "reels", "subtitles": False,
                                                            "remove_silences": False}).json()["id"], 300)
    assert j["status"] == "done", j
    assert j["result"]["steps"] == ["analizar", "encuadre", "exportar"]
    assert j["result"]["face"] and j["result"]["face"] > 0.8
    assert client.get(f"/api/projects/{pid}").json()["doc"]["format"]["track_enabled"]


def test_auto_same_aspect_skips_reframe(tone_video):
    pid, _ = _project(tone_video)
    j = wait(client.post(f"/api/projects/{pid}/auto", json={"platform": "youtube", "subtitles": False}).json()["id"], 300)
    assert j["status"] == "done" and "encuadre" not in j["result"]["steps"]
    assert j["result"]["export"]["width"] == 1920


def test_mkv_gets_proxy(silent_video):
    pid, job = _project(silent_video, prepare=True)
    assert wait(job["id"])["status"] == "done"
    assert (config.project_dir(pid) / "proxy.mp4").exists()


def test_missing_windows_runtime_is_explained(monkeypatch, tone_video):
    msg = transcribe.explain(ImportError("DLL load failed while importing _ext: No se encontró el módulo especificado."))
    assert "Visual C++" in msg and "aka.ms" in msg
    assert "internet" in transcribe.explain(OSError("Max retries exceeded with url: huggingface.co"))
    monkeypatch.setattr(transcribe, "import_error", lambda: "Faltan componentes de Windows (Visual C++)")
    pid, _ = _project(tone_video)
    r = client.post(f"/api/projects/{pid}/transcribe", json={"model": "tiny"})
    assert r.status_code == 503 and "Visual C++" in r.json()["detail"]
    assert client.post(f"/api/projects/{pid}/auto", json={}).status_code == 503
    assert client.get("/api/system").json()["whisper_error"] is not None


def test_bundled_fonts_served():
    fonts = client.get("/api/fonts/bundled").json()
    fams = {f["family"] for f in fonts}
    assert {"Inter", "Outfit", "Big Shoulders", "Pixelify Sans"} <= fams
    inter = next(f for f in fonts if f["family"] == "Inter")
    assert inter["css_scale"] == pytest.approx(0.8265, abs=0.002)   # = 0.82 medido en etapas anteriores
    r = client.get(f"/api/fonts/file/{inter['file']}")
    assert r.status_code == 200 and len(r.content) > 50000
    assert client.get("/api/fonts").json()[0] in fams
    assert "WORKSPACE" not in client.get("/api/fonts/file/..%2Fconfig.py").text


@pytest.mark.parametrize("url", ["/..%2F..%2Fbackend%2Fapp%2Fconfig.py", "/%2E%2E/%2E%2E/backend/app/config.py",
                                 "/..%2F..%2F..%2F..%2Fetc%2Fpasswd"])
def test_no_path_traversal(url):
    """Regresión: la ruta de la interfaz permitía leer archivos fuera de frontend/dist."""
    r = client.get(url)
    assert "WORKSPACE" not in r.text and "root:" not in r.text


def test_selfcheck_passes(capsys):
    from app import selfcheck
    assert selfcheck.main() == 0
    out = capsys.readouterr().out
    assert "Los subtítulos se graban en el video" in out and "[FALLA]" not in out


def test_project_id_cannot_escape_workspace():
    for url in ["/api/projects/..%2F..%2Ftmp/exports/x.mp4", "/api/projects/..%2F..%2Fetc/previews/passwd",
                "/api/projects/zzzzzzzzzzzz/exports"]:
        assert client.get(url).status_code == 404
