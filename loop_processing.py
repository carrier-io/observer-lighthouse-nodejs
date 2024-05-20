from util import update_summary_file, all_results_file_exist, load_all_results_data, dump_all_results_data
from os import environ, rename, listdir, path
import logging
import requests
from json import loads
from datetime import datetime

# Initialize logging
logger = logging.getLogger()
logging.basicConfig(level=logging.INFO)

# Environment variables
env_vars = [
    'GALLOPER_PROJECT_ID', 'GALLOPER_URL', 'REPORT_ID', 'TESTS_BUCKET',
    'REPORTS_BUCKET', 'ARTIFACT', 'token', 'tests_path', 'JOB_NAME', 'current_loop'
]
PROJECT_ID, URL, REPORT_ID, BUCKET, REPORTS_BUCKET, TEST, TOKEN, TESTS_PATH, TEST_NAME, CURRENT_LOOP = [environ.get(var)
                                                                                                        for var in
                                                                                                        env_vars]
logger.info(f"REPORT_ID: {REPORT_ID}")
logger.info(f"Loaded environment variables.")
CURRENT_LOOP = int(CURRENT_LOOP or 1)
json_file = ""
json_path = ""

integrations = loads(environ.get("integrations", '{}'))
s3_config = integrations.get('system', {}).get('s3_integration', {})

all_results_template = {
    "load_time": [], "speed_index": [], "time_to_first_byte": [], "time_to_first_paint": [],
    "dom_content_loading": [], "dom_processing": [], "first_contentful_paint": [],
    "largest_contentful_paint": [], "cumulative_layout_shift": [], "total_blocking_time": [],
    "first_visual_change": [], "last_visual_change": [], "time_to_interactive": []
}

