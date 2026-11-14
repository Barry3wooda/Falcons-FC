# Falcons FC ⚽

A full-stack football ticketing system built with Django. Fans can browse matches, book seats, and get personalised match recommendations. Ticket prices adapt to demand using a machine learning model. It was developed as a final university project at the University of Messina.

## Features

- **Ticket booking** with online payments through Stripe
- **ML dynamic pricing:** a Random Forest Regressor trained on Kaggle data predicts a demand score that adjusts ticket prices, with a fallback if the model is unavailable
- **Recommendation engine:** collaborative filtering built from scratch in NumPy (interaction matrix and cosine similarity). It blends 70% of a user's own history with 30% of similar users, and handles three cold-start cases
- **Smart group seat allocator:** finds contiguous seats for a group with a sliding window and block scoring. When no block is large enough, it splits the group evenly (for example 8+8 rather than 15+1) with a minimum subgroup size of 2
- **Waitlist** for sold-out sections
- **Background tasks** for scheduled and asynchronous jobs through Celery

## Architecture

| Component | Role |
|---|---|
| Django | Web application and business logic |
| PostgreSQL | Main database |
| Redis | Cache and message broker |
| Celery Worker | Runs asynchronous tasks |
| Celery Beat | Runs scheduled tasks |
| Stripe | Payment processing |

## Tech Stack

Python, Django, PostgreSQL, Redis, Celery, Stripe, NumPy, scikit-learn [confirm], Docker [confirm if used]

## Getting Started

```bash
# 1. Clone the repository
git clone https://github.com/Barry3wooda/[repo-name].git
cd [repo-name]

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables (database, Redis, Stripe keys)
cp .env.example .env            # [confirm file name]

# 5. Apply migrations and seed demo data
python manage.py migrate
python manage.py [seed-command]

# 6. Start the services
python manage.py runserver
celery -A [project_name] worker -l info
celery -A [project_name] beat -l info
```

## Demo Data

The seeder creates six user profiles to show how the recommendation engine behaves: `vip_derby`, `tribune_league`, `vip_cup`, `curve_derby`, `mixed`, and `new` (a cold-start user). They all use the password `test1234`.

## Project Documentation

The project follows Scrum: a 12-item product backlog, 7 sprints, user stories with acceptance criteria, and 17 UML diagrams. [Link to the report or diagrams, if you add them to the repo]

## Screenshots

[Add screenshots of the match list, seat selection, and recommendations]

## Author

Abdalbarry · [GitHub](https://github.com/Barry3wooda)
