FROM python:3.12-alpine
RUN apk add --no-cache gcc tzdata
ENV TZ=Europe/Warsaw
WORKDIR /adapter
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt
COPY main.py main.py
EXPOSE 5000
CMD python main.py