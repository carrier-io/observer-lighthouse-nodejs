from util import update_summary_file, all_results_file_exist, load_all_results_data, dump_all_results_data
from os import environ, rename
from traceback import format_exc
import requests
from json import loads
from datetime import datetime
import pytz
import sys
import os

PROJECT_ID = environ.get('GALLOPER_PROJECT_ID')
URL = environ.get('GALLOPER_URL')
REPORT_ID = environ.get('REPORT_ID')
BUCKET = environ.get("TESTS_BUCKET")
REPORTS_BUCKET = environ.get("REPORTS_BUCKET")
TEST = environ.get("ARTIFACT")
TOKEN = environ.get("token")
PATH_TO_FILE = f'/tmp/{TEST}'
TESTS_PATH = environ.get("tests_path", '/')
TEST_NAME = environ.get("JOB_NAME")
CURRENT_LOOP = int(environ.get("current_loop", 1))


try:
    if all_results_file_exist():
        all_results = load_all_results_data()
    else:
        all_results = {"load_time": [], "speed_index": [], "time_to_first_byte": [], "time_to_first_paint": [],
                       "dom_content_loading": [], "dom_processing": [], "first_contentful_paint": [],
                       "largest_contentful_paint": [], "cumulative_layout_shift": [], "total_blocking_time": [],
                       "first_visual_change": [], "last_visual_change": [], "time_to_interactive": []}
    format_str = "%d%b%Y_%H:%M:%S"
    timestamp = datetime.now().strftime(format_str)
    _timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    html_path = f"/{timestamp}_user-flow.report.html"
    rename("/user-flow.report.html", html_path)

    json_path = f"/{timestamp}_user-flow.report.json"
    rename("/user-flow.report.json", json_path)
    # Read and process results json
    with open(json_path, "r") as f:
        json_data = loads(f.read())
        index = 0
        records = []
        for step in json_data["steps"]:
            page_thresholds_total = 0
            page_thresholds_failed = 0
            file_name = html_path.split("/")[-1]
            if "metrics" in list(step["lhr"]["audits"].keys()):
                step_type = "page"
                result = {
                    "requests": 1,
                    "domains": 1,
                    "timestamps": _timestamp,
                    "load_time": int(step["lhr"]["audits"]["metrics"]["details"]['items'][0]["observedLoad"]),
                    "speed_index": int(step["lhr"]["audits"]["metrics"]["details"]['items'][0]["speedIndex"]),
                    "time_to_first_byte": int(step["lhr"]["audits"]['server-response-time']['numericValue']),
                    "time_to_first_paint": int(
                        step["lhr"]["audits"]["metrics"]["details"]['items'][0]["observedFirstPaint"]),
                    "dom_content_loading": int(
                        step["lhr"]["audits"]["metrics"]["details"]['items'][0]["observedDomContentLoaded"]),
                    "dom_processing": int(
                        step["lhr"]["audits"]["metrics"]["details"]['items'][0]["observedDomContentLoaded"]),
                    "first_contentful_paint": int(
                        step["lhr"]["audits"]["metrics"]["details"]['items'][0]["firstContentfulPaint"]),
                    "largest_contentful_paint": int(
                        step["lhr"]["audits"]["metrics"]["details"]['items'][0]["largestContentfulPaint"]),
                    "cumulative_layout_shift": round(
                        float(int(step["lhr"]["audits"]["metrics"]["details"]['items'][0]["cumulativeLayoutShift"])),
                        3),
                    "total_blocking_time": int(
                        step["lhr"]["audits"]["metrics"]["details"]['items'][0]["totalBlockingTime"]),
                    "first_visual_change": int(
                        step["lhr"]["audits"]["metrics"]["details"]['items'][0]["observedFirstVisualChange"]),
                    "last_visual_change": int(
                        step["lhr"]["audits"]["metrics"]["details"]['items'][0]["observedLastVisualChange"]),
                    "time_to_interactive": int(step["lhr"]["audits"]["metrics"]["details"]['items'][0]["interactive"])
                }
            else:
                step_type = "action"
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
                    "cumulative_layout_shift": round(float(step["lhr"]["audits"]['cumulative-layout-shift']['numericValue']), 3),
                    "total_blocking_time": int(step["lhr"]["audits"]['total-blocking-time']['numericValue']),
                    "first_visual_change": 0,
                    "last_visual_change": 0,
                    "time_to_interactive": 0
                }

            # Add page results to the summary dict
            for metric in list(all_results.keys()):
                if step_type == "action" and metric in ["total_blocking_time", "cumulative_layout_shift"]:
                    all_results[metric].append(result[metric])
                elif step_type == "page" and metric not in ["total_blocking_time", "cumulative_layout_shift"]:
                    all_results[metric].append(result[metric])

            # Update report with page results
            data = {
                "name": step["name"],
                "type": step_type,
                "loop": CURRENT_LOOP,
                "identifier": f'{step["lhr"]["requestedUrl"]}@{step["name"]}',
                "metrics": result,
                "bucket_name": "reports",
                "file_name": f"{file_name}#index={index}",
                "resolution": "auto",
                "browser_version": "chrome",
                "thresholds_total": page_thresholds_total,
                "thresholds_failed": page_thresholds_failed,
                "locators": [],
                "session_id": "session_id"
            }
            index += 1

            records.append(data)

            # Send html file with page results
            file = {'file': open(html_path, 'rb')}

            try:
                requests.post(f"{URL}/api/v1/artifacts/artifacts/{PROJECT_ID}/reports",
                              files=file, allow_redirects=True,
                              headers={'Authorization': f"Bearer {TOKEN}"})
            except Exception:
                print(format_exc())

            json_file = {'file': open(json_path, 'rb')}
            file_name = json_path.split("/")[-1]
            try:
                requests.post(f"{URL}/api/v1/artifacts/artifacts/{PROJECT_ID}/reports",
                              files=json_file, allow_redirects=True,
                              headers={'Authorization': f"Bearer {TOKEN}"})
            except Exception:
                print(format_exc())
        update_summary_file(REPORT_ID, records)
        dump_all_results_data(all_results)

except Exception:
    print(format_exc())
