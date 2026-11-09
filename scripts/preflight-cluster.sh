#!/usr/bin/env bash
set -euo pipefail
echo '== Nodes and storage class =='
kubectl get nodes
kubectl get storageclass longhorn
echo '== Longhorn volume robustness =='
kubectl -n longhorn-system get volumes.longhorn.io -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUSTNESS:.status.robustness,SIZE:.spec.size
echo '== Longhorn capacity policies =='
kubectl -n longhorn-system get settings.longhorn.io storage-minimal-available-percentage storage-reserved-percentage-for-default-disk -o custom-columns=NAME:.metadata.name,VALUE:.value
echo '== Elasticsearch host prerequisite (must be >= 262144 on every schedulable node) =='
for node in scharnhorst gneisenau; do
  ssh "aaron@${node}.hs.ahcomputing.com" 'cat /proc/sys/vm/max_map_count'
done
echo 'No resources were changed. Do not apply manifests until the prerequisite and capacity are confirmed.'
