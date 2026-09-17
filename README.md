# 🚀 SkillPath AI

### **AI-Powered Learning Roadmap Generator**

**SkillPath AI** is a Streamlit web app that generates **personalized, AI-driven learning roadmaps** using the GROQ API and helps users **track their progress toward their learning goals**.

---

## ✨ Features

* 🔐 **User Login & Register** — Secure authentication with salted password hashing (PBKDF2)
* 🧠 **AI-Generated Learning Roadmaps** — Personalized based on domain, skill level, duration, goal, weekly hours, and current knowledge
* 📁 **My Roadmaps** — Save and reload multiple previously generated roadmaps
* 🛠️ **Projects** — AI-suggested portfolio projects tied to the roadmap
* 🔗 **Resources** — AI-curated learning resources, including courses, documentation, guides, and links
* 📅 **Weekly Plan** — Week-by-week breakdown of the roadmap
* ✅ **Task-Level Progress Tracking** — Mark completion percentage for each task
* 🤖 **AI Learning Coach** — Chat-based assistant for asking questions about the roadmap
* 📊 **Analytics Dashboard** — Roadmap count, completed tasks, overall progress percentage, streak, and project count
* 👤 **User Profile** — Manage bio, target role, experience level, preferred learning style, and daily study minutes
* 🎯 **AI Skill Assessment** — AI-generated quiz for a selected domain with scoring
* 🔄 **Adaptive Roadmap** — Regenerates and strengthens the roadmap based on current progress and weak topics
* 📆 **Daily Learning Plan** — AI-generated learning plan for a specific date
* 🏆 **Learning Goals & Achievements** — Set goals with target dates, mark goals as completed, and earn badges
* 📄 **PDF Export** — Download the current roadmap as a PDF using ReportLab

---

## 🛠️ Tech Stack

| Technology              | Purpose                   |
| ----------------------- | ------------------------- |
| **Streamlit**           | Web Application Framework |
| **Python**              | Programming Language      |
| **GROQ API**            | AI Engine                 |
| **openai/gpt-oss-120b** | AI Model                  |
| **SQLite**              | Database                  |
| **ReportLab**           | PDF Generation            |

---

## ⚙️ Run Locally

### **1. Install Dependencies**

```bash
pip install -r requirements.txt
```

### **2. Set Your GROQ API Key**

Set your GROQ API key as an environment variable.

**macOS / Linux:**

```bash
export GROQ_API_KEY="your_api_key_here"
```

**Windows:**

```bash
set GROQ_API_KEY="your_api_key_here"
```

### **3. Run the Application**

```bash
streamlit run app.py
```

---

## ☁️ Deployment — Streamlit Cloud

To deploy **SkillPath AI** on Streamlit Cloud:

1. Push your project to **GitHub**.
2. Deploy the repository on **Streamlit Cloud**.
3. Open **App Settings → Secrets**.
4. Add your GROQ API key:

```toml
GROQ_API_KEY = "your_api_key_here"
```

5. Deploy the application.

> 🔒 **Important:** Never commit your API key to the GitHub repository.

---

## 📌 Notes

* **SQLite** is used for local storage and is suitable for demo/testing purposes.
* For production use with **persistent multi-user data**, migrate the database to **Supabase or PostgreSQL**.

---

## 🔮 Future Improvements

* 🌍 **Multi-language support**
* 🎮 **Gamification**

  * Badges
  * Streaks
  * Leaderboards
* 📱 **Mobile-friendly UI**
* 👥 **Team & collaborative roadmaps**

---

## 📄 License

This project is open-source and available under the **MIT License**.

---

## 🙋‍♀️ Author

**Hijab Zara**

🎓 **Bachelor of Artificial Intelligence Student**

