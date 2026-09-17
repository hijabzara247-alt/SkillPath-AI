# 🚀 SkillPath AI

### **AI-Powered Learning Roadmap Generator**

**SkillPath AI** is an intelligent learning companion that creates **personalized, AI-generated learning roadmaps**, tracks learning progress, and adapts to individual goals — helping users learn any skill in a **structured and guided way**.

---

## ✨ Features

* 🔐 **User Login & Registration System**
* 🧠 **AI-Personalized Learning Roadmaps**
* 📁 **Projects & Learning Resources**
* 📅 **Weekly & Daily Learning Plans**
* ✅ **Task-Level Progress Tracking**
* 🤖 **AI Learning Coach**
* 📊 **Analytics Dashboard**
* 👤 **User Profile Management**
* 🎯 **AI-Based Skill Assessment**
* 🔄 **Adaptive Roadmap Generation**
* 🏆 **Learning Goals & Achievements**
* 📄 **PDF Roadmap Export**

---

## 🛠️ Tech Stack

| Technology                | Purpose                          |
| ------------------------- | -------------------------------- |
| **Python 3.10+**          | Programming Language             |
| **Streamlit**             | Frontend & Application Framework |
| **GROQ API**              | AI / LLM Engine                  |
| **SQLite**                | Demo / Local Database            |
| **Supabase / PostgreSQL** | Production Database              |

---

## ⚙️ Run Locally

### **1. Clone the Repository**

```bash
git clone https://github.com/your-username/skillpath-ai.git
cd skillpath-ai
```

### **2. Install Dependencies**

```bash
pip install -r requirements.txt
```

### **3. Set Your GROQ API Key**

Create a `.env` file and add:

```env
GROQ_API_KEY=your_groq_api_key
```

**Never commit your API key to GitHub.**

### **4. Run the Application**

```bash
streamlit run app.py
```

---

## ☁️ Deployment — Streamlit Cloud

To deploy **SkillPath AI**:

1. Push the project to **GitHub**.
2. Open **Streamlit Cloud**.
3. Connect your GitHub repository.
4. Select `app.py` as the main application file.
5. Deploy the application.
6. Go to **App Settings → Secrets**.
7. Add your GROQ API key:

```toml
GROQ_API_KEY = "your_groq_api_key"
```

> 🔒 **Important:** Never commit your API key or `.env` file to the repository.

---

## 📌 Notes

* **SQLite** is currently used for demo and testing purposes.
* For a production application with **persistent multi-user data**, SQLite can be migrated to **Supabase or PostgreSQL**.
* The AI features require a valid **GROQ API key**.

---

## 🔮 Future Improvements

* 🌍 **Multi-Language Support**
* 🎮 **Gamification**

  * Badges
  * Streaks
  * Leaderboards
* 📱 **Mobile-Friendly UI**
* 👥 **Team & Collaborative Roadmaps**
* 🔔 **Learning Reminders & Notifications**
* 📈 **Advanced Learning Analytics**

---

## 📄 License

This project is open-source and available under the **MIT License**.

---

## 🙋‍♀️ Author

**Hijab Zara**

🎓 **Bachelor of Artificial Intelligence Student**

> Building AI-powered applications and exploring AI automation, intelligent systems, and modern web technologies.
