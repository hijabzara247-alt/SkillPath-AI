# SkillPath AI

AI Learning Roadmap Generator .

## Features
- User login/register
- AI personalized roadmaps
- Projects, resources and weekly plans
- Task-level progress tracking
- AI Learning Coach
- Analytics
- User profile
- AI skill assessment
- Adaptive roadmap
- Daily learning plans
- Learning goals and achievements
- PDF export

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

Set `GROQ_API_KEY` as an environment variable before running.

## Streamlit Cloud
Add `GROQ_API_KEY` under **App Settings → Secrets**. Never commit your API key.

> Note: SQLite is suitable for demo/testing. For production persistent multi-user data, migrate the database to Supabase/PostgreSQL.
