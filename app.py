#!/usr/bin/env python3
"""Reel Splitter web app: upload a 16:9 video, get 9:16 parts with title + Part-N."""
import hmac
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from flask import (Flask, Response, abort, jsonify, render_template_string,
                   request, send_from_directory)
from werkzeug.utils import secure_filename

BASE = Path(__file__).parent.resolve()
JOBS_DIR = BASE / "jobs"
JOBS_DIR.mkdir(exist_ok=True)
PASSWORD = os.environ.get("REEL_PASSWORD", "")
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "5000"))

app = Flask(__name__)
jobs = {}
one_at_a_time = threading.Semaphore(1)  # never run two encodes at once
ID_RE = re.compile(r"^[0-9a-f]{32}$")


@app.before_request
def require_login():
    if not PASSWORD:
        return None
    auth = request.authorization
    if auth and hmac.compare_digest(auth.password or "", PASSWORD):
        return None
    return Response("Login required", 401, {"WWW-Authenticate": 'Basic realm="Reel Splitter"'})


def run_job(jid, cmd, input_path):
    job = jobs[jid]
    with one_at_a_time:
        job["state"] = "running"
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, bufsize=1)
            for line in p.stdout:
                line = line.strip()
                if not line:
                    continue
                job["tail"] = (job["tail"] + [line])[-8:]
                m = re.search(r"-> (\d+) parts", line)
                if m:
                    job["total"] = int(m.group(1))
                m = re.match(r"\[(\d+)/(\d+)\]", line)
                if m:
                    job["done"] = int(m.group(1)) - 1
                    job["total"] = int(m.group(2))
            p.wait()
            if p.returncode == 0:
                job["done"] = job["total"]
                job["state"] = "done"
            else:
                job["state"] = "error"
                job["error"] = " | ".join(job["tail"][-3:]) or "ffmpeg failed"
        except Exception as e:  # noqa: BLE001
            job["state"] = "error"
            job["error"] = str(e)
        finally:
            try:
                os.remove(input_path)  # free disk; parts are what matter
            except OSError:
                pass


@app.route("/")
def index():
    return render_template_string(PAGE)


@app.route("/start", methods=["POST"])
def start():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify(error="Choose a video file"), 400
    try:
        part_seconds = max(5, min(600, int(request.form.get("part_seconds", 60))))
        width = int(request.form.get("width", 720))
        start_part = max(1, int(request.form.get("start_part", 1)))
    except ValueError:
        return jsonify(error="Bad number in the form"), 400
    if width not in (480, 720, 1080):
        return jsonify(error="Bad width"), 400
    bg = request.form.get("bg", "black")
    preset = request.form.get("preset", "veryfast")
    if bg not in ("black", "white") or preset not in ("ultrafast", "superfast", "veryfast", "medium"):
        return jsonify(error="Bad option"), 400

    jid = uuid.uuid4().hex
    jdir = JOBS_DIR / jid
    jdir.mkdir()
    name = secure_filename(f.filename) or "video.mp4"
    input_path = jdir / name
    f.save(input_path)
    title = (request.form.get("title") or "").strip() or Path(name).stem.replace("_", " ")

    cmd = [sys.executable, str(BASE / "reel_splitter.py"), str(input_path),
           "--title", title, "--part-seconds", str(part_seconds), "--width", str(width),
           "--bg", bg, "--start-part", str(start_part), "--preset", preset,
           "--outdir", str(jdir / "parts"), "--zip"]
    jobs[jid] = {"state": "queued", "done": 0, "total": 0, "error": "", "tail": []}
    threading.Thread(target=run_job, args=(jid, cmd, input_path), daemon=True).start()
    return jsonify(id=jid)


@app.route("/status/<jid>")
def status(jid):
    job = jobs.get(jid)
    if not ID_RE.match(jid) or job is None:
        return jsonify(state="gone")
    out = {k: job[k] for k in ("state", "done", "total", "error")}
    if job["state"] == "done":
        pdir = JOBS_DIR / jid / "parts"
        out["files"] = sorted(p.name for p in pdir.glob("part_*.mp4"))
        out["zip"] = (JOBS_DIR / jid / "parts.zip").exists()
    return jsonify(out)


@app.route("/files/<jid>/<name>")
def files(jid, name):
    if not ID_RE.match(jid):
        abort(404)
    if name == "parts.zip":
        return send_from_directory(JOBS_DIR / jid, name, as_attachment=True,
                                   download_name="reel_parts.zip")
    if not re.match(r"^part_\d+\.mp4$", name):
        abort(404)
    return send_from_directory(JOBS_DIR / jid / "parts", name, as_attachment=True)


@app.route("/delete/<jid>", methods=["POST"])
def delete(jid):
    if not ID_RE.match(jid):
        abort(404)
    shutil.rmtree(JOBS_DIR / jid, ignore_errors=True)
    jobs.pop(jid, None)
    return jsonify(ok=True)


PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reel Splitter</title>
<style>
body{font-family:system-ui,sans-serif;background:#0f0f12;color:#eee;margin:0 auto;padding:16px;max-width:520px}
h1{font-size:20px}
label{display:block;margin:12px 0 4px;font-size:14px;color:#aaa}
input,select,button{width:100%;box-sizing:border-box;padding:12px;border-radius:8px;border:1px solid #333;background:#1a1a20;color:#eee;font-size:16px}
button{background:#5b6cff;border:0;margin-top:16px;font-weight:600}
button:disabled{opacity:.5}
.row{display:flex;gap:8px}.row>div{flex:1}
.bar{height:10px;background:#222;border-radius:5px;overflow:hidden;margin-top:8px}
.bar i{display:block;height:100%;width:0;background:#5b6cff}
a{color:#8fa0ff}
.file{display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid #222}
.small{font-size:13px;color:#888}
</style></head><body>
<h1>Reel Splitter</h1>
<p class="small">16:9 video in, 9:16 parts out, with title on top and Part-N below. Use your own videos only.</p>
<label>Video file</label><input type="file" id="file" accept="video/*">
<label>Title (shown on top)</label><input id="title" placeholder="My Video Name">
<div class="row">
<div><label>Part length (sec)</label><input id="part_seconds" type="number" value="60" min="5" max="600"></div>
<div><label>First part number</label><input id="start_part" type="number" value="1" min="1"></div>
</div>
<div class="row">
<div><label>Background</label><select id="bg"><option>black</option><option>white</option></select></div>
<div><label>Quality</label><select id="width"><option value="720">720p (faster)</option><option value="1080">1080p</option><option value="480">480p (fastest)</option></select></div>
</div>
<label>Speed</label><select id="preset"><option value="veryfast">Normal</option><option value="ultrafast">Fastest (bigger files)</option><option value="medium">Slow (smaller files)</option></select>
<button id="go">Start</button>
<div id="box" style="display:none;margin-top:16px"><div id="msg"></div><div class="bar"><i id="fill"></i></div></div>
<div id="result"></div>
<script>
const $=id=>document.getElementById(id);
let jobId=null;
function show(t,p){$('box').style.display='block';$('msg').textContent=t;$('fill').style.width=p+'%'}
$('go').onclick=()=>{
  const f=$('file').files[0]; if(!f){alert('Choose a video first');return}
  const fd=new FormData(); fd.append('file',f);
  ['title','part_seconds','width','bg','start_part','preset'].forEach(k=>fd.append(k,$(k).value));
  $('go').disabled=true; $('result').innerHTML=''; show('Uploading 0%',0);
  const x=new XMLHttpRequest(); x.open('POST','/start');
  x.upload.onprogress=e=>{if(e.lengthComputable){const p=Math.round(e.loaded/e.total*100);show('Uploading '+p+'%',p)}};
  x.onload=()=>{let r={};try{r=JSON.parse(x.responseText)}catch(e){}
    if(x.status!==200){show(r.error||'Upload failed',0);$('go').disabled=false;return}
    jobId=r.id; try{localStorage.setItem('reelJob',jobId)}catch(e){} poll()};
  x.onerror=()=>{show('Upload failed',0);$('go').disabled=false};
  x.send(fd);
};
function poll(){
  fetch('/status/'+jobId).then(r=>r.json()).then(s=>{
    if(s.state==='gone'){show('That job is gone.',0);$('go').disabled=false;return}
    if(s.state==='error'){show('Error: '+s.error,0);$('go').disabled=false;return}
    if(s.state==='done'){finish(s);return}
    const t=s.total;show(t?('Making parts '+s.done+' / '+t):'Starting...',t?Math.round(s.done/t*100):0);
    setTimeout(poll,2000);
  }).catch(()=>setTimeout(poll,4000));
}
function finish(s){
  show('Done: '+s.files.length+' parts',100); $('go').disabled=false;
  let h='';
  if(s.zip)h+='<button onclick="location.href=\\'/files/'+jobId+'/parts.zip\\'">Download all (zip)</button>';
  s.files.forEach(n=>{h+='<div class="file"><span>'+n+'</span><a href="/files/'+jobId+'/'+n+'">Download</a></div>'});
  h+='<button id="del" style="background:#3a2020">Delete files from server</button>';
  $('result').innerHTML=h;
  $('del').onclick=()=>{if(confirm('Delete this job and all its parts?'))fetch('/delete/'+jobId,{method:'POST'}).then(()=>{$('result').innerHTML='';show('Deleted.',0);try{localStorage.removeItem('reelJob')}catch(e){}})};
}
try{const j=localStorage.getItem('reelJob');if(j){jobId=j;$('go').disabled=true;show('Checking last job...',0);poll()}}catch(e){}
</script></body></html>"""

if __name__ == "__main__":
    print(f"Reel Splitter running at http://{HOST}:{PORT}"
          + ("  (password on)" if PASSWORD else "  (no password)"))
    app.run(host=HOST, port=PORT, threaded=True)
