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

integrations = loads(environ.get("integrations", '{}'))
s3_config = integrations.get('system', {}).get('s3_integration', {})

try:
    # Get thresholds
    res = None
    try:
        threshold_url = f"{URL}/api/v1/ui_performance/thresholds/{PROJECT_ID}?report_id={REPORT_ID}"
        print(f"[HTTP REQUEST] {threshold_url}")
        res = requests.get(
            threshold_url,
            headers={'Authorization': f"bearer {TOKEN}"})
        print(f"[HTTP RESPONSE] Status: {res.status_code}")
    except Exception as e:
        print(f"[HTTP ERROR] Exception during request: {str(e)}")
        print(format_exc())

    if not res or res.status_code != 200:
        if res:
            print(f"[THRESHOLDS] API returned status: {res.status_code}")
            if res.status_code == 403:
                print(f"[THRESHOLDS] Access forbidden - check token permissions")
            elif res.status_code == 404:
                print(f"[THRESHOLDS] Report not found")
            if res.text:
                print(f"[THRESHOLDS] Response: {res.text[:500]}")
        else:
            print(f"[THRESHOLDS] No response from API")
        thresholds = []
    else:
        try:
            response_data = res.json()
            # Handle response format: could be a dict with 'rows' or a list
            if isinstance(response_data, dict) and 'rows' in response_data:
                thresholds = response_data['rows']
                print(f"[THRESHOLDS] Fetched {len(thresholds)} thresholds from API (dict with 'rows')")
            elif isinstance(response_data, list):
                thresholds = response_data
                print(f"[THRESHOLDS] Fetched {len(thresholds)} thresholds from API (list)")
            else:
                thresholds = []
                print(f"[THRESHOLDS] Unexpected response format: {type(response_data)}")
        except ValueError:
            thresholds = []
            print(f"[THRESHOLDS] Failed to parse JSON response")
    
    # Filter thresholds by test name and environment (like reference implementation)
    filtered_thresholds = [
        th for th in thresholds
        if th.get('test') == TEST_NAME and th.get('environment') == ENV
    ]
    print(f"[THRESHOLDS] After filtering by test='{TEST_NAME}' and env='{ENV}': {len(filtered_thresholds)} thresholds")
    thresholds = filtered_thresholds

    print("*********************** Thresholds")
    for each in thresholds:
        print(each)
    print("***********************")

    failed_thresholds = []
    
    # Initialize counters - count metric evaluations like ui_email_notification
    total = 0
    failed = 0

    metrics_list = ["load_time", "dom", "tti", "fcp", "lcp", "cls", "tbt", "fvc", "lvc"]

    upload_test_results(TEST_NAME, URL, PROJECT_ID, TOKEN, REPORT_ID, s3_config)
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
                summary_results[each["identifier"]][METRICS_MAPPER.get(metric)].append(float(each[metric]) if each[metric] else 0.0)
            else:
                summary_results[each["identifier"]][METRICS_MAPPER.get(metric)].append(int(each[metric]) if each[metric] else 0)

    print("******************* Summary results (for every and personal threshold")
    print(summary_results)
    print("*******************")
    
    # Group thresholds by scope for easier lookup (like ui_email_notification.py)
    thresholds_grouped = {}
    for th in thresholds:
        scope = th.get('scope')
        if scope not in thresholds_grouped:
            thresholds_grouped[scope] = []
        thresholds_grouped[scope].append(th)
    
    # Determine result type based on identifier
    def get_result_type(identifier):
        # Actions have @ symbol after the domain
        if '@[T]_' in identifier or '@[A]_' in identifier:
            return 'action'
        return 'page'
    
    # Process thresholds using the ui_email_notification approach:
    # Iterate over results, then over metrics, checking applicable thresholds
    for step_identifier, step_data in summary_results.items():
        result_type = get_result_type(step_identifier)
        
        # Get applicable thresholds for this step
        applicable_thresholds = (
            thresholds_grouped.get('every', []) + 
            thresholds_grouped.get(step_identifier, []) +
            thresholds_grouped.get('all', [])
        )
        
        # Determine which metrics to check based on result type
        metrics_to_check = ["load_time", "dom", "tti", "fcp", "lcp", "cls", "tbt", "fvc", "lvc"] \
            if result_type == "page" else ["cls", "tbt", "inp"]
        
        # Check each metric
        for metric_short in metrics_to_check:
            # Map short name to full name
            metric_full = METRICS_MAPPER.get(metric_short, metric_short)
            
            # Skip if this step doesn't have this metric
            if metric_full not in step_data:
                continue
            
            # Find thresholds for this metric
            metric_thresholds = [th for th in applicable_thresholds if th.get('target') == metric_full]
            
            if not metric_thresholds:
                continue
            
            # Get the actual value
            actual_value = get_aggregated_value('max', step_data.get(metric_full, []))
            
            # Check against ALL thresholds for this metric (multiple thresholds per metric are possible)
            for threshold in metric_thresholds:
                total += 1
                threshold_value = threshold.get('value', 0)
                comparison = threshold.get('comparison', 'lte')
                
                # Convert milliseconds to seconds for comparison (except for CLS which is unitless)
                comparison_value = actual_value if metric_full == 'cumulative_layout_shift' else actual_value / 1000
                
                if is_threshold_failed(comparison_value, comparison, threshold_value):
                    failed += 1
                    failed_threshold = dict(actual_value=actual_value, page=step_identifier, **threshold)
                    failed_thresholds.append(failed_threshold)
                    print(f"Threshold: {threshold['scope']} {threshold['target']} value {comparison_value:.3f}"
                          f" violates rule {comparison} {threshold_value} [FAILED]")
                else:
                    print(f"Threshold: {threshold['scope']} {threshold['target']} value {comparison_value:.3f}"
                          f" comply with rule {comparison} {threshold_value} [PASSED]")

    # Load all results for reporting
    all_results = load_all_results_data()

    # Finalize report
    time = datetime.now(tz=pytz.timezone("UTC"))
    exception_message = ""
    status = {"status": "Finished", "percentage": 100, "description": "Test is finished"}
    if total:
        violated = round(float(failed / total) * 100, 2)
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
        "thresholds_total": total,
        "thresholds_failed": failed,
        "exception": exception_message
    }

    try:
        requests.put(f"{URL}/api/v1/ui_performance/reports/{PROJECT_ID}", json=report_data,
                     headers={'Authorization': f"Bearer {TOKEN}", 'Content-type': 'application/json'})
    except Exception:
        print(format_exc())

    # Email notification
    # try:
    #     integrations = loads(environ.get("integrations"))
    # except:
    #     integrations = None


    if integrations and integrations.get("reporters") and "reporter_email" in integrations["reporters"].keys():
        email_notification_id = integrations["reporters"]["reporter_email"].get("task_id")
        if email_notification_id:
            emails = integrations["reporters"]["reporter_email"].get("recipients", [])
            if emails:
                task_url = f"{URL}/api/v1/tasks/run_task/{PROJECT_ID}/{email_notification_id}"

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
                event["performance_degradation_rate"] = quality_gate_config.get('degradation_rate')
                event["missed_thresholds"] = quality_gate_config.get('missed_thresholds')

                res = requests.post(task_url, json=event, headers={'Authorization': f'bearer {TOKEN}',
                                                                   'Content-type': 'application/json'})
                print(res)


    if integrations and integrations.get("reporters") and "reporter_engagement" in integrations['reporters'].keys():
        if URL and TOKEN and PROJECT_ID and failed_thresholds:
            payload = integrations['reporters']['reporter_engagement']
            args = {
                'thresholds_failed': failed,
                'thresholds_total': total,
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
