from flask import Flask, render_template_string, request, jsonify, send_from_directory
import json, os, uuid, sys, re
import webbrowser

app = Flask(__name__)

def get_data_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

DATA_DIR      = get_data_dir()
UPLOAD_FOLDER = os.path.join(DATA_DIR, "uploads")
DB_FILE       = os.path.join(DATA_DIR, "data.json")
STAFF_DIR     = os.path.join(DATA_DIR, "staff")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STAFF_DIR, exist_ok=True)

ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}

DEFAULT_DATA = {
    "products": [],
    "customers": [],
    "pid_cnt": 1,
    "cid_cnt": 1
}

STAFF_META_FILE = os.path.join(DATA_DIR, "staff_meta.json")

def load_staff_meta():
    if os.path.exists(STAFF_META_FILE):
        with open(STAFF_META_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"staff": []}

def save_staff_meta(data):
    with open(STAFF_META_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_db(db_file=None):
    if db_file is None:
        db_file = DB_FILE
    if os.path.exists(db_file):
        with open(db_file, "r", encoding="utf-8") as f:
            return json.load(f)
    save_db(DEFAULT_DATA, db_file)
    return dict(DEFAULT_DATA)

def save_db(data, db_file=None):
    if db_file is None:
        db_file = DB_FILE
    with open(db_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def slugify(name):
    name = name.strip().lower()
    name = re.sub(r'[àáạảãâầấậẩẫăằắặẳẵ]', 'a', name)
    name = re.sub(r'[èéẹẻẽêềếệểễ]', 'e', name)
    name = re.sub(r'[ìíịỉĩ]', 'i', name)
    name = re.sub(r'[òóọỏõôồốộổỗơờớợởỡ]', 'o', name)
    name = re.sub(r'[ùúụủũưừứựửữ]', 'u', name)
    name = re.sub(r'[ỳýỵỷỹ]', 'y', name)
    name = re.sub(r'[đ]', 'd', name)
    name = re.sub(r'[^a-z0-9]+', '_', name)
    return name.strip('_') or 'nhanvien'

def get_staff_db_file(slug):
    return os.path.join(STAFF_DIR, slug, "data.json")

def get_staff_upload_folder(slug):
    folder = os.path.join(STAFF_DIR, slug, "uploads")
    os.makedirs(folder, exist_ok=True)
    return folder

# ─── BOSS ROUTES ──────────────────────────────────────────────────────────────

@app.route("/api/upload", methods=["POST"])
def upload_image():
    return _upload(UPLOAD_FOLDER)

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route("/api/products", methods=["GET"])
def get_products():
    return jsonify(load_db()["products"])

@app.route("/api/products", methods=["POST"])
def add_product():
    db = load_db(); d = request.json
    d["id"] = db["pid_cnt"]; d.setdefault("cycle", None); d.setdefault("image", "")
    if "date" not in d: d["date"] = d.get("start", "")
    if "history" not in d: d["history"] = [{"date": d["date"], "skip": False, "note": d.get("note", "")}]
    db["products"].append(d); db["pid_cnt"] += 1; save_db(db)
    return jsonify({"ok": True, "id": d["id"]})

@app.route("/api/products/<int:pid>", methods=["PUT"])
def update_product(pid):
    db = load_db(); d = request.json
    for i, p in enumerate(db["products"]):
        if p["id"] == pid:
            db["products"][i] = {**p, **d, "id": pid}; save_db(db); return jsonify({"ok": True})
    return jsonify({"ok": False}), 404

@app.route("/api/products/<int:pid>/history", methods=["POST"])
def add_history(pid):
    db = load_db(); entry = request.json
    for i, p in enumerate(db["products"]):
        if p["id"] == pid:
            if "history" not in db["products"][i]: db["products"][i]["history"] = []
            db["products"][i]["history"].append(entry)
            if not entry.get("skip"): db["products"][i]["date"] = entry.get("date", p.get("date", ""))
            save_db(db); return jsonify({"ok": True})
    return jsonify({"ok": False}), 404

@app.route("/api/products/<int:pid>", methods=["DELETE"])
def delete_product(pid):
    db = load_db(); db["products"] = [p for p in db["products"] if p["id"] != pid]
    save_db(db); return jsonify({"ok": True})

@app.route("/api/customers", methods=["GET"])
def get_customers():
    return jsonify(load_db()["customers"])

@app.route("/api/customers", methods=["POST"])
def add_customer():
    db = load_db(); d = request.json; d["id"] = db["cid_cnt"]
    db["customers"].append(d); db["cid_cnt"] += 1; save_db(db)
    return jsonify({"ok": True, "id": d["id"]})

@app.route("/api/customers/<int:cid>", methods=["PUT"])
def update_customer(cid):
    db = load_db(); d = request.json
    for i, c in enumerate(db["customers"]):
        if c["id"] == cid:
            db["customers"][i] = {**c, **d, "id": cid}; save_db(db); return jsonify({"ok": True})
    return jsonify({"ok": False}), 404

@app.route("/api/customers/<int:cid>", methods=["DELETE"])
def delete_customer(cid):
    db = load_db(); db["customers"] = [c for c in db["customers"] if c["id"] != cid]
    save_db(db); return jsonify({"ok": True})

# ─── STAFF ROUTES ──────────────────────────────────────────────────────────────

@app.route("/api/staff", methods=["GET"])
def get_staff_list():
    meta = load_staff_meta()
    for s in meta["staff"]:
        db_file = get_staff_db_file(s["slug"])
        if os.path.exists(db_file):
            db = load_db(db_file)
            s["product_count"] = len(db.get("products", []))
            s["customer_count"] = len(db.get("customers", []))
        else:
            s["product_count"] = 0
            s["customer_count"] = 0
    return jsonify(meta["staff"])

@app.route("/api/staff", methods=["POST"])
def add_staff():
    d = request.json
    name = d.get("name", "").strip()
    role = d.get("role", "").strip()
    phone = d.get("phone", "").strip()
    note = d.get("note", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Tên không được trống"}), 400
    meta = load_staff_meta()
    slug = slugify(name)
    existing_slugs = [s["slug"] for s in meta["staff"]]
    base_slug = slug
    counter = 2
    while slug in existing_slugs:
        slug = f"{base_slug}_{counter}"; counter += 1
    staff_folder = os.path.join(STAFF_DIR, slug)
    os.makedirs(staff_folder, exist_ok=True)
    os.makedirs(os.path.join(staff_folder, "uploads"), exist_ok=True)
    db_file = get_staff_db_file(slug)
    if not os.path.exists(db_file):
        save_db(dict(DEFAULT_DATA), db_file)
    new_staff = {"id": str(uuid.uuid4())[:8], "slug": slug, "name": name, "role": role, "phone": phone, "note": note}
    meta["staff"].append(new_staff)
    save_staff_meta(meta)
    return jsonify({"ok": True, "staff": new_staff})

@app.route("/api/staff/<slug>", methods=["PUT"])
def update_staff(slug):
    meta = load_staff_meta(); d = request.json
    for i, s in enumerate(meta["staff"]):
        if s["slug"] == slug:
            meta["staff"][i] = {**s, "name": d.get("name", s["name"]),
                "role": d.get("role", s.get("role","")),
                "phone": d.get("phone", s.get("phone","")),
                "note": d.get("note", s.get("note",""))}
            save_staff_meta(meta); return jsonify({"ok": True})
    return jsonify({"ok": False}), 404

@app.route("/api/staff/<slug>", methods=["DELETE"])
def delete_staff(slug):
    meta = load_staff_meta()
    meta["staff"] = [s for s in meta["staff"] if s["slug"] != slug]
    save_staff_meta(meta)
    return jsonify({"ok": True})

def _upload(folder):
    if "file" not in request.files: return jsonify({"ok": False, "error": "No file"}), 400
    f = request.files["file"]
    if not f.filename or "." not in f.filename: return jsonify({"ok": False, "error": "Invalid file"}), 400
    ext = f.filename.rsplit(".", 1)[1].lower()
    if ext not in ALLOWED_EXT: return jsonify({"ok": False, "error": "Not allowed"}), 400
    fname = f"{uuid.uuid4().hex}.{ext}"
    f.save(os.path.join(folder, fname))
    return jsonify({"ok": True, "fname": fname})

@app.route("/api/staff/<slug>/upload", methods=["POST"])
def staff_upload(slug):
    folder = get_staff_upload_folder(slug)
    r = _upload(folder)
    data = r.get_json()
    if data.get("ok"):
        data["url"] = f"/staff-uploads/{slug}/{data['fname']}"
        del data["fname"]
    from flask import Response
    return Response(json.dumps(data), mimetype='application/json')

@app.route("/staff-uploads/<slug>/<path:filename>")
def staff_uploaded_file(slug, filename):
    folder = get_staff_upload_folder(slug)
    return send_from_directory(folder, filename)

@app.route("/api/staff/<slug>/products", methods=["GET"])
def staff_get_products(slug):
    return jsonify(load_db(get_staff_db_file(slug)).get("products", []))

@app.route("/api/staff/<slug>/products", methods=["POST"])
def staff_add_product(slug):
    db_file = get_staff_db_file(slug); db = load_db(db_file); d = request.json
    d["id"] = db["pid_cnt"]; d.setdefault("cycle", None); d.setdefault("image", "")
    if "date" not in d: d["date"] = d.get("start", "")
    if "history" not in d: d["history"] = [{"date": d["date"], "skip": False, "note": d.get("note", "")}]
    db["products"].append(d); db["pid_cnt"] += 1; save_db(db, db_file)
    return jsonify({"ok": True, "id": d["id"]})

@app.route("/api/staff/<slug>/products/<int:pid>", methods=["PUT"])
def staff_update_product(slug, pid):
    db_file = get_staff_db_file(slug); db = load_db(db_file); d = request.json
    for i, p in enumerate(db["products"]):
        if p["id"] == pid:
            db["products"][i] = {**p, **d, "id": pid}; save_db(db, db_file); return jsonify({"ok": True})
    return jsonify({"ok": False}), 404

@app.route("/api/staff/<slug>/products/<int:pid>/history", methods=["POST"])
def staff_add_history(slug, pid):
    db_file = get_staff_db_file(slug); db = load_db(db_file); entry = request.json
    for i, p in enumerate(db["products"]):
        if p["id"] == pid:
            if "history" not in db["products"][i]: db["products"][i]["history"] = []
            db["products"][i]["history"].append(entry)
            if not entry.get("skip"): db["products"][i]["date"] = entry.get("date", p.get("date", ""))
            save_db(db, db_file); return jsonify({"ok": True})
    return jsonify({"ok": False}), 404

@app.route("/api/staff/<slug>/products/<int:pid>", methods=["DELETE"])
def staff_delete_product(slug, pid):
    db_file = get_staff_db_file(slug); db = load_db(db_file)
    db["products"] = [p for p in db["products"] if p["id"] != pid]
    save_db(db, db_file); return jsonify({"ok": True})

@app.route("/api/staff/<slug>/customers", methods=["GET"])
def staff_get_customers(slug):
    return jsonify(load_db(get_staff_db_file(slug)).get("customers", []))

@app.route("/api/staff/<slug>/customers", methods=["POST"])
def staff_add_customer(slug):
    db_file = get_staff_db_file(slug); db = load_db(db_file); d = request.json
    d["id"] = db["cid_cnt"]; db["customers"].append(d); db["cid_cnt"] += 1
    save_db(db, db_file); return jsonify({"ok": True, "id": d["id"]})

@app.route("/api/staff/<slug>/customers/<int:cid>", methods=["PUT"])
def staff_update_customer(slug, cid):
    db_file = get_staff_db_file(slug); db = load_db(db_file); d = request.json
    for i, c in enumerate(db["customers"]):
        if c["id"] == cid:
            db["customers"][i] = {**c, **d, "id": cid}; save_db(db, db_file); return jsonify({"ok": True})
    return jsonify({"ok": False}), 404

@app.route("/api/staff/<slug>/customers/<int:cid>", methods=["DELETE"])
def staff_delete_customer(slug, cid):
    db_file = get_staff_db_file(slug); db = load_db(db_file)
    db["customers"] = [c for c in db["customers"] if c["id"] != cid]
    save_db(db, db_file); return jsonify({"ok": True})

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Perfect Packs – Quản Lý</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=DM+Sans:ital,wght@0,300;0,400;0,500;0,600;1,300&display=swap" rel="stylesheet">
<style>
:root{
  --navy:#0d1b2a;--navy-mid:#162032;--navy-light:#1e2d40;
  --gold:#c9a84c;--gold-light:#e2c97e;--gold-dim:#7a6128;
  --cream:#f5f0e8;--cream-mid:#ede6d6;
  --text-main:#1a1a2e;--text-muted:#6b7280;--text-light:#9ca3af;
  --white:#ffffff;--success:#2d9c6f;--danger:#c0392b;--warning:#d4890a;
  --sidebar-w:240px;--radius:12px;
  --shadow:0 4px 24px rgba(13,27,42,0.10);--shadow-lg:0 8px 40px rgba(13,27,42,0.18);
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'DM Sans',sans-serif;background:var(--cream);color:var(--text-main);min-height:100vh;display:flex;overflow:hidden;}

/* SIDEBAR */
.sidebar{width:var(--sidebar-w);background:var(--navy);display:flex;flex-direction:column;height:100vh;position:fixed;left:0;top:0;z-index:100;box-shadow:4px 0 30px rgba(0,0,0,0.25);}
.brand{padding:28px 22px 22px;border-bottom:1px solid rgba(201,168,76,0.2);}
.brand-logo{width:38px;height:38px;background:linear-gradient(135deg,var(--gold),var(--gold-light));border-radius:10px;display:flex;align-items:center;justify-content:center;margin-bottom:12px;font-size:18px;box-shadow:0 2px 12px rgba(201,168,76,0.35);}
.brand-name{font-family:'Playfair Display',serif;color:var(--white);font-size:15px;font-weight:700;}
.brand-name span{display:block;color:var(--gold);font-size:11px;font-family:'DM Sans',sans-serif;font-weight:400;letter-spacing:0.12em;text-transform:uppercase;margin-top:2px;}
.nav-section{padding:18px 12px 0;flex:1;overflow-y:auto;}
.nav-label{font-size:10px;color:rgba(201,168,76,0.5);text-transform:uppercase;letter-spacing:0.15em;padding:0 10px;margin-bottom:8px;font-weight:600;}
.nav-item{display:flex;align-items:center;gap:12px;padding:11px 14px;border-radius:10px;cursor:pointer;color:rgba(255,255,255,0.55);font-size:14px;transition:all .22s ease;margin-bottom:3px;user-select:none;position:relative;}
.nav-item:hover{background:rgba(255,255,255,0.06);color:rgba(255,255,255,0.85);}
.nav-item.active{background:linear-gradient(135deg,rgba(201,168,76,0.22),rgba(201,168,76,0.08));color:var(--gold-light);font-weight:500;}
.nav-item.active::before{content:'';position:absolute;left:0;top:20%;bottom:20%;width:3px;background:var(--gold);border-radius:0 3px 3px 0;}
.nav-item .icon{width:18px;height:18px;opacity:0.7;flex-shrink:0;}
.nav-item.active .icon{opacity:1;}
.nav-divider{height:1px;background:rgba(255,255,255,0.07);margin:10px 14px;}
.staff-nav-item{display:flex;align-items:center;gap:10px;padding:9px 14px;border-radius:10px;cursor:pointer;color:rgba(255,255,255,0.5);font-size:13px;transition:all .2s;margin-bottom:2px;user-select:none;position:relative;}
.staff-nav-item:hover{background:rgba(255,255,255,0.05);color:rgba(255,255,255,0.8);}
.staff-nav-item.active{background:linear-gradient(135deg,rgba(201,168,76,0.18),rgba(201,168,76,0.06));color:var(--gold-light);font-weight:500;}
.staff-nav-item.active::before{content:'';position:absolute;left:0;top:20%;bottom:20%;width:3px;background:var(--gold-light);border-radius:0 3px 3px 0;}
.staff-avatar{width:26px;height:26px;border-radius:50%;background:linear-gradient(135deg,var(--gold-dim),var(--gold));display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:var(--navy);flex-shrink:0;}
.sidebar-footer{padding:16px 22px;border-top:1px solid rgba(255,255,255,0.06);font-size:11px;color:rgba(255,255,255,0.25);}

/* MAIN */
.main{margin-left:var(--sidebar-w);flex:1;height:100vh;overflow-y:auto;}
.page{display:none;padding:32px 36px;animation:fadeIn .3s ease;}
.page.active{display:block;}
@keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.page-title{font-family:'Playfair Display',serif;font-size:28px;color:var(--navy);font-weight:700;}
.page-subtitle{font-size:13px;color:var(--text-muted);margin-top:4px;margin-bottom:28px;}

/* STAFF PAGE */
.staff-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:18px;margin-bottom:32px;}
.staff-card{background:var(--white);border-radius:16px;padding:24px;box-shadow:var(--shadow);border:1px solid rgba(201,168,76,0.08);transition:transform .2s,box-shadow .2s;position:relative;overflow:hidden;}
.staff-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--gold),var(--gold-light));}
.staff-card:hover{transform:translateY(-3px);box-shadow:var(--shadow-lg);}
.staff-card-avatar{width:52px;height:52px;border-radius:50%;background:linear-gradient(135deg,var(--navy),var(--navy-light));display:flex;align-items:center;justify-content:center;font-family:'Playfair Display',serif;font-size:20px;font-weight:700;color:var(--gold-light);margin-bottom:14px;box-shadow:0 3px 12px rgba(13,27,42,0.2);}
.staff-card-name{font-family:'Playfair Display',serif;font-size:16px;font-weight:700;color:var(--navy);margin-bottom:3px;}
.staff-card-role{font-size:12px;color:var(--text-muted);margin-bottom:12px;}
.staff-card-stats{display:flex;gap:16px;padding:10px 0;border-top:1px solid var(--cream-mid);border-bottom:1px solid var(--cream-mid);margin-bottom:12px;}
.staff-stat{text-align:center;flex:1;}
.staff-stat-val{font-family:'Playfair Display',serif;font-size:20px;font-weight:700;color:var(--navy);}
.staff-stat-lbl{font-size:10px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.06em;}
.staff-card-actions{display:flex;gap:8px;}
.add-staff-card{background:transparent;border:2px dashed rgba(201,168,76,0.3);cursor:pointer;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;min-height:200px;transition:all .2s;}
.add-staff-card:hover{border-color:var(--gold);background:rgba(201,168,76,0.04);}
.add-staff-card .plus-icon{width:44px;height:44px;border-radius:50%;background:linear-gradient(135deg,var(--gold),var(--gold-light));display:flex;align-items:center;justify-content:center;font-size:22px;box-shadow:0 3px 14px rgba(201,168,76,0.35);}
.add-staff-card span{font-size:13px;font-weight:500;color:var(--text-muted);}

