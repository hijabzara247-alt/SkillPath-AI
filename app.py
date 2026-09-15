import os
import re
import json
import sqlite3
import hashlib
import secrets
from datetime import datetime, timedelta
from html import escape
from pathlib import Path

import streamlit as st
from groq import Groq
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
APP_TITLE = "SkillPath AI"
MODEL_NAME = "openai/gpt-oss-120b"
DB_FILE = "skillpath_ai.db"
PDF_DIR = Path("skillpath_pdfs")
PDF_DIR.mkdir(exist_ok=True)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
try:
    if not GROQ_API_KEY and "GROQ_API_KEY" in st.secrets:
        GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
except Exception:
    pass
if not GROQ_API_KEY:
    st.error("GROQ_API_KEY is missing. Add it in Streamlit Cloud → Settings → Secrets.")
    st.stop()
client = Groq(api_key=GROQ_API_KEY)

# ============================================================
# 2. DATABASE
# ============================================================
def db():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            goal TEXT DEFAULT 'Job',
            created_at TEXT NOT NULL,
            last_login TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS roadmaps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            domain TEXT NOT NULL,
            skill_level TEXT,
            duration TEXT,
            goal TEXT,
            weekly_hours TEXT,
            knowledge TEXT,
            roadmap_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS task_progress (
            roadmap_id INTEGER NOT NULL,
            topic TEXT NOT NULL,
            task TEXT NOT NULL,
            percent INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (roadmap_id, topic, task),
            FOREIGN KEY(roadmap_id) REFERENCES roadmaps(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            activity TEXT NOT NULL,
            details TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    cur.execute("CREATE TABLE IF NOT EXISTS profiles (user_id INTEGER PRIMARY KEY, bio TEXT DEFAULT '', target_role TEXT DEFAULT '', experience TEXT DEFAULT 'Beginner', preferred_style TEXT DEFAULT 'Hands-on', daily_minutes INTEGER DEFAULT 60, updated_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id))")
    cur.execute("CREATE TABLE IF NOT EXISTS assessments (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, domain TEXT NOT NULL, score INTEGER NOT NULL, total INTEGER NOT NULL, answers TEXT DEFAULT '', created_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id))")
    cur.execute("CREATE TABLE IF NOT EXISTS goals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, title TEXT NOT NULL, target_date TEXT NOT NULL, status TEXT DEFAULT 'Active', created_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id))")
    cur.execute("CREATE TABLE IF NOT EXISTS daily_plans (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, roadmap_id INTEGER, plan_date TEXT NOT NULL, plan_json TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(user_id, plan_date), FOREIGN KEY(user_id) REFERENCES users(id))")
    conn.commit()
    conn.close()


init_db()

# ============================================================
# 3. SESSION STATE
# ============================================================
DEFAULT_SESSION = {
    "user_id": None,
    "user_name": "SkillPath User",
    "email": "",
    "roadmap_id": None,
    "data": None,
}


def session_copy():
    return dict(DEFAULT_SESSION)


def now():
    return datetime.now().isoformat(timespec="seconds")


def clean(value):
    return str(value or "").strip()


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 120000).hex()
    return f"{salt}${digest}"


def verify_password(password, stored):
    try:
        salt, expected = stored.split("$", 1)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 120000).hex()
        return secrets.compare_digest(actual, expected)
    except Exception:
        return False


def valid_email(email):
    return bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", clean(email)))


def log_activity(user_id, activity, details=""):
    if not user_id:
        return
    conn = db()
    conn.execute(
        "INSERT INTO activities(user_id, activity, details, created_at) VALUES(?,?,?,?)",
        (user_id, activity, details, now())
    )
    conn.commit()
    conn.close()

# ============================================================
# 4. AI HELPERS
# ============================================================
def groq_text(system_prompt, user_prompt, temperature=0.4, max_tokens=6500):
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""


def extract_json(text):
    text = clean(text)
    text = re.sub(r"^```(?:json)?", "", text, flags=re.I).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
    raise ValueError("AI returned invalid JSON. Please try again.")


def list_clean(value, limit=8):
    if not isinstance(value, list):
        value = [value] if value else []
    return [clean(x) for x in value if clean(x)][:limit]


def normalize_roadmap(data, domain, duration):
    if not isinstance(data, dict):
        data = {}

    data["title"] = clean(data.get("title")) or f"{domain.title()} Learning Roadmap"
    data["summary"] = clean(data.get("summary")) or f"A personalized roadmap for {domain}."
    data["level"] = clean(data.get("level")) or "Level 1"
    data["weeks"] = clean(data.get("weeks")) or duration

    topics = data.get("topics", [])
    if not isinstance(topics, list):
        topics = []
    out_topics = []

    for i, item in enumerate(topics[:10], start=1):
        if isinstance(item, str):
            name = clean(item)
            item = {}
        elif isinstance(item, dict):
            name = clean(item.get("name") or item.get("topic") or item.get("title"))
        else:
            continue
        if not name:
            continue
        tasks_raw = item.get("tasks", []) if isinstance(item, dict) else []
        tasks = list_clean(tasks_raw, 5)
        if not tasks:
            tasks = [
                f"Study the fundamentals of {name}",
                f"Complete a practical exercise on {name}",
                f"Review your mistakes and summarize {name}",
            ]
        out_topics.append({
            "name": name,
            "description": clean(item.get("description", "")) if isinstance(item, dict) else "",
            "week": clean(item.get("week", i)) if isinstance(item, dict) else str(i),
            "tasks": tasks,
            "practice": clean(item.get("practice", "")) if isinstance(item, dict) else "",
        })

    if not out_topics:
        out_topics = [
            {"name": f"{domain.title()} Foundations", "description": "Build core concepts.", "week": "1", "tasks": ["Learn the fundamentals", "Take notes", "Complete a small exercise"], "practice": "30–45 minutes of practice."},
            {"name": f"{domain.title()} Core Skills", "description": "Build practical ability.", "week": "2", "tasks": ["Study core techniques", "Practice examples", "Review mistakes"], "practice": "Complete guided exercises."},
            {"name": f"{domain.title()} Project Work", "description": "Apply skills in a realistic project.", "week": "3", "tasks": ["Choose a project", "Build the first version", "Improve the result"], "practice": "Work on a mini project."},
            {"name": f"{domain.title()} Advanced Practice", "description": "Strengthen weak areas.", "week": "4", "tasks": ["Solve harder tasks", "Review weak areas", "Create a portfolio piece"], "practice": "Do an independent challenge."},
        ]

    data["topics"] = out_topics

    projects = data.get("projects", [])
    if not isinstance(projects, list):
        projects = []
    out_projects = []
    for item in projects[:6]:
        if isinstance(item, str):
            out_projects.append({"name": clean(item), "difficulty": "Beginner", "description": "", "skills": []})
        elif isinstance(item, dict):
            name = clean(item.get("name") or item.get("title") or item.get("project"))
            if name:
                out_projects.append({
                    "name": name,
                    "difficulty": clean(item.get("difficulty")) or "Beginner",
                    "description": clean(item.get("description")),
                    "skills": list_clean(item.get("skills", []), 6),
                })
    data["projects"] = out_projects

    resources = data.get("resources", [])
    if not isinstance(resources, list):
        resources = []
    out_resources = []
    for item in resources[:10]:
        if isinstance(item, str):
            out_resources.append({"name": clean(item), "type": "Resource", "description": "", "url": ""})
        elif isinstance(item, dict):
            name = clean(item.get("name") or item.get("title") or item.get("resource"))
            if name:
                url = clean(item.get("url"))
                if url and not re.match(r"^https?://", url, re.I):
                    url = ""
                out_resources.append({
                    "name": name,
                    "type": clean(item.get("type")) or "Resource",
                    "description": clean(item.get("description")),
                    "url": url,
                })
    data["resources"] = out_resources

    weekly = data.get("weekly_plan", [])
    if not isinstance(weekly, list):
        weekly = []
    out_weekly = []
    for i, item in enumerate(weekly[:12], start=1):
        if isinstance(item, dict):
            out_weekly.append({
                "week": clean(item.get("week")) or str(i),
                "focus": clean(item.get("focus") or item.get("title")) or f"Week {i}",
                "tasks": list_clean(item.get("tasks", []), 6),
            })
        elif isinstance(item, str):
            out_weekly.append({"week": str(i), "focus": clean(item), "tasks": []})
    data["weekly_plan"] = out_weekly

    data["milestones"] = list_clean(data.get("milestones", []), 8)
    data["career_preparation"] = list_clean(data.get("career_preparation", []), 8)
    data["capstone"] = clean(data.get("capstone"))
    return data


def roadmap_prompt(domain, level, duration, goal, weekly_hours, knowledge):
    return f"""
Create a personalized learning roadmap.

Domain: {domain}
Skill level: {level}
Duration: {duration}
Main goal: {goal}
Weekly time: {weekly_hours}
Current knowledge: {knowledge}

Return JSON only using this exact structure:
{{
  "title": "...",
  "summary": "...",
  "level": "Level 1 / Level 2 / Level 3",
  "weeks": "...",
  "topics": [
    {{
      "name": "topic name",
      "description": "short description",
      "week": "1",
      "tasks": ["task 1", "task 2", "task 3"],
      "practice": "practical exercise"
    }}
  ],
  "projects": [
    {{"name":"...", "difficulty":"Beginner", "description":"...", "skills":["..."]}}
  ],
  "resources": [
    {{"name":"...", "type":"Course/YouTube/Guide/Documentation/Book", "description":"...", "url":"https://..."}}
  ],
  "weekly_plan": [
    {{"week":"1", "focus":"...", "tasks":["...","..."]}}
  ],
  "milestones": ["..."],
  "capstone": "...",
  "career_preparation": ["..."]
}}

Rules:
- Give 4–10 topics and 2–6 tasks per topic.
- Tasks must be small, actionable learning tasks.
- Make ALL topics directly relevant to {domain}.
- Never inject generic Python, Machine Learning, Deep Learning or Generative AI topics unless they are relevant to the selected domain.
- Give 3–6 realistic portfolio projects.
- Give 5–10 resources and include a useful official/course URL when you know it.
- Match the roadmap to the learner's goal and available weekly time.
"""

