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
METRICS_MAPPER = {"load_time": "load_time", "dom": "dom_processing", "tti": "time_to_interactive",
                  "fcp": "first_contentful_paint", "lcp": "largest_contentful_paint",
                  "tbt": "total_blocking_time", "cls": "cumulative_layout_shift",
                  "fvc": "first_visual_change", "lvc": "last_visual_change",
                  "ttfb": "time_to_first_byte", "inp": "interaction_to_next_paint"}

integrations = loads(environ.get("integrations", '{}'))
s3_config = integrations.get('system', {}).get('s3_integration', {})

try:
    # Fetch test configuration for quality gate settings
    degradation_rate = None
    missed_thresholds_percent = None
    try:
        test_config_url = f"{URL}/api/v1/ui_performance/tests/{PROJECT_ID}"
        print(f"[HTTP REQUEST] {test_config_url}")
        test_res = requests.get(
            test_config_url,
            headers={'Authorization': f"bearer {TOKEN}"})
        print(f"[HTTP RESPONSE] Status: {test_res.status_code}")
        
        if test_res.status_code == 200:
            test_data = test_res.json()
            if isinstance(test_data, dict) and 'rows' in test_data:
                for test in test_data['rows']:
                    if test.get('name') == TEST_NAME:
                        print(f"[CONFIG] Found configuration for test '{TEST_NAME}'")
                        integrations_config = test.get('integrations', {})
                        processing_config = integrations_config.get('processing', {})
                        quality_gate_config = processing_config.get('quality_gate', {})
                        
                        degradation_rate = quality_gate_config.get('degradation_rate')
                        missed_thresholds_percent = quality_gate_config.get('missed_thresholds')
                        
                        print(f"[CONFIG] Quality gate: degradation_rate={degradation_rate}, missed_thresholds={missed_thresholds_percent}")
                        break
                else:
                    print(f"[CONFIG] Test '{TEST_NAME}' not found in response")
            else:
                print(f"[CONFIG] Unexpected response format: {type(test_data)}")
        else:
            print(f"[CONFIG] Failed to fetch configuration: status {test_res.status_code}")
    except Exception as e:
        print(f"[CONFIG] Error: {str(e)}")
        print(format_exc())
    
    # Fetch thresholds from API
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
    print(f"[THRESHOLDS] Filtered to {len(filtered_thresholds)} for test='{TEST_NAME}', env='{ENV}'")
    thresholds = filtered_thresholds

    print("\n===== Thresholds =====")
    for each in thresholds:
        print(each)
    print("======================\n")

    failed_thresholds = []
    total = 0
    failed = 0

    metrics_list = ["load_time", "dom", "tti", "fcp", "lcp", "cls", "tbt", "fvc", "lvc", "ttfb", "inp"]

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
                                                   "first_visual_change": [], "last_visual_change": [],
                                                   "time_to_first_byte": [], "interaction_to_next_paint": []}
        for metric in metrics_list:
            if metric == "cls":
                summary_results[each["identifier"]][METRICS_MAPPER.get(metric)].append(float(each[metric]) if each[metric] else 0.0)
            else:
                summary_results[each["identifier"]][METRICS_MAPPER.get(metric)].append(int(each[metric]) if each[metric] else 0)

    print("\n===== Summary Results =====")
    print(summary_results)
    print("===========================\n")
    
    # Group thresholds by scope
    thresholds_grouped = {}
    for th in thresholds:
        scope = th.get('scope')
        if scope not in thresholds_grouped:
            thresholds_grouped[scope] = []
        thresholds_grouped[scope].append(th)
    
    def get_result_type(identifier):
        if '@[T]_' in identifier or '@[A]_' in identifier:
            return 'action'
        return 'page'
    
    # Evaluate thresholds against results
    for step_identifier, step_data in summary_results.items():
        result_type = get_result_type(step_identifier)
        
        applicable_thresholds = (
            thresholds_grouped.get('every', []) + 
            thresholds_grouped.get(step_identifier, []) +
            thresholds_grouped.get('all', [])
        )
        
        metrics_to_check = ["load_time", "dom", "tti", "fcp", "lcp", "cls", "tbt", "fvc", "lvc", "ttfb", "inp"] \
            if result_type == "page" else ["cls", "tbt", "inp"]
        
        for metric_short in metrics_to_check:
            metric_full = METRICS_MAPPER.get(metric_short, metric_short)
            if metric_full not in step_data:
                continue
            
            metric_thresholds = [th for th in applicable_thresholds if th.get('target') == metric_full]
            if not metric_thresholds:
                continue
            
            actual_value = get_aggregated_value('max', step_data.get(metric_full, []))
            
            for threshold in metric_thresholds:
                total += 1
                threshold_value = threshold.get('value', 0)
                comparison = threshold.get('comparison', 'lte')
                
                # Apply degradation rate tolerance if configured
                adjusted_threshold = threshold_value
                if degradation_rate is not None and degradation_rate > 0:
                    tolerance = threshold_value * (degradation_rate / 100.0)
                    if comparison in ['gte', 'gt']:
                        adjusted_threshold = threshold_value + tolerance
                    elif comparison in ['lte', 'lt']:
                        adjusted_threshold = threshold_value - tolerance
                
                # Convert milliseconds to seconds (except CLS)
                comparison_value = actual_value if metric_full == 'cumulative_layout_shift' else actual_value / 1000
                
                if is_threshold_failed(comparison_value, comparison, adjusted_threshold):
                    failed += 1
                    failed_threshold = dict(actual_value=actual_value, page=step_identifier, **threshold)
                    failed_thresholds.append(failed_threshold)
                    degradation_info = f" (tolerance: {adjusted_threshold:.3f})" if degradation_rate else ""
                    print(f"[THRESHOLD] {threshold['scope']} {threshold['target']} = {comparison_value:.3f} "
                          f"violates {comparison} {threshold_value}{degradation_info} [FAILED]")
                else:
                    degradation_info = f" (tolerance: {adjusted_threshold:.3f})" if degradation_rate else ""
                    print(f"[THRESHOLD] {threshold['scope']} {threshold['target']} = {comparison_value:.3f} "
                          f"complies {comparison} {threshold_value}{degradation_info} [PASSED]")

    # Load all results for reporting
    all_results = load_all_results_data()

    print(f"\n===== Threshold Summary =====")
    print(f"Total evaluated: {total}")
    print(f"Failed: {failed}")
    print(f"=============================\n")
    
    time = datetime.now(tz=pytz.timezone("UTC"))
    exception_message = ""
    status = {"status": "Finished", "percentage": 100, "description": "No thresholds configured for this test"}
    if total:
        violated = round(float(failed / total) * 100, 2)
        print(f"[GATE] Failed rate: {violated}%")
        
        quality_gate_threshold = missed_thresholds_percent
        
        if quality_gate_threshold is None or quality_gate_threshold == 0:
            status = {"status": "Finished", "percentage": 100, "description": f"Quality gate not configured. {failed} of {total} thresholds failed ({violated}%)"}
            print(f"[GATE] Quality gate not configured")
            print(f"[GATE] {failed} of {total} thresholds failed ({violated}%)")
        else:
            print(f"[GATE] Threshold: {quality_gate_threshold}%")
            if violated > quality_gate_threshold:
                exception_message = f"Failed thresholds rate {violated}% exceeds quality gate {quality_gate_threshold}%"
                status = {"status": "Failed", "percentage": 100, "description": f"Missed {violated}% thresholds (gate: {quality_gate_threshold}%)"}
            else:
                status = {"status": "Success", "percentage": 100, "description": f"Successfully met quality gate: {violated}% failed (gate: {quality_gate_threshold}%)"}

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

    # Send email notification if configured
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
