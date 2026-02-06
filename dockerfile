FROM python:3.12-alpine AS builder
WORKDIR /apl
RUN apk add --no-cache gcc musl-dev
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

FROM python:3.12-alpine
RUN apk add --no-cache tzdata
ENV TZ=Europe/Warsaw
WORKDIR /adapter
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY main.py main.py
EXPOSE 5000
CMD python main.py