# ============================================================
# 5. USER AUTHENTICATION
# ============================================================
def register_user(name, email, password, goal):
    name, email, password = clean(name), clean(email).lower(), clean(password)
    if not name or not email or not password:
        return "⚠️ Please fill in name, email and password.", gr.update(), gr.update(), gr.update()
    if not valid_email(email):
        return "⚠️ Please enter a valid email address.", gr.update(), gr.update(), gr.update()
    if len(password) < 6:
        return "⚠️ Password must be at least 6 characters.", gr.update(), gr.update(), gr.update()

    conn = db()
    try:
        cur = conn.execute(
            "INSERT INTO users(name,email,password_hash,goal,created_at,last_login) VALUES(?,?,?,?,?,?)",
            (name, email, password_hash(password), goal, now(), now())
        )
        user_id = cur.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return "⚠️ An account with this email already exists. Please log in.", gr.update(), gr.update(), gr.update()
    conn.close()

    log_activity(user_id, "Created account", "Welcome to SkillPath AI")
    session = session_copy()
    session.update({"user_id": user_id, "user_name": name, "email": email})
    return (
        f"✅ Account created. Welcome, **{name}**!",
        session,
        gr.update(visible=False),
        gr.update(visible=True),
    )


def login_user(email, password):
    email, password = clean(email).lower(), clean(password)
    if not email or not password:
        s = session_copy()
        return "⚠️ Enter your email and password.", s, gr.update(visible=True), gr.update(visible=False), dashboard_html(s), topbar_html(s)

    conn = db()
    row = conn.execute(
        "SELECT id,name,email,goal,password_hash FROM users WHERE email=?",
        (email,)
    ).fetchone()
    if row and verify_password(password, row["password_hash"]):
        conn.execute("UPDATE users SET last_login=? WHERE id=?", (now(), row["id"]))
        conn.commit()
    else:
        row = None
    conn.close()

    if not row:
        s = session_copy()
        return "❌ Incorrect email or password.", s, gr.update(visible=True), gr.update(visible=False), dashboard_html(s), topbar_html(s)

    s = session_copy()
    s.update({"user_id": row["id"], "user_name": row["name"], "email": row["email"]})
    log_activity(row["id"], "Logged in", "")
    return (
        f"✅ Welcome back, **{row['name']}**!",
        s,
        gr.update(visible=False),
        gr.update(visible=True),
        dashboard_html(s),
        topbar_html(s)
    )


def logout_user():
    s = session_copy()
    return (
        s,
        gr.update(visible=True),
        gr.update(visible=False),
        "👋 You have been logged out.",
        dashboard_html(s),
        topbar_html(s)
    )


# ============================================================
# 6. ROADMAP DATABASE OPERATIONS
# ============================================================
def save_new_roadmap(user_id, data, domain, level, duration, goal, weekly_hours, knowledge):
    conn = db()
    cur = conn.execute("""
        INSERT INTO roadmaps(user_id,domain,skill_level,duration,goal,weekly_hours,knowledge,roadmap_json,created_at)
        VALUES(?,?,?,?,?,?,?,?,?)
    """, (
        user_id, domain, level, duration, goal, weekly_hours, knowledge,
        json.dumps(data, ensure_ascii=False), now()
    ))
    rid = cur.lastrowid
    for topic in data["topics"]:
        for task in topic["tasks"]:
            conn.execute("""
                INSERT OR REPLACE INTO task_progress(roadmap_id,topic,task,percent,updated_at)
                VALUES(?,?,?,?,?)
            """, (rid, topic["name"], task, 0, now()))
    conn.commit()
    conn.close()
    return rid


def load_roadmap(user_id, roadmap_id):
    if not user_id or not roadmap_id:
        return None
    conn = db()
    row = conn.execute(
        "SELECT * FROM roadmaps WHERE id=? AND user_id=?",
        (int(roadmap_id), user_id)
    ).fetchone()
    if not row:
        conn.close()
        return None
    data = json.loads(row["roadmap_json"])
    rows = conn.execute(
        "SELECT topic,task,percent FROM task_progress WHERE roadmap_id=?",
        (row["id"],)
    ).fetchall()
    conn.close()

    task_map = {(r["topic"], r["task"]): int(r["percent"]) for r in rows}
    return {"id": row["id"], "domain": row["domain"], "data": data, "task_map": task_map}


def roadmap_rows(user_id):
    if not user_id:
        return []
    conn = db()
    rows = conn.execute("""
        SELECT id,domain,skill_level,duration,goal,created_at
        FROM roadmaps WHERE user_id=? ORDER BY id DESC
    """, (user_id,)).fetchall()
    conn.close()
    return rows


def all_task_progress(user_id, roadmap_id):
    conn = db()
    rows = conn.execute("""
        SELECT tp.topic,tp.task,tp.percent
        FROM task_progress tp
        JOIN roadmaps r ON r.id=tp.roadmap_id
        WHERE tp.roadmap_id=? AND r.user_id=?
    """, (roadmap_id, user_id)).fetchall()
    conn.close()
    return {(r["topic"], r["task"]): int(r["percent"]) for r in rows}

# ============================================================
# 7. PROGRESS / ANALYTICS
# ============================================================
def topic_percent(session, topic):
    if not session.get("roadmap_id"):
        return 0
    data = session.get("data") or {}
    task_map = all_task_progress(session.get("user_id"), session.get("roadmap_id"))
    for t in data.get("topics", []):
        if t["name"] == topic:
            vals = [task_map.get((topic, task), 0) for task in t.get("tasks", [])]
            return round(sum(vals) / len(vals)) if vals else 0
    return 0


def all_topic_progress(session):
    data = session.get("data") or {}
    return {t["name"]: topic_percent(session, t["name"]) for t in data.get("topics", [])}


def overall_percent(session):
    values = list(all_topic_progress(session).values())
    return round(sum(values) / len(values)) if values else 0


def completed_tasks(session):
    if not session.get("roadmap_id"):
        return 0, 0
    task_map = all_task_progress(session.get("user_id"), session.get("roadmap_id"))
    total = len(task_map)
    done = sum(1 for x in task_map.values() if x >= 100)
    return done, total


def analytics(session):
    user_id = session.get("user_id")
    if not user_id:
        return {"roadmaps": 0, "done": 0, "total": 0, "progress": 0, "projects": 0, "resources": 0, "streak": 0}

    conn = db()
    roadmap_count = conn.execute("SELECT COUNT(*) c FROM roadmaps WHERE user_id=?", (user_id,)).fetchone()["c"]

    # Calculate all-time completed tasks across the user's roadmaps.
    done = conn.execute("""
        SELECT COUNT(*) c FROM task_progress tp
        JOIN roadmaps r ON r.id=tp.roadmap_id
        WHERE r.user_id=? AND tp.percent>=100
    """, (user_id,)).fetchone()["c"]
    total = conn.execute("""
        SELECT COUNT(*) c FROM task_progress tp
        JOIN roadmaps r ON r.id=tp.roadmap_id
        WHERE r.user_id=?
    """, (user_id,)).fetchone()["c"]

    project_count = 0
    resource_count = 0
    rows = conn.execute("SELECT roadmap_json FROM roadmaps WHERE user_id=?", (user_id,)).fetchall()
    for row in rows:
        try:
            d = json.loads(row["roadmap_json"])
            project_count += len(d.get("projects", []))
            resource_count += len(d.get("resources", []))
        except Exception:
            pass

    # Simple activity streak: count consecutive dates with activity, including today if present.
    activity_dates = conn.execute("""
        SELECT DISTINCT substr(created_at,1,10) d FROM activities
        WHERE user_id=? ORDER BY d DESC
    """, (user_id,)).fetchall()
    dates = {r["d"] for r in activity_dates}
    streak = 0
    cursor = datetime.now().date()
    while cursor.isoformat() in dates:
        streak += 1
        cursor -= timedelta(days=1)

    conn.close()
    progress = round(done / total * 100) if total else 0
    return {"roadmaps": roadmap_count, "done": done, "total": total, "progress": progress, "projects": project_count, "resources": resource_count, "streak": streak}

# ============================================================
# 8. HTML UI
# ============================================================
def e(x):
    return escape(clean(x))


def bar(p, cls=""):
    p = max(0, min(100, int(p)))
    return f'<div class="bar-bg {cls}"><div class="bar-fill" style="width:{p}%"></div></div>'


def nav_btn_style():
    return "nav-btn"


def topbar_html(session):
    if not session.get("user_id"):
        name = "SkillPath User"
        level = "Beginner"
        initials = "SA"
    else:
        name = session.get("user_name", "SkillPath User")
        level = "Learner"
        initials = "".join([part[0] for part in name.split()[:2]]).upper() or "SA"
    return f"""<div class=\"topbar\"><div class=\"search\">🔍 &nbsp; Search skills, topics, or resources...</div><div class=\"user\">🔔<div class=\"avatar\">{e(initials)}</div><div><b>{e(name)}</b><br><small>{e(level)}</small></div>▾</div></div>"""


