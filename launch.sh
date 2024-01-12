#!/bin/sh
export reports=""

while [ $# -gt 0 ]; do
    case "$1" in
        -tid)
            test_id="$2"
            shift 2
            ;;
        -sc)
            script_name="$2"
            shift 2
            ;;
        -r)
            reports="${reports};$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

python3 minio_tests_reader.py
echo "Scripts downloaded"
echo "Start test"
npx mocha --timeout 30000 "/$script_name" $CMD
echo "Test is done. Results processing..."
python3 results_processing.py "$test_id" "$reports"