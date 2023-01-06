from util import is_threshold_failed, get_aggregated_value, upload_test_results, get_summary_file_lines, \
    load_all_results_data
from os import environ, rename
from traceback import format_exc
import requests
from json import loads
from datetime import datetime
import pytz
import sys
from engagement_reporter import EngagementReporter
from time import sleep

sleep(30)

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
METRICS_MAPPER = {"load_time": "load_time", "dom": "dom_processing", "tti": "time_to_interactive",
                  "fcp": "first_contentful_paint", "lcp": "largest_contentful_paint",
                  "tbt": "total_blocking_time", "cls": "cumulative_layout_shift",
                  "fvc": "first_visual_change", "lvc": "last_visual_change"}

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

    print("*********************** Thresholds")
    for each in thresholds:
        print(each)
    print("***********************")

    failed_thresholds = []
    all_thresholds: list = list(filter(lambda _th: _th['scope'] == 'all', thresholds))
    every_thresholds: list = list(filter(lambda _th: _th['scope'] == 'every', thresholds))
    page_thresholds: list = list(filter(lambda _th: _th['scope'] != 'every' and _th['scope'] != 'all', thresholds))
    test_thresholds_total = 0
    test_thresholds_failed = 0

    metrics_list = ["load_time", "dom", "tti", "fcp", "lcp", "cls", "tbt", "fvc", "lvc"]

    upload_test_results(TEST_NAME, URL, PROJECT_ID, TOKEN, REPORT_ID)
    file_data = get_summary_file_lines(REPORT_ID)
    header = file_data.pop(0).decode('utf-8').replace("\n", "")

    results = []
    for each in file_data:
        _ = {}
        result = each.decode('utf-8').replace("\n", "").split(",")
        for i, metric in enumerate(header.split(",")):
            _[metric] = result[i]
        results.append(_)

    summary_results = {}
    for each in results:
        if each["identifier"] not in summary_results.keys():
            summary_results[each["identifier"]] = {"load_time": [], "dom_processing": [], "time_to_interactive": [],
                                                   "first_contentful_paint": [], "largest_contentful_paint": [],
                                                   "total_blocking_time": [], "cumulative_layout_shift": [],
                                                   "first_visual_change": [], "last_visual_change": []}
        for metric in metrics_list:
            if metric == "cls":
                summary_results[each["identifier"]][METRICS_MAPPER.get(metric)].append(float(each[metric]))
            else:
                summary_results[each["identifier"]][METRICS_MAPPER.get(metric)].append(int(each[metric]))

    print("******************* Summary results (for every and personal threshold")
    print(summary_results)
    print("*******************")
    
    # Process thresholds with scope = every
    for th in every_thresholds:
        for step in summary_results.keys():
            test_thresholds_total += 1
            step_result = get_aggregated_value(th["aggregation"], summary_results[step].get(th["target"]))
            if not is_threshold_failed(step_result, th["comparison"], th["value"]):
                print(f"Threshold: {th['scope']} {th['target']} {th['aggregation']} value {step_result}"
                      f" comply with rule {th['comparison']} {th['value']} [PASSED]")
            else:
                test_thresholds_failed += 1
                threshold = dict(actual_value=step_result, page=step, **th)
                failed_thresholds.append(threshold)
                print(f"Threshold: {th['scope']} {th['target']} {th['aggregation']} value {step_result}"
                      f" violates rule {th['comparison']} {th['value']} [FAILED]")

    # Process thresholds for current page
    for th in page_thresholds:
        for step in summary_results.keys():
            if th["scope"] == step:
                test_thresholds_total += 1
                step_result = get_aggregated_value(th["aggregation"], summary_results[step].get(th["target"]))
                if not is_threshold_failed(step_result, th["comparison"], th["value"]):
                    print(
                        f"Threshold: {th['scope']} {th['target']} {th['aggregation']} value {step_result}"
                        f" comply with rule {th['comparison']} {th['value']} [PASSED]")
                else:
                    test_thresholds_failed += 1
                    threshold = dict(actual_value=step_result, **th)
                    failed_thresholds.append(threshold)
                    print(
                        f"Threshold: {th['scope']} {th['target']} {th['aggregation']} value {step_result}"
                        f" violates rule {th['comparison']} {th['value']} [FAILED]")

    all_results = load_all_results_data()

    # Process thresholds with scope = all
    for th in all_thresholds:
        test_thresholds_total += 1
        result = get_aggregated_value(th["aggregation"], all_results.get(th["target"]))
        if not is_threshold_failed(result, th["comparison"], th["value"]):
            print(f"Threshold: {th['scope']} {th['target']} {th['aggregation']} value {result}"
                  f" comply with rule {th['comparison']} {th['value']} [PASSED]")
        else:
            test_thresholds_failed += 1
            threshold = dict(actual_value=result, **th)
            failed_thresholds.append(threshold)
            print(f"Threshold: {th['scope']} {th['target']} {th['aggregation']} value {result}"
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
        "results": all_results,
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
    try:
        integrations = loads(environ.get("integrations"))
    except:
        integrations = None


    if integrations and integrations.get("reporters") and "reporter_email" in integrations["reporters"].keys():
        email_notification_id = integrations["reporters"]["reporter_email"].get("task_id")
        if email_notification_id:
            emails = integrations["reporters"]["reporter_email"].get("recipients", [])
            if emails:
                task_url = f"{URL}/api/v1/tasks/task/{PROJECT_ID}/{email_notification_id}"

                event = {
                    "notification_type": "ui",
                    "smtp_host": integrations["reporters"]["reporter_email"]["integration_settings"]["host"],
                    "smtp_port": integrations["reporters"]["reporter_email"]["integration_settings"]["port"],
                    "smtp_user": integrations["reporters"]["reporter_email"]["integration_settings"]["user"],
                    "smtp_sender": integrations["reporters"]["reporter_email"]["integration_settings"]["sender"],
                    "smtp_password": integrations["reporters"]["reporter_email"]["integration_settings"]["passwd"],
                    "user_list": emails,
                    "test_id": sys.argv[1],
                    "report_id": REPORT_ID
                }
                if integrations.get("processing") and "quality_gate" in integrations["processing"].keys():
                    quality_gate_config = integrations['processing']['quality_gate']
                else:
                    quality_gate_config = {}
                if quality_gate_config.get('check_performance_degradation') and \
                        quality_gate_config['check_performance_degradation'] != -1:
                    event["performance_degradation_rate"] = quality_gate_config['performance_degradation_rate']
                if quality_gate_config.get('check_missed_thresholds') and \
                        quality_gate_config['check_missed_thresholds'] != -1:
                    event["missed_thresholds"] = quality_gate_config['missed_thresholds_rate']

                res = requests.post(task_url, json=event, headers={'Authorization': f'bearer {TOKEN}',
                                                                   'Content-type': 'application/json'})
                print(res)


    if integrations and integrations.get("reporters") and "reporter_engagement" in integrations['reporters'].keys():
        if URL and TOKEN and PROJECT_ID and failed_thresholds:
            payload = integrations['reporters']['reporter_engagement']
            args = {
                'thresholds_failed': test_thresholds_failed,
                'thresholds_total': test_thresholds_total,
                'test_name': TEST_NAME,
                'env': ENV,
                'report_id': REPORT_ID,
            }
            reporter_url = URL + payload['report_url'] + '/' + PROJECT_ID
            query_url = URL + payload['query_url'] + '/' + PROJECT_ID
            reporter = EngagementReporter(
                reporter_url, query_url,
                TOKEN, payload['id'],
                args
            )
            reporter.report_findings(failed_thresholds)

except Exception:
    print(format_exc())