def dashboard_html(session):
    if not session.get("user_id"):
        return "<div></div>"
    data = session.get("data")
    stats = analytics(session)
    name = session.get("user_name", "SkillPath User")

    if not data:
        return f"""
        <div class="page-pad">
          <div class="hero">
            <div><div class="hello">👋 Hello, {e(name)}! 👋</div>
            <div class="hero-sub">Your personalized learning journey starts here. Let's build your future with AI.</div>
            <div class="badges"><span class="badge learn">◉ Learn</span><span class="badge build">◉ Build</span><span class="badge grow">◉ Grow</span></div></div>
            <div class="hero-art"><div class="mountain">▲</div><div class="cloud c1">☁</div><div class="cloud c2">☁</div><div class="quote">“Better Skills<br>Better Opportunities<br>A Brighter Future”</div></div>
          </div>
          <div class="stats-grid">
            <div class="stat-card blue-card"><div class="icon-circle blue">A</div><div class="stat-label">Total Roadmaps</div><div class="stat-value">{stats['roadmaps']}</div><div class="stat-note">Created by AI</div></div>
            <div class="stat-card green-card"><div class="icon-circle green">✓</div><div class="stat-label">Completed Tasks</div><div class="stat-value">{stats['done']}</div><div class="stat-note">Start your journey</div></div>
            <div class="stat-card purple-card"><div class="icon-circle purple">▣</div><div class="stat-label">Learning Progress</div><div class="stat-value">{stats['progress']}%</div>{bar(stats['progress'])}</div>
            <div class="stat-card orange-card"><div class="icon-circle orange">🏆</div><div class="stat-label">Learning Streak</div><div class="stat-value">{stats['streak']} days</div><div class="stat-note">Keep going!</div></div>
          </div>
          <div class="dashboard-empty"><div class="empty-icon">🎓</div><h2>Create your first roadmap</h2><p>Use <b>Generate Roadmap</b> to turn your learning goal into a personalized plan.</p><div class="mini-tip">💡 You can choose English, Python, AI Automation, Web Development, Data Science or any other skill.</div></div>
          <div class="footer">SkillPath AI • Learn • Build • Grow • Powered by Groq &amp; Gradio</div>
        </div>
        """

    topic_prog = all_topic_progress(session)
    overall = overall_percent(session)
    done, total = completed_tasks(session)
    projects = data.get("projects", [])
    resources = data.get("resources", [])
    current_level = data.get("level", "Level 1")

    tracker = ""
    for topic, p in topic_prog.items():
        tracker += f'<div class="tracker-item"><div class="tracker-head"><span>{e(topic)}</span><b>{p}%</b></div>{bar(p)}</div>'

    resource_cards = ""
    for i, r in enumerate(resources[:4]):
        url = clean(r.get("url"))
        link = f'<a href="{e(url)}" target="_blank" rel="noopener" class="resource-link">Open resource ↗</a>' if url else '<span class="resource-no-link">Link not provided</span>'
        resource_cards += f"""
        <div class="resource-mini">
          <div class="resource-icon">📚</div><span class="resource-type">{e(r.get('type','Resource'))}</span>
          <b>{e(r.get('name'))}</b><small>{e(r.get('description',''))[:70]}</small>{link}
        </div>"""

    activity = activity_html(session.get("user_id"))
    next_topic = next((t["name"] for t in data.get("topics", []) if topic_prog.get(t["name"], 0) < 100), "Start an advanced project")

    return f"""
    <div class="page-pad">
      <div class="hero">
        <div><div class="hello">👋 Hello, {e(name)}! 👋</div>
        <div class="hero-sub">Your personalized learning journey starts here. Let's build your future with AI.</div>
        <div class="badges"><span class="badge learn">◉ Learn</span><span class="badge build">◉ Build</span><span class="badge grow">◉ Grow</span></div></div>
        <div class="hero-art"><div class="mountain">▲</div><div class="cloud c1">☁</div><div class="cloud c2">☁</div><div class="quote">“Better Skills<br>Better Opportunities<br>A Brighter Future”</div></div>
      </div>

      <div class="stats-grid">
        <div class="stat-card blue-card"><div class="icon-circle blue">A</div><div class="stat-label">Total Roadmaps</div><div class="stat-value">{stats['roadmaps']}</div><div class="stat-note">Created by AI</div></div>
        <div class="stat-card green-card"><div class="icon-circle green">✓</div><div class="stat-label">Completed Tasks</div><div class="stat-value">{done}</div><div class="stat-note">Out of {total}</div></div>
        <div class="stat-card purple-card"><div class="icon-circle purple">▣</div><div class="stat-label">Learning Progress</div><div class="stat-value">{overall}%</div>{bar(overall)}</div>
        <div class="stat-card orange-card"><div class="icon-circle orange">🏆</div><div class="stat-label">Current Level</div><div class="stat-value">{e(current_level)}</div><div class="stat-note">🔥 {stats['streak']} day streak</div></div>
      </div>

      <div class="two-col">
        <div class="panel"><div class="panel-title"><span>📖 Current Roadmap</span><span class="view">{len(data.get('topics',[]))} topics</span></div>
          <div class="roadmap-main"><div class="roadmap-icon">🎯</div><div class="roadmap-content"><h3>{e(data.get('title'))}</h3><p>{e(data.get('summary'))}</p><b>{e(current_level)} • {overall}% complete</b>{bar(overall)}<div class="roadmap-meta"><span>📅 {e(data.get('weeks'))}</span><span>🧩 {len(projects)} Projects</span><span>📚 {len(resources)} Resources</span></div></div></div>
        </div>
        <div class="panel"><div class="panel-title"><span>📊 Progress Tracker</span><span class="view">Task based</span></div>{tracker}</div>
      </div>

      <div class="panel quick-panel"><div class="panel-title"><span>⚡ Quick Actions</span></div><div class="quick-grid">
        <div class="quick-card q-blue"><b>✨</b><span>Generate New<br>Roadmap</span></div>
        <div class="quick-card q-green"><b>⌘</b><span>View Projects</span></div>
        <div class="quick-card q-purple"><b>📖</b><span>Browse Resources</span></div>
        <div class="quick-card q-orange"><b>🗓</b><span>Plan Weekly</span></div>
        <div class="quick-card q-teal"><b>📊</b><span>Track Progress</span></div>
      </div></div>

      <div class="two-col lower">
        <div class="panel"><div class="panel-title"><span>📚 Latest Resources</span><span class="view">Clickable</span></div><div class="resource-mini-grid">{resource_cards or '<div class="empty">No resources yet.</div>'}</div></div>
        <div class="panel"><div class="panel-title"><span>💡 Suggested Next Step</span></div><div class="next-step"><div class="next-icon">📅</div><div><b>Complete {e(next_topic)}</b><p>Finish the current task to move closer to your next milestone.</p></div></div><div class="continue-btn">▶ Continue Learning</div></div>
      </div>

      <div class="panel activity"><div class="panel-title"><span>🕘 Recent Activity</span><span class="view">Live</span></div>{activity}</div>
      <div class="footer">SkillPath AI • Learn • Build • Grow • Powered by Groq &amp; Gradio</div>
    </div>
    """


def activity_html(user_id):
    if not user_id:
        return '<div class="empty">No activity yet.</div>'
    conn = db()
    rows = conn.execute("""
        SELECT activity,details,created_at FROM activities
        WHERE user_id=? ORDER BY id DESC LIMIT 6
    """, (user_id,)).fetchall()
    conn.close()
    if not rows:
        return '<div class="empty">No activity yet.</div>'
    out = '<div class="activity-list">'
    for r in rows:
        stamp = clean(r["created_at"]).replace("T", " ")
        out += f'<div>• <b>{e(r["activity"])}</b> <span>{e(r["details"])}</span><small>{e(stamp)}</small></div>'
    return out + '</div>'


def roadmap_html(session):
    data = session.get("data")
    if not data:
        return '<div class="panel"><h2>🗺️ Roadmap</h2><p>Generate a roadmap first.</p></div>'
    cards = ''
    topic_prog = all_topic_progress(session)
    for i, t in enumerate(data.get("topics", []), 1):
        tasks = ''.join(f'<li>{e(x)}</li>' for x in t.get("tasks", []))
        p = topic_prog.get(t["name"], 0)
        cards += f'''<div class="detail-card"><div class="number">{i}</div><div style="flex:1"><h3>{e(t['name'])}</h3><span class="week">Week {e(t.get('week'))} • {p}% complete</span>{bar(p)}<p>{e(t.get('description'))}</p><ul>{tasks}</ul><small><b>Practice:</b> {e(t.get('practice'))}</small></div></div>'''
    milestones = ''.join(f'<li>{e(x)}</li>' for x in data.get("milestones", [])) or '<li>Keep progressing through the roadmap.</li>'
    career = ''.join(f'<li>{e(x)}</li>' for x in data.get("career_preparation", [])) or '<li>Build projects and document your work.</li>'
    return f'''<div class="panel"><div class="panel-title"><span>🗺️ {e(data.get('title'))}</span><span class="view">{overall_percent(session)}% overall</span></div><p class="muted">{e(data.get('summary'))}</p><div class="detail-list">{cards}</div><h3>🏁 Milestones</h3><ul>{milestones}</ul><h3>🚀 Capstone</h3><p>{e(data.get('capstone'))}</p><h3>💼 Career Preparation</h3><ul>{career}</ul></div>'''


def projects_html(session):
    data = session.get("data")
    if not data:
        return '<div class="panel"><h2>🧩 Projects</h2><p>Generate a roadmap first.</p></div>'
    cards = ''
    for p in data.get("projects", []):
        cards += f'''<div class="project-card"><div class="project-top"><span class="project-icon">🛠</span><span class="difficulty">{e(p.get('difficulty'))}</span></div><h3>{e(p.get('name'))}</h3><p>{e(p.get('description'))}</p><small><b>Skills:</b> {e(', '.join(p.get('skills', [])))}</small></div>'''
    return f'<div class="panel"><div class="panel-title"><span>🧩 Project Lab</span></div><div class="cards-grid">{cards or "<div class=empty>No projects yet.</div>"}</div></div>'


