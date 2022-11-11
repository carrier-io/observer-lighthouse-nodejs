import math
import requests
from traceback import format_exc
import os
from json import loads, dumps


def is_threshold_failed(actual, comparison, expected):
    if comparison == 'gte':
        return actual >= expected
    elif comparison == 'lte':
        return actual <= expected
    elif comparison == 'gt':
        return actual > expected
    elif comparison == 'lt':
        return actual < expected
    elif comparison == 'eq':
        return actual == expected
    return False


def get_aggregated_value(aggregation, metrics):
    if aggregation == 'max':
        return max(metrics)
    elif aggregation == 'min':
        return min(metrics)
    elif aggregation == 'avg':
        return int(sum(metrics) / len(metrics))
    elif aggregation == 'pct95':
        return percentile(metrics, 95)
    elif aggregation == 'pct50':
        return percentile(metrics, 50)
    else:
        raise Exception(f"No such aggregation {aggregation}")


def percentile(data, percentile):
    size = len(data)
    return sorted(data)[int(math.ceil((size * percentile) / 100)) - 1]


def upload_test_results(test_name, galloper_url, project_id, token, report_id):
    bucket = test_name.replace("_", "").lower()
    import gzip
    import shutil
    with open(f"/tmp/{report_id}.csv", 'rb') as f_in:
        with gzip.open(f"/tmp/{report_id}.csv.gz", 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)

    upload_file(f"{report_id}.csv.gz", "/tmp/", galloper_url, project_id, token, bucket=bucket)


def upload_file(file_name, file_path, galloper_url, project_id, token, bucket="reports"):

    file = {'file': open(f"{file_path}{file_name}", 'rb')}
    try:
        requests.post(f"{galloper_url}/api/v1/artifacts/artifacts/{project_id}/{bucket}",
                      files=file, allow_redirects=True, headers={'Authorization': f"Bearer {token}"})
    except Exception:
        print(format_exc())


def update_summary_file(report_id, records):
    file_exists = os.path.exists(f"/tmp/{report_id}.csv")
    header = "timestamp,name,identifier,type,loop,load_time,dom,tti,fcp,lcp,cls,tbt,fvc,lvc,file_name\n".encode('utf-8')
    with open(f"/tmp/{report_id}.csv", 'ab+') as f:
        if not file_exists:
            f.write(header)
        for each in records:
            f.write(
                f"{each['metrics']['timestamps']},{each['name']},{each['identifier']},{each['type']},{each['loop']},"
                f"{each['metrics']['load_time']},{each['metrics']['dom_processing']},"
                f"{each['metrics']['time_to_interactive']},{each['metrics']['first_contentful_paint']},"
                f"{each['metrics']['largest_contentful_paint']},"
                f"{each['metrics']['cumulative_layout_shift']},{each['metrics']['total_blocking_time']},"
                f"{each['metrics']['first_visual_change']},{each['metrics']['last_visual_change']},"
                f"{each['file_name']}\n".encode('utf-8'))


def get_summary_file_lines(report_id):
    with open(f"/tmp/{report_id}.csv", 'rb') as f:
        return f.readlines()


def all_results_file_exist():
    return os.path.exists("/tmp/all_results.json")


def load_all_results_data():
    with open("/tmp/all_results.json", "r") as f:
        return loads(f.read())


def dump_all_results_data(all_results):
    with open("/tmp/all_results.json", "w") as f:
        return f.write(dumps(all_results))
