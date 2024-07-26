FROM python:latest
EXPOSE 8000

WORKDIR /justyse/
COPY . /justyse/

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

CMD ["fastapi", "dev", "main.py", "--port=8000", "--host=0.0.0.0"]