def resources_html(session):
    data = session.get("data")
    if not data:
        return '<div class="panel"><h2>📚 Resources</h2><p>Generate a roadmap first.</p></div>'
    rows = ''
    for r in data.get("resources", []):
        url = clean(r.get("url"))
        button = f'<a href="{e(url)}" target="_blank" rel="noopener" class="resource-button">Open Resource ↗</a>' if url else '<span class="resource-no-link">No URL returned by AI</span>'
        rows += f'''<div class="resource-row"><div class="resource-big">📚</div><div style="flex:1"><h3>{e(r.get('name'))}</h3><span class="resource-type">{e(r.get('type'))}</span><p>{e(r.get('description'))}</p>{button}</div></div>'''
    return f'<div class="panel"><div class="panel-title"><span>📚 Learning Resources</span><span class="view">Open in new tab</span></div>{rows or "<div class=empty>No resources yet.</div>"}</div>'


def weekly_html(session):
    data = session.get("data")
    if not data:
        return '<div class="panel"><h2>🗓 Weekly Plan</h2><p>Generate a roadmap first.</p></div>'
    rows = ''
    for w in data.get("weekly_plan", []):
        tasks = ''.join(f'<li>{e(x)}</li>' for x in w.get("tasks", []))
        rows += f'''<div class="week-card"><div class="week-number">W{e(w.get('week'))}</div><div><h3>{e(w.get('focus'))}</h3><ul>{tasks}</ul></div></div>'''
    return f'<div class="panel"><div class="panel-title"><span>🗓 Weekly Learning Plan</span></div>{rows or "<div class=empty>No weekly plan yet.</div>"}</div>'


def history_html(session):
    rows = roadmap_rows(session.get("user_id"))
    if not rows:
        return '<div class="panel"><h2>🗂 My Roadmaps</h2><p>No saved roadmaps yet.</p></div>'
    items = ''
    for r in rows:
        items += f'''<div class="history-card"><b>#{r['id']} — {e(r['domain'])}</b><span>{e(r['skill_level'])} • {e(r['duration'])} • {e(r['goal'])}</span><small>{e(r['created_at'])}</small></div>'''
    return f'<div class="panel"><div class="panel-title"><span>🗂 My Roadmaps</span></div>{items}</div>'


def progress_html(session):
    data = session.get("data")
    if not data:
        return '<div class="panel"><h2>📊 Progress Tracker</h2><p>Generate or load a roadmap first.</p></div>'
    topics = ''
    for t in data.get("topics", []):
        p = topic_percent(session, t["name"])
        topics += f'<div class="tracker-big"><div class="tracker-head"><b>{e(t["name"])}</b><span>{p}%</span></div>{bar(p)}<small>{len(t.get("tasks", []))} tasks • average of task progress</small></div>'
    return f'<div class="panel"><div class="panel-title"><span>📊 Personalized Progress</span><b>{overall_percent(session)}% overall</b></div><p class="muted">Progress is calculated from the individual tasks in your current roadmap.</p>{topics}</div>'


def analytics_html(session):
    a = analytics(session)
    return f'''
    <div class="analytics-grid">
      <div class="analytics-card"><span>🗺️</span><b>{a['roadmaps']}</b><small>Roadmaps</small></div>
      <div class="analytics-card"><span>✅</span><b>{a['done']}</b><small>Completed Tasks</small></div>
      <div class="analytics-card"><span>📈</span><b>{a['progress']}%</b><small>Overall Progress</small></div>
      <div class="analytics-card"><span>🔥</span><b>{a['streak']}</b><small>Day Streak</small></div>
      <div class="analytics-card"><span>🧩</span><b>{a['projects']}</b><small>Projects</small></div>
      <div class="analytics-card"><span>📚</span><b>{a['resources']}</b><small>Resources</small></div>
    </div>
    <div class="panel"><h3>📊 What your numbers mean</h3><p class="muted">Your overall progress is based on completed task percentages. Project and resource totals come from all roadmaps in your account.</p></div>
    '''

# ============================================================
# 9. ROADMAP GENERATION CALLBACK
# ============================================================
def generate_roadmap(session, domain, level, duration, goal, weekly_hours, knowledge):
    if not session.get("user_id"):
        return session, "⚠️ Please log in first.", dashboard_html(session), roadmap_html(session), projects_html(session), resources_html(session), weekly_html(session), progress_html(session), analytics_html(session), gr.update(choices=[], value=None), gr.update(choices=[], value=None)

    domain = clean(domain)
    if not domain:
        return session, "⚠️ Please enter a learning domain.", dashboard_html(session), roadmap_html(session), projects_html(session), resources_html(session), weekly_html(session), progress_html(session), analytics_html(session), gr.update(choices=[], value=None), gr.update(choices=[], value=None)

    try:
        raw = groq_text(
            "You are SkillPath AI, a professional learning-roadmap planner. Return valid JSON only. Do not use markdown fences.",
            roadmap_prompt(domain, level, duration, goal, weekly_hours, knowledge),
            temperature=0.35,
            max_tokens=7000
        )
        data = normalize_roadmap(extract_json(raw), domain, duration)
        rid = save_new_roadmap(session["user_id"], data, domain, level, duration, goal, weekly_hours, knowledge)
        new_session = dict(session)
        new_session.update({"roadmap_id": rid, "data": data, "domain": domain})
        log_activity(session["user_id"], "Generated roadmap", data.get("title", domain))

        topics = [t["name"] for t in data.get("topics", [])]
        task_choices = data.get("topics", [])[0].get("tasks", []) if data.get("topics") else []
        return (
            new_session,
            f"✅ Roadmap **#{rid}** created for **{domain}**.",
            dashboard_html(new_session), roadmap_html(new_session), projects_html(new_session), resources_html(new_session), weekly_html(new_session), progress_html(new_session), analytics_html(new_session),
            gr.Dropdown(choices=topics, value=topics[0] if topics else None),
            gr.Dropdown(choices=task_choices, value=task_choices[0] if task_choices else None)
        )
    except Exception as ex:
        return session, f"❌ Roadmap generation failed: {e(ex)}", dashboard_html(session), roadmap_html(session), projects_html(session), resources_html(session), weekly_html(session), progress_html(session), analytics_html(session), gr.update(), gr.update()


def load_roadmap_callback(session, roadmap_id):
    if not session.get("user_id"):
        return session, "⚠️ Please log in first.", dashboard_html(session), roadmap_html(session), projects_html(session), resources_html(session), weekly_html(session), progress_html(session), analytics_html(session), gr.update(choices=[]), gr.update(choices=[])
    item = load_roadmap(session["user_id"], roadmap_id)
    if not item:
        return session, "❌ Roadmap not found in your account.", dashboard_html(session), roadmap_html(session), projects_html(session), resources_html(session), weekly_html(session), progress_html(session), analytics_html(session), gr.update(choices=[]), gr.update(choices=[])
    new_session = dict(session)
    new_session.update({"roadmap_id": item["id"], "data": item["data"], "domain": item["domain"]})
    topics = [t["name"] for t in item["data"].get("topics", [])]
    tasks = item["data"].get("topics", [])[0].get("tasks", []) if item["data"].get("topics") else []
    log_activity(session["user_id"], "Loaded roadmap", f"#{item['id']}")
    return new_session, f"✅ Loaded roadmap **#{item['id']}**.", dashboard_html(new_session), roadmap_html(new_session), projects_html(new_session), resources_html(new_session), weekly_html(new_session), progress_html(new_session), analytics_html(new_session), gr.Dropdown(choices=topics, value=topics[0] if topics else None), gr.Dropdown(choices=tasks, value=tasks[0] if tasks else None)

# ============================================================
# 10. TASK-LEVEL PROGRESS CALLBACKS
# ============================================================
def tasks_for_topic(session, topic):
    if not session.get("data"):
        return []
    for t in session["data"].get("topics", []):
        if t["name"] == topic:
            return t.get("tasks", [])
    return []


def task_value(session, topic, task):
    if not session.get("roadmap_id") or not topic or not task:
        return 0
    m = all_task_progress(session.get("user_id"), session.get("roadmap_id"))
    return m.get((topic, task), 0)


def topic_changed(session, topic):
    tasks = tasks_for_topic(session, topic)
    return gr.Dropdown(choices=tasks, value=tasks[0] if tasks else None), task_value(session, topic, tasks[0] if tasks else None)


def task_changed(session, topic, task):
    return task_value(session, topic, task)


def update_task_progress(session, topic, task, percent):
    if not session.get("user_id") or not session.get("roadmap_id"):
        return session, "⚠️ Generate or load a roadmap first.", progress_html(session), dashboard_html(session), analytics_html(session)
    if not topic or not task:
        return session, "⚠️ Select a topic and task.", progress_html(session), dashboard_html(session), analytics_html(session)
    percent = max(0, min(100, int(percent)))

    conn = db()
    conn.execute("""
        INSERT OR REPLACE INTO task_progress(roadmap_id,topic,task,percent,updated_at)
        VALUES(?,?,?,?,?)
    """, (session["roadmap_id"], topic, task, percent, now()))
    conn.commit()
    conn.close()
    log_activity(session["user_id"], "Updated task progress", f"{topic} → {percent}%")
    return session, f"✅ **{task}** is now **{percent}%** complete.", progress_html(session), dashboard_html(session), analytics_html(session)

