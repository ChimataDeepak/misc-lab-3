#!/usr/bin/env bash
# Runs the MapReduce job with Hadoop Streaming (local job runner, single container).
# apache/hadoop:3.4.1 publishes amd64 only -> on Apple Silicon it runs under emulation.
set -euo pipefail
cd "$(dirname "$0")/.."
DATA=${1:-data/receipts.csv}
mkdir -p data
rm -rf data/hadoop-out
# The image runs as user hadoop (uid 1000); on a Linux host the checkout belongs to someone else (CI: uid 1001),
# so let the container write data/ and leave its output removable by the host user. The local job runner shares
# this filesystem, so the scripts are referenced by path (-files would symlink them into the read-only /work).
chmod a+rwx data
docker run --rm --platform linux/amd64 -v "$PWD":/work -w /work apache/hadoop:3.4.1 bash -c '
  set -e
  umask 000
  JAR=$(ls /opt/hadoop/share/hadoop/tools/lib/hadoop-streaming-*.jar)
  hadoop jar "$JAR" -D mapreduce.framework.name=local -D fs.defaultFS=file:/// \
    -mapper "awk -f /work/hadoop/mapper.awk" -reducer "awk -f /work/hadoop/reducer.awk" \
    -input '"$DATA"' -output data/hadoop-out'
cat data/hadoop-out/part-*
