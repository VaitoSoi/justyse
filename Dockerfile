FROM python:latest
EXPOSE 8000

VOLUME /justyse
WORKDIR /justyse
COPY requirements.txt /justyse/requirements.txt

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

ENTRYPOINT ["uvicorn", "main:app"]