# ============================================================
# 11. AI LEARNING COACH
# ============================================================
def coach_reply(session, message, history):
    if not session.get("user_id"):
        return history or [], "⚠️ Please log in first."
    message = clean(message)
    if not message:
        return history or [], ""
    data = session.get("data") or {}
    if not data:
        answer = "Please generate a roadmap first. Then I can act as your personal SkillPath AI coach."
        history = history or []
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": answer})
        return history, ""

    topic_prog = all_topic_progress(session)
    context = {
        "title": data.get("title"),
        "domain": session.get("domain", ""),
        "topics": [
            {"name": t["name"], "progress": topic_prog.get(t["name"], 0), "tasks": t.get("tasks", [])}
            for t in data.get("topics", [])
        ],
        "projects": [p.get("name") for p in data.get("projects", [])],
        "goal": data.get("career_preparation", []),
    }
    system = """You are SkillPath AI Learning Coach. Give concise, practical, encouraging advice. Use the user's current roadmap and progress. Recommend the next best action, explain why, and when useful give a small practice task. Never invent progress that is not provided."""
    prompt = f"Roadmap context:\n{json.dumps(context, ensure_ascii=False)}\n\nUser question:\n{message}"
    try:
        answer = groq_text(system, prompt, temperature=0.55, max_tokens=1400)
    except Exception as ex:
        answer = f"I could not reach the AI coach right now: {ex}"
    history = history or []
    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": answer})
    log_activity(session["user_id"], "Used AI Learning Coach", message[:80])
    return history, ""

# ============================================================
# 12. PDF
# ============================================================
def create_pdf(session):
    if not session.get("user_id") or not session.get("data"):
        return None, "⚠️ Generate or load a roadmap first."
    data = session["data"]
    progress = all_topic_progress(session)
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", data.get("title", "Roadmap"))[:60]
    pdf_path = PDF_DIR / f"{safe_name}_{session['roadmap_id']}.pdf"

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CenterTitle2", parent=styles["Title"], alignment=TA_CENTER, fontSize=22, spaceAfter=15))
    doc = SimpleDocTemplate(str(pdf_path), pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    story = [Paragraph("SkillPath AI", styles["CenterTitle2"]), Paragraph(e(data.get("title")), styles["Heading1"]), Paragraph(e(data.get("summary")), styles["BodyText"]), Spacer(1, 12)]

    story.append(Paragraph("Learning Topics & Progress", styles["Heading2"]))
    rows = [["Topic", "Week", "Progress"]]
    for t in data.get("topics", []):
        rows.append([e(t.get("name")), e(t.get("week")), f"{progress.get(t['name'],0)}%"])
    table = Table(rows, colWidths=[280, 80, 80])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#2563eb")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#dbeafe")),
        ("PADDING", (0,0), (-1,-1), 7),
    ]))
    story += [table, Spacer(1, 15), Paragraph("Projects", styles["Heading2"])]
    for p in data.get("projects", []):
        story += [Paragraph(f"<b>{e(p.get('name'))}</b> — {e(p.get('difficulty'))}", styles["BodyText"]), Paragraph(e(p.get("description")), styles["BodyText"]), Spacer(1, 6)]

    story.append(Paragraph("Resources", styles["Heading2"]))
    for r in data.get("resources", []):
        story.append(Paragraph(f"<b>{e(r.get('name'))}</b> ({e(r.get('type'))}) — {e(r.get('url'))}", styles["BodyText"]))

    story += [PageBreak(), Paragraph("Weekly Plan", styles["Heading1"])]
    for w in data.get("weekly_plan", []):
        story.append(Paragraph(f"<b>Week {e(w.get('week'))}: {e(w.get('focus'))}</b>", styles["BodyText"]))
        for task in w.get("tasks", []):
            story.append(Paragraph(f"• {e(task)}", styles["BodyText"]))
        story.append(Spacer(1, 8))

    story.append(Paragraph("Milestones", styles["Heading2"]))
    for m in data.get("milestones", []):
        story.append(Paragraph(f"• {e(m)}", styles["BodyText"]))
    story.append(Paragraph("Capstone", styles["Heading2"]))
    story.append(Paragraph(e(data.get("capstone")), styles["BodyText"]))
    story.append(Paragraph("Career Preparation", styles["Heading2"]))
    for c in data.get("career_preparation", []):
        story.append(Paragraph(f"• {e(c)}", styles["BodyText"]))

    doc.build(story)
    log_activity(session["user_id"], "Downloaded PDF roadmap", data.get("title", ""))
    return str(pdf_path), "✅ PDF generated successfully."

# ============================================================
# 3. SESSION STATE
# ============================================================
DEFAULT_SESSION = {
    "user_id": None,
    "user_name": "SkillPath User",
    "email": "",
    "roadmap_id": None,
    "data": None,
}


def session_copy():
    return dict(DEFAULT_SESSION)


def now():
    return datetime.now().isoformat(timespec="seconds")


def clean(value):
    return str(value or "").strip()


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 120000).hex()
    return f"{salt}${digest}"


def verify_password(password, stored):
    try:
        salt, expected = stored.split("$", 1)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 120000).hex()
        return secrets.compare_digest(actual, expected)
    except Exception:
        return False


def valid_email(email):
    return bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", clean(email)))


def log_activity(user_id, activity, details=""):
    if not user_id:
        return
    conn = db()
    conn.execute(
        "INSERT INTO activities(user_id, activity, details, created_at) VALUES(?,?,?,?)",
        (user_id, activity, details, now())
    )
    conn.commit()
    conn.close()

# ============================================================
# 4. AI HELPERS
# ============================================================
def groq_text(system_prompt, user_prompt, temperature=0.4, max_tokens=6500):
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""


def extract_json(text):
    text = clean(text)
    text = re.sub(r"^```(?:json)?", "", text, flags=re.I).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
    raise ValueError("AI returned invalid JSON. Please try again.")


def list_clean(value, limit=8):
    if not isinstance(value, list):
        value = [value] if value else []
    return [clean(x) for x in value if clean(x)][:limit]


def normalize_roadmap(data, domain, duration):
    if not isinstance(data, dict):
        data = {}

    data["title"] = clean(data.get("title")) or f"{domain.title()} Learning Roadmap"
    data["summary"] = clean(data.get("summary")) or f"A personalized roadmap for {domain}."
    data["level"] = clean(data.get("level")) or "Level 1"
    data["weeks"] = clean(data.get("weeks")) or duration

    topics = data.get("topics", [])
    if not isinstance(topics, list):
        topics = []
    out_topics = []

    for i, item in enumerate(topics[:10], start=1):
        if isinstance(item, str):
            name = clean(item)
            item = {}
        elif isinstance(item, dict):
            name = clean(item.get("name") or item.get("topic") or item.get("title"))
        else:
            continue
        if not name:
            continue
        tasks_raw = item.get("tasks", []) if isinstance(item, dict) else []
        tasks = list_clean(tasks_raw, 5)
        if not tasks:
            tasks = [
                f"Study the fundamentals of {name}",
                f"Complete a practical exercise on {name}",
                f"Review your mistakes and summarize {name}",
            ]
        out_topics.append({
            "name": name,
            "description": clean(item.get("description", "")) if isinstance(item, dict) else "",
            "week": clean(item.get("week", i)) if isinstance(item, dict) else str(i),
            "tasks": tasks,
            "practice": clean(item.get("practice", "")) if isinstance(item, dict) else "",
        })

    if not out_topics:
        out_topics = [
            {"name": f"{domain.title()} Foundations", "description": "Build core concepts.", "week": "1", "tasks": ["Learn the fundamentals", "Take notes", "Complete a small exercise"], "practice": "30–45 minutes of practice."},
            {"name": f"{domain.title()} Core Skills", "description": "Build practical ability.", "week": "2", "tasks": ["Study core techniques", "Practice examples", "Review mistakes"], "practice": "Complete guided exercises."},
            {"name": f"{domain.title()} Project Work", "description": "Apply skills in a realistic project.", "week": "3", "tasks": ["Choose a project", "Build the first version", "Improve the result"], "practice": "Work on a mini project."},
            {"name": f"{domain.title()} Advanced Practice", "description": "Strengthen weak areas.", "week": "4", "tasks": ["Solve harder tasks", "Review weak areas", "Create a portfolio piece"], "practice": "Do an independent challenge."},
        ]

    data["topics"] = out_topics

    projects = data.get("projects", [])
    if not isinstance(projects, list):
        projects = []
    out_projects = []
    for item in projects[:6]:
        if isinstance(item, str):
            out_projects.append({"name": clean(item), "difficulty": "Beginner", "description": "", "skills": []})
        elif isinstance(item, dict):
            name = clean(item.get("name") or item.get("title") or item.get("project"))
            if name:
                out_projects.append({
                    "name": name,
                    "difficulty": clean(item.get("difficulty")) or "Beginner",
                    "description": clean(item.get("description")),
                    "skills": list_clean(item.get("skills", []), 6),
                })
    data["projects"] = out_projects

    resources = data.get("resources", [])
    if not isinstance(resources, list):
        resources = []
    out_resources = []
    for item in resources[:10]:
        if isinstance(item, str):
            out_resources.append({"name": clean(item), "type": "Resource", "description": "", "url": ""})
        elif isinstance(item, dict):
            name = clean(item.get("name") or item.get("title") or item.get("resource"))
            if name:
                url = clean(item.get("url"))
                if url and not re.match(r"^https?://", url, re.I):
                    url = ""
                out_resources.append({
                    "name": name,
                    "type": clean(item.get("type")) or "Resource",
                    "description": clean(item.get("description")),
                    "url": url,
                })
    data["resources"] = out_resources

    weekly = data.get("weekly_plan", [])
    if not isinstance(weekly, list):
        weekly = []
    out_weekly = []
    for i, item in enumerate(weekly[:12], start=1):
        if isinstance(item, dict):
            out_weekly.append({
                "week": clean(item.get("week")) or str(i),
                "focus": clean(item.get("focus") or item.get("title")) or f"Week {i}",
                "tasks": list_clean(item.get("tasks", []), 6),
            })
        elif isinstance(item, str):
            out_weekly.append({"week": str(i), "focus": clean(item), "tasks": []})
    data["weekly_plan"] = out_weekly

    data["milestones"] = list_clean(data.get("milestones", []), 8)
    data["career_preparation"] = list_clean(data.get("career_preparation", []), 8)
    data["capstone"] = clean(data.get("capstone"))
    return data


