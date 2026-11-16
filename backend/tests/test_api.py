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


def _new_with_video(path, name="P"):
    pid = client.post("/api/projects", json={"name": name}).json()["id"]
    j = client.post(f"/api/projects/{pid}/import-path", json={"path": str(path)}).json()
    assert wait(j["id"])["status"] == "done"
    return pid


def test_scenes_and_facetrack_jobs(scene_video, face_video):
    pid = _new_with_video(scene_video, "Escenas")
    j = wait(client.post(f"/api/projects/{pid}/scenes", json={}).json()["id"])
    assert j["status"] == "done" and j["result"]["scenes"] == 2
    assert len(client.get(f"/api/projects/{pid}").json()["doc"]["scenes"]) == 2
    # sin rostros: error claro
    j = wait(client.post(f"/api/projects/{pid}/facetrack").json()["id"])
    assert j["status"] == "failed" and "rostro" in j["error"]

    pid = _new_with_video(face_video, "Rostro")
    j = wait(client.post(f"/api/projects/{pid}/facetrack").json()["id"])
    assert j["status"] == "done" and j["result"]["detection_rate"] > 0.8
    fmt = client.get(f"/api/projects/{pid}").json()["doc"]["format"]
    assert fmt["track_enabled"] and len(fmt["track"]) >= 2


def test_music_upload_and_preview_clip(tone_video, music_file):
    pid = _new_with_video(tone_video, "Música")
    r = client.post(f"/api/projects/{pid}/music", files={"file": ("cancion.wav", music_file.read_bytes(), "audio/wav")})
    assert r.status_code == 200 and r.json()["doc"]["audio"]["music"]["duration"] == pytest.approx(5, abs=0.1)
    assert client.get(f"/api/projects/{pid}/media/music").status_code == 200
    bad = client.post(f"/api/projects/{pid}/music", files={"file": ("x.txt", b"hola", "text/plain")})
    assert bad.status_code == 400

    # transición por defecto + previsualización exacta de 2 s alrededor de una unión
    proj = client.get(f"/api/projects/{pid}").json()
    doc = proj["doc"]
    doc["cuts"] = [{"id": "c1", "start": 2.0, "end": 4.0, "kind": "manual", "enabled": True, "reason": ""}]
    doc["transition_default"] = {"type": "dissolve", "duration": 0.5, "intensity": 1, "direction": "left"}
    assert client.put(f"/api/projects/{pid}", json={"rev": proj["rev"], "doc": doc}).status_code == 200
    j = wait(client.post(f"/api/projects/{pid}/preview-clip", json={"center": 2.0, "span": 2.0}).json()["id"])
    assert j["status"] == "done", j
    assert j["result"]["duration"] == pytest.approx(2.0, abs=0.05) and j["result"]["transitions"] == 1
    assert client.get(f"/api/projects/{pid}/previews/{j['result']['video']}").status_code == 200

    r = client.delete(f"/api/projects/{pid}/music")
    assert r.json()["doc"]["audio"]["music"] is None
    assert not music_file.with_name("x").exists() and music_file.exists()   # el archivo del usuario sigue ahí


def test_import_project_and_relink(tone_video, tmp_path):
    import shutil
    copy = tmp_path / "copia.mov"
    shutil.copy(tone_video, copy)
    pid = _new_with_video(copy, "Original")
    proj = client.get(f"/api/projects/{pid}").json()
    proj["doc"]["cuts"] = [{"id": "c1", "start": 1, "end": 2, "kind": "manual", "enabled": True, "reason": ""}]
    client.put(f"/api/projects/{pid}", json={"rev": proj["rev"], "doc": proj["doc"]})
    exported = client.get(f"/api/projects/{pid}/project-file").content

    copy.unlink()   # el video "se movió"
    assert client.get(f"/api/projects/{pid}").json()["media_available"] is False

    r = client.post("/api/projects/import", files={"file": ("mi.svep.json", exported, "application/json")})
    assert r.status_code == 200
    new = r.json()
    assert new["id"] != pid and new["media_available"] is False and len(new["doc"]["cuts"]) == 1

    # reconectar al mismo video en otra ubicación conserva los cortes
    j = client.post(f"/api/projects/{new['id']}/relink", json={"path": str(tone_video)}).json()
    assert wait(j["id"])["status"] == "done"
    after = client.get(f"/api/projects/{new['id']}").json()
    assert after["media_available"] and len(after["doc"]["cuts"]) == 1 and after["doc"]["proxy_ready"]

    # otro video con distinta duración: se rechaza salvo que se fuerce
    other = tmp_path / "otro.mp4"
    import subprocess
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=320x240:r=25:d=3",
                    "-pix_fmt", "yuv420p", str(other)], check=True)
    assert client.post(f"/api/projects/{new['id']}/relink", json={"path": str(other)}).status_code == 409
    assert client.post("/api/projects/import", files={"file": ("x.json", b"{malo", "application/json")}).status_code == 400
