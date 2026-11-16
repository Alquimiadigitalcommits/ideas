import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import stream_durations

client = TestClient(app)


def wait(job_id, timeout=240):
    t = time.time()
    while time.time() - t < timeout:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("done", "failed", "canceled"):
            return j
        time.sleep(0.2)
    raise AssertionError("timeout esperando job")


def test_system():
    r = client.get("/api/system").json()
    assert r["ffmpeg"]["ok"] and r["whisper"]
    assert "tiktok" in r["profiles"]
    assert len(client.get("/api/fonts").json()) > 0


def test_full_flow(speech_video):
    p = client.post("/api/projects", json={"name": "Prueba"}).json()
    pid = p["id"]

    # importación por ruta: el original no se copia ni se modifica
    mtime = speech_video.stat().st_mtime
    j = client.post(f"/api/projects/{pid}/import-path", json={"path": str(speech_video)}).json()
    j = wait(j["id"])
    assert j["status"] == "done", j
    proj = client.get(f"/api/projects/{pid}").json()
    assert proj["doc"]["proxy_ready"] and proj["doc"]["media"]["width"] == 1280
    assert proj["doc"]["format"]["aspect"] == "16:9"
    assert client.get(f"/api/projects/{pid}/media/preview").status_code == 200
    r = client.get(f"/api/projects/{pid}/media/preview", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206 and len(r.content) == 100
    assert client.get(f"/api/projects/{pid}/media/waveform").json()["peaks"]
    assert client.get(f"/api/projects/{pid}/media/thumbs.jpg").status_code == 200

    # transcripción
    j = wait(client.post(f"/api/projects/{pid}/transcribe", json={"model": "tiny", "language": "es"}).json()["id"])
    assert j["status"] == "done", j
    proj = client.get(f"/api/projects/{pid}").json()
    assert len(proj["doc"]["captions"]) >= 5

    # auto-edición
    j = wait(client.post(f"/api/projects/{pid}/autoedit", json={}).json()["id"])
    assert j["status"] == "done", j
    assert j["result"]["cuts"] >= 4 and j["result"]["used_words"]
    proj = client.get(f"/api/projects/{pid}").json()
    cuts = proj["doc"]["cuts"]

    # edición del usuario: recuperar un corte + cambiar formato, con control de revisión
    doc = proj["doc"]
    doc["cuts"][0]["enabled"] = False
    doc["format"]["aspect"] = "9:16"
    doc["captions"][0]["text"] = "TEXTO EDITADO"
    saved = client.put(f"/api/projects/{pid}", json={"rev": proj["rev"], "doc": doc})
    assert saved.status_code == 200
    stale = client.put(f"/api/projects/{pid}", json={"rev": proj["rev"], "doc": doc})
    assert stale.status_code == 409 and stale.json()["project"]["rev"] == saved.json()["rev"]

    srt = client.get(f"/api/projects/{pid}/subtitles.srt").text
    assert "TEXTO EDITADO" in srt

    # exportación real
    j = wait(client.post(f"/api/projects/{pid}/export",
                         json={"profile": "tiktok", "preset": "ultrafast", "crf": 30}).json()["id"])
    assert j["status"] == "done", j
    res = j["result"]
    assert res["width"] == 1080 and res["height"] == 1920
    removed = sum(c["end"] - c["start"] for c in cuts[1:])
    assert res["duration"] == pytest.approx(proj["doc"]["media"]["duration"] - removed, abs=0.15)
    exports = client.get(f"/api/projects/{pid}/exports").json()
    names = [e["name"] for e in exports]
    assert res["video"] in names and any(n.endswith(".srt") for n in names)
    dl = client.get(f"/api/projects/{pid}/exports/{res['video']}")
    assert dl.status_code == 200 and len(dl.content) > 10000

    from pathlib import Path
    out = Path(res["dir"]) / res["video"]
    d = stream_durations(out)
    assert abs(float(d["video"]["duration"]) - float(d["audio"]["duration"])) < 0.06
    assert speech_video.stat().st_mtime == mtime  # original intacto

    assert client.get(f"/api/projects/{pid}/project-file").json()["id"] == pid
    assert client.delete(f"/api/projects/{pid}").json()["ok"]
    assert speech_video.exists()


def test_import_errors(tmp_path):
    pid = client.post("/api/projects", json={"name": "Errores"}).json()["id"]
    r = client.post(f"/api/projects/{pid}/import-path", json={"path": str(tmp_path / "no.mp4")})
    assert r.status_code == 400
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"nada")
    assert client.post(f"/api/projects/{pid}/import-path", json={"path": str(bad)}).status_code == 400
    r = client.post(f"/api/projects/{pid}/import", files={"file": ("x.avi", b"123", "video/x-msvideo")})
    assert r.status_code == 400
    assert client.post(f"/api/projects/{pid}/transcribe", json={}).status_code == 400


def test_upload_and_cancel_export(tone_video):
    pid = client.post("/api/projects", json={"name": "Cancelar"}).json()["id"]
    with open(tone_video, "rb") as f:
        j = client.post(f"/api/projects/{pid}/import", files={"file": ("tono prueba.mov", f, "video/quicktime")}).json()
    assert wait(j["id"])["status"] == "done"
    # exportación deliberadamente lenta para poder cancelarla en curso
    j = client.post(f"/api/projects/{pid}/export",
                    json={"profile": "youtube", "preset": "veryslow", "crf": 10, "width": 3840, "height": 2160}).json()
    t = time.time()
    while client.get(f"/api/jobs/{j['id']}").json()["status"] != "running" and time.time() - t < 10:
        time.sleep(0.05)
    time.sleep(0.5)
    assert client.post(f"/api/jobs/{j['id']}/cancel").status_code == 200
    j = wait(j["id"], timeout=30)
    assert j["status"] == "canceled"
    names = [e["name"] for e in client.get(f"/api/projects/{pid}/exports").json()]
    assert not any(n.endswith(".mp4") for n in names)  # sin archivos a medias
