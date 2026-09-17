🚀 SkillPath AI
AI-Powered Learning Roadmap Generator

SkillPath AI is an intelligent learning companion that creates personalized,
AI-generated learning roadmaps, tracks your progress, and adapts to your 
goals — helping you learn any skill in a structured, guided way.

✨ Features

🔐 User login / register system

🧠 AI-personalized learning roadmaps

📁 Projects, resources, and weekly learning plans

✅ Task-level progress tracking

🤖 AI Learning Coach

📊 Analytics dashboard

👤 User profile management

🎯 AI-based skill assessment

🔄 Adaptive roadmap generation

📅 Daily learning plans

🏆 Learning goals and achievements

📄 PDF export of roadmaps

🛠️ Tech Stack

Frontend/Backend: Streamlit

Language: Python 3.10+

AI Engine: GROQ API

Database: SQLite (demo) / Supabase or PostgreSQL (production)

⚙️ Run Locally

Clone the repository
bash
   git clone <your-repo-url>
   cd skillpath-ai
Install dependencies
bash
   pip install -r requirements.txt
Set your GROQ API key as an environment variable
bash
   export GROQ_API_KEY="your_api_key_here"     # macOS/Linux
   set GROQ_API_KEY="your_api_key_here"        # Windows
Run the app
bash
   streamlit run app.py
☁️ Deployment (Streamlit Cloud)
Push your project to GitHub
Deploy the repo on Streamlit Cloud
Go to App Settings → Secrets and add:
   GROQ_API_KEY = "your_api_key_here"
Never commit your API key to the repository
📌 Notes
SQLite is used for demo/testing purposes only.
For production use with persistent multi-user data, migrate the database to Supabase or PostgreSQL.
🔮 Future Improvements
Multi-language support
Gamification (badges, streaks, leaderboards)
Mobile-friendly UI
Team/collaborative roadmaps
📄 License

This project is open-source and available under the MIT License.

🙋‍♀️ Author

Hijab Zara Bachelor of Artificial Intelligence Student
