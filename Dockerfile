FROM python:3.11

WORKDIR /usr/app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY main.py .
CMD [ "python", "-u", "main.py" ]