def roadmap_prompt(domain, level, duration, goal, weekly_hours, knowledge):
    return f"""
Create a personalized learning roadmap.

Domain: {domain}
Skill level: {level}
Duration: {duration}
Main goal: {goal}
Weekly time: {weekly_hours}
Current knowledge: {knowledge}

Return JSON only using this exact structure:
{{
  "title": "...",
  "summary": "...",
  "level": "Level 1 / Level 2 / Level 3",
  "weeks": "...",
  "topics": [
    {{
      "name": "topic name",
      "description": "short description",
      "week": "1",
      "tasks": ["task 1", "task 2", "task 3"],
      "practice": "practical exercise"
    }}
  ],
  "projects": [
    {{"name":"...", "difficulty":"Beginner", "description":"...", "skills":["..."]}}
  ],
  "resources": [
    {{"name":"...", "type":"Course/YouTube/Guide/Documentation/Book", "description":"...", "url":"https://..."}}
  ],
  "weekly_plan": [
    {{"week":"1", "focus":"...", "tasks":["...","..."]}}
  ],
  "milestones": ["..."],
  "capstone": "...",
  "career_preparation": ["..."]
}}

Rules:
- Give 4–10 topics and 2–6 tasks per topic.
- Tasks must be small, actionable learning tasks.
- Make ALL topics directly relevant to {domain}.
- Never inject generic Python, Machine Learning, Deep Learning or Generative AI topics unless they are relevant to the selected domain.
- Give 3–6 realistic portfolio projects.
- Give 5–10 resources and include a useful official/course URL when you know it.
- Match the roadmap to the learner's goal and available weekly time.
"""

# ============================================================
# 13. PHASE 5 — ADAPTIVE LEARNING + USER GROWTH
# ============================================================
def get_profile(user_id):
    if not user_id:
        return {"bio":"", "target_role":"", "experience":"Beginner", "preferred_style":"Hands-on", "daily_minutes":60}
    conn=db(); row=conn.execute("SELECT bio,target_role,experience,preferred_style,daily_minutes FROM profiles WHERE user_id=?",(user_id,)).fetchone(); conn.close()
    return dict(row) if row else {"bio":"", "target_role":"", "experience":"Beginner", "preferred_style":"Hands-on", "daily_minutes":60}

def save_profile(session, bio, target_role, experience, preferred_style, daily_minutes):
    if not session.get("user_id"): return session,"⚠️ Please log in first.",topbar_html(session)
    try: minutes=max(15,min(600,int(daily_minutes)))
    except: minutes=60
    conn=db(); conn.execute("""INSERT INTO profiles(user_id,bio,target_role,experience,preferred_style,daily_minutes,updated_at) VALUES(?,?,?,?,?,?,?)
    ON CONFLICT(user_id) DO UPDATE SET bio=excluded.bio,target_role=excluded.target_role,experience=excluded.experience,preferred_style=excluded.preferred_style,daily_minutes=excluded.daily_minutes,updated_at=excluded.updated_at""",(session["user_id"],clean(bio),clean(target_role),experience,preferred_style,minutes,now())); conn.commit(); conn.close()
    log_activity(session["user_id"],"Updated profile",clean(target_role)); return session,"✅ Profile saved successfully.",topbar_html(session)

def assessment_prompt(domain):
    return "Create exactly 8 beginner-friendly skill assessment questions for " + domain + ". Return JSON only with questions, each containing question, options (exactly 4 strings beginning A/B/C/D), answer (A/B/C/D), explanation. No trick questions."

def generate_assessment(session, domain):
    if not session.get("user_id"): return "⚠️ Please log in first.",[],""
    domain=clean(domain) or "your selected domain"
    try:
        data=extract_json(groq_text("You create accurate educational assessments.",assessment_prompt(domain),0.2,3000)); qs=data.get("questions",[])[:8]
        if len(qs)<5: raise ValueError("The AI returned too few questions.")
        out=[f"### 🧠 {domain} Skill Assessment","Answer format: **1A, 2B, 3C...**",""]
        for i,q in enumerate(qs,1):
            out.append(f"**{i}. {clean(q.get('question'))}**")
            for opt in q.get("options",[])[:4]: out.append(f"- {clean(opt)}")
            out.append("")
        return "\n".join(out),qs,""
    except Exception as ex: return "❌ Assessment generation failed: " + clean(str(ex)),[],""

def evaluate_assessment(session, domain, questions, answers):
    if not session.get("user_id"): return "⚠️ Please log in first.",""
    if not questions: return "⚠️ Generate the assessment first.",""
    amap={int(n):a for n,a in re.findall(r'(\d{1,2})([ABCD])',clean(answers).upper().replace(" ",""))}
    score=0; wrong=[]
    for i,q in enumerate(questions,1):
        correct=str(q.get("answer","A")).strip().upper()[:1]
        if amap.get(i)==correct: score+=1
        else: wrong.append(f"Q{i}: {correct}")
    total=len(questions); pct=round(score*100/total) if total else 0
    conn=db(); conn.execute("INSERT INTO assessments(user_id,domain,score,total,answers,created_at) VALUES(?,?,?,?,?,?)",(session["user_id"],domain,score,total,json.dumps(amap),now())); conn.commit(); conn.close()
    log_activity(session["user_id"],"Completed skill assessment",f"{domain}: {score}/{total}")
    level="Strong foundation" if pct>=75 else "Developing foundation" if pct>=50 else "Beginner foundation"
    review="" if not wrong else "\n\n**Review:** " + ", ".join(wrong[:6])
    return f"### 🎯 Result\n**Score: {score}/{total} ({pct}%)**\n\n**Level signal:** {level}{review}",""

def adaptive_replan(session, focus):
    if not session.get("user_id") or not session.get("data"):
        return session,"⚠️ Generate or load a roadmap first.",dashboard_html(session),roadmap_html(session),projects_html(session),resources_html(session),weekly_html(session),progress_html(session),analytics_html(session),gr.update(choices=[]),gr.update(choices=[])
    data=session["data"]; progress=all_topic_progress(session); profile=get_profile(session["user_id"]); weak=sorted(progress.items(),key=lambda x:x[1])[:5]
    prompt="Adapt this learning roadmap. Current progress: " + json.dumps(progress) + ". Weakest topics: " + json.dumps(weak) + ". Profile: " + json.dumps(profile) + ". Extra focus: " + clean(focus) + ". Existing roadmap: " + json.dumps(data,ensure_ascii=False) + ". Return JSON only in the exact roadmap structure. Strengthen weak areas, preserve useful completed context, add practical tasks/projects, and keep resources relevant."
    try:
        newdata=normalize_roadmap(extract_json(groq_text("You are an adaptive learning architect. Return valid JSON only.",prompt,0.3,7000)),data.get("title","Adaptive Roadmap"),data.get("weeks","12 Weeks"))
        rid=save_new_roadmap(session["user_id"],newdata,data.get("title","Learning"),data.get("level","Adaptive"),data.get("weeks","12 Weeks"),data.get("goal","Job"),profile.get("daily_minutes",60),profile.get("bio",""))
        session["roadmap_id"]=rid; session["data"]=newdata; log_activity(session["user_id"],"Created adaptive roadmap",f"Roadmap #{rid}")
        topics=[t.get("name") for t in newdata.get("topics",[])]
        return session,"✅ Adaptive roadmap created and activated.",dashboard_html(session),roadmap_html(session),projects_html(session),resources_html(session),weekly_html(session),progress_html(session),analytics_html(session),gr.update(choices=topics,value=topics[0] if topics else None),gr.update(choices=[])
    except Exception as ex: return session,"❌ Adaptive roadmap failed: "+clean(str(ex)),dashboard_html(session),roadmap_html(session),projects_html(session),resources_html(session),weekly_html(session),progress_html(session),analytics_html(session),gr.update(),gr.update()

def daily_plan(session, plan_date, focus):
    if not session.get("user_id") or not session.get("data"): return "⚠️ Generate or load a roadmap first."
    date=clean(plan_date) or datetime.now().strftime("%Y-%m-%d"); data=session["data"]; progress=all_topic_progress(session); profile=get_profile(session["user_id"])
    prompt="Create a realistic daily learning plan for " + date + ". Roadmap: " + json.dumps(data,ensure_ascii=False) + ". Progress: " + json.dumps(progress) + ". Daily minutes: " + str(profile.get("daily_minutes",60)) + ". Style: " + str(profile.get("preferred_style","Hands-on")) + ". Focus: " + clean(focus) + ". Return JSON only: title, estimated_minutes, tasks (2-5 objects with task, minutes, output), reflection."
    try:
        plan=extract_json(groq_text("You are a practical study planner.",prompt,0.3,2200)); conn=db(); conn.execute("INSERT INTO daily_plans(user_id,roadmap_id,plan_date,plan_json,created_at) VALUES(?,?,?,?,?) ON CONFLICT(user_id,plan_date) DO UPDATE SET roadmap_id=excluded.roadmap_id,plan_json=excluded.plan_json,created_at=excluded.created_at",(session["user_id"],session.get("roadmap_id"),date,json.dumps(plan,ensure_ascii=False),now())); conn.commit(); conn.close()
        log_activity(session["user_id"],"Generated daily learning plan",date)
        html=f'<div class="panel"><h3 style="color:#18345e">📅 {e(plan.get("title","Daily Learning Plan"))}</h3><p class="muted">{e(date)} • {e(plan.get("estimated_minutes",60))} minutes</p><div class="detail-list">'
        for i,t in enumerate(plan.get("tasks",[]),1): html+=f'<div class="detail-card"><div class="number">{i}</div><div><h3>{e(t.get("task"))}</h3><p>{e(t.get("minutes",0))} min • Expected output: {e(t.get("output"))}</p></div></div>'
        html+=f'<div class="mini-tip"><b>Reflection:</b> {e(plan.get("reflection","What did you learn today?"))}</div></div></div>'; return html
    except Exception as ex: return "❌ Daily plan failed: "+clean(str(ex))

