.PHONY: setup migrate run worker test
setup:
	python -m venv .venv
	.venv/bin/pip install -r requirements.txt
migrate:
	python manage.py makemigrations knowledge
	python manage.py migrate
run:
	python manage.py runserver
worker:
	python manage.py process_jobs
test:
	python manage.py test
