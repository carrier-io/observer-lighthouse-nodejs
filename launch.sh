#!/bin/sh

mkdir -p reports
export reports="/tmp/reports"

set -- $@ $custom_cmd  # Include custom_cmd in the list of arguments to be parsed
echo "CMD with value: $custom_cmd"
npm_args=""
region_args=""
test_id=""
script_name=""
loops=1
aggregation=""
default_region="en-US.de-CH.de-DE.en-CH.en-GB.fr-CH.fr-FR.pt-BR.es-MX.en-CA.zh-HK" # Set your default region here

while [ "$#" -gt 0 ]; do
    case "$1" in
        -tid)
            test_id="$2"
            echo "Detected -tid with value: $test_id"
            shift
            ;;
        -sc)
            script_name="$2"
            echo "Detected -sc with value: $script_name"
            shift
            ;;
        -r)
            reports="$2"
            echo "Detected -r with value: $2"
            shift
            ;;
        -l)
            loops="$2"
            echo "Detected -l with value: $loops"
            shift
            ;;
        -a)
            aggregation="$2"
            echo "Detected -a with value: $aggregation"
            shift
            ;;
        --*)
            npm_args="$npm_args $1 $2" # Append both the flag and its value
            echo "Added custom arg: $1 with value: $2 to npm_args"
            shift
            ;;
        *)
            # Append region codes to a space-delimited string
            if [[ "$1" =~ ^[a-zA-Z]{2}-[A-Z]{2}$ ]]; then
                region_args="$region_args $1"
            else
                echo "Unrecognized argument: $1"
            fi
            ;;
    esac
    shift
done

echo "Executing: python3 minio_tests_reader.py"
python3 minio_tests_reader.py
echo "Scripts downloaded"
echo "Start test"

# Wait for the /$script_name file to exist
timeout=10
while [ ! -f "/$script_name" ] && [ $timeout -gt 0 ]; do
    sleep 1
    timeout=$((timeout - 1))
done

if [ $timeout -eq 0 ]; then
    echo "File /$script_name not found within 10 seconds. Exiting."
    exit 1
else
    echo "File /$script_name found. Continuing with the test."
fi

c=1
region_args=$(echo $default_region | tr '.' '\n')
while [ $c -le $loops ]; do
    export current_loop=$c
    # Get the region for the current iteration
    current_region=$(echo "$region_args" | sed -n "${c}p")
    if [ -z "$current_region" ]; then
        current_region=$default_region
    fi

    echo "Start iteration $c for region $current_region"
    export REGION=$current_region  # Set the REGION environment variable
    echo "Executing: npm test $script_name with arguments: $npm_args and region: $REGION"
    eval "npm test $script_name -- $npm_args --current_loop=$current_loop --regions=$REGION"  # Use eval to correctly expand npm_args
    echo "Processing results for iteration $c in region $REGION"
    echo "Executing: python3 loop_processing.py \"$test_id\" \"$reports\" \"$REGION\""
    python3 loop_processing.py "$test_id" "$reports" "$REGION"
    echo "Finish iteration $c"
    c=$((c + 1))
done
echo "Test is done. Results processing..."
echo "Executing: python3 post_processing.py \"$test_id\" \"$reports\""
python3 post_processing.py "$test_id" "$reports"
