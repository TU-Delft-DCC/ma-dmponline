DMP to AVG registry and TOPdesk

- after cloning, in Django root (same as manage.py)
- create .env file with necessary authentication information (tokens, email) (copy .env_example)
- `python3 -m venv venv`
- `.venv/bin/activate`
- `pip install -r requirements.txt`
- `python manage.py migrate`
- `python manage.py runserver 0.0.0.0:8000`
- Running the script for cron: `python manage.py fetch -b [first page] -e [last_page]` where pages refer to API pages of DMPonline
- Testing is done with pytest: `pytest`
- If caching problems occur: `pytest -o cache_dir=/tmp`
- Test coverage is calculated with: `coverage run -m pytest && coverage html`
- Docker image can be build with: `docker-compose up`