try:
    all_results = load_all_results_data() if all_results_file_exist() else all_results_template
    timestamp = datetime.now().strftime("%d%b%Y_%H:%M:%S")
    _timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    records = []

    logger.info(f"Processing files in 'reports/' directory.")
    files = listdir('reports/')
    logger.info(f"Found next files in 'reports/' directory.")
    logger.info(files)
    for filename in files:
        file_path = path.join('reports/', filename)
        new_path = f"/tmp/{timestamp}_{filename}"
        rename(file_path, new_path)
        logger.info(f"Renamed {filename} to {new_path}")
        if filename.endswith('.json'):
            json_file = filename
            json_path = new_path
    if json_file:
        logger.info(f"Processing JSON file: {json_file}")
        with open(json_path, "r") as f:
            json_data = loads(f.read())
            for index, step in enumerate(json_data["steps"]):
                result, file_name = {}, json_path.split("/")[-1]
                step["name"] = step["name"].replace(",", "_").replace(" ", "_")
                # Check if 'metrics' key exists
                if "metrics" in step["lhr"]["audits"]:
                    # Check if 'details' key exists
                    if "details" in step["lhr"]["audits"]["metrics"]:
                        data_m = step["lhr"]["audits"]["metrics"]["details"]['items'][0]
                        if "observedLoad" in data_m and "largestContentfulPaint" in data_m:
                            step_type = "page"
                            logger.info(f"Start Processing Page {step['name']} from {json_file}")
                            metrics = step["lhr"]["audits"]["metrics"]["details"]['items'][0]
                            result = {
                                "requests": 1,
                                "domains": 1,
                                "timestamps": _timestamp,
                                "load_time": int(
                                    step["lhr"]["audits"]["metrics"]["details"]['items'][0]["observedLoad"]),
                                "speed_index": int(
                                    step["lhr"]["audits"]["metrics"]["details"]['items'][0]["speedIndex"]),
                                "time_to_first_byte": int(
                                    step["lhr"]["audits"]['server-response-time']['numericValue']),
                                "time_to_first_paint": int(
                                    step["lhr"]["audits"]["metrics"]["details"]['items'][0]["observedFirstPaint"]),
                                "dom_content_loading": int(
                                    step["lhr"]["audits"]["metrics"]["details"]['items'][0][
                                        "observedDomContentLoaded"]),
                                "dom_processing": int(
                                    step["lhr"]["audits"]["metrics"]["details"]['items'][0][
                                        "observedDomContentLoaded"]),
                                "first_contentful_paint": int(
                                    step["lhr"]["audits"]["metrics"]["details"]['items'][0]["firstContentfulPaint"]),
                                "largest_contentful_paint": int(
                                    step["lhr"]["audits"]["metrics"]["details"]['items'][0]["largestContentfulPaint"]),
                                "cumulative_layout_shift": round(
                                    float(int(
                                        step["lhr"]["audits"]["metrics"]["details"]['items'][0][
                                            "cumulativeLayoutShift"])),
                                    3),
                                "total_blocking_time": int(
                                    step["lhr"]["audits"]["metrics"]["details"]['items'][0]["totalBlockingTime"]),
                                "first_visual_change": int(
                                    step["lhr"]["audits"]["metrics"]["details"]['items'][0][
                                        "observedFirstVisualChange"]),
                                "last_visual_change": int(
                                    step["lhr"]["audits"]["metrics"]["details"]['items'][0][
                                        "observedLastVisualChange"]),
                                "time_to_interactive": int(
                                    step["lhr"]["audits"]["metrics"]["details"]['items'][0]["interactive"])
                            }
                            logger.info(f"Processed Page {step['name']} from {json_file}")
                        else:
                            logger.info(
                                f"Skipping step {index} {step['name']} in {json_file} due to missing 'observedLoad' key.")
                            continue
                    else:
                        logger.info(
                            f"Skipping step {index} {step['name']} in {json_file} due to missing 'details' key.")
                        continue
                elif 'cumulative-layout-shift' in step["lhr"]["audits"]:
                    step_type = "action"
                    logger.info(f"Start Processing Action {step['name']} from {json_file}")
                    try:
                        shift = round(float(step["lhr"]["audits"]['cumulative-layout-shift']['numericValue']), 3)
                    except:
                        logger.info("[INFO] No cumulative-layout-shift")
                    result = {
                        "requests": 1,
                        "timestamps": _timestamp,
                        "domains": 1,
                        "load_time": 0,
                        "speed_index": 0,
                        "time_to_first_byte": 0,
                        "time_to_first_paint": 0,
                        "dom_content_loading": 0,
                        "dom_processing": 0,
                        "first_contentful_paint": 0,
                        "largest_contentful_paint": 0,
                        "cumulative_layout_shift": shift,
                        "total_blocking_time": int(step["lhr"]["audits"]['total-blocking-time']['numericValue']),
                        "first_visual_change": 0,
                        "last_visual_change": 0,
                        "time_to_interactive": 0
                    }
                    logger.info(f"Processed Action {step['name']} from {json_file}")
                else:
                    continue
                for metric in all_results:
                    if (step_type == "action" and metric in ["total_blocking_time", "cumulative_layout_shift"]) \
                            or (step_type == "page" and metric not in ["total_blocking_time",
                                                                       "cumulative_layout_shift"]):
                        logger.debug("INSIDE ACTION TYPE")
                        logger.debug(step["name"])
                        all_results[metric].append(result.get(metric, 0))

                if 'requestedUrl' in step["lhr"]:
                    logger.debug("STEP requestedUrl")
                    logger.debug(step["lhr"]["requestedUrl"])
                    url_ = step["lhr"]["requestedUrl"]
                else:
                    logger.debug("KeyError: 'requestedUrl'")
                    logger.debug(step["lhr"]["finalDisplayedUrl"])
                    url_ = step["lhr"]["finalDisplayedUrl"]

                data = {
                    "name": step["name"].replace(",", "_").replace(" ", "_"),
                    "type": step_type,
                    "loop": CURRENT_LOOP,
                    "identifier": f'{url_}@{step["name"]}',
                    "metrics": result,
                    "bucket_name": "reports",
                    "file_name": f"{file_name.replace('.json', '.html')}#index={index}",
                    "resolution": "auto",
                    "browser_version": "chrome",
                    "thresholds_total": 0,
                    "thresholds_failed": 0,
                    "locators": [],
                    "session_id": "session_id"
                }
                records.append(data)

                try:
                    requests.post(
                        f"{URL}/api/v1/artifacts/artifacts/{PROJECT_ID}/reports",
                        params=s3_config, files={'file': open(json_path, 'rb')},
                        allow_redirects=True,
                        headers={'Authorization': f"Bearer {TOKEN}"}
                    )
                    logger.debug(f"Uploaded {json_path} to reports.")
                except Exception as e:
                    logger.error(f"Failed to upload {json_path}. Error: {e}")

                try:
                    requests.post(
                        f"{URL}/api/v1/artifacts/artifacts/{PROJECT_ID}/reports",
                        params=s3_config, files={'file': open(json_path.replace('.json', '.html'), 'rb')},
                        allow_redirects=True,
                        headers={'Authorization': f"Bearer {TOKEN}"}
                    )
                    logger.debug(f"Uploaded {json_path} to reports.")
                except Exception as e:
                    logger.error(f"Failed to upload {json_path}. Error: {e}")
        logger.debug("update_summary_file started")
        update_summary_file(REPORT_ID, records)
        dump_all_results_data(all_results)
        logger.info(f"Finished processing all files in 'reports/' directory.")
    else:
        logger.error(f"NO JSON files found in reports/")
except Exception as e:
    logger.error(f"An error occurred: {e}")