/* STAFF WORKSPACE HEADER */
.workspace-header{background:linear-gradient(135deg,var(--navy),var(--navy-light));border-radius:16px;padding:22px 26px;margin-bottom:24px;display:flex;align-items:center;gap:18px;}
.workspace-avatar{width:54px;height:54px;border-radius:50%;background:linear-gradient(135deg,var(--gold-dim),var(--gold));display:flex;align-items:center;justify-content:center;font-family:'Playfair Display',serif;font-size:22px;font-weight:700;color:var(--navy);flex-shrink:0;box-shadow:0 3px 14px rgba(201,168,76,0.3);}
.workspace-info{flex:1;}
.workspace-name{font-family:'Playfair Display',serif;font-size:20px;font-weight:700;color:var(--white);}
.workspace-meta{display:flex;gap:14px;margin-top:6px;flex-wrap:wrap;}
.workspace-meta-item{font-size:12px;color:rgba(255,255,255,0.6);display:flex;align-items:center;gap:5px;}
.workspace-meta-item strong{color:var(--gold-light);}
.workspace-tabs{display:flex;gap:6px;margin-left:auto;flex-shrink:0;}
.ws-tab{padding:8px 16px;border-radius:8px;cursor:pointer;font-size:13px;font-weight:500;color:rgba(255,255,255,0.5);border:1.5px solid transparent;transition:all .2s;background:none;}
.ws-tab:hover{color:rgba(255,255,255,0.8);background:rgba(255,255,255,0.07);}
.ws-tab.active{background:rgba(201,168,76,0.2);color:var(--gold-light);border-color:rgba(201,168,76,0.35);}

