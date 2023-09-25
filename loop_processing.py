from util import update_summary_file, all_results_file_exist, load_all_results_data, dump_all_results_data
from os import environ, rename, listdir, path
from traceback import format_exc
import requests
from json import loads
from datetime import datetime

# Environment variables
env_vars = [
    'GALLOPER_PROJECT_ID', 'GALLOPER_URL', 'REPORT_ID', 'TESTS_BUCKET',
    'REPORTS_BUCKET', 'ARTIFACT', 'token', 'tests_path', 'JOB_NAME', 'current_loop'
]
PROJECT_ID, URL, REPORT_ID, BUCKET, REPORTS_BUCKET, TEST, TOKEN, TESTS_PATH, TEST_NAME, CURRENT_LOOP = [environ.get(var)
                                                                                                        for var in
                                                                                                        env_vars]

print(f"Loaded environment variables.")

PATH_TO_FILE = f'/tmp/{TEST}'
CURRENT_LOOP = int(CURRENT_LOOP or 1)

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
    records = []

    print(f"Processing files in 'reports/' directory.")
    for filename in listdir('reports/'):
        file_path = path.join('reports/', filename)
        new_path = f"/{timestamp}_{filename}"
        rename(file_path, new_path)
        print(f"Renamed {filename} to {new_path}")

        if filename.endswith('.json'):
            print(f"Processing JSON file: {filename}")
            with open(new_path, "r") as f:
                json_data = loads(f.read())
                for index, step in enumerate(json_data["steps"]):
                    result, file_name = {}, new_path.split("/")[-1]

                    # Check if 'metrics' key exists
                    if "metrics" in step["lhr"]["audits"]:
                        # Check if 'details' key exists
                        if "details" in step["lhr"]["audits"]["metrics"]:
                            step_type = "page"
                            metrics = step["lhr"]["audits"]["metrics"]["details"]['items'][0]
                            result = {
                                "requests": 1,
                                "domains": 1,
                                "timestamps": timestamp,
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
                            print(f"Processed Page {step['name']} from {filename}")
                        else:
                            print(f"Skipping step {index} {step['name']} in {filename} due to missing 'details' key.")
                            continue
                    else:
                        step_type = "action"
                        result = {
                            "requests": 1,
                            "timestamps": timestamp,
                            "domains": 1,
                            "load_time": 0,
                            "speed_index": 0,
                            "time_to_first_byte": 0,
                            "time_to_first_paint": 0,
                            "dom_content_loading": 0,
                            "dom_processing": 0,
                            "first_contentful_paint": 0,
                            "largest_contentful_paint": 0,
                            "cumulative_layout_shift": round(
                                float(step["lhr"]["audits"]['cumulative-layout-shift']['numericValue']), 3),
                            "total_blocking_time": int(step["lhr"]["audits"]['total-blocking-time']['numericValue']),
                            "first_visual_change": 0,
                            "last_visual_change": 0,
                            "time_to_interactive": 0
                        }
                        print(f"Processed Action {step['name']} from {filename}")
                    for metric in all_results:
                        if (step_type == "action" and metric in ["total_blocking_time", "cumulative_layout_shift"]) \
                                or (step_type == "page" and metric not in ["total_blocking_time",
                                                                           "cumulative_layout_shift"]):
                            all_results[metric].append(result.get(metric, 0))

                    data = {
                        "name": step["name"],
                        "type": step_type,
                        "loop": CURRENT_LOOP,
                        "identifier": f'{step["lhr"]["requestedUrl"]}@{step["name"]}',
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
                        params=s3_config, files={'file': open(new_path, 'rb')},
                        allow_redirects=True,
                        headers={'Authorization': f"Bearer {TOKEN}"}
                    )
                    print(f"Uploaded {new_path} to reports.")
                except Exception as e:
                    print(f"Failed to upload {new_path}. Error: {e}")

                try:
                    requests.post(
                        f"{URL}/api/v1/artifacts/artifacts/{PROJECT_ID}/reports",
                        params=s3_config, files={'file': open(new_path.replace('.json', '.html'), 'rb')},
                        allow_redirects=True,
                        headers={'Authorization': f"Bearer {TOKEN}"}
                    )
                    print(f"Uploaded {new_path} to reports.")
                except Exception as e:
                    print(f"Failed to upload {new_path}. Error: {e}")

    update_summary_file(REPORT_ID, records)
    dump_all_results_data(all_results)
    print(f"Finished processing all files in 'reports/' directory.")

except Exception as e:
    print(f"An error occurred: {e}")
