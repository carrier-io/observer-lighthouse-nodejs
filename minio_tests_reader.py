from os import environ
import requests
import zipfile
from json import loads
from traceback import format_exc
from carrier_logger import logger

PROJECT_ID = environ.get('GALLOPER_PROJECT_ID')
URL = environ.get('GALLOPER_URL')
BUCKET = environ.get("TESTS_BUCKET")
TEST = environ.get("ARTIFACT")
TOKEN = environ.get("token")
PATH_TO_FILE = f'/tmp/{TEST}'
TESTS_PATH = environ.get("tests_path", '/')
REPORT_ID = environ.get('REPORT_ID')

integrations = loads(environ.get("integrations", '{}'))
s3_config = integrations.get('system', {}).get('s3_integration', {})

if not all(a for a in [URL, BUCKET, TEST]):
    logger.warning("Missing required parameters (URL, BUCKET, or TEST). Exiting.")
    exit(0)

try:
    endpoint = f'/api/v1/artifacts/artifact/{PROJECT_ID}/{BUCKET}/{TEST}'
    headers = {'Authorization': f'bearer {TOKEN}'} if TOKEN else {}
    logger.info(f"Downloading artifact: {endpoint}")
    r = requests.get(f'{URL}/{endpoint}', params=s3_config, allow_redirects=True, headers=headers)
    with open(PATH_TO_FILE, 'wb') as file_data:
        file_data.write(r.content)
    logger.info(f"Artifact downloaded to: {PATH_TO_FILE}")

    with zipfile.ZipFile(PATH_TO_FILE, 'r') as zip_ref:
        zip_ref.extractall(TESTS_PATH)
    logger.info(f"Artifact extracted to: {TESTS_PATH}")

    headers = {'content-type': 'application/json', 'Authorization': f'bearer {TOKEN}'}
    url = f'{URL}/api/v1/ui_performance/report_status/{PROJECT_ID}/{REPORT_ID}'
    data = {"test_status": {"status": "In progress", "percentage": 10,
                            "description": "Test started."}}
    response = requests.put(url, json=data, headers=headers)
    try:
        logger.info(f"Status update response: {response.json()['message']}")
    except:
        logger.debug(f"Status update response: {response.text}")
except Exception as e:
    logger.error(f"Error in minio_tests_reader: {str(e)}")
    logger.debug(format_exc())
