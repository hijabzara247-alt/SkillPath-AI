🚀 SkillPath AI

AI-Powered Learning Roadmap Generator

SkillPath AI is an intelligent learning companion that creates personalized, AI-generated learning roadmaps, tracks learning progress, and adapts to individual goals — helping users learn any skill in a structured and guided way.

✨ Features

🔐 User Login & Registration System

🧠 AI-Personalized Learning Roadmaps

📁 Projects & Learning Resources

📅 Weekly & Daily Learning Plans

✅ Task-Level Progress Tracking

🤖 AI Learning Coach

📊 Analytics Dashboard

👤 User Profile Management

🎯 AI-Based Skill Assessment

🔄 Adaptive Roadmap Generation

🏆 Learning Goals & Achievements

📄 PDF Roadmap Export
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
