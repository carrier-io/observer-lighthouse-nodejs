from util import is_threshold_failed, get_aggregated_value, update_test_results
from os import environ, rename
from traceback import format_exc
import requests
from json import loads
from datetime import datetime
import pytz
import sys

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
ENV = environ.get("ENV")
QUALITY_GATE = int(environ.get("QUALITY_GATE", 20))


try:
    # Get thresholds
    res = None
    try:
        res = requests.get(
            f"{URL}/api/v1/ui_performance/thresholds/{PROJECT_ID}?test={TEST_NAME}&env={ENV}&order=asc",
            headers={'Authorization': f"Bearer {TOKEN}"})
    except Exception:
        print(format_exc())

    if not res or res.status_code != 200:
        thresholds = []

    try:
        thresholds = res.json()
    except ValueError:
        thresholds = []

    all_thresholds: list = list(filter(lambda _th: _th['scope'] == 'all', thresholds))
    every_thresholds: list = list(filter(lambda _th: _th['scope'] == 'every', thresholds))
    page_thresholds: list = list(filter(lambda _th: _th['scope'] != 'every' and _th['scope'] != 'all', thresholds))
    test_thresholds_total = 0
    test_thresholds_failed = 0

    all_results = {"total": [], "speed_index": [], "time_to_first_byte": [], "time_to_first_paint": [],
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
                    "total": int(step["lhr"]["audits"]["metrics"]["details"]['items'][0]["observedLoad"]),
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
                    "total": 0,
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
                all_results[metric].append(result[metric])

            # Process thresholds with scope = every
            for th in every_thresholds:
                test_thresholds_total += 1
                page_thresholds_total += 1
                if not is_threshold_failed(result.get(th["target"]), th["comparison"], th["value"]):
                    print(f"Threshold: {th['scope']} {th['target']} {th['aggregation']} value {result.get(th['target'])}"
                          f" comply with rule {th['comparison']} {th['value']} [PASSED]")
                else:
                    test_thresholds_failed += 1
                    page_thresholds_failed += 1
                    print(f"Threshold: {th['scope']} {th['target']} {th['aggregation']} value {result.get(th['target'])}"
                          f" violates rule {th['comparison']} {th['value']} [FAILED]")

            # Process thresholds for current page
            for th in page_thresholds:
                if th["scope"] == f'{step["lhr"]["requestedUrl"]}@{step["name"]}':
                    test_thresholds_total += 1
                    page_thresholds_total += 1
                    if not is_threshold_failed(result.get(th["target"]), th["comparison"], th["value"]):
                        print(f"Threshold: {th['scope']} {th['target']} {th['aggregation']} value {result.get(th['target'])}"
                              f" comply with rule {th['comparison']} {th['value']} [PASSED]")
                    else:
                        test_thresholds_failed += 1
                        page_thresholds_failed += 1
                        print(f"Threshold: {th['scope']} {th['target']} {th['aggregation']} value {result.get(th['target'])}"
                              f" violates rule {th['comparison']} {th['value']} [FAILED]")

            # Update report with page results
            data = {
                "name": step["name"],
                "type": step_type,
                "loop": 1,
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
        update_test_results(TEST_NAME, URL, PROJECT_ID, TOKEN, REPORT_ID, records)
    # Process thresholds with scope = all
    for th in all_thresholds:
        test_thresholds_total += 1
        if not is_threshold_failed(get_aggregated_value(th["aggregation"], all_results.get(th["target"])),
                                   th["comparison"], th["value"]):
            print(f"Threshold: {th['scope']} {th['target']} {th['aggregation']} value {all_results.get(th['target'])}"
                  f" comply with rule {th['comparison']} {th['value']} [PASSED]")
        else:
            test_thresholds_failed += 1
            print(f"Threshold: {th['scope']} {th['target']} {th['aggregation']} value {all_results.get(th['target'])}"
                  f" violates rule {th['comparison']} {th['value']} [FAILED]")

    # Finalize report
    time = datetime.now(tz=pytz.timezone("UTC"))
    exception_message = ""
    status = {"status": "Finished", "percentage": 100, "description": "Test is finished"}
    if test_thresholds_total:
        violated = round(float(test_thresholds_failed / test_thresholds_total) * 100, 2)
        print(f"Failed thresholds: {violated}")
        if violated > QUALITY_GATE:
            exception_message = f"Failed thresholds rate more then {violated}%"
            status = {"status": "Failed", "percentage": 100, "description": f"Missed more then {violated}% thresholds"}
        else:
            status = {"status": "Success", "percentage": 100, "description": f"Successfully met more than "
                                                                             f"{100 - violated}% of thresholds"}

    report_data = {
        "report_id": REPORT_ID,
        "time": time.strftime('%Y-%m-%d %H:%M:%S'),
        "status": status,
        "thresholds_total": test_thresholds_total,
        "thresholds_failed": test_thresholds_failed,
        "exception": exception_message
    }

    try:
        requests.put(f"{URL}/api/v1/ui_performance/reports/{PROJECT_ID}", json=report_data,
                     headers={'Authorization': f"Bearer {TOKEN}", 'Content-type': 'application/json'})
    except Exception:
        print(format_exc())

    # Email notification
    if len(sys.argv) > 2 and "email" in sys.argv[2].split(";"):
        secrets_url = f"{URL}/api/v1/secrets/{PROJECT_ID}/"
        try:
            email_notification_id = requests.get(secrets_url + "email_notification_id",
                                                 headers={'Authorization': f'bearer {TOKEN}',
                                                          'Content-type': 'application/json'}
                                                 ).json()["secret"]
        except:
            email_notification_id = ""

        if email_notification_id:
            task_url = f"{URL}/api/v1/task/{PROJECT_ID}/{email_notification_id}"

            event = {
                "notification_type": "ui",
                "test_id": sys.argv[1],
                "report_id": REPORT_ID
            }

            res = requests.post(task_url, json=event, headers={'Authorization': f'bearer {TOKEN}',
                                                               'Content-type': 'application/json'})

except Exception:
    print(format_exc())