def goals_html(session):
    if not session.get("user_id"): return "<div class='empty'>Log in to manage goals.</div>"
    conn=db(); rows=conn.execute("SELECT id,title,target_date,status FROM goals WHERE user_id=? ORDER BY status,target_date",(session["user_id"],)).fetchall(); conn.close()
    if not rows: return "<div class='empty'>No goals yet. Add your first learning goal.</div>"
    html='<div class="detail-list">'
    for r in rows:
        overdue=r["status"]=="Active" and r["target_date"]<datetime.now().strftime("%Y-%m-%d")
        html+=f'<div class="detail-card"><div class="number">{"✓" if r["status"]=="Completed" else "🎯"}</div><div><h3>{e(r["title"])}</h3><p>Goal ID: {r["id"]} • Target: {e(r["target_date"])} • Status: {e(r["status"])} {"• Overdue" if overdue else ""}</p></div></div>'
    return html+'</div>'

def add_goal(session,title,target_date):
    if not session.get("user_id"): return "⚠️ Please log in first.",goals_html(session)
    title=clean(title); target_date=clean(target_date)
    if not title: return "⚠️ Enter a goal.",goals_html(session)
    try: datetime.strptime(target_date,"%Y-%m-%d")
    except: return "⚠️ Date must be YYYY-MM-DD.",goals_html(session)
    conn=db(); conn.execute("INSERT INTO goals(user_id,title,target_date,status,created_at) VALUES(?,?,?,?,?)",(session["user_id"],title,target_date,"Active",now())); conn.commit(); conn.close(); log_activity(session["user_id"],"Added learning goal",title); return "✅ Goal added.",goals_html(session)

def complete_goal(session,goal_id):
    if not session.get("user_id"): return "⚠️ Please log in first.",goals_html(session)
    try: gid=int(goal_id)
    except: return "⚠️ Enter a valid Goal ID.",goals_html(session)
    conn=db(); conn.execute("UPDATE goals SET status='Completed' WHERE id=? AND user_id=?",(gid,session["user_id"])); conn.commit(); conn.close(); return "✅ Goal updated.",goals_html(session)

def achievements_html(session):
    if not session.get("user_id"): return "<div class='empty'>Log in to see achievements.</div>"
    conn=db(); roads=conn.execute("SELECT COUNT(*) c FROM roadmaps WHERE user_id=?",(session["user_id"],)).fetchone()["c"]; done=conn.execute("SELECT COUNT(*) c FROM task_progress tp JOIN roadmaps r ON r.id=tp.roadmap_id WHERE r.user_id=? AND tp.percent>=100",(session["user_id"],)).fetchone()["c"]; assessments=conn.execute("SELECT COUNT(*) c FROM assessments WHERE user_id=?",(session["user_id"],)).fetchone()["c"]; conn.close()
    badges=[]
    if roads: badges.append(("🗺️","Roadmap Starter","Created your first roadmap"))
    if done>=1: badges.append(("✅","First Win","Completed your first task"))
    if done>=10: badges.append(("🔥","Momentum Builder","Completed 10+ tasks"))
    if assessments: badges.append(("🧠","Self-Aware Learner","Completed a skill assessment"))
    if not badges: badges=[("🌱","Getting Started","Create a roadmap and complete your first task")]
    return '<div class="cards-grid">'+''.join(f'<div class="project-card"><div class="project-icon">{a}</div><h3>{e(b)}</h3><p>{e(c)}</p></div>' for a,b,c in badges)+'</div>'


