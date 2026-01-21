from os import environ
from centry_loki import log_loki

URL = environ.get('GALLOPER_URL')
LOKI_PORT = environ.get('LOKI_PORT', 3100)
REPORT_ID = environ.get('REPORT_ID')
PROJECT_ID = environ.get('GALLOPER_PROJECT_ID')



loki_context = {
    "url": f"{URL.replace('https://', 'http://')}:{LOKI_PORT}/loki/api/v1/push",
    "hostname": "lighthouse",
    "labels": {
        "project": PROJECT_ID,
        "report_id": REPORT_ID
    }
}
logger = log_loki.get_logger(loki_context)