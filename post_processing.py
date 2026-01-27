from carrier_logger import logger
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
from junit_reporter import UIPerformanceJUnitReporter
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
        logger.debug(f"Fetching test configuration from: {test_config_url}")
        test_res = requests.get(
            test_config_url,
            headers={'Authorization': f"bearer {TOKEN}"})
        logger.debug(f"Test configuration response status: {test_res.status_code}")
        
        if test_res.status_code == 200:
            test_data = test_res.json()
            if isinstance(test_data, dict) and 'rows' in test_data:
                for test in test_data['rows']:
                    if test.get('name') == TEST_NAME:
                        logger.info(f"Found configuration for test '{TEST_NAME}'")
                        integrations_config = test.get('integrations', {})
                        processing_config = integrations_config.get('processing', {})
                        quality_gate_config = processing_config.get('quality_gate', {})
                        
                        degradation_rate = quality_gate_config.get('degradation_rate')
                        missed_thresholds_percent = quality_gate_config.get('missed_thresholds')
                        
                        logger.info(f"Quality gate configuration - degradation_rate: {degradation_rate}, missed_thresholds: {missed_thresholds_percent}")
                        break
                else:
                    logger.warning(f"Test '{TEST_NAME}' not found in configuration response")
            else:
                logger.warning(f"Unexpected test configuration response format: {type(test_data)}")
        else:
            logger.error(f"Failed to fetch test configuration: HTTP {test_res.status_code}")
    except Exception as e:
        logger.error(f"Error fetching test configuration: {str(e)}")
        logger.debug(format_exc())
    
    # Fetch environment from report
    try:
        report_url = f"{URL}/api/v1/ui_performance/reports/{PROJECT_ID}?report_id={REPORT_ID}"
        logger.debug(f"Fetching report environment from: {report_url}")
        report_res = requests.get(
            report_url,
            headers={'Authorization': f"bearer {TOKEN}"})
        logger.debug(f"Report response status: {report_res.status_code}")
        
        if report_res.status_code == 200:
            report_data = report_res.json()
            ENV = report_data.get('environment')
            logger.info(f"Retrieved environment from report: {ENV}")
        else:
            logger.warning(f"Failed to fetch report environment: HTTP {report_res.status_code}")
    except Exception as e:
        logger.error(f"Error fetching report environment: {str(e)}")
        logger.debug(format_exc())

    # Fetch thresholds from API
    res = None
    try:
        threshold_url = f"{URL}/api/v1/ui_performance/thresholds/{PROJECT_ID}?test={TEST_NAME}&env={ENV}"
        logger.debug(f"Fetching thresholds from: {threshold_url}")
        res = requests.get(
            threshold_url,
            headers={'Authorization': f"bearer {TOKEN}"})
        logger.debug(f"Thresholds response status: {res.status_code}")
    except Exception as e:
        logger.error(f"Exception during thresholds request: {str(e)}")
        logger.debug(format_exc())

    if not res or res.status_code != 200:
        if res:
            logger.warning(f"Thresholds API returned status: {res.status_code}")
            if res.status_code == 403:
                logger.error(f"Access forbidden - check token permissions")
            elif res.status_code == 404:
                logger.warning(f"Report not found for REPORT_ID: {REPORT_ID}")
            if res.text:
                logger.debug(f"Response body: {res.text[:500]}")
        else:
            logger.error(f"No response from thresholds API")
        thresholds = []
    else:
        try:
            response_data = res.json()
            # Handle response format: could be a dict with 'rows' or a list
            if isinstance(response_data, dict) and 'rows' in response_data:
                thresholds = response_data['rows']
                logger.info(f"Fetched {len(thresholds)} thresholds from API")
            elif isinstance(response_data, list):
                thresholds = response_data
                logger.info(f"Fetched {len(thresholds)} thresholds from API")
            else:
                thresholds = []
                logger.warning(f"Unexpected thresholds response format: {type(response_data)}")
        except ValueError:
            thresholds = []
            logger.error(f"Failed to parse JSON response from thresholds API")
    
    logger.info(f"Fetched {len(thresholds)} thresholds for test='{TEST_NAME}', env='{ENV}'")

    logger.debug("===== Thresholds =====")
    for each in thresholds:
        logger.debug(each)
    logger.debug("======================")

    failed_thresholds = []
    all_evaluated_thresholds = []
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

    logger.debug("===== Summary Results =====")
    logger.debug(summary_results)
    logger.debug("===========================")
    
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
                
                # Create threshold record for reporting
                threshold_record = dict(
                    actual_value=actual_value,
                    page=step_identifier,
                    adjusted_threshold=adjusted_threshold,
                    **threshold
                )
                
                if is_threshold_failed(comparison_value, comparison, adjusted_threshold):
                    failed += 1
                    threshold_record['status'] = 'failed'
                    failed_thresholds.append(threshold_record)
                    all_evaluated_thresholds.append(threshold_record)
                    degradation_info = f" (tolerance: {adjusted_threshold:.3f})" if degradation_rate else ""
                    logger.warning(f"{threshold['scope']} {threshold['target']} = {comparison_value:.3f} "
                          f"violates {comparison} {threshold_value}{degradation_info} [FAILED]")
                else:
                    threshold_record['status'] = 'passed'
                    all_evaluated_thresholds.append(threshold_record)
                    degradation_info = f" (tolerance: {adjusted_threshold:.3f})" if degradation_rate else ""
                    logger.debug(f"{threshold['scope']} {threshold['target']} = {comparison_value:.3f} "
                          f"complies {comparison} {threshold_value}{degradation_info} [PASSED]")

    # Load all results for reporting
    all_results = load_all_results_data()

    logger.info(f"\n===== Threshold Summary =====")
    logger.info(f"Total evaluated: {total}")
    logger.info(f"Failed: {failed}")
    logger.info(f"=============================")
    
    time = datetime.now(tz=pytz.timezone("UTC"))
    exception_message = ""
    status = {"status": "Finished", "percentage": 100, "description": "No thresholds configured for this test"}
    if total:
        violated = round(float(failed / total) * 100, 2)
        logger.info(f"[GATE] Failed rate: {violated}%")
        
        quality_gate_threshold = missed_thresholds_percent
        
        if quality_gate_threshold is None or quality_gate_threshold == 0:
            status = {"status": "Finished", "percentage": 100, "description": f"Quality gate not configured. {failed} of {total} thresholds failed ({violated}%)"}
            logger.info(f"Quality gate not configured")
            logger.info(f"{failed} of {total} thresholds failed ({violated}%)")
        else:
            logger.info(f"Quality gate threshold: {quality_gate_threshold}%")
            if violated > quality_gate_threshold:
                exception_message = f"Failed thresholds rate {violated}% exceeds quality gate {quality_gate_threshold}%"
                status = {"status": "Failed", "percentage": 100, "description": f"Missed {violated}% thresholds (gate: {quality_gate_threshold}%)"}
                logger.error(f"Quality gate FAILED: {violated}% failed thresholds exceeds gate {quality_gate_threshold}%")
            else:
                status = {"status": "Success", "percentage": 100, "description": f"Successfully met quality gate: {violated}% failed (gate: {quality_gate_threshold}%)"}
                logger.info(f"Quality gate PASSED: {violated}% failed thresholds within gate {quality_gate_threshold}%")

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
    except Exception as e:
        logger.error(f"Failed to update report: {e}")
        logger.debug(format_exc())

    # Generate JUnit report only if quality gate is configured
    if missed_thresholds_percent is not None and missed_thresholds_percent > 0:
        try:
            junit_report_path = UIPerformanceJUnitReporter.create_junit_report(
                all_thresholds=all_evaluated_thresholds,
                failed_thresholds=failed_thresholds,
                total_thresholds=total,
                failed_count=failed,
                quality_gate_status=status,
                degradation_rate=degradation_rate,
                missed_thresholds_percent=missed_thresholds_percent
            )
            
            # Upload JUnit report to artifacts
            if junit_report_path:
                try:
                    bucket = TEST_NAME.replace("_", "").lower()
                    upload_url = f"{URL}/api/v1/artifacts/artifacts/{PROJECT_ID}/{bucket}"
                    headers = {'Authorization': f'bearer {TOKEN}'}
                    with open(junit_report_path, 'rb') as f:
                        files = {'file': f}
                        upload_response = requests.post(
                            upload_url, 
                            params=s3_config, 
                            allow_redirects=True, 
                            files=files, 
                            headers=headers
                        )
                    logger.info(f"JUnit report uploaded to {upload_url}, Status: {upload_response.status_code}")
                except Exception as upload_error:
                    logger.error(f"Failed to upload JUnit report: {str(upload_error)}")
                    logger.debug(format_exc())
        except Exception as e:
            logger.error(f"Failed to create JUnit report: {str(e)}")
            logger.debug(format_exc())
    else:
        logger.info(f"Quality gate not configured - JUnit report generation skipped")

    # Send email notification if configured
    if integrations and integrations.get("reporters") and "reporter_email" in integrations["reporters"].keys():
        email_notification_id = integrations["reporters"]["reporter_email"].get("task_id")
        if email_notification_id:
            emails = integrations["reporters"]["reporter_email"].get("recipients", [])
            if emails:
                logger.info("Preparing email notification")
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
                logger.info(f"Email notification sent: {res.status_code}")
                logger.debug(f"Email response: {res.text}")

    if integrations and integrations.get("reporters") and "reporter_engagement" in integrations['reporters'].keys():
        if URL and TOKEN and PROJECT_ID and failed_thresholds:
            logger.info("Preparing engagement reporter notification")
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
            logger.info("Engagement report findings submitted")

except Exception as e:
    logger.error(f"Post-processing failed: {e}")
    logger.debug(format_exc())