/* TOOLBAR */
.toolbar{background:var(--white);border-radius:var(--radius);padding:16px 20px;display:flex;flex-direction:column;gap:12px;margin-bottom:20px;box-shadow:var(--shadow);border:1px solid rgba(201,168,76,0.1);}
.toolbar-row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;}
.filter-chip-label{font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.08em;white-space:nowrap;}
.chip{padding:5px 13px;border-radius:20px;border:1.5px solid var(--cream-mid);background:var(--cream);font-size:12px;font-family:'DM Sans',sans-serif;color:var(--text-muted);cursor:pointer;transition:all .18s;font-weight:500;white-space:nowrap;}
.chip:hover{border-color:var(--gold);color:var(--gold-dim);}
.chip.active{background:var(--navy);color:var(--gold-light);border-color:var(--navy);}
.input-wrap{position:relative;}
.input-wrap svg{position:absolute;left:11px;top:50%;transform:translateY(-50%);color:var(--text-light);pointer-events:none;width:15px;height:15px;}
.inp{padding:9px 13px 9px 34px;border:1.5px solid var(--cream-mid);border-radius:8px;font-size:13px;font-family:'DM Sans',sans-serif;background:var(--cream);color:var(--text-main);outline:none;transition:border-color .2s,box-shadow .2s;min-width:155px;}
.inp:focus{border-color:var(--gold);box-shadow:0 0 0 3px rgba(201,168,76,0.12);}
.inp::placeholder{color:var(--text-light);}
.sel{padding:9px 13px;border:1.5px solid var(--cream-mid);border-radius:8px;font-size:13px;font-family:'DM Sans',sans-serif;background:var(--cream);color:var(--text-main);outline:none;transition:border-color .2s;cursor:pointer;min-width:140px;}
.sel:focus{border-color:var(--gold);}
.btn{padding:9px 18px;border-radius:8px;border:none;font-size:13px;font-family:'DM Sans',sans-serif;font-weight:500;cursor:pointer;display:flex;align-items:center;gap:7px;transition:all .2s;white-space:nowrap;}
.btn svg{width:15px;height:15px;}
.btn-primary{background:linear-gradient(135deg,var(--gold),var(--gold-light));color:var(--navy);box-shadow:0 2px 10px rgba(201,168,76,0.3);}
.btn-primary:hover{transform:translateY(-1px);box-shadow:0 4px 16px rgba(201,168,76,0.4);}
.btn-success{background:linear-gradient(135deg,#166534,#22c55e);color:#fff;box-shadow:0 2px 10px rgba(34,197,94,0.3);}
.btn-success:hover{transform:translateY(-1px);box-shadow:0 4px 16px rgba(34,197,94,0.4);}
.btn-secondary{background:var(--navy-light);color:var(--white);}
.btn-secondary:hover{background:var(--navy-mid);}
.btn-danger{background:#fef2f2;color:var(--danger);border:1px solid #fecaca;}
.btn-danger:hover{background:#fee2e2;}
.btn-sm{padding:6px 12px;font-size:12px;}
.btn-cancel{background:var(--cream);color:var(--text-muted);border:1.5px solid var(--cream-mid);}
.btn-cancel:hover{background:var(--cream-mid);}

/* TABLE */
.table-card{background:var(--white);border-radius:var(--radius);box-shadow:var(--shadow);border:1px solid rgba(201,168,76,0.08);overflow:hidden;}
.table-scroll{overflow-x:auto;}
table{width:100%;border-collapse:collapse;font-size:13.5px;}
thead{background:var(--navy);}
thead th{color:var(--gold-light);font-weight:500;padding:14px 16px;text-align:left;font-size:11.5px;letter-spacing:0.04em;text-transform:uppercase;white-space:nowrap;}
tbody tr{border-bottom:1px solid rgba(0,0,0,0.04);transition:background .15s;}
tbody tr:last-child{border-bottom:none;}
tbody tr:hover{background:rgba(201,168,76,0.04);}
td{padding:13px 16px;vertical-align:middle;white-space:nowrap;}
.stt{color:var(--text-light);font-weight:600;font-size:12px;}
.badge{display:inline-flex;align-items:center;padding:3px 10px;border-radius:20px;font-size:11.5px;font-weight:500;}
.badge-blue{background:#eff6ff;color:#1d4ed8;}
.badge-green{background:#f0fdf4;color:var(--success);}
.badge-orange{background:#fff7ed;color:var(--warning);}
.badge-purple{background:#faf5ff;color:#7c3aed;}
.badge-red{background:#fef2f2;color:var(--danger);}
.badge-cyan{background:#ecfeff;color:#0e7490;}
.cycle-pill{display:inline-block;background:linear-gradient(135deg,#0d1b2a11,#c9a84c18);border:1px solid rgba(201,168,76,0.25);color:var(--navy);padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600;}
.qty-pill{display:inline-block;background:linear-gradient(135deg,#f0fdf411,#22c55e18);border:1px solid rgba(34,197,94,0.3);color:#166534;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600;}
.count-pill{background:var(--navy);color:var(--gold);padding:3px 11px;border-radius:20px;font-size:12px;font-weight:600;}
.phone-link{color:var(--navy);text-decoration:none;font-weight:500;}
.phone-link:hover{color:var(--gold-dim);text-decoration:underline;}
.table-footer{padding:12px 20px;border-top:1px solid var(--cream-mid);display:flex;align-items:center;justify-content:space-between;font-size:12.5px;color:var(--text-muted);}
.note-cell{max-width:180px;white-space:normal;font-size:12px;color:var(--text-muted);font-style:italic;line-height:1.45;}
.prod-thumb{width:52px;height:52px;object-fit:cover;border-radius:9px;border:1.5px solid var(--cream-mid);display:block;box-shadow:0 2px 8px rgba(0,0,0,0.09);transition:transform .2s,box-shadow .2s,border-color .2s;cursor:zoom-in;}
.prod-thumb:hover{transform:scale(1.1);box-shadow:0 6px 20px rgba(13,27,42,0.2);border-color:var(--gold);}
.prod-no-img{width:52px;height:52px;border-radius:9px;border:1.5px dashed var(--cream-mid);background:var(--cream);display:flex;align-items:center;justify-content:center;font-size:22px;color:var(--text-light);}
.img-upload-area{width:130px;height:130px;border:2px dashed var(--cream-mid);border-radius:12px;display:flex;flex-direction:column;align-items:center;justify-content:center;cursor:pointer;background:var(--cream);transition:border-color .2s,background .2s;gap:8px;}
.img-upload-area:hover{border-color:var(--gold);background:rgba(201,168,76,0.05);}
.img-preview-wrap{position:relative;display:inline-block;}
.img-preview-wrap img{width:130px;height:130px;object-fit:cover;border-radius:12px;border:2px solid var(--gold);display:block;box-shadow:0 4px 16px rgba(201,168,76,0.2);}
.img-remove-btn{position:absolute;top:-9px;right:-9px;background:var(--danger);color:#fff;border:2.5px solid #fff;border-radius:50%;width:26px;height:26px;cursor:pointer;font-size:12px;display:flex;align-items:center;justify-content:center;transition:background .2s;box-shadow:0 2px 8px rgba(0,0,0,0.2);}
.img-remove-btn:hover{background:#991b1b;}
.lightbox{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:9999;align-items:center;justify-content:center;cursor:zoom-out;backdrop-filter:blur(4px);}
.lightbox.open{display:flex;animation:fadeIn .2s ease;}
.lightbox img{max-width:90vw;max-height:88vh;border-radius:14px;box-shadow:0 12px 80px rgba(0,0,0,0.7);animation:lightboxIn .25s cubic-bezier(.32,1,.45,1);}
@keyframes lightboxIn{from{transform:scale(0.88);opacity:0}to{transform:scale(1);opacity:1}}
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:18px;margin-bottom:28px;}
.stat-card{background:var(--white);border-radius:var(--radius);padding:22px 24px;box-shadow:var(--shadow);border:1px solid rgba(201,168,76,0.08);position:relative;overflow:hidden;transition:transform .2s,box-shadow .2s;}
.stat-card:hover{transform:translateY(-2px);box-shadow:var(--shadow-lg);}
.stat-card::after{content:'';position:absolute;right:-20px;top:-20px;width:90px;height:90px;border-radius:50%;background:rgba(201,168,76,0.07);}
.stat-icon{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:20px;margin-bottom:14px;}
.stat-icon.navy{background:linear-gradient(135deg,var(--navy),var(--navy-light));}
.stat-icon.gold{background:linear-gradient(135deg,var(--gold-dim),var(--gold));}
.stat-icon.green{background:linear-gradient(135deg,#166534,#22c55e);}
.stat-icon.blue{background:linear-gradient(135deg,#1e3a5f,#3b82f6);}
.stat-val{font-family:'Playfair Display',serif;font-size:32px;font-weight:700;color:var(--navy);line-height:1;margin-bottom:6px;}
.stat-label{font-size:13px;color:var(--text-muted);}
.stats-row{display:grid;grid-template-columns:1fr 1fr;gap:18px;}
.chart-card{background:var(--white);border-radius:var(--radius);padding:24px;box-shadow:var(--shadow);border:1px solid rgba(201,168,76,0.08);}
.chart-title{font-family:'Playfair Display',serif;font-size:16px;color:var(--navy);font-weight:700;margin-bottom:4px;}
.chart-sub{font-size:12px;color:var(--text-muted);margin-bottom:18px;}
.bar-chart{display:flex;flex-direction:column;gap:12px;}
.bar-row{display:flex;align-items:center;gap:12px;}
.bar-label{font-size:12.5px;color:var(--text-muted);width:90px;flex-shrink:0;text-align:right;}
.bar-track{flex:1;height:8px;background:var(--cream-mid);border-radius:4px;overflow:hidden;}
.bar-fill{height:100%;border-radius:4px;}
.bar-val{font-size:12px;font-weight:600;color:var(--navy);width:28px;}
.donut-wrap{display:flex;align-items:center;gap:20px;}
.donut-legend{display:flex;flex-direction:column;gap:10px;}
.legend-item{display:flex;align-items:center;gap:8px;font-size:12.5px;}
.legend-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0;}
.overlay{display:none;position:fixed;inset:0;background:rgba(13,27,42,0.55);backdrop-filter:blur(5px);z-index:200;align-items:flex-end;justify-content:center;}
.overlay.open{display:flex;animation:fadeIn .22s ease;}
.modal{background:var(--white);border-radius:20px 20px 0 0;width:680px;max-width:100vw;max-height:92vh;overflow-y:auto;box-shadow:0 -8px 50px rgba(0,0,0,0.22);animation:slideUp .28s cubic-bezier(.32,1,.45,1);}
@keyframes slideUp{from{transform:translateY(60px);opacity:0}to{transform:none;opacity:1}}
.modal-drag{width:40px;height:4px;background:var(--cream-mid);border-radius:2px;margin:12px auto 0;}
.modal-tabs{display:flex;border-bottom:1.5px solid var(--cream-mid);}
.modal-tab{flex:1;padding:14px 12px;cursor:pointer;font-size:13.5px;font-weight:500;color:var(--text-muted);border:none;border-bottom:2.5px solid transparent;margin-bottom:-1.5px;transition:all .2s;background:none;font-family:'DM Sans',sans-serif;display:flex;align-items:center;justify-content:center;gap:6px;}
.modal-tab:hover{color:var(--navy);background:rgba(201,168,76,0.04);}
.modal-tab.active{color:var(--navy);border-bottom-color:var(--gold);font-weight:600;}
.tab-badge{background:var(--navy);color:var(--gold);font-size:10px;padding:1px 6px;border-radius:10px;font-weight:700;}
.modal-panel{display:none;padding:22px 26px 4px;}
.modal-panel.active{display:block;animation:fadeIn .2s ease;}
.form-section-title{font-size:11.5px;font-weight:700;color:var(--navy);text-transform:uppercase;letter-spacing:0.1em;margin-bottom:14px;display:flex;align-items:center;gap:8px;}
.form-section-title::before{content:'';width:3px;height:13px;background:var(--gold);border-radius:2px;flex-shrink:0;}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:15px;margin-bottom:20px;}
.form-group{display:flex;flex-direction:column;gap:5px;}
.form-group.full{grid-column:1/-1;}
.form-label{font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.06em;}
.form-label .req{color:var(--danger);}
.fi-wrap{position:relative;}
.fi-icon{position:absolute;left:11px;top:50%;transform:translateY(-50%);pointer-events:none;font-size:14px;line-height:1;}
.form-inp{padding:10px 13px;border:1.5px solid var(--cream-mid);border-radius:9px;font-size:13.5px;font-family:'DM Sans',sans-serif;background:var(--cream);outline:none;transition:border-color .2s,box-shadow .2s;color:var(--text-main);width:100%;}
.form-inp.pl{padding-left:36px;}
.form-inp:focus{border-color:var(--gold);box-shadow:0 0 0 3px rgba(201,168,76,0.12);}
.modal-footer{padding:14px 26px 20px;display:flex;gap:10px;justify-content:flex-end;background:var(--white);border-top:1px solid var(--cream-mid);position:sticky;bottom:0;}
.history-item{background:var(--cream);border-radius:10px;padding:12px 16px;margin-bottom:8px;border:1px solid var(--cream-mid);}
.history-item.skip{background:#fef2f2;border-color:#fecaca;}
.history-meta{display:flex;align-items:center;gap:10px;font-size:13px;flex-wrap:wrap;}
.history-note{font-size:12px;color:var(--text-muted);margin-top:5px;font-style:italic;}
.prod-mini{background:var(--cream);border-radius:10px;padding:13px 16px;border:1px solid var(--cream-mid);margin-bottom:10px;}
.prod-mini-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:7px;}
.prod-mini-name{font-size:14px;font-weight:600;color:var(--navy);}
.prod-mini-meta{display:flex;gap:14px;font-size:12px;color:var(--text-muted);}
.empty-state{text-align:center;padding:40px 20px;color:var(--text-muted);}
.empty-state .em-icon{font-size:36px;margin-bottom:10px;}
.empty-state p{font-size:14px;}
.toast-wrap{position:fixed;bottom:24px;right:24px;z-index:998;display:flex;flex-direction:column;gap:8px;}
.toast{background:var(--navy);color:var(--white);padding:12px 18px;border-radius:10px;font-size:13px;display:flex;align-items:center;gap:8px;box-shadow:0 4px 20px rgba(0,0,0,0.25);animation:slideUpT .3s ease;border-left:3px solid var(--gold);}
@keyframes slideUpT{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:none}}
::-webkit-scrollbar{width:6px;height:6px;}
::-webkit-scrollbar-track{background:transparent;}
::-webkit-scrollbar-thumb{background:rgba(201,168,76,0.3);border-radius:3px;}
.status-pill{display:inline-flex;align-items:center;gap:5px;padding:4px 11px;border-radius:20px;font-size:12px;font-weight:600;white-space:nowrap;}
.status-pill.overdue{background:#fef2f2;color:var(--danger);border:1px solid #fecaca;}
.status-pill.due-soon-before{background:#fffbeb;color:#92400e;border:1px solid #fcd34d;}
.status-pill.normal{background:#f8fafc;color:var(--text-muted);border:1px solid #e2e8f0;}
.prod-select-wrap{position:relative;display:inline-block;}
.prod-select-btn{background:var(--cream);border:1.5px solid var(--cream-mid);border-radius:8px;padding:5px 10px;font-size:12px;cursor:pointer;font-family:'DM Sans',sans-serif;color:var(--navy);display:flex;align-items:center;gap:5px;transition:border-color .2s;}
.prod-select-btn:hover{border-color:var(--gold);}
.prod-dropdown{position:absolute;top:calc(100% + 4px);left:0;background:var(--white);border:1.5px solid var(--cream-mid);border-radius:10px;box-shadow:var(--shadow-lg);z-index:50;min-width:360px;overflow:hidden;display:none;}
.prod-dropdown.open{display:block;animation:fadeIn .15s ease;}
.prod-dropdown-header{padding:10px 14px;background:var(--navy);color:var(--gold-light);font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;display:grid;grid-template-columns:24px 44px 1fr 100px 64px;gap:8px;align-items:center;}
.prod-dropdown-item{padding:9px 14px;display:grid;grid-template-columns:24px 44px 1fr 100px 64px;gap:8px;align-items:center;font-size:12px;border-bottom:1px solid var(--cream-mid);color:var(--text-main);}
.prod-dropdown-item:last-child{border-bottom:none;}
.prod-dropdown-item:hover{background:rgba(201,168,76,0.06);}
.action-btns{display:flex;gap:6px;}
.btn-eye{background:rgba(201,168,76,0.12);color:var(--gold-dim);border:1.5px solid rgba(201,168,76,0.3);}
.btn-eye:hover{background:rgba(201,168,76,0.22);color:var(--navy);border-color:var(--gold);}
.hv-header{background:linear-gradient(135deg,var(--navy),var(--navy-light));padding:22px 26px;border-radius:20px 20px 0 0;}
.hv-title{font-family:'Playfair Display',serif;color:var(--white);font-size:18px;font-weight:700;margin-bottom:4px;}
.hv-meta{display:flex;gap:16px;flex-wrap:wrap;margin-top:10px;}
.hv-meta-item{display:flex;align-items:center;gap:6px;font-size:12px;color:rgba(255,255,255,0.65);background:rgba(255,255,255,0.08);padding:4px 10px;border-radius:20px;}
.hv-meta-item strong{color:var(--gold-light);}
.hv-body{padding:24px 26px 8px;}
.hv-timeline{position:relative;padding-left:28px;}
.hv-timeline::before{content:'';position:absolute;left:9px;top:0;bottom:0;width:2px;background:linear-gradient(to bottom,var(--gold),rgba(201,168,76,0.1));}
.hv-entry{position:relative;margin-bottom:14px;}
.hv-entry::before{content:'';position:absolute;left:-23px;top:14px;width:12px;height:12px;border-radius:50%;border:2.5px solid var(--white);box-shadow:0 0 0 2px var(--gold);background:var(--gold);}
.hv-entry.skip::before{background:#c0392b;box-shadow:0 0 0 2px #c0392b;}
.hv-card{background:var(--cream);border:1px solid var(--cream-mid);border-radius:12px;padding:13px 16px;transition:box-shadow .2s;}
.hv-card:hover{box-shadow:0 3px 16px rgba(13,27,42,0.09);}
.hv-card.skip{background:#fef2f2;border-color:#fecaca;}
.hv-card.first{background:linear-gradient(135deg,rgba(13,27,42,0.04),rgba(201,168,76,0.1));border-color:rgba(201,168,76,0.3);}
.hv-card-top{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;}
.hv-card-date{font-size:14px;font-weight:700;color:var(--navy);}
.hv-card-gap{font-size:11.5px;color:var(--text-muted);background:var(--white);border:1px solid var(--cream-mid);padding:2px 9px;border-radius:20px;}
.hv-card-note{font-size:12px;color:var(--text-muted);margin-top:6px;font-style:italic;}
.hv-stats-row{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:20px;}
.hv-stat{background:var(--cream);border:1px solid var(--cream-mid);border-radius:10px;padding:12px 14px;text-align:center;}
.hv-stat-val{font-family:'Playfair Display',serif;font-size:22px;font-weight:700;color:var(--navy);}
.hv-stat-lbl{font-size:11px;color:var(--text-muted);margin-top:2px;}
</style>
</head>
<body>

<aside class="sidebar">
  <div class="brand">
    <div class="brand-logo">📦</div>
    <div class="brand-name">Perfect Packs<span>Quản lý doanh nghiệp</span></div>
  </div>
  <nav class="nav-section">
    <div class="nav-label">Menu chính</div>
    <div class="nav-item active" id="nav-stats" onclick="navigate('stats',this)">
      <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
      <span>Thống Kê</span>
    </div>
    <div class="nav-item" id="nav-products" onclick="navigate('products',this)">
      <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 7H4a2 2 0 00-2 2v10a2 2 0 002 2h16a2 2 0 002-2V9a2 2 0 00-2-2z"/><path d="M16 7V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v2"/></svg>
      <span>Sản Phẩm</span>
    </div>
    <div class="nav-item" id="nav-customers" onclick="navigate('customers',this)">
      <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>
      <span>Khách Hàng</span>
    </div>
    <div class="nav-item" id="nav-reminders" onclick="navigate('reminders',this)">
      <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
      <span>Nhắc Nhở</span>
      <span id="sidebar-badge" style="display:none;background:#c0392b;color:#fff;font-size:10px;font-weight:700;padding:1px 7px;border-radius:10px;min-width:18px;text-align:center;margin-left:auto"></span>
    </div>

    <div class="nav-divider"></div>
    <div class="nav-label">Nhân Viên</div>
    <div class="nav-item" id="nav-staff" onclick="navigate('staff',this)">
      <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a5 5 0 015 5 5 5 0 01-5 5 5 5 0 01-5-5 5 5 0 015-5M4 20v-1a8 8 0 0116 0v1"/></svg>
      <span>Quản Lý NV</span>
    </div>
    <div id="staff-nav-list"></div>
  </nav>
  <div class="sidebar-footer">v5.2 · Perfect Packs</div>
</aside>

<main class="main">

<!-- ══ THỐNG KÊ ══ -->
<div class="page active" id="page-stats">
  <div class="page-title">Tổng Quan</div>
  <div class="page-subtitle">Báo cáo hiệu suất kinh doanh</div>
  <div class="stats-grid">
    <div class="stat-card"><div class="stat-icon navy">📦</div><div class="stat-val" id="stat-products">0</div><div class="stat-label">Tổng sản phẩm</div></div>
    <div class="stat-card"><div class="stat-icon gold">👥</div><div class="stat-val" id="stat-customers">0</div><div class="stat-label">Tổng khách hàng</div></div>
    <div class="stat-card"><div class="stat-icon green">🏢</div><div class="stat-val" id="stat-sectors">0</div><div class="stat-label">Lĩnh vực</div></div>
    <div class="stat-card"><div class="stat-icon blue">⏱</div><div class="stat-val" id="stat-avg-cycle">0</div><div class="stat-label">Chu kỳ TB (ngày)</div></div>
  </div>
  <div class="stats-row">
    <div class="chart-card">
      <div class="chart-title">Sản phẩm theo lĩnh vực</div>
      <div class="chart-sub">Phân bổ theo ngành nghề</div>
      <div class="bar-chart" id="sector-chart"></div>
    </div>
    <div class="chart-card">
      <div class="chart-title">Khách hàng theo lĩnh vực</div>
      <div class="chart-sub">Tỷ lệ phân bổ</div>
      <div class="donut-wrap">
        <svg width="120" height="120" viewBox="0 0 120 120" id="donut-svg">
          <circle cx="60" cy="60" r="48" fill="none" stroke="#f0ece2" stroke-width="20"/>
          <text x="60" y="64" text-anchor="middle" font-size="14" font-family="Playfair Display,serif" fill="#0d1b2a" font-weight="700" id="donut-center">0</text>
        </svg>
        <div class="donut-legend" id="donut-legend"></div>
      </div>
    </div>
  </div>
</div>

<!-- ══ SẢN PHẨM ══ -->
<div class="page" id="page-products">
  <div class="page-title">Sản Phẩm</div>
  <div class="page-subtitle">Quản lý đơn hàng & sản phẩm</div>
  <div class="toolbar">
    <div class="toolbar-row">
      <div class="input-wrap">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
        <input class="inp" id="p-search" placeholder="Tìm công ty / sản phẩm / chủ DN…" oninput="renderProducts()">
      </div>
      <select class="sel" id="p-sector" onchange="renderProducts()"><option value="">Tất cả lĩnh vực</option></select>
      <button class="btn btn-primary" style="margin-left:auto" onclick="openProductModal()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>Thêm mới
      </button>
    </div>
  </div>
  <div class="table-card">
    <div class="table-scroll">
      <table>
        <thead><tr>
          <th>#</th><th>Tên Công Ty</th><th style="text-align:center">Ảnh</th>
          <th>Tên Sản Phẩm</th><th>Chủ Doanh Nghiệp</th><th>Lĩnh Vực</th>
          <th>Ngày Đặt Gần Nhất</th><th>Số Lần Đặt</th><th>Chu Kỳ Nhắc</th>
          <th>Số Lượng</th><th>Ghi Chú</th><th>Thao Tác</th>
        </tr></thead>
        <tbody id="product-tbody"></tbody>
      </table>
    </div>
    <div class="table-footer"><span id="product-count"></span><span style="color:var(--gold-dim);font-weight:500">Perfect Packs</span></div>
  </div>
</div>

<!-- ══ KHÁCH HÀNG ══ -->
<div class="page" id="page-customers">
  <div class="page-title">Khách Hàng</div>
  <div class="page-subtitle">Quản lý danh sách khách hàng</div>
  <div class="toolbar">
    <div class="toolbar-row">
      <div class="input-wrap">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
        <input class="inp" id="c-search" placeholder="Tìm công ty / chủ DN / SĐT…" oninput="renderCustomers()">
      </div>
      <select class="sel" id="c-sector" onchange="renderCustomers()"><option value="">Tất cả lĩnh vực</option></select>
      <select class="sel" id="c-personality" onchange="renderCustomers()">
        <option value="">Tất cả tính cách</option>
        <option>Thân thiện</option><option>Chuyên nghiệp</option><option>Khó tính</option>
        <option>Dễ chịu</option><option>Quyết đoán</option><option>Cẩn thận</option>
      </select>
      <button class="btn btn-primary" style="margin-left:auto" onclick="openCustomerModal()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>Thêm mới
      </button>
    </div>
  </div>
  <div class="table-card">
    <div class="table-scroll">
      <table>
        <thead><tr>
          <th>#</th><th>Tên Công Ty</th><th>Sản Phẩm</th>
          <th>Số Điện Thoại</th><th>Số SP</th><th>Tính Cách</th>
          <th>Chủ Doanh Nghiệp</th><th>Lĩnh Vực</th><th>Thao Tác</th>
        </tr></thead>
        <tbody id="customer-tbody"></tbody>
      </table>
    </div>
    <div class="table-footer"><span id="customer-count"></span><span style="color:var(--gold-dim);font-weight:500">Perfect Packs</span></div>
  </div>
</div>

<!-- ══ NHẮC NHỞ ══ -->
<div class="page" id="page-reminders">
  <div class="page-title">Nhắc Nhở Đặt Hàng</div>
  <div class="page-subtitle">Dự đoán ngày đặt hàng tiếp theo theo từng sản phẩm</div>
  <div class="toolbar">
    <div class="toolbar-row">
      <div class="input-wrap">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
        <input class="inp" id="r-search" placeholder="Tìm công ty / sản phẩm…" oninput="renderReminderPage()">
      </div>
      <div style="display:flex;align-items:center;gap:8px;background:var(--cream);border:1.5px solid var(--cream-mid);border-radius:8px;padding:6px 13px;">
        <span style="font-size:13px;color:var(--text-muted);font-weight:500;white-space:nowrap">🔔 Nhắc ±</span>
        <input type="number" id="remind-window2" value="5" min="1" max="60"
          style="width:52px;padding:4px 6px;border:1.5px solid var(--cream-mid);border-radius:6px;font-size:13px;font-family:'DM Sans',sans-serif;background:var(--white);outline:none;text-align:center;font-weight:600;"
          oninput="renderReminderPage()">
        <span style="font-size:13px;color:var(--text-muted);white-space:nowrap">ngày</span>
      </div>
    </div>
    <div class="toolbar-row">
      <span class="filter-chip-label">Trạng thái:</span>
      <div class="chip active" id="rf-all" onclick="setRemindFilter('all',this)">Tất cả</div>
      <div class="chip" id="rf-duesoon-before" onclick="setRemindFilter('due-soon-before',this)">🟡 5 Ngày trước</div>
      <div class="chip" id="rf-duesoon-after" onclick="setRemindFilter('due-soon-after',this)">🟠 5 Ngày sau</div>
      <div class="chip" id="rf-overdue" onclick="setRemindFilter('overdue',this)">🔴 Quá hạn</div>
      <div class="chip" id="rf-normal" onclick="setRemindFilter('normal',this)">🟢 Chưa đến</div>
    </div>
  </div>
  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:20px" id="remind-summary-grid"></div>
  <div class="table-card">
    <div class="table-scroll">
      <table>
        <thead><tr>
          <th>#</th><th>Tên Công Ty</th><th style="text-align:center">Ảnh</th>
          <th>Tên Sản Phẩm</th><th>Chủ DN / SĐT</th>
          <th>Ngày Đặt Gần Nhất</th><th>Chu Kỳ (ngày)</th><th>Dự Kiến Đặt Lại</th>
          <th>Trạng Thái</th><th>Thao Tác</th>
        </tr></thead>
        <tbody id="remind-tbody"></tbody>
      </table>
    </div>
    <div class="table-footer"><span id="remind-count"></span><span style="color:var(--gold-dim);font-weight:500">Perfect Packs</span></div>
  </div>
  <div id="remind-empty" class="empty-state" style="display:none;margin-top:24px">
    <div class="em-icon">🔔</div><p>Chưa có sản phẩm để tính chu kỳ nhắc nhở</p>
  </div>
</div>

<!-- ══ NHÂN VIÊN - DANH SÁCH ══ -->
<div class="page" id="page-staff">
  <div class="page-title">Nhân Viên</div>
  <div class="page-subtitle">Quản lý và xem dữ liệu từng nhân viên</div>
  <div class="staff-grid" id="staff-grid"></div>
</div>

<!-- ══ NHÂN VIÊN - WORKSPACE ══ -->
<div class="page" id="page-staff-workspace">
  <div class="workspace-header" id="ws-header">
    <div class="workspace-avatar" id="ws-avatar">—</div>
    <div class="workspace-info">
      <div class="workspace-name" id="ws-name">—</div>
      <div class="workspace-meta" id="ws-meta"></div>
    </div>
    <div class="workspace-tabs">
      <button class="ws-tab active" id="wst-products" onclick="switchWsTab('products')">📦 Sản Phẩm</button>
      <button class="ws-tab" id="wst-customers" onclick="switchWsTab('customers')">👥 Khách Hàng</button>
      <button class="ws-tab" id="wst-reminders" onclick="switchWsTab('reminders')">🔔 Nhắc Nhở</button>
    </div>
  </div>

  <!-- WS: Products -->
  <div id="ws-products">
    <div class="toolbar">
      <div class="toolbar-row">
        <div class="input-wrap">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
          <input class="inp" id="ws-p-search" placeholder="Tìm sản phẩm…" oninput="wsRenderProducts()">
        </div>
        <button class="btn btn-primary" style="margin-left:auto" onclick="openProductModal(null,true)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>Thêm mới
        </button>
      </div>
    </div>
    <div class="table-card">
      <div class="table-scroll">
        <table>
          <thead><tr>
            <th>#</th><th>Tên Công Ty</th><th style="text-align:center">Ảnh</th>
            <th>Tên Sản Phẩm</th><th>Chủ DN</th><th>Lĩnh Vực</th>
            <th>Ngày Đặt Gần Nhất</th><th>Số Lần Đặt</th><th>Chu Kỳ</th>
            <th>Số Lượng</th><th>Ghi Chú</th><th>Thao Tác</th>
          </tr></thead>
          <tbody id="ws-product-tbody"></tbody>
        </table>
      </div>
      <div class="table-footer"><span id="ws-product-count"></span></div>
    </div>
  </div>

  <!-- WS: Customers -->
  <div id="ws-customers" style="display:none">
    <div class="toolbar">
      <div class="toolbar-row">
        <div class="input-wrap">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
          <input class="inp" id="ws-c-search" placeholder="Tìm khách hàng…" oninput="wsRenderCustomers()">
        </div>
        <button class="btn btn-primary" style="margin-left:auto" onclick="openCustomerModal(null,true)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>Thêm mới
        </button>
      </div>
    </div>
    <div class="table-card">
      <div class="table-scroll">
        <table>
          <thead><tr>
            <th>#</th><th>Tên Công Ty</th><th>Sản Phẩm</th>
            <th>Số Điện Thoại</th><th>Số SP</th><th>Tính Cách</th>
            <th>Chủ Doanh Nghiệp</th><th>Lĩnh Vực</th><th>Thao Tác</th>
          </tr></thead>
          <tbody id="ws-customer-tbody"></tbody>
        </table>
      </div>
      <div class="table-footer"><span id="ws-customer-count"></span></div>
    </div>
  </div>

  <!-- WS: Reminders -->
  <div id="ws-reminders" style="display:none">
    <div class="toolbar">
      <div class="toolbar-row">
        <div class="input-wrap">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
          <input class="inp" id="ws-r-search" placeholder="Tìm…" oninput="wsRenderReminders()">
        </div>
      </div>
    </div>
    <div class="table-card">
      <div class="table-scroll">
        <table>
          <thead><tr>
            <th>#</th><th>Tên Công Ty</th><th style="text-align:center">Ảnh</th>
            <th>Tên Sản Phẩm</th><th>Ngày Đặt Gần Nhất</th>
            <th>Chu Kỳ</th><th>Dự Kiến</th><th>Trạng Thái</th><th>Thao Tác</th>
          </tr></thead>
          <tbody id="ws-remind-tbody"></tbody>
        </table>
      </div>
      <div class="table-footer"><span id="ws-remind-count"></span></div>
    </div>
  </div>
</div>

</main>

<!-- ════ MODAL: NHÂN VIÊN ════ -->
<div class="overlay" id="staff-modal">
  <div class="modal" style="max-width:500px">
    <div class="modal-drag"></div>
    <div style="padding:22px 26px 4px">
      <div class="form-section-title" id="staff-modal-title">Thêm nhân viên mới</div>
      <div class="form-grid">
        <div class="form-group">
          <label class="form-label">Tên Nhân Viên <span class="req">*</span></label>
          <div class="fi-wrap"><span class="fi-icon">👤</span><input class="form-inp pl" id="sm-name" placeholder="VD: Nguyễn Văn A"></div>
        </div>
        <div class="form-group">
          <label class="form-label">Chức Vụ</label>
          <div class="fi-wrap"><span class="fi-icon">💼</span><input class="form-inp pl" id="sm-role" placeholder="VD: Nhân viên kinh doanh"></div>
        </div>
        <div class="form-group">
          <label class="form-label">Số Điện Thoại</label>
          <div class="fi-wrap"><span class="fi-icon">📞</span><input class="form-inp pl" id="sm-phone" type="tel" placeholder="VD: 0901 234 567"></div>
        </div>
        <div class="form-group">
          <label class="form-label">Ghi Chú</label>
          <input class="form-inp" id="sm-note" placeholder="Ghi chú thêm…">
        </div>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-cancel" onclick="closeModal('staff-modal')">Đóng</button>
      <button class="btn btn-primary" onclick="saveStaff()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="15" height="15"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
        Lưu lại
      </button>
    </div>
  </div>
</div>

<!-- ════ MODAL: SẢN PHẨM ════ -->
<div class="overlay" id="product-modal">
  <div class="modal">
    <div class="modal-drag"></div>
    <div class="modal-tabs">
      <button class="modal-tab active" id="pm-t-form" onclick="switchTab('pm','form')">
        <span id="pm-tab-label">✏️ Thêm mới</span>
      </button>
      <button class="modal-tab" id="pm-t-history" onclick="switchTab('pm','history')" style="display:none">
        📋 Lịch sử đặt hàng <span class="tab-badge" id="pm-history-badge">0</span>
      </button>
    </div>
    <div class="modal-panel active" id="pm-p-form">
      <div id="pm-customer-select-wrap">
        <div class="form-section-title">Chọn khách hàng</div>
        <div class="form-group full" style="margin-bottom:18px">
          <label class="form-label">Khách Hàng <span class="req">*</span></label>
          <div class="fi-wrap">
            <span class="fi-icon">👥</span>
            <select class="form-inp pl" id="pm-customer-select" onchange="onCustomerSelect()">
              <option value="">— Chọn khách hàng —</option>
            </select>
          </div>
        </div>
        <div id="pm-customer-preview" style="display:none;background:linear-gradient(135deg,rgba(13,27,42,0.04),rgba(201,168,76,0.08));border:1.5px solid rgba(201,168,76,0.25);border-radius:10px;padding:12px 16px;margin-bottom:18px;">
          <div style="display:flex;gap:20px;flex-wrap:wrap;font-size:13px">
            <span>🏢 <strong id="pm-prev-company"></strong></span>
            <span>👤 <span id="pm-prev-owner"></span></span>
            <span>🏭 <span id="pm-prev-sector"></span></span>
            <span id="pm-prev-phone-wrap">📞 <span id="pm-prev-phone"></span></span>
          </div>
        </div>
      </div>
      <div id="pm-edit-info-wrap" style="display:none">
        <div class="form-section-title">Thông tin khách hàng</div>
        <div class="form-grid" style="margin-bottom:18px">
          <div class="form-group">
            <label class="form-label">Tên Công Ty</label>
            <div class="fi-wrap"><span class="fi-icon">🏢</span><input class="form-inp pl" id="pm-company" readonly style="background:var(--cream-mid);color:var(--text-muted);cursor:default"></div>
          </div>
          <div class="form-group">
            <label class="form-label">Chủ Doanh Nghiệp</label>
            <div class="fi-wrap"><span class="fi-icon">👤</span><input class="form-inp pl" id="pm-owner" readonly style="background:var(--cream-mid);color:var(--text-muted);cursor:default"></div>
          </div>
          <div class="form-group">
            <label class="form-label">Lĩnh Vực</label>
            <div class="fi-wrap"><span class="fi-icon">🏭</span><input class="form-inp pl" id="pm-sector" readonly style="background:var(--cream-mid);color:var(--text-muted);cursor:default"></div>
          </div>
        </div>
      </div>
      <input type="hidden" id="pm-company-hidden">
      <input type="hidden" id="pm-owner-hidden">
      <input type="hidden" id="pm-sector-hidden">
      <div class="form-section-title">Thông tin sản phẩm</div>
      <div class="form-grid">
        <div class="form-group full">
          <label class="form-label">Tên Sản Phẩm <span class="req">*</span></label>
          <div class="fi-wrap"><span class="fi-icon">📦</span><input class="form-inp pl" id="pm-product" placeholder="VD: Hộp carton 3 lớp…"></div>
        </div>
        <div class="form-group">
          <label class="form-label">Chu Kỳ Nhắc Nhở (ngày)</label>
          <div class="fi-wrap"><span class="fi-icon">🔔</span><input class="form-inp pl" id="pm-cycle-remind" type="number" min="1" max="999" placeholder="Để trống = tự tính"></div>
        </div>
        <div class="form-group full">
          <label class="form-label">Ảnh Sản Phẩm</label>
          <div style="display:flex;align-items:flex-start;gap:18px">
            <div id="pm-image-area"></div>
            <div style="font-size:12px;color:var(--text-muted);margin-top:10px;line-height:1.9">📷 JPG, PNG, WebP, GIF · Tối đa 5MB</div>
          </div>
          <input type="file" id="pm-image-file" accept="image/*" style="display:none" onchange="onImageSelect(event)">
        </div>
      </div>
      <div class="form-section-title">Ngày đặt hàng</div>
      <div class="form-grid">
        <div class="form-group">
          <label class="form-label">Ngày Đặt Gần Nhất <span class="req">*</span></label>
          <input class="form-inp" id="pm-date" type="date">
        </div>
        <div class="form-group">
          <label class="form-label">Số Lượng</label>
          <div class="fi-wrap"><span class="fi-icon">📊</span><input class="form-inp pl" id="pm-qty" type="number" min="1" placeholder="VD: 500…"></div>
        </div>
        <div class="form-group full">
          <label class="form-label">Ghi Chú</label>
          <input class="form-inp" id="pm-note" placeholder="Ghi chú thêm…">
        </div>
      </div>
    </div>
    <div class="modal-panel" id="pm-p-history">
      <div id="pm-history-list" style="padding-bottom:16px"></div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-cancel" onclick="closeModal('product-modal')">Đóng</button>
      <button class="btn btn-primary" id="pm-save" onclick="saveProduct()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="15" height="15"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>Lưu lại
      </button>
    </div>
  </div>
</div>

<!-- ════ MODAL: XÁC NHẬN ĐẶT HÀNG ════ -->
<div class="overlay" id="confirm-order-modal">
  <div class="modal" style="max-width:480px">
    <div class="modal-drag"></div>
    <div style="padding:24px 26px 4px">
      <div style="font-family:'Playfair Display',serif;font-size:18px;color:var(--navy);margin-bottom:6px">✅ Xác nhận đặt hàng mới</div>
      <div id="co-info" style="background:linear-gradient(135deg,rgba(13,27,42,0.04),rgba(201,168,76,0.08));border:1.5px solid rgba(201,168,76,0.2);border-radius:10px;padding:12px 16px;margin-bottom:20px;font-size:13px"></div>
      <div class="form-group" style="margin-bottom:12px">
        <label class="form-label">Ngày Đặt <span class="req">*</span></label>
        <input class="form-inp" id="co-date" type="date">
      </div>
      <div class="form-group" style="margin-bottom:12px">
        <label class="form-label">Số Lượng</label>
        <div class="fi-wrap"><span class="fi-icon">📊</span><input class="form-inp pl" id="co-qty" type="number" min="1"></div>
      </div>
      <div class="form-group" style="margin-bottom:4px">
        <label class="form-label">Ghi Chú</label>
        <input class="form-inp" id="co-note" placeholder="Ghi chú…">
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-cancel" onclick="closeModal('confirm-order-modal')">Hủy</button>
      <button class="btn btn-primary" onclick="confirmOrder()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="15" height="15"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>Lưu đợt mới
      </button>
    </div>
  </div>
</div>

<!-- ════ MODAL: KHÔNG LÀM ════ -->
<div class="overlay" id="skip-order-modal">
  <div class="modal" style="max-width:480px">
    <div class="modal-drag"></div>
    <div style="padding:24px 26px 4px">
      <div style="font-family:'Playfair Display',serif;font-size:18px;color:var(--navy);margin-bottom:6px">❌ Khách hàng không làm</div>
      <div id="so-info" style="background:#fef2f2;border:1.5px solid #fecaca;border-radius:10px;padding:12px 16px;margin-bottom:18px;font-size:13px"></div>
      <div style="font-size:13px;color:var(--text-muted);line-height:1.8;margin-bottom:16px;background:var(--cream);border-radius:9px;padding:12px 14px;border:1px solid var(--cream-mid)">
        🔄 Bỏ qua kỳ này. Nhắc lại: <strong id="so-next-date" style="color:var(--navy);font-size:15px"></strong>
      </div>
      <div class="form-group">
        <label class="form-label">Ghi chú (tùy chọn)</label>
        <input class="form-inp" id="so-note" placeholder="VD: Khách bận, hẹn tháng sau…">
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-cancel" onclick="closeModal('skip-order-modal')">Hủy</button>
      <button class="btn btn-danger" onclick="confirmSkip()">❌ Xác nhận bỏ qua</button>
    </div>
  </div>
</div>

<!-- ════ MODAL: KHÁCH HÀNG ════ -->
<div class="overlay" id="customer-modal">
  <div class="modal">
    <div class="modal-drag"></div>
    <div class="modal-tabs">
      <button class="modal-tab active" id="cm-t-form" onclick="switchTab('cm','form')">
        <span id="cm-tab-label">✏️ Thêm mới</span>
      </button>
      <button class="modal-tab" id="cm-t-prods" onclick="switchTab('cm','prods')" style="display:none">
        📦 Sản phẩm <span class="tab-badge" id="cm-prod-badge">0</span>
      </button>
    </div>
    <div class="modal-panel active" id="cm-p-form">
      <div class="form-section-title">Thông tin khách hàng</div>
      <div class="form-grid">
        <div class="form-group">
          <label class="form-label">Tên Công Ty <span class="req">*</span></label>
          <div class="fi-wrap"><span class="fi-icon">🏢</span><input class="form-inp pl" id="cm-company" placeholder="VD: Công ty ABC"></div>
        </div>
        <div class="form-group">
          <label class="form-label">Chủ Doanh Nghiệp <span class="req">*</span></label>
          <div class="fi-wrap"><span class="fi-icon">👤</span><input class="form-inp pl" id="cm-owner" placeholder="VD: Trần Thị B"></div>
        </div>
        <div class="form-group">
          <label class="form-label">Số Điện Thoại</label>
          <div class="fi-wrap"><span class="fi-icon">📞</span><input class="form-inp pl" id="cm-phone" type="tel"></div>
        </div>
        <div class="form-group">
          <label class="form-label">Lĩnh Vực <span class="req">*</span></label>
          <div class="fi-wrap"><span class="fi-icon">🏭</span><input class="form-inp pl" id="cm-sector" list="sl-c" placeholder="VD: Thực phẩm…"><datalist id="sl-c"></datalist></div>
        </div>
        <div class="form-group">
          <label class="form-label">Tính Cách</label>
          <select class="form-inp" id="cm-personality">
            <option value="">-- Chọn --</option>
            <option>Thân thiện</option><option>Chuyên nghiệp</option><option>Khó tính</option>
            <option>Dễ chịu</option><option>Quyết đoán</option><option>Cẩn thận</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">Ghi Chú</label>
          <input class="form-inp" id="cm-note" placeholder="Ghi chú…">
        </div>
      </div>
    </div>
    <div class="modal-panel" id="cm-p-prods">
      <div id="cm-prod-list" style="padding-bottom:16px"></div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-cancel" onclick="closeModal('customer-modal')">Đóng</button>
      <button class="btn btn-primary" id="cm-save" onclick="saveCustomer()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="15" height="15"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>Lưu lại
      </button>
    </div>
  </div>
</div>

<!-- ════ MODAL: LỊCH SỬ ════ -->
<div class="overlay" id="history-view-modal">
  <div class="modal" style="max-width:600px">
    <div class="hv-header">
      <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px">
        <div style="flex:1">
          <div style="font-size:11px;color:rgba(201,168,76,0.7);text-transform:uppercase;letter-spacing:0.12em;margin-bottom:6px">📋 Lịch sử đặt hàng</div>
          <div class="hv-title" id="hv-product-name">—</div>
          <div style="font-size:13px;color:rgba(255,255,255,0.6);margin-top:4px" id="hv-company-name">—</div>
        </div>
        <div id="hv-thumb"></div>
      </div>
      <div class="hv-meta" id="hv-meta"></div>
    </div>
    <div class="hv-body">
      <div class="hv-stats-row" id="hv-stats"></div>
      <div style="font-size:11px;font-weight:700;color:var(--navy);text-transform:uppercase;letter-spacing:0.1em;margin-bottom:14px;display:flex;align-items:center;gap:8px">
        <span style="width:3px;height:13px;background:var(--gold);border-radius:2px;display:inline-block;flex-shrink:0"></span>
        Timeline đặt hàng
      </div>
      <div class="hv-timeline" id="hv-timeline"></div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-cancel" onclick="closeModal('history-view-modal')">Đóng</button>
      <button class="btn btn-primary" id="hv-order-btn">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="15" height="15"><path d="M12 5v14M5 12l7 7 7-7"/></svg>Xác nhận đặt mới
      </button>
    </div>
  </div>
</div>

<div class="lightbox" id="lightbox" onclick="this.classList.remove('open')">
  <img id="lightbox-img" src="" alt="">
</div>
<div class="toast-wrap" id="toast-wrap"></div>

<script>
/* ═══ STATE ═══ */
let products=[], customers=[];
let wsProducts=[], wsCustomers=[];
let staffList=[];
let currentStaffSlug=null;
let editPid=null, editCid=null, editStaffSlug=null;
let isWsContext=false;
let remindFilter='all';
let pendingImageFile=null, currentImageUrl='';
let _actionPid=null, _actionIsWs=false;

const COLORS=['#c9a84c','#0d1b2a','#2d9c6f','#3b82f6','#d4890a','#7c3aed','#c0392b','#16a085'];
const PCLS={Thân_thiện:'badge-green',Chuyên_nghiệp:'badge-blue',Khó_tính:'badge-red',Dễ_chịu:'badge-orange',Quyết_đoán:'badge-purple',Cẩn_thận:'badge-cyan'};
function pCls(p){return PCLS[p?.replace(/ /g,'_')]||'badge-blue';}

/* ═══ UTILS ═══ */
const norm=s=>String(s||'').trim().toLowerCase();
const esc=s=>String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
function days(a,b){if(!a||!b)return null;const d=Math.round((new Date(b)-new Date(a))/86400000);return isNaN(d)?null:d;}
function fmtD(d){if(!d)return '—';const[y,m,dd]=d.split('-');return `${dd}/${m}/${y}`;}
function todayStr(){return new Date().toISOString().split('T')[0];}
function addDays(s,n){const d=new Date(s);d.setDate(d.getDate()+n);return d.toISOString().split('T')[0];}
function getSectors(prods,custs){return[...new Set([...prods.map(p=>p.sector),...custs.map(c=>c.sector)].filter(Boolean))].sort();}
function getProdsOf(company,prods){return prods.filter(p=>norm(p.company)===norm(company));}
function entryDate(e){return e.date||e.start||'';}
function lastOrderDate(p){const h=p.history||[];for(let i=h.length-1;i>=0;i--){if(!h[i].skip){const d=entryDate(h[i]);if(d)return d;}}return p.date||p.start||'';}
function lastNote(p){const h=p.history||[];if(!h.length)return '';return h[h.length-1].note||'';}
function lastOrderQty(p){const h=p.history||[];for(let i=h.length-1;i>=0;i--){if(!h[i].skip&&h[i].qty>0)return h[i].qty;}return null;}
function orderCount(p){return (p.history||[]).filter(e=>!e.skip).length;}
function calcCycleFromHistory(p){
  if(p.cycle>0)return p.cycle;
  const real=(p.history||[]).filter(e=>!e.skip).map(e=>entryDate(e)).filter(Boolean).sort();
  if(real.length>=2){let total=0,cnt=0;for(let i=1;i<real.length;i++){const d=days(real[i-1],real[i]);if(d&&d>0){total+=d;cnt++;}}if(cnt>0)return Math.round(total/cnt);}
  return null;
}
function productReminderInfo(p){
  const today=todayStr();const win=getReminderWindow();const cycle=calcCycleFromHistory(p);const lastDate=lastOrderDate(p);
  if(!cycle||!lastDate)return{status:'no-data',nextOrder:null,daysLeft:null,cycle:null};
  const nextOrder=addDays(lastDate,cycle);const daysLeft=Math.round((new Date(nextOrder)-new Date(today))/86400000);
  let status;
  if(today>addDays(nextOrder,win))status='overdue';
  else if(today>=nextOrder)status='due-soon-after';
  else if(today>=addDays(nextOrder,-win))status='due-soon-before';
  else status='normal';
  return{status,nextOrder,daysLeft,cycle};
}
function customerOf(company,custs){return custs.find(c=>norm(c.company)===norm(company))||null;}
function getReminderWindow(){return parseInt(document.getElementById('remind-window2')?.value)||5;}
function initials(name){if(!name)return '?';const w=name.trim().split(/\s+/);return w.length>1?(w[0][0]+w[w.length-1][0]).toUpperCase():name.substring(0,2).toUpperCase();}

/* ═══ API helpers ═══ */
async function api(path,method='GET',body=null){
  const opts={method,headers:{'Content-Type':'application/json'}};
  if(body)opts.body=JSON.stringify(body);
  const r=await fetch(path,opts);return r.json();
}

/* ─── KEY FIX: base luôn có /api prefix ─── */
function apiBase(){
  return isWsContext && currentStaffSlug ? `/api/staff/${currentStaffSlug}` : '/api';
}

function uploadUrl(){
  return isWsContext && currentStaffSlug ? `/api/staff/${currentStaffSlug}/upload` : '/api/upload';
}

async function loadAll(){[products,customers]=await Promise.all([api('/api/products'),api('/api/customers')]);}
async function loadStaff(){staffList=await api('/api/staff');}
async function loadWs(slug){
  [wsProducts,wsCustomers]=await Promise.all([
    api(`/api/staff/${slug}/products`),
    api(`/api/staff/${slug}/customers`)
  ]);
}

/* ═══ NAVIGATE ═══ */
function navigate(page,el){
  document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));
  if(el)el.classList.add('active');
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.getElementById('page-'+page).classList.add('active');
  if(page==='stats')updateStats();
  if(page==='products'){renderProducts();syncSels();}
  if(page==='customers'){renderCustomers();syncSels();}
  if(page==='reminders')renderReminderPage();
  if(page==='staff'){loadStaff().then(renderStaffPage);}
}

async function openStaffWorkspace(slug){
  currentStaffSlug=slug;isWsContext=true;
  await loadWs(slug);
  const s=staffList.find(x=>x.slug===slug);
  document.getElementById('ws-avatar').textContent=initials(s?.name||slug);
  document.getElementById('ws-name').textContent=s?.name||slug;
  document.getElementById('ws-meta').innerHTML=[
    s?.role?`<div class="workspace-meta-item">💼 ${esc(s.role)}</div>`:'',
    s?.phone?`<div class="workspace-meta-item">📞 <strong>${esc(s.phone)}</strong></div>`:'',
    `<div class="workspace-meta-item">📦 <strong>${wsProducts.length}</strong> sản phẩm</div>`,
    `<div class="workspace-meta-item">👥 <strong>${wsCustomers.length}</strong> khách hàng</div>`,
  ].filter(Boolean).join('');
  document.querySelectorAll('.nav-item,.staff-nav-item').forEach(n=>n.classList.remove('active'));
  const sni=document.getElementById('sni-'+slug);if(sni)sni.classList.add('active');
  switchWsTab('products');
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.getElementById('page-staff-workspace').classList.add('active');
}

function switchWsTab(tab){
  ['products','customers','reminders'].forEach(t=>{
    const el=document.getElementById('ws-'+t);if(el)el.style.display=t===tab?'':'none';
    const btn=document.getElementById('wst-'+t);if(btn)btn.classList.toggle('active',t===tab);
  });
  if(tab==='products')wsRenderProducts();
  if(tab==='customers')wsRenderCustomers();
  if(tab==='reminders')wsRenderReminders();
}

/* ═══ STAFF PAGE ═══ */
function renderStaffPage(){
  const grid=document.getElementById('staff-grid');
  grid.innerHTML=staffList.map(s=>`
    <div class="staff-card">
      <div class="staff-card-avatar">${initials(s.name)}</div>
      <div class="staff-card-name">${esc(s.name)}</div>
      <div class="staff-card-role">${esc(s.role||'Nhân viên')}</div>
      <div class="staff-card-stats">
        <div class="staff-stat"><div class="staff-stat-val">${s.product_count||0}</div><div class="staff-stat-lbl">Sản phẩm</div></div>
        <div class="staff-stat"><div class="staff-stat-val">${s.customer_count||0}</div><div class="staff-stat-lbl">Khách hàng</div></div>
      </div>
      <div class="staff-card-actions">
        <button class="btn btn-primary btn-sm" style="flex:1;justify-content:center" onclick="openStaffWorkspace('${s.slug}')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>Xem dữ liệu
        </button>
        <button class="btn btn-secondary btn-sm" onclick="openStaffModal('${s.slug}')">✏️</button>
        <button class="btn btn-danger btn-sm" onclick="delStaff('${s.slug}')">🗑</button>
      </div>
    </div>
  `).join('')+`
    <div class="staff-card add-staff-card" onclick="openStaffModal()">
      <div class="plus-icon">+</div>
      <span>Thêm nhân viên mới</span>
    </div>
  `;
  renderStaffSidebar();
}

function renderStaffSidebar(){
  const list=document.getElementById('staff-nav-list');
  list.innerHTML=staffList.map(s=>`
    <div class="staff-nav-item" id="sni-${s.slug}" onclick="openStaffWorkspace('${s.slug}')">
      <div class="staff-avatar">${initials(s.name)}</div>
      <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(s.name)}</span>
    </div>
  `).join('');
}

/* ═══ STAFF MODAL ═══ */
function openStaffModal(slug=null){
  editStaffSlug=slug;
  if(slug){
    const s=staffList.find(x=>x.slug===slug);
    document.getElementById('staff-modal-title').textContent='✏️ Chỉnh sửa nhân viên';
    document.getElementById('sm-name').value=s?.name||'';
    document.getElementById('sm-role').value=s?.role||'';
    document.getElementById('sm-phone').value=s?.phone||'';
    document.getElementById('sm-note').value=s?.note||'';
  }else{
    document.getElementById('staff-modal-title').textContent='Thêm nhân viên mới';
    ['sm-name','sm-role','sm-phone','sm-note'].forEach(f=>document.getElementById(f).value='');
  }
  document.getElementById('staff-modal').classList.add('open');
}

async function saveStaff(){
  const name=document.getElementById('sm-name').value.trim();
  const role=document.getElementById('sm-role').value.trim();
  const phone=document.getElementById('sm-phone').value.trim();
  const note=document.getElementById('sm-note').value.trim();
  if(!name){toast('⚠️ Vui lòng nhập tên nhân viên!',true);return;}
  if(editStaffSlug){
    await api(`/api/staff/${editStaffSlug}`,'PUT',{name,role,phone,note});
    toast('✅ Đã cập nhật thông tin nhân viên!');
  }else{
    await api('/api/staff','POST',{name,role,phone,note});
    toast('✅ Đã thêm nhân viên mới!');
  }
  await loadStaff();closeModal('staff-modal');renderStaffPage();
}

async function delStaff(slug){
  const s=staffList.find(x=>x.slug===slug);
  if(!confirm(`Xóa nhân viên "${s?.name||slug}"?\nLưu ý: File data.json của họ vẫn còn trong thư mục staff/${slug}/`))return;
  await api(`/api/staff/${slug}`,'DELETE');
  await loadStaff();renderStaffPage();toast('🗑️ Đã xóa nhân viên khỏi danh sách!');
}

/* ═══ WS RENDERS ═══ */
function wsRenderProducts(){
  const q=(document.getElementById('ws-p-search')?.value||'').toLowerCase();
  const data=wsProducts.filter(p=>!q||norm(p.company).includes(q)||norm(p.product).includes(q));
  const tbody=document.getElementById('ws-product-tbody');
  if(!data.length){tbody.innerHTML=`<tr><td colspan="12"><div class="empty-state"><div class="em-icon">📭</div><p>Chưa có sản phẩm nào</p></div></td></tr>`;document.getElementById('ws-product-count').textContent='0 sản phẩm';return;}
  tbody.innerHTML=data.map((p,i)=>{
    const od=lastOrderDate(p);const cnt=orderCount(p);const cycle=calcCycleFromHistory(p);const lastQty=lastOrderQty(p);const nt=lastNote(p);
    const thumb=p.image?`<td style="text-align:center;padding:8px 14px"><img src="${esc(p.image)}" class="prod-thumb" onclick="openLightbox('${esc(p.image)}')"></td>`:`<td style="text-align:center;padding:8px 14px"><div class="prod-no-img">📦</div></td>`;
    return`<tr><td class="stt">${i+1}</td><td><strong>${esc(p.company)}</strong></td>${thumb}<td>${esc(p.product)}</td><td>${esc(p.owner)}</td><td><span class="badge badge-blue">${esc(p.sector)}</span></td><td>📅 ${od?fmtD(od):'—'}</td><td><span class="count-pill">${cnt} lần</span></td><td>${cycle?`<span class="cycle-pill">${cycle} ngày</span>`:'—'}</td><td>${lastQty?`<span class="qty-pill">📊 ${lastQty.toLocaleString()}</span>`:'—'}</td><td class="note-cell">${nt?esc(nt):'—'}</td><td><div class="action-btns"><button class="btn btn-eye btn-sm" onclick="openHistoryModal(${p.id},true)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg></button><button class="btn btn-secondary btn-sm" onclick="openProductModal(${p.id},true)">✏️</button><button class="btn btn-danger btn-sm" onclick="wsDelProduct(${p.id})">🗑</button></div></td></tr>`;
  }).join('');
  document.getElementById('ws-product-count').textContent=`${data.length} sản phẩm`;
}

function wsRenderCustomers(){
  const q=(document.getElementById('ws-c-search')?.value||'').toLowerCase();
  const data=wsCustomers.filter(c=>!q||norm(c.company).includes(q)||norm(c.owner).includes(q));
  const tbody=document.getElementById('ws-customer-tbody');
  if(!data.length){tbody.innerHTML=`<tr><td colspan="9"><div class="empty-state"><div class="em-icon">👤</div><p>Chưa có khách hàng nào</p></div></td></tr>`;document.getElementById('ws-customer-count').textContent='0 khách hàng';return;}
  tbody.innerHTML=data.map((c,i)=>{
    const cnt=getProdsOf(c.company,wsProducts).length;
    return`<tr><td class="stt">${i+1}</td><td><strong>${esc(c.company)}</strong></td><td>${wsRenderProdSelectCell(c)}</td><td>${c.phone?`<a href="tel:${c.phone}" class="phone-link">📞 ${esc(c.phone)}</a>`:'—'}</td><td><span class="count-pill">${cnt}</span></td><td>${c.personality?`<span class="badge ${pCls(c.personality)}">${esc(c.personality)}</span>`:'—'}</td><td>${esc(c.owner)}</td><td><span class="badge badge-blue">${esc(c.sector)}</span></td><td><div class="action-btns"><button class="btn btn-secondary btn-sm" onclick="openCustomerModal(${c.id},true)">✏️</button><button class="btn btn-danger btn-sm" onclick="wsDelCustomer(${c.id})">🗑</button></div></td></tr>`;
  }).join('');
  document.getElementById('ws-customer-count').textContent=`${data.length} khách hàng`;
}

function wsRenderProdSelectCell(c){
  const prods=getProdsOf(c.company,wsProducts);
  if(!prods.length)return'<span style="color:var(--text-light);font-size:12px">Chưa có SP</span>';
  const uid=`wsd-${c.id}`;
  const rows=prods.map((p,i)=>{
    const od=fmtD(lastOrderDate(p));const cycle=calcCycleFromHistory(p);
    const cyc=cycle?`<span class="cycle-pill" style="font-size:11px">${cycle}ng</span>`:'—';
    const thumb=p.image?`<img src="${esc(p.image)}" style="width:32px;height:32px;object-fit:cover;border-radius:6px;border:1px solid var(--cream-mid);cursor:zoom-in" onclick="openLightbox('${esc(p.image)}')">`:`<div style="width:32px;height:32px;border-radius:6px;background:var(--cream);border:1px dashed var(--cream-mid);display:flex;align-items:center;justify-content:center;font-size:14px">📦</div>`;
    return`<div class="prod-dropdown-item"><span style="color:var(--text-light);font-weight:600">${i+1}</span>${thumb}<span>${esc(p.product)}</span><span style="color:var(--text-muted)">📅 ${od}</span><span>${cyc}</span></div>`;
  }).join('');
  return`<div class="prod-select-wrap" id="${uid}"><button class="prod-select-btn" onclick="toggleProdDrop('${uid}')">📦 ${prods.length} SP <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="12" height="12"><polyline points="6 9 12 15 18 9"/></svg></button><div class="prod-dropdown" id="${uid}-drop"><div class="prod-dropdown-header"><span>#</span><span>Ảnh</span><span>Tên SP</span><span>Ngày đặt</span><span>Chu kỳ</span></div>${rows}</div></div>`;
}

function wsRenderReminders(){
  const q=(document.getElementById('ws-r-search')?.value||'').toLowerCase();
  const all=wsProducts.map(p=>({p,info:productReminderInfo(p)})).filter(x=>x.info.status!=='no-data'&&(!q||norm(x.p.company).includes(q)||norm(x.p.product).includes(q)));
  const ORDER={overdue:0,'due-soon-after':1,'due-soon-before':2,normal:3};
  all.sort((a,b)=>ORDER[a.info.status]-ORDER[b.info.status]);
  const tbody=document.getElementById('ws-remind-tbody');
  if(!all.length){tbody.innerHTML=`<tr><td colspan="9"><div class="empty-state"><div class="em-icon">🔔</div><p>Chưa đủ dữ liệu để tính nhắc nhở</p></div></td></tr>`;document.getElementById('ws-remind-count').textContent='';return;}
  function sPill(info){
    if(info.status==='overdue')return`<span class="status-pill overdue">🔴 Trễ ${Math.abs(info.daysLeft)} ngày</span>`;
    if(info.status==='due-soon-after')return`<span class="status-pill" style="background:#fff4ec;color:#c2410c;border:1px solid #fed7aa">🟠 Sau ${Math.abs(info.daysLeft)} ngày</span>`;
    if(info.status==='due-soon-before')return`<span class="status-pill due-soon-before">🟡 Còn ${info.daysLeft} ngày</span>`;
    return`<span class="status-pill normal">🟢 Còn ${info.daysLeft} ngày</span>`;
  }
  tbody.innerHTML=all.map(({p,info},i)=>{
    const od=lastOrderDate(p);const thumb=p.image?`<td style="text-align:center;padding:8px 14px"><img src="${esc(p.image)}" class="prod-thumb" onclick="openLightbox('${esc(p.image)}')"></td>`:`<td style="text-align:center;padding:8px 14px"><div class="prod-no-img">📦</div></td>`;
    return`<tr><td class="stt">${i+1}</td><td><strong>${esc(p.company)}</strong></td>${thumb}<td>${esc(p.product)}</td><td>📅 ${od?fmtD(od):'—'}</td><td>${info.cycle?`<span class="cycle-pill">${info.cycle} ngày</span>`:'—'}</td><td>${info.nextOrder?`<strong>${fmtD(info.nextOrder)}</strong>`:'—'}</td><td>${sPill(info)}</td><td><div class="action-btns"><button class="btn btn-eye btn-sm" onclick="openHistoryModal(${p.id},true)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg></button><button class="btn btn-success btn-sm" onclick="openConfirmOrder(${p.id},true)">✅</button><button class="btn btn-danger btn-sm" onclick="openSkipOrder(${p.id},true)">❌</button></div></td></tr>`;
  }).join('');
  document.getElementById('ws-remind-count').textContent=`${all.length} sản phẩm`;
}

async function wsDelProduct(pid){
  if(!confirm('Xóa sản phẩm này?'))return;
  await api(`/api/staff/${currentStaffSlug}/products/${pid}`,'DELETE');
  await loadWs(currentStaffSlug);wsRenderProducts();toast('🗑️ Đã xóa!');
}
async function wsDelCustomer(cid){
  if(!confirm('Xóa khách hàng này?'))return;
  await api(`/api/staff/${currentStaffSlug}/customers/${cid}`,'DELETE');
  await loadWs(currentStaffSlug);wsRenderCustomers();toast('🗑️ Đã xóa!');
}

/* ═══ syncSels ═══ */
function syncSels(){
  ['p-sector','c-sector'].forEach(id=>{
    const el=document.getElementById(id);if(!el)return;const cur=el.value;
    el.innerHTML='<option value="">Tất cả lĩnh vực</option>';
    getSectors(products,customers).forEach(s=>{const o=document.createElement('option');o.value=s;o.textContent=s;if(s===cur)o.selected=true;el.appendChild(o);});
  });
  const dl=document.getElementById('sl-c');if(dl){dl.innerHTML='';
    const ctx=isWsContext?getSectors(wsProducts,wsCustomers):getSectors(products,customers);
    ctx.forEach(s=>{const o=document.createElement('option');o.value=s;dl.appendChild(o);});
  }
}

/* ═══ IMAGE ═══ */
function thumbHtml(p){
  const s='text-align:center;padding:8px 14px;';
  if(p.image)return`<td style="${s}"><img src="${esc(p.image)}" class="prod-thumb" onclick="openLightbox('${esc(p.image)}')" title="Nhấn để phóng to"></td>`;
  return`<td style="${s}"><div class="prod-no-img">📦</div></td>`;
}
function openLightbox(src){document.getElementById('lightbox-img').src=src;document.getElementById('lightbox').classList.add('open');}
function renderImageUploadArea(eu){
  currentImageUrl=eu||'';const wrap=document.getElementById('pm-image-area');if(!wrap)return;
  if(eu){wrap.innerHTML=`<div><div class="img-preview-wrap"><img src="${esc(eu)}" onclick="openLightbox('${esc(eu)}')" style="cursor:zoom-in"><button class="img-remove-btn" onclick="removeImage()">✕</button></div><div style="margin-top:10px"><button class="btn btn-secondary btn-sm" onclick="document.getElementById('pm-image-file').click()">🔄 Đổi ảnh</button></div></div>`;}
  else{wrap.innerHTML=`<div class="img-upload-area" onclick="document.getElementById('pm-image-file').click()"><span style="font-size:34px">📷</span><span style="font-size:12px;color:var(--text-muted);font-weight:500">Nhấn để chọn ảnh</span></div>`;}
}
function onImageSelect(e){
  const file=e.target.files[0];if(!file)return;
  if(file.size>5*1024*1024){toast('⚠️ Ảnh vượt quá 5MB!',true);return;}
  pendingImageFile=file;const reader=new FileReader();
  reader.onload=ev=>{
    currentImageUrl=ev.target.result;const wrap=document.getElementById('pm-image-area');
    wrap.innerHTML=`<div><div class="img-preview-wrap"><img src="${ev.target.result}" onclick="openLightbox('${ev.target.result}')" style="cursor:zoom-in"><button class="img-remove-btn" onclick="removeImage()">✕</button></div><div style="margin-top:10px"><button class="btn btn-secondary btn-sm" onclick="document.getElementById('pm-image-file').click()">🔄 Đổi ảnh</button></div></div>`;
  };reader.readAsDataURL(file);
}
function removeImage(){pendingImageFile=null;currentImageUrl='';const fi=document.getElementById('pm-image-file');if(fi)fi.value='';renderImageUploadArea('');}

/* ═══ RENDER PRODUCTS (boss) ═══ */
function renderProducts(){
  const q=document.getElementById('p-search').value.toLowerCase();
  const sec=document.getElementById('p-sector').value;
  const data=products.filter(p=>(!q||norm(p.company).includes(q)||norm(p.product).includes(q)||norm(p.owner).includes(q))&&(!sec||p.sector===sec));
  const tbody=document.getElementById('product-tbody');
  if(!data.length){tbody.innerHTML=`<tr><td colspan="12"><div class="empty-state"><div class="em-icon">📭</div><p>Không tìm thấy sản phẩm nào</p></div></td></tr>`;document.getElementById('product-count').textContent='0 sản phẩm';return;}
  tbody.innerHTML=data.map((p,i)=>{
    const od=lastOrderDate(p);const nt=lastNote(p);const cnt=orderCount(p);const cycle=calcCycleFromHistory(p);const lastQty=lastOrderQty(p);
    return`<tr><td class="stt">${i+1}</td><td><strong>${esc(p.company)}</strong></td>${thumbHtml(p)}<td>${esc(p.product)}</td><td>${esc(p.owner)}</td><td><span class="badge badge-blue">${esc(p.sector)}</span></td><td>📅 ${od?fmtD(od):'—'}</td><td><span class="count-pill">${cnt} lần</span></td><td>${cycle?`<span class="cycle-pill">${cycle} ngày</span>`:'<span style="color:var(--text-light);font-size:12px">Chưa đủ dữ liệu</span>'}</td><td>${lastQty?`<span class="qty-pill">📊 ${lastQty.toLocaleString()}</span>`:'—'}</td><td class="note-cell">${nt?esc(nt):'—'}</td><td><div class="action-btns"><button class="btn btn-eye btn-sm" onclick="openHistoryModal(${p.id},false)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg></button><button class="btn btn-secondary btn-sm" onclick="openProductModal(${p.id},false)">✏️ Sửa</button><button class="btn btn-danger btn-sm" onclick="delProduct(${p.id})">🗑</button></div></td></tr>`;
  }).join('');
  document.getElementById('product-count').textContent=`${data.length} / ${products.length} sản phẩm`;
}

/* ═══ PRODUCT MODAL ═══ */
function getContextData(){return isWsContext?{prods:wsProducts,custs:wsCustomers}:{prods:products,custs:customers};}

function populateCustomerSelect(){
  const sel=document.getElementById('pm-customer-select');if(!sel)return;
  sel.innerHTML='<option value="">— Chọn khách hàng —</option>';
  const {custs}=getContextData();
  [...custs].sort((a,b)=>a.company.localeCompare(b.company)).forEach(c=>{
    const o=document.createElement('option');o.value=c.id;o.textContent=`${c.company}  ·  ${c.owner}`;sel.appendChild(o);
  });
}
function onCustomerSelect(){
  const sel=document.getElementById('pm-customer-select');const cid=parseInt(sel.value);
  const preview=document.getElementById('pm-customer-preview');
  if(!cid){preview.style.display='none';return;}
  const {custs}=getContextData();const c=custs.find(x=>x.id===cid);if(!c){preview.style.display='none';return;}
  document.getElementById('pm-company-hidden').value=c.company;
  document.getElementById('pm-owner-hidden').value=c.owner;
  document.getElementById('pm-sector-hidden').value=c.sector;
  document.getElementById('pm-prev-company').textContent=c.company;
  document.getElementById('pm-prev-owner').textContent=c.owner;
  document.getElementById('pm-prev-sector').textContent=c.sector;
  const pw=document.getElementById('pm-prev-phone-wrap');
  if(c.phone){document.getElementById('pm-prev-phone').textContent=c.phone;pw.style.display='';}else pw.style.display='none';
  preview.style.display='flex';
}

function openProductModal(id=null,ws=false){
  isWsContext=ws;editPid=id;switchTab('pm','form');
  const histBtn=document.getElementById('pm-t-history');
  const selectWrap=document.getElementById('pm-customer-select-wrap');
  const editWrap=document.getElementById('pm-edit-info-wrap');
  ['pm-product','pm-date','pm-cycle-remind','pm-qty','pm-note'].forEach(f=>document.getElementById(f).value='');
  pendingImageFile=null;const fi=document.getElementById('pm-image-file');if(fi)fi.value='';
  const {prods}=getContextData();
  if(id){
    const p=prods.find(x=>x.id===id);if(!p)return;
    document.getElementById('pm-tab-label').textContent='✏️ Chỉnh sửa';
    selectWrap.style.display='none';editWrap.style.display='';
    document.getElementById('pm-company').value=p.company;
    document.getElementById('pm-owner').value=p.owner;
    document.getElementById('pm-sector').value=p.sector;
    document.getElementById('pm-product').value=p.product;
    document.getElementById('pm-cycle-remind').value=p.cycle||'';
    document.getElementById('pm-date').value=lastOrderDate(p);
    document.getElementById('pm-qty').value=lastOrderQty(p)||'';
    document.getElementById('pm-note').value=lastNote(p)||'';
    renderImageUploadArea(p.image||'');
    const h=p.history||[];
    histBtn.style.display='';document.getElementById('pm-history-badge').textContent=h.length;
    document.getElementById('pm-history-list').innerHTML=h.length
      ?[...h].reverse().map((e,i)=>`<div class="history-item${e.skip?' skip':''}"><div class="history-meta"><span style="background:var(--navy);color:var(--gold);font-size:10px;padding:2px 8px;border-radius:10px;font-weight:700">#${h.length-i}</span>${e.skip?`<span class="badge badge-red">❌ Bỏ qua · ${fmtD(entryDate(e))}</span>`:`<span>📅 Đặt hàng: <strong>${fmtD(entryDate(e))}</strong></span>`}${!e.skip&&e.qty?`<span class="qty-pill" style="font-size:11px">📊 ${Number(e.qty).toLocaleString()}</span>`:''}</div>${e.note?`<div class="history-note">💬 ${esc(e.note)}</div>`:''}</div>`).join('')
      :'<div class="empty-state"><div class="em-icon">📋</div><p>Chưa có lịch sử</p></div>';
  }else{
    document.getElementById('pm-tab-label').textContent='✏️ Thêm mới';
    selectWrap.style.display='';editWrap.style.display='none';histBtn.style.display='none';
    populateCustomerSelect();
    document.getElementById('pm-customer-select').value='';
    document.getElementById('pm-customer-preview').style.display='none';
    ['pm-company-hidden','pm-owner-hidden','pm-sector-hidden'].forEach(f=>document.getElementById(f).value='');
    renderImageUploadArea('');
    document.getElementById('pm-date').value=todayStr();
  }
  document.getElementById('product-modal').classList.add('open');
}

async function saveProduct(){
  const v=f=>document.getElementById(f).value.trim();
  const product=v('pm-product');const date=document.getElementById('pm-date').value;const note=v('pm-note');
  const cycleRaw=parseInt(document.getElementById('pm-cycle-remind').value);const cycle=cycleRaw>0?cycleRaw:null;
  const qtyRaw=parseInt(document.getElementById('pm-qty').value);const qty=qtyRaw>0?qtyRaw:null;
  let company,owner,sector;
  if(editPid){company=v('pm-company');owner=v('pm-owner');sector=v('pm-sector');}
  else{company=v('pm-company-hidden');owner=v('pm-owner-hidden');sector=v('pm-sector-hidden');if(!company){toast('⚠️ Vui lòng chọn khách hàng!',true);return;}}
  if(!product||!date){toast('⚠️ Vui lòng điền tên sản phẩm và ngày đặt!',true);return;}
  const {prods}=getContextData();
  let imageUrl='';
  if(editPid){const ex=prods.find(x=>x.id===editPid);imageUrl=ex?.image||'';}
  if(pendingImageFile){
    const fd=new FormData();fd.append('file',pendingImageFile);
    try{
      const uUrl=uploadUrl();
      const r=await fetch(uUrl,{method:'POST',body:fd});const j=await r.json();
      if(j.ok){imageUrl=j.url||`/uploads/${j.fname}`;pendingImageFile=null;}else toast('⚠️ Upload ảnh thất bại!',true);
    }catch{toast('⚠️ Lỗi khi upload ảnh!',true);}
  }else if(currentImageUrl&&!currentImageUrl.startsWith('data:')){imageUrl=currentImageUrl;}
  else if(!currentImageUrl){imageUrl='';}

  /* ─── KEY FIX: dùng apiBase() ─── */
  const base=apiBase();

  if(editPid){
    const p=prods.find(x=>x.id===editPid);const newHistory=[...(p.history||[])];
    const lastRealIdx=newHistory.map((e,i)=>(!e.skip?i:-1)).filter(i=>i>=0).pop();
    if(lastRealIdx!==undefined){newHistory[lastRealIdx]={...newHistory[lastRealIdx],date,qty,note};}
    else{newHistory.push({date,skip:false,qty,note});}
    await api(`${base}/products/${editPid}`,'PUT',{company,product,owner,sector,date,cycle,image:imageUrl,history:newHistory});
    toast('✅ Đã cập nhật sản phẩm!');
  }else{
    await api(`${base}/products`,'POST',{company,product,owner,sector,date,cycle,image:imageUrl,note,history:[{date,skip:false,qty,note}]});
    toast('✅ Đã thêm sản phẩm mới!');
  }
  if(isWsContext&&currentStaffSlug){await loadWs(currentStaffSlug);wsRenderProducts();}
  else{await loadAll();renderProducts();syncSels();updateSidebarBadge();}
  closeModal('product-modal');
}

async function delProduct(id){
  if(!confirm('Xóa sản phẩm này?'))return;
  await api(`/api/products/${id}`,'DELETE');await loadAll();renderProducts();toast('🗑️ Đã xóa!');
}

/* ═══ CUSTOMERS (boss) ═══ */
function renderCustomers(){
  const q=document.getElementById('c-search').value.toLowerCase();
  const sec=document.getElementById('c-sector').value;const pers=document.getElementById('c-personality').value;
  const data=customers.filter(c=>(!q||norm(c.company).includes(q)||norm(c.owner).includes(q)||norm(c.phone).includes(q))&&(!sec||c.sector===sec)&&(!pers||c.personality===pers));
  const tbody=document.getElementById('customer-tbody');
  if(!data.length){tbody.innerHTML=`<tr><td colspan="9"><div class="empty-state"><div class="em-icon">👤</div><p>Không tìm thấy</p></div></td></tr>`;document.getElementById('customer-count').textContent='0 khách hàng';return;}
  tbody.innerHTML=data.map((c,i)=>{
    const cnt=getProdsOf(c.company,products).length;
    return`<tr><td class="stt">${i+1}</td><td><strong>${esc(c.company)}</strong></td><td>${renderProdSelectCell(c)}</td><td>${c.phone?`<a href="tel:${c.phone}" class="phone-link">📞 ${esc(c.phone)}</a>`:'—'}</td><td><span class="count-pill">${cnt}</span></td><td>${c.personality?`<span class="badge ${pCls(c.personality)}">${esc(c.personality)}</span>`:'—'}</td><td>${esc(c.owner)}</td><td><span class="badge badge-blue">${esc(c.sector)}</span></td><td><div class="action-btns"><button class="btn btn-secondary btn-sm" onclick="openCustomerModal(${c.id},false)">✏️ Sửa</button><button class="btn btn-danger btn-sm" onclick="delCustomer(${c.id})">🗑</button></div></td></tr>`;
  }).join('');
  document.getElementById('customer-count').textContent=`${data.length} / ${customers.length} khách hàng`;
}

function renderProdSelectCell(c){
  const prods=getProdsOf(c.company,products);
  if(!prods.length)return'<span style="color:var(--text-light);font-size:12px">Chưa có SP</span>';
  const uid=`pd-${c.id}`;
  const rows=prods.map((p,i)=>{
    const od=fmtD(lastOrderDate(p));const cycle=calcCycleFromHistory(p);
    const cyc=cycle?`<span class="cycle-pill" style="font-size:11px">${cycle}ng</span>`:'—';
    const thumb=p.image?`<img src="${esc(p.image)}" style="width:32px;height:32px;object-fit:cover;border-radius:6px;border:1px solid var(--cream-mid);cursor:zoom-in" onclick="openLightbox('${esc(p.image)}')">`:`<div style="width:32px;height:32px;border-radius:6px;background:var(--cream);border:1px dashed var(--cream-mid);display:flex;align-items:center;justify-content:center;font-size:14px">📦</div>`;
    return`<div class="prod-dropdown-item"><span style="color:var(--text-light);font-weight:600">${i+1}</span>${thumb}<span style="font-weight:500;overflow:hidden;text-overflow:ellipsis">${esc(p.product)}</span><span style="color:var(--text-muted)">📅 ${od}</span><span>${cyc}</span></div>`;
  }).join('');
  return`<div class="prod-select-wrap" id="${uid}"><button class="prod-select-btn" onclick="toggleProdDrop('${uid}')">📦 ${prods.length} SP <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="12" height="12"><polyline points="6 9 12 15 18 9"/></svg></button><div class="prod-dropdown" id="${uid}-drop"><div class="prod-dropdown-header"><span>#</span><span>Ảnh</span><span>Tên SP</span><span>Ngày đặt</span><span>Chu kỳ</span></div>${rows}</div></div>`;
}
function toggleProdDrop(uid){
  document.querySelectorAll('.prod-dropdown.open').forEach(d=>{if(d.id!==uid+'-drop')d.classList.remove('open');});
  document.getElementById(uid+'-drop').classList.toggle('open');
}
document.addEventListener('click',e=>{if(!e.target.closest('.prod-select-wrap'))document.querySelectorAll('.prod-dropdown.open').forEach(d=>d.classList.remove('open'));});

/* ═══ CUSTOMER MODAL ═══ */
function openCustomerModal(id=null,ws=false){
  isWsContext=ws;editCid=id;switchTab('cm','form');
  const prodBtn=document.getElementById('cm-t-prods');
  const {prods,custs}=getContextData();
  if(id){
    const c=custs.find(x=>x.id===id);if(!c)return;
    document.getElementById('cm-tab-label').textContent='✏️ Chỉnh sửa';
    document.getElementById('cm-company').value=c.company;document.getElementById('cm-owner').value=c.owner;
    document.getElementById('cm-phone').value=c.phone||'';document.getElementById('cm-sector').value=c.sector;
    document.getElementById('cm-personality').value=c.personality||'';document.getElementById('cm-note').value=c.note||'';
    const cp=getProdsOf(c.company,prods);
    prodBtn.style.display='';document.getElementById('cm-prod-badge').textContent=cp.length;
    document.getElementById('cm-prod-list').innerHTML=cp.length
      ?cp.map(p=>`<div class="prod-mini"><div class="prod-mini-top"><div style="display:flex;align-items:center;gap:10px">${p.image?`<img src="${esc(p.image)}" style="width:38px;height:38px;object-fit:cover;border-radius:7px;border:1.5px solid var(--gold);cursor:zoom-in" onclick="openLightbox('${esc(p.image)}')">`:''}
<span class="prod-mini-name">${esc(p.product)}</span></div><span class="cycle-pill">${calcCycleFromHistory(p)?calcCycleFromHistory(p)+' ngày':'—'}</span></div><div class="prod-mini-meta"><span>📅 ${fmtD(lastOrderDate(p))}</span><span>🔢 ${orderCount(p)} lần</span></div></div>`).join('')
      :'<div class="empty-state"><div class="em-icon">📦</div><p>Chưa có sản phẩm</p></div>';
  }else{
    document.getElementById('cm-tab-label').textContent='✏️ Thêm mới';
    ['cm-company','cm-owner','cm-phone','cm-sector','cm-note'].forEach(f=>document.getElementById(f).value='');
    document.getElementById('cm-personality').value='';prodBtn.style.display='none';
  }
  syncSels();document.getElementById('customer-modal').classList.add('open');
}

async function saveCustomer(){
  const v=f=>document.getElementById(f).value.trim();
  const company=v('cm-company'),owner=v('cm-owner'),phone=v('cm-phone'),sector=v('cm-sector');
  const personality=document.getElementById('cm-personality').value,note=v('cm-note');
  if(!company||!owner||!sector){toast('⚠️ Vui lòng điền đầy đủ!',true);return;}
  const body={company,owner,phone,sector,personality,note};

  /* ─── KEY FIX: dùng apiBase() ─── */
  const base=apiBase();

  if(editCid){await api(`${base}/customers/${editCid}`,'PUT',body);toast('✅ Đã cập nhật!');}
  else{await api(`${base}/customers`,'POST',body);toast('✅ Đã thêm khách hàng mới!');}
  if(isWsContext&&currentStaffSlug){await loadWs(currentStaffSlug);wsRenderCustomers();}
  else{await loadAll();renderCustomers();syncSels();}
  closeModal('customer-modal');
}

async function delCustomer(id){
  if(!confirm('Xóa khách hàng này?'))return;
  await api(`/api/customers/${id}`,'DELETE');await loadAll();renderCustomers();toast('🗑️ Đã xóa!');
}

/* ═══ TAB / MODAL ═══ */
function switchTab(prefix,tab){
  ['form','history','prods'].forEach(t=>{
    const btn=document.getElementById(`${prefix}-t-${t}`);const panel=document.getElementById(`${prefix}-p-${t}`);
    if(btn)btn.classList.toggle('active',t===tab);if(panel)panel.classList.toggle('active',t===tab);
  });
  const sb=document.getElementById(`${prefix}-save`);if(sb)sb.style.display=tab==='form'?'':'none';
}
function closeModal(id){document.getElementById(id).classList.remove('open');}
document.querySelectorAll('.overlay').forEach(o=>o.addEventListener('click',e=>{if(e.target===o)o.classList.remove('open');}));

/* ═══ SIDEBAR BADGE ═══ */
function updateSidebarBadge(){
  const n=products.filter(p=>{const s=productReminderInfo(p).status;return s==='overdue'||s==='due-soon-before'||s==='due-soon-after';}).length;
  const b=document.getElementById('sidebar-badge');if(!b)return;b.textContent=n;b.style.display=n>0?'':'none';
}

/* ═══ REMINDER PAGE ═══ */
function setRemindFilter(f,el){
  remindFilter=f;
  document.querySelectorAll('#rf-all,#rf-overdue,#rf-duesoon-after,#rf-duesoon-before,#rf-normal').forEach(e=>e.classList.remove('active'));
  el.classList.add('active');renderReminderPage();
}
function renderReminderPage(){
  const q=(document.getElementById('r-search')?.value||'').toLowerCase();
  const all=products.map(p=>({p,info:productReminderInfo(p)})).filter(x=>x.info.status!=='no-data');
  const by={overdue:[],'due-soon-after':[],'due-soon-before':[],normal:[]};
  all.forEach(x=>{if(by[x.info.status])by[x.info.status].push(x);});
  document.getElementById('remind-summary-grid').innerHTML=[
    {label:'5 Ngày trước nhắc nhở',count:by['due-soon-before'].length,icon:'🟡'},
    {label:'5 Ngày sau nhắc nhở',count:by['due-soon-after'].length,icon:'🟠'},
    {label:'Chưa đến hạn',count:by.normal.length,icon:'🟢'},
    {label:'Quá hạn',count:by.overdue.length,icon:'🔴'},
  ].map(s=>`<div style="background:var(--white);border-radius:var(--radius);padding:18px 20px;box-shadow:var(--shadow);border:1px solid rgba(201,168,76,0.08);display:flex;align-items:center;gap:14px"><span style="font-size:26px">${s.icon}</span><div><div style="font-family:'Playfair Display',serif;font-size:28px;font-weight:700;color:var(--navy);line-height:1">${s.count}</div><div style="font-size:12px;color:var(--text-muted);margin-top:3px">${s.label}</div></div></div>`).join('');
  const ORDER={overdue:0,'due-soon-after':1,'due-soon-before':2,normal:3};
  const shown=all.filter(x=>{
    const s=x.info.status;
    if(remindFilter!=='all'){if(remindFilter==='due-soon-after'&&s!=='due-soon-after')return false;if(remindFilter==='due-soon-before'&&s!=='due-soon-before')return false;if(remindFilter!=='due-soon-after'&&remindFilter!=='due-soon-before'&&s!==remindFilter)return false;}
    if(q&&!norm(x.p.company).includes(q)&&!norm(x.p.product).includes(q))return false;return true;
  }).sort((a,b)=>ORDER[a.info.status]-ORDER[b.info.status]);
  const tbody=document.getElementById('remind-tbody');const countEl=document.getElementById('remind-count');
  const emptyEl=document.getElementById('remind-empty');const tableCard=document.querySelector('#page-reminders .table-card');
  if(!all.length){tableCard.style.display='none';emptyEl.style.display='';countEl.textContent='';updateSidebarBadge();return;}
  tableCard.style.display='';emptyEl.style.display='none';
  if(!shown.length){tbody.innerHTML=`<tr><td colspan="10"><div class="empty-state"><div class="em-icon">🔍</div><p>Không có kết quả</p></div></td></tr>`;countEl.textContent='0 kết quả';updateSidebarBadge();return;}
  function statusPill(info){
    if(info.status==='overdue')return`<span class="status-pill overdue">🔴 Trễ ${Math.abs(info.daysLeft)} ngày</span>`;
    if(info.status==='due-soon-after')return`<span class="status-pill" style="background:#fff4ec;color:#c2410c;border:1px solid #fed7aa">🟠 Sau ${Math.abs(info.daysLeft)} ngày</span>`;
    if(info.status==='due-soon-before')return`<span class="status-pill due-soon-before">🟡 Còn ${info.daysLeft} ngày</span>`;
    return`<span class="status-pill normal">🟢 Còn ${info.daysLeft} ngày</span>`;
  }
  tbody.innerHTML=shown.map(({p,info},i)=>{
    const cust=customerOf(p.company,customers);const phone=cust?.phone?`<br><a href="tel:${cust.phone}" class="phone-link" style="font-size:12px">📞 ${esc(cust.phone)}</a>`:'';const od=lastOrderDate(p);
    return`<tr><td class="stt">${i+1}</td><td><strong>${esc(p.company)}</strong></td>${thumbHtml(p)}<td>${esc(p.product)}</td><td>${esc(cust?.owner||p.owner||'—')}${phone}</td><td>📅 ${od?fmtD(od):'—'}</td><td>${info.cycle?`<span class="cycle-pill">${info.cycle} ngày</span>`:'—'}</td><td>${info.nextOrder?`<strong>${fmtD(info.nextOrder)}</strong>`:'—'}</td><td>${statusPill(info)}</td><td><div class="action-btns"><button class="btn btn-eye btn-sm" onclick="openHistoryModal(${p.id},false)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg></button><button class="btn btn-success btn-sm" onclick="openConfirmOrder(${p.id},false)">✅ Đã đặt</button><button class="btn btn-danger btn-sm" onclick="openSkipOrder(${p.id},false)">❌ Bỏ qua</button></div></td></tr>`;
  }).join('');
  countEl.textContent=`${shown.length} / ${all.length} sản phẩm`;updateSidebarBadge();
}

/* ═══ CONFIRM / SKIP ORDER ═══ */
function openConfirmOrder(pid,ws=false){
  _actionPid=pid;_actionIsWs=ws;
  const {prods}=ws?{prods:wsProducts}:getContextData();
  const p=prods.find(x=>x.id===pid);const info=productReminderInfo(p);
  document.getElementById('co-date').value=todayStr();
  document.getElementById('co-qty').value='';document.getElementById('co-note').value='';
  document.getElementById('co-info').innerHTML=`🏢 <strong>${esc(p.company)}</strong> &nbsp;·&nbsp; 📦 ${esc(p.product)}<br><span style="color:var(--text-muted)">${info.nextOrder?`Dự kiến: <strong>${fmtD(info.nextOrder)}</strong> · `:''}Chu kỳ: ${info.cycle?info.cycle+' ngày':'chưa có'}</span>`;
  document.getElementById('confirm-order-modal').classList.add('open');
}

async function confirmOrder(){
  /* ─── KEY FIX: dùng apiBase() với _actionIsWs ─── */
  const base=_actionIsWs&&currentStaffSlug?`/api/staff/${currentStaffSlug}`:'/api';
  const {prods}=_actionIsWs?{prods:wsProducts}:getContextData();
  const p=prods.find(x=>x.id===_actionPid);const date=document.getElementById('co-date').value;
  const note=document.getElementById('co-note').value.trim();
  const qtyRaw=parseInt(document.getElementById('co-qty').value);const qty=qtyRaw>0?qtyRaw:null;
  if(!date){toast('⚠️ Vui lòng chọn ngày!',true);return;}
  await api(`${base}/products/${p.id}/history`,'POST',{date,skip:false,qty,note});
  if(_actionIsWs&&currentStaffSlug){await loadWs(currentStaffSlug);wsRenderProducts();wsRenderReminders();}
  else{await loadAll();renderReminderPage();renderProducts();updateSidebarBadge();}
  closeModal('confirm-order-modal');toast(`✅ Đã ghi nhận đơn cho ${p.company}!`);
}

function openSkipOrder(pid,ws=false){
  _actionPid=pid;_actionIsWs=ws;
  const {prods}=ws?{prods:wsProducts}:getContextData();
  const p=prods.find(x=>x.id===pid);const info=productReminderInfo(p);
  document.getElementById('so-note').value='';
  document.getElementById('so-info').innerHTML=`🏢 <strong>${esc(p.company)}</strong> &nbsp;·&nbsp; 📦 ${esc(p.product)}`;
  document.getElementById('so-next-date').textContent=fmtD(addDays(todayStr(),info.cycle||30));
  document.getElementById('skip-order-modal').classList.add('open');
}

async function confirmSkip(){
  /* ─── KEY FIX: dùng apiBase() với _actionIsWs ─── */
  const base=_actionIsWs&&currentStaffSlug?`/api/staff/${currentStaffSlug}`:'/api';
  const {prods}=_actionIsWs?{prods:wsProducts}:getContextData();
  const p=prods.find(x=>x.id===_actionPid);const info=productReminderInfo(p);
  const note=document.getElementById('so-note').value.trim();const today=todayStr();
  await api(`${base}/products/${p.id}/history`,'POST',{date:today,skip:true,note});
  if(_actionIsWs&&currentStaffSlug){await loadWs(currentStaffSlug);wsRenderReminders();}
  else{await loadAll();renderReminderPage();updateSidebarBadge();}
  closeModal('skip-order-modal');toast(`⏭ Bỏ qua — nhắc lại ${fmtD(addDays(today,info.cycle||30))}`);
}

/* ═══ STATS ═══ */
function updateStats(){
  document.getElementById('stat-products').textContent=products.length;
  document.getElementById('stat-customers').textContent=customers.length;
  document.getElementById('stat-sectors').textContent=getSectors(products,customers).length;
  const cycs=products.map(p=>calcCycleFromHistory(p)).filter(c=>c&&c>0);
  document.getElementById('stat-avg-cycle').textContent=cycs.length?Math.round(cycs.reduce((a,b)=>a+b,0)/cycs.length):0;
  const sc={};products.forEach(p=>{if(p.sector)sc[p.sector]=(sc[p.sector]||0)+1;});
  const se=Object.entries(sc).sort((a,b)=>b[1]-a[1]),mx=se.length?se[0][1]:1;
  document.getElementById('sector-chart').innerHTML=se.length?se.map(([s,v],i)=>`<div class="bar-row"><div class="bar-label">${s}</div><div class="bar-track"><div class="bar-fill" style="width:${Math.round(v/mx*100)}%;background:${COLORS[i%COLORS.length]}"></div></div><div class="bar-val">${v}</div></div>`).join(''):'<div class="empty-state"><div class="em-icon">📊</div><p>Chưa có dữ liệu</p></div>';
  const cc={};customers.forEach(c=>{if(c.sector)cc[c.sector]=(cc[c.sector]||0)+1;});
  const ce=Object.entries(cc),total=ce.reduce((a,[,v])=>a+v,0);
  const svg=document.getElementById('donut-svg');svg.querySelectorAll('.arc').forEach(e=>e.remove());
  document.getElementById('donut-center').textContent=total;
  const legend=document.getElementById('donut-legend');
  if(!ce.length){legend.innerHTML='<p style="color:var(--text-muted);font-size:13px">Chưa có dữ liệu</p>';return;}
  const R=48,cx=60,cy=60,circ=2*Math.PI*R;let offset=0;
  ce.forEach(([s,v],i)=>{
    const dash=v/total*circ;const c2=document.createElementNS('http://www.w3.org/2000/svg','circle');
    c2.setAttribute('class','arc');c2.setAttribute('cx',cx);c2.setAttribute('cy',cy);c2.setAttribute('r',R);
    c2.setAttribute('fill','none');c2.setAttribute('stroke',COLORS[i%COLORS.length]);c2.setAttribute('stroke-width','20');
    c2.setAttribute('stroke-dasharray',`${dash} ${circ-dash}`);c2.setAttribute('stroke-dashoffset',-offset);
    c2.setAttribute('transform',`rotate(-90 ${cx} ${cy})`);svg.insertBefore(c2,svg.querySelector('text'));offset+=dash;
  });
  legend.innerHTML=ce.map(([s,v],i)=>`<div class="legend-item"><div class="legend-dot" style="background:${COLORS[i%COLORS.length]}"></div><span>${s} (${v})</span></div>`).join('');
}

/* ═══ HISTORY VIEW MODAL ═══ */
function openHistoryModal(pid,ws=false){
  const {prods,custs}=ws?{prods:wsProducts,custs:wsCustomers}:getContextData();
  const p=prods.find(x=>x.id===pid);if(!p)return;
  const info=productReminderInfo(p);const h=[...(p.history||[])];const realEntries=h.filter(e=>!e.skip);const cycle=calcCycleFromHistory(p);const cust=customerOf(p.company,custs);
  document.getElementById('hv-product-name').textContent=p.product;
  document.getElementById('hv-company-name').textContent=`🏢 ${p.company}  ·  👤 ${cust?.owner||p.owner||''}`;
  const thumbEl=document.getElementById('hv-thumb');
  thumbEl.innerHTML=p.image?`<img src="${esc(p.image)}" style="width:64px;height:64px;object-fit:cover;border-radius:10px;border:2px solid rgba(201,168,76,0.4);cursor:zoom-in;box-shadow:0 3px 12px rgba(0,0,0,0.3)" onclick="openLightbox('${esc(p.image)}')">`:'';
  document.getElementById('hv-meta').innerHTML=[
    cust?.phone?`<div class="hv-meta-item">📞 <strong>${esc(cust.phone)}</strong></div>`:'',
    `<div class="hv-meta-item">🔢 Tổng: <strong>${realEntries.length} lần</strong></div>`,
    cycle?`<div class="hv-meta-item">🔄 Chu kỳ: <strong>${cycle} ngày</strong></div>`:'',
    info.nextOrder?`<div class="hv-meta-item">📆 Dự kiến: <strong>${fmtD(info.nextOrder)}</strong></div>`:'',
  ].filter(Boolean).join('');
  document.getElementById('hv-stats').innerHTML=[
    {val:realEntries.length,lbl:'Lần đặt hàng'},
    {val:cycle?cycle+'ng':'—',lbl:'Chu kỳ'},
    {val:info.nextOrder?fmtD(info.nextOrder):'—',lbl:'Dự kiến đặt lại'},
  ].map(s=>`<div class="hv-stat"><div class="hv-stat-val">${s.val}</div><div class="hv-stat-lbl">${s.lbl}</div></div>`).join('');
  const reversed=[...h].reverse();
  document.getElementById('hv-timeline').innerHTML=reversed.length?reversed.map((e,i)=>{
    const isFirst=i===reversed.length-1;const d=entryDate(e);let gapHtml='';
    if(!e.skip&&i<reversed.length-1){const prev=reversed.slice(i+1).find(x=>!x.skip);if(prev){const g=days(entryDate(prev),d);if(g>0)gapHtml=`<span class="hv-card-gap">+${g} ngày</span>`;}}
    const qtyHtml=(!e.skip&&e.qty)?`<span class="qty-pill" style="font-size:11.5px;margin-left:6px">📊 ${Number(e.qty).toLocaleString()}</span>`:'';
    return`<div class="hv-entry${e.skip?' skip':''}"><div class="hv-card${e.skip?' skip':isFirst?' first':''}"><div class="hv-card-top"><div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap"><span style="background:${e.skip?'#c0392b':'var(--navy)'};color:${e.skip?'#fff':'var(--gold)'};font-size:10px;padding:2px 8px;border-radius:10px;font-weight:700;flex-shrink:0">#${h.length-([...h].length-1-i)}</span>${e.skip?`<span style="color:var(--danger);font-weight:600;font-size:13px">❌ Bỏ qua · ${fmtD(d)}</span>`:`<span class="hv-card-date">📅 ${fmtD(d)}</span>${qtyHtml}`}</div>${gapHtml}</div>${e.note?`<div class="hv-card-note">💬 ${esc(e.note)}</div>`:''}</div></div>`;
  }).join(''):'<div class="empty-state"><div class="em-icon">📋</div><p>Chưa có lịch sử</p></div>';
  document.getElementById('hv-order-btn').onclick=()=>{closeModal('history-view-modal');openConfirmOrder(pid,ws);};
  document.getElementById('history-view-modal').classList.add('open');
}

/* ═══ TOAST ═══ */
function toast(msg,warn=false){
  const t=document.createElement('div');t.className='toast';if(warn)t.style.borderLeftColor='#d4890a';t.textContent=msg;
  document.getElementById('toast-wrap').appendChild(t);setTimeout(()=>t.remove(),3000);
}

/* ═══ INIT ═══ */
window.addEventListener('DOMContentLoaded',async()=>{
  await loadAll();await loadStaff();updateStats();syncSels();updateSidebarBadge();renderStaffSidebar();
});
</script>
</body>
</html>"""

if __name__ == "__main__":
    import threading, time
    url = "http://localhost:5000"
    print(f"🚀 Perfect Packs đang chạy tại: {url}")
    print(f"📁 Dữ liệu lưu tại: {DATA_DIR}")
    print(f"👥 Nhân viên lưu tại: {STAFF_DIR}")
    def open_browser():
        time.sleep(1)
        webbrowser.open(url)
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(debug=False, port=5000)