# ============================================================
# STREAMLIT UI — SkillPath AI Phase 5
# ============================================================
st.set_page_config(page_title=APP_TITLE, page_icon="🚀", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.block-container {padding-top: 1.2rem; max-width: 1400px;}
[data-testid="stSidebar"] {background: #0b1f3a;}
[data-testid="stSidebar"] * {color: white !important;}
.hero {padding: 28px; border-radius: 18px; background: linear-gradient(135deg,#eef5ff,#f5f0ff); margin-bottom: 18px;}
.hero h1 {color:#18345e; margin-bottom:6px;}
.card {background:white; border:1px solid #e5eaf2; border-radius:16px; padding:20px; margin:8px 0; box-shadow:0 4px 14px rgba(0,0,0,.04);}
.metric {background:white; border:1px solid #e5eaf2; border-radius:16px; padding:18px;}
.small {color:#667085; font-size:14px;}
</style>
""", unsafe_allow_html=True)

if "session" not in st.session_state:
    st.session_state.session = session_copy()
if "assessment_questions" not in st.session_state:
    st.session_state.assessment_questions = []
if "coach_history" not in st.session_state:
    st.session_state.coach_history = []

def s(): return st.session_state.session

def set_session(v): st.session_state.session = dict(v)

def stream_register(name,email,password,goal):
    name, email, password = clean(name), clean(email).lower(), clean(password)
    if not name or not email or not password: return False, "Please fill all fields."
    if not valid_email(email): return False, "Please enter a valid email."
    if len(password) < 6: return False, "Password must be at least 6 characters."
    conn=db()
    try:
        cur=conn.execute("INSERT INTO users(name,email,password_hash,goal,created_at,last_login) VALUES(?,?,?,?,?,?)",(name,email,password_hash(password),goal,now(),now()))
        uid=cur.lastrowid; conn.commit()
    except sqlite3.IntegrityError:
        conn.close(); return False,"An account with this email already exists."
    conn.close(); log_activity(uid,"Created account","Welcome to SkillPath AI")
    ss=session_copy(); ss.update({"user_id":uid,"user_name":name,"email":email}); set_session(ss)
    return True,f"Welcome, {name}!"

def stream_login(email,password):
    email,password=clean(email).lower(),clean(password)
    conn=db(); row=conn.execute("SELECT id,name,email,goal,password_hash FROM users WHERE email=?",(email,)).fetchone()
    if row and verify_password(password,row["password_hash"]):
        conn.execute("UPDATE users SET last_login=? WHERE id=?",(now(),row["id"])); conn.commit(); conn.close()
        ss=session_copy(); ss.update({"user_id":row["id"],"user_name":row["name"],"email":row["email"]}); set_session(ss); log_activity(row["id"],"Logged in",""); return True,f"Welcome back, {row['name']}!"
    conn.close(); return False,"Incorrect email or password."

def stream_generate(domain,level,duration,goal,weekly_hours,knowledge):
    ss=s()
    if not ss.get("user_id"): return "Please log in first."
    domain=clean(domain)
    if not domain: return "Enter a learning domain."
    try:
        raw=groq_text("You are SkillPath AI, a professional learning-roadmap planner. Return valid JSON only. Do not use markdown fences.",roadmap_prompt(domain,level,duration,goal,weekly_hours,knowledge),0.35,7000)
        data=normalize_roadmap(extract_json(raw),domain,duration)
        rid=save_new_roadmap(ss["user_id"],data,domain,level,duration,goal,weekly_hours,knowledge)
        ss=dict(ss); ss.update({"roadmap_id":rid,"data":data,"domain":domain}); set_session(ss)
        log_activity(ss["user_id"],"Generated roadmap",data.get("title",domain))
        return f"✅ Roadmap #{rid} created for {domain}."
    except Exception as ex: return f"❌ Roadmap generation failed: {ex}"

def stream_load(rid):
    ss=s()
    try: rid=int(rid)
    except: return "Invalid roadmap ID."
    item=load_roadmap(ss["user_id"],rid)
    if not item: return "Roadmap not found."
    ss=dict(ss); ss.update({"roadmap_id":item["id"],"data":item["data"],"domain":item["domain"]}); set_session(ss); return f"✅ Loaded roadmap #{rid}."

def stream_update_progress(topic,task,pct):
    ss=s()
    if not ss.get("user_id") or not ss.get("roadmap_id"): return "Generate or load a roadmap first."
    if not topic or not task: return "Select topic and task."
    pct=max(0,min(100,int(pct)))
    conn=db(); conn.execute("INSERT OR REPLACE INTO task_progress(roadmap_id,topic,task,percent,updated_at) VALUES(?,?,?,?,?)",(ss["roadmap_id"],topic,task,pct,now())); conn.commit(); conn.close(); log_activity(ss["user_id"],"Updated task progress",f"{topic} → {pct}%"); return f"✅ {task}: {pct}%"

def stream_adaptive(focus):
    ss=s(); data=ss.get("data")
    if not ss.get("user_id") or not data: return "Generate or load a roadmap first."
    progress=all_topic_progress(ss); profile=get_profile(ss["user_id"]); weak=sorted(progress.items(),key=lambda x:x[1])[:5]
    prompt="Adapt this learning roadmap. Current progress: " + json.dumps(progress) + ". Weakest topics: " + json.dumps(weak) + ". Profile: " + json.dumps(profile) + ". Extra focus: " + clean(focus) + ". Existing roadmap: " + json.dumps(data,ensure_ascii=False) + ". Return JSON only in the exact roadmap structure. Strengthen weak areas, preserve useful completed context, add practical tasks/projects, and keep resources relevant."
    try:
        newdata=normalize_roadmap(extract_json(groq_text("You are an adaptive learning architect. Return valid JSON only.",prompt,0.3,7000)),data.get("title","Adaptive Roadmap"),data.get("weeks","12 Weeks"))
        rid=save_new_roadmap(ss["user_id"],newdata,data.get("title","Learning"),data.get("level","Adaptive"),data.get("weeks","12 Weeks"),data.get("goal","Job"),profile.get("daily_minutes",60),profile.get("bio",""))
        ss=dict(ss); ss.update({"roadmap_id":rid,"data":newdata}); set_session(ss); log_activity(ss["user_id"],"Created adaptive roadmap",f"Roadmap #{rid}"); return f"✅ Adaptive roadmap #{rid} created and activated."
    except Exception as ex: return f"❌ Adaptive roadmap failed: {ex}"

def show_html(x): st.markdown(x,unsafe_allow_html=True)

def roadmap_text(data):
    if not data: return "No roadmap yet."
    out=[]
    for i,t in enumerate(data.get("topics",[]),1):
        out.append(f"### {i}. {t.get('name','Topic')}\n{t.get('description','')}\n\n**Tasks:**\n"+"\n".join(f"- {x}" for x in t.get("tasks",[])))
    return "\n\n".join(out)

# ---------- Sidebar ----------
with st.sidebar:
    st.markdown("# 🚀 SkillPath AI")
    st.caption("Turn your goals into a personalized learning journey.")
    if s().get("user_id"):
        st.success(f"Hi, {s()['user_name']}")
    page=st.radio("Navigation",["Dashboard","Generate Roadmap","My Roadmaps","Projects","Resources","Weekly Plan","Progress","AI Coach","Analytics","Growth Hub","PDF Export"],index=0)
    if s().get("user_id") and st.button("Logout",use_container_width=True):
        set_session(session_copy()); st.session_state.coach_history=[]; st.rerun()

st.markdown(f'<div class="hero"><h1>SkillPath AI</h1><div>Turn your goals into a personalized learning journey.</div></div>',unsafe_allow_html=True)

# ---------- Authentication gate ----------
if not s().get("user_id"):
    st.info("Create an account or log in to use your personal AI roadmap.")
    c1,c2=st.columns(2)
    with c1:
        st.subheader("🔐 Login")
        le=st.text_input("Email",key="le"); lp=st.text_input("Password",type="password",key="lp")
        if st.button("Login",type="primary",use_container_width=True):
            ok,msg=stream_login(le,lp); (st.success if ok else st.error)(msg); st.rerun() if ok else None
    with c2:
        st.subheader("✨ Create account")
        rn=st.text_input("Name",key="rn"); reml=st.text_input("Email",key="reml"); rp=st.text_input("Password",type="password",key="rp"); rg=st.selectbox("Main goal",["Job","University","Freelancing","Career Switch","Personal Learning"],key="rg")
        if st.button("Create account",use_container_width=True):
            ok,msg=stream_register(rn,reml,rp,rg); (st.success if ok else st.error)(msg); st.rerun() if ok else None
    st.stop()

# ---------- Dashboard ----------
if page=="Dashboard":
    data=s().get("data")
    st.subheader(f"Welcome back, {s()['user_name']} 👋")
    a=analytics(s()); cols=st.columns(4)
    metrics=[
    ("Roadmaps", a.get("roadmaps", 0)),
    ("Completed Tasks", a.get("completed_tasks", 0)),
    ("Overall Progress", f"{a.get('overall', 0)}%"),
    ("Projects", a.get("projects", 0))
    ]
    for col,(label,val) in zip(cols,metrics): col.markdown(f'<div class="metric"><div class="small">{label}</div><h2>{val}</h2></div>',unsafe_allow_html=True)
    st.markdown("### 📚 Current Roadmap")
    show_html(roadmap_html(s()) if data else '<div class="card">No roadmap yet. Open <b>Generate Roadmap</b> to start.</div>')
    st.markdown("### 🏆 Achievements")
    show_html(achievements_html(s()))

elif page=="Generate Roadmap":
    st.subheader("🗺️ Generate a personalized roadmap")
    c1,c2=st.columns(2)
    with c1:
        domain=st.text_input("Learning domain",placeholder="e.g. Generative AI")
        level=st.selectbox("Skill level",["Beginner","Intermediate","Advanced"])
        duration=st.selectbox("Duration",["4 Weeks","8 Weeks","12 Weeks","16 Weeks","6 Months"])
    with c2:
        goal=st.selectbox("Learning goal",["Job","University","Freelancing","Career Switch","Personal Learning"])
        weekly=st.slider("Hours per week",1,40,8)
        knowledge=st.text_area("Current knowledge",placeholder="Tell the AI what you already know")
    if st.button("🚀 Generate Roadmap",type="primary"):
        st.info(stream_generate(domain,level,duration,goal,weekly,knowledge)); st.rerun()
    if s().get("data"): show_html(roadmap_html(s()))

elif page=="My Roadmaps":
    st.subheader("📁 My Roadmaps")
    rows=roadmap_rows(s()["user_id"])
    if not rows: st.info("No roadmaps yet.")
    else:
        for r in rows:
            st.markdown(f"**#{r['id']} — {r['domain']}** • {r['skill_level']} • {r['created_at']}")
        rid=st.number_input("Roadmap ID to load",min_value=1,step=1,value=int(rows[0]['id']))
        if st.button("Load roadmap",type="primary"): st.info(stream_load(rid)); st.rerun()

elif page=="Projects":
    st.subheader("🛠️ Projects")
    show_html(projects_html(s()))

elif page=="Resources":
    st.subheader("🔗 Learning Resources")
    show_html(resources_html(s()))

elif page=="Weekly Plan":
    st.subheader("📅 Weekly Plan")
    show_html(weekly_html(s()))

elif page=="Progress":
    st.subheader("📈 Task Progress")
    if not s().get("data"): st.info("Generate or load a roadmap first.")
    else:
        topics=[t["name"] for t in s()["data"].get("topics",[])]
        topic=st.selectbox("Topic",topics)
        tasks=tasks_for_topic(s(),topic)
        task=st.selectbox("Task",tasks) if tasks else ""
        current=task_value(s(),topic,task)
        pct=st.slider("Completion",0,100,int(current),5)
        if st.button("Save progress",type="primary"): st.success(stream_update_progress(topic,task,pct)); st.rerun()
        show_html(progress_html(s()))

elif page=="AI Coach":
    st.subheader("🤖 AI Learning Coach")
    if not s().get("data"): st.info("Generate a roadmap first.")
    for m in st.session_state.coach_history:
        with st.chat_message(m["role"]): st.markdown(m["content"])
    prompt=st.chat_input("Ask your coach something...")
    if prompt:
        history=st.session_state.coach_history
        history, _=coach_reply(s(),prompt,history)
        st.session_state.coach_history=history; st.rerun()

elif page=="Analytics":
    st.subheader("📊 Analytics")
    a=analytics(s()); cols=st.columns(5)
    vals=[
    ("Roadmaps", a["roadmaps"]),
    ("Completed", a["done"]),
    ("Progress", f"{a['progress']}%"),
    ("Streak", a["streak"]),
    ("Projects", a["projects"])
]
    for col,(x,y) in zip(cols,vals): col.metric(x,y)
    show_html(analytics_html(s()))

elif page=="Growth Hub":
    st.subheader("🚀 Growth Hub")
    tabs=st.tabs(["Profile","Skill Assessment","Adaptive Roadmap","Daily Plan","Goals","Achievements"])
    with tabs[0]:
        p=get_profile(s()["user_id"]); bio=st.text_area("About your learning journey",p.get("bio","")); role=st.text_input("Target role",p.get("target_role","")); exp=st.selectbox("Experience",["Beginner","Intermediate","Advanced"],index=["Beginner","Intermediate","Advanced"].index(p.get("experience","Beginner"))); style=st.selectbox("Preferred style",["Hands-on","Reading first","Video first","Balanced"],index=["Hands-on","Reading first","Video first","Balanced"].index(p.get("preferred_style","Hands-on"))); mins=st.number_input("Daily minutes",15,600,int(p.get("daily_minutes",60)),15)
        if st.button("Save Profile",type="primary"): save_profile(s(),bio,role,exp,style,mins); st.success("Profile saved."); st.rerun()
    with tabs[1]:
        adomain=st.text_input("Assessment domain",value=s().get("domain", "Python"))
        if st.button("Generate Assessment",type="primary"):
            qmd,qs,_=generate_assessment(s(),adomain); st.session_state.assessment_questions=qs; st.markdown(qmd); st.session_state.assessment_md=qmd
        if st.session_state.assessment_questions:
            st.markdown(st.session_state.get("assessment_md","")); ans=st.text_input("Your answers",placeholder="1A, 2C, 3B, 4D...")
            if st.button("Check My Score"): result,_=evaluate_assessment(s(),adomain,st.session_state.assessment_questions,ans); st.success(result)
    with tabs[2]:
        focus=st.text_area("Extra focus",placeholder="more projects, interview prep, weak topics")
        if st.button("Create Adaptive Roadmap",type="primary"): st.info(stream_adaptive(focus)); st.rerun()
    with tabs[3]:
        pd=st.date_input("Plan date",datetime.now().date()); pf=st.text_input("Optional focus")
        if st.button("Generate Daily Plan",type="primary"): st.markdown(daily_plan(s(),pd.strftime("%Y-%m-%d"),pf),unsafe_allow_html=True)
    with tabs[4]:
        gt=st.text_input("Goal title"); gd=st.date_input("Target date")
        if st.button("Add Goal"): msg,_=add_goal(s(),gt,gd.strftime("%Y-%m-%d")); st.success(msg); st.rerun()
        show_html(goals_html(s())); gid=st.number_input("Goal ID to complete",min_value=1,step=1,value=1)
        if st.button("Mark completed"): msg,_=complete_goal(s(),gid); st.success(msg); st.rerun()
    with tabs[5]: show_html(achievements_html(s()))

elif page=="PDF Export":
    st.subheader("📄 Export Roadmap PDF")
    if st.button("Generate PDF",type="primary"):
        try:
            path=create_pdf(s()); st.success("PDF created successfully.");
            with open(path,"rb") as f: st.download_button("Download PDF",f,file_name=Path(path).name,mime="application/pdf")
        except Exception as ex: st.error(str(ex))

st.caption("SkillPath AI • AI Learning Roadmap Generator")
