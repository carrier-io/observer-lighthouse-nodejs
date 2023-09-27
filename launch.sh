#!/bin/bash

args=$@
export reports=""
IFS=" " read -ra PARAMS <<< "$args"
for index in "${!PARAMS[@]}"
do
    if [[ ${PARAMS[index]} == "-tid" ]]; then
        test_id=${PARAMS[index + 1]}
    fi
    if [[ ${PARAMS[index]} == "-sc" ]]; then
        script_name=${PARAMS[index + 1]}
    fi
    if [[ ${PARAMS[index]} == "-r" ]]; then
        reports=$reports";"${PARAMS[index + 1]}
    fi
    if [[ ${PARAMS[index]} == "-l" ]]; then
        loops=${PARAMS[index + 1]}
    fi
    if [[ ${PARAMS[index]} == "-a" ]]; then
        aggregation=${PARAMS[index + 1]}
    fi
done

python3 minio_tests_reader.py
echo "Scripts downloaded"
echo "Start test"

for (( c=1; c<=$loops; c++ ))
do
  export current_loop=$c
  echo "Start iteration $c"
  node /$script_name $custom_cmd
  echo "Processing results for $c iteration!"
  python3 loop_processing.py $test_id $reports
  echo "Finish iteration $c"
done


echo "Test is done. Results processing..."
python3 post_processing.py $test_id $reports
