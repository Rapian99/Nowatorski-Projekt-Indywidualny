import os
import time
import requests
from loguru import logger
import sys
from flask import Flask
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from prometheus_client import make_wsgi_app, Gauge
from waitress import serve
import threading
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

TASMOTA_IP = os.getenv("TASMOTA_IP", "172.29.132.114")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 60))
PORT = int(os.getenv("PORT", 5000))
INFLUX_URL = os.getenv("INFLUX_URL", "http://influxdb:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "my-super-secret-token")
INFLUX_ORG = os.getenv("INFLUX_ORG", "my-org")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "sensors")
TEMP = Gauge("tasmota_temperature_celsius", "Temperature from BME280", ["sensor_id"])
HUM = Gauge("tasmota_humidity_percent", "Humidity from BME280", ["sensor_id"])
PRESS = Gauge("tasmota_pressure_hpa", "Pressure from BME280", ["sensor_id"])

PM1 = Gauge("tasmota_pm1_0_ugm3", "PM1.0 mass concentration", ["sensor_id"])
PM25 = Gauge("tasmota_pm2_5_ugm3", "PM2.5 mass concentration", ["sensor_id"])
PM4 = Gauge("tasmota_pm4_0_ugm3", "PM4.0 mass concentration", ["sensor_id"])
PM10 = Gauge("tasmota_pm10_0_ugm3", "PM10.0 mass concentration", ["sensor_id"])

NC05 = Gauge("tasmota_nc0_5_cm3", "Number Concentration 0.5", ["sensor_id"])
NC1 = Gauge("tasmota_nc1_0_cm3", "Number Concentration 1.0", ["sensor_id"])

logger.remove()
logger.add(
    sys.stdout, level="DEBUG", format='ts="{time}" level="{level}" message="{message}"'
)

app = Flask(__name__)


def write_to_influx(measurement, tags, fields):
    try:
        client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
        write_api = client.write_api(write_options=SYNCHRONOUS)

        p = Point(measurement)
        for k, v in tags.items():
            p.tag(k, v)
        for k, v in fields.items():
            p.field(k, float(v))

        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=p)
        logger.debug(f"Wrote to InfluxDB: {measurement}")
    except Exception as e:
        logger.warning(f"Failed to write to InfluxDB: {e}")


def fetch_data():
    """Wątek w tle: odpytuje Tasmotę i aktualizuje metryki."""
    url = f"http://{TASMOTA_IP}/cm?cmnd=Status%208"
    sid = "Tasmota_Station_1"

    while True:
        try:
            logger.debug(f"Pulling data from Tasmota at {TASMOTA_IP}...")
            r = requests.get(url, timeout=5)

            if r.status_code == 200:
                sns = r.json().get("StatusSNS", {})
                if "BME280" in sns:
                    b = sns["BME280"]
                    TEMP.labels(sid).set(b.get("Temperature", 0))
                    HUM.labels(sid).set(b.get("Humidity", 0))
                    PRESS.labels(sid).set(b.get("Pressure", 0))
                    write_to_influx(
                        "weather",
                        {"sensor": sid},
                        {
                            "temperature": b.get("Temperature", 0),
                            "humidity": b.get("Humidity", 0),
                            "pressure": b.get("Pressure", 0),
                        },
                    )
                if "SPS30" in sns:
                    s = sns["SPS30"]
                    PM1.labels(sid).set(s.get("PM1_0", 0))
                    PM25.labels(sid).set(s.get("PM2_5", 0))
                    PM4.labels(sid).set(s.get("PM4_0", 0))
                    PM10.labels(sid).set(s.get("PM10", 0))
                    NC05.labels(sid).set(s.get("NCPM0_5", 0))
                    NC1.labels(sid).set(s.get("NCPM1_0", 0))
                    write_to_influx(
                        "air_quality",
                        {"sensor": sid},
                        {
                            "pm1": s.get("PM1_0", 0),
                            "pm25": s.get("PM2_5", 0),
                            "pm10": s.get("PM10", 0),
                        },
                    )

                logger.success(f"Metrics updated at {time.strftime('%H:%M:%S')}")
            else:
                logger.error(f"Tasmota error: HTTP {r.status_code}")

        except Exception as e:
            logger.error(f"Connection failed: {e}")

        time.sleep(POLL_INTERVAL)


def main():
    threading.Thread(target=fetch_data, daemon=True).start()
    app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {"/metrics": make_wsgi_app()})

    logger.info(f"Adapter (PULL MODE) running on port {PORT}")
    serve(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
