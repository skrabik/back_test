FROM python:3.12-slim

# Setup env
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONFAULTHANDLER 1

WORKDIR /src

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . ./
CMD ["python", "main.py"]
