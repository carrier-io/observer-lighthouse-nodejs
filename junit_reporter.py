from junit_xml import TestSuite, TestCase
from os import environ
from carrier_logger import logger


class UIPerformanceJUnitReporter:
    """JUnit XML reporter for UI Performance test results"""
    
    METRICS_UNITS = {
        'load_time': 's',
        'dom_processing': 's',
        'time_to_interactive': 's',
        'first_contentful_paint': 's',
        'largest_contentful_paint': 's',
        'total_blocking_time': 's',
        'cumulative_layout_shift': '',
        'first_visual_change': 's',
        'last_visual_change': 's',
        'time_to_first_byte': 's',
        'interaction_to_next_paint': 's'
    }

    @staticmethod
    def create_junit_report(all_thresholds, failed_thresholds, total_thresholds, failed_count, quality_gate_status, 
                           degradation_rate=None, missed_thresholds_percent=None):
        """Create JUnit XML report for UI performance test results."""
        test_name = environ.get("JOB_NAME", "UI_Performance_Test")
        report_id = environ.get("REPORT_ID", "unknown")
        path = f"/tmp/{report_id}_junit_report.xml"
        
        test_suites = []
        threshold_cases = []
        
        for th in all_thresholds:
            scope = th.get('scope', 'unknown')
            target = th.get('target', 'unknown')
            threshold_value = th.get('value', 0)
            comparison = th.get('comparison', 'lte')
            actual_value = th.get('actual_value', 0)
            page = th.get('page', scope)
            status = th.get('status', 'unknown')
            adjusted_threshold = th.get('adjusted_threshold', threshold_value)

            unit = UIPerformanceJUnitReporter.METRICS_UNITS.get(target, '')
            display_value = actual_value if target == 'cumulative_layout_shift' else actual_value / 1000

            unit_suffix = f" {unit}" if unit else ""
            system_out = f"Value: {display_value:.2f}{unit_suffix}. Threshold value: {threshold_value:.2f}{unit_suffix}"
            
            if degradation_rate and degradation_rate > 0 and adjusted_threshold != threshold_value:
                system_out += f". Degradation rate: {degradation_rate}% (adj. threshold: {adjusted_threshold:.2f}{unit_suffix})"
            
            if scope == page:
                testcase_name = f"Threshold for {scope}, target - {target}"
            else:
                testcase_name = f"Threshold for {scope} ({page}), target - {target}"

            test_case = TestCase(
                name=testcase_name,
                stdout=system_out
            )

            if status == 'failed':
                scope_info = f"{scope} ({page})" if scope != page else scope
                failure_msg = f"{target} for {scope_info} violated threshold {comparison} {adjusted_threshold:.2f}{unit_suffix}. "
                failure_msg += f"Actual value: {display_value:.2f}{unit_suffix}"
                test_case.add_failure_info(failure_msg)

            threshold_cases.append(test_case)

        test_suites.append(TestSuite("Thresholds", threshold_cases))

        try:
            with open(path, 'w') as f:
                TestSuite.to_file(f, test_suites, prettyprint=True)
            logger.info(f"JUnit report created: {path}")
            return path
        except Exception as e:
            logger.error(f"Error creating JUnit report: {str(e)}")
            return None
