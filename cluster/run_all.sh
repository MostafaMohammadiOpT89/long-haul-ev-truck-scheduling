#!/bin/bash
# Distribute all job JSONs to Solstorm compute nodes and run them via SSH (FOMO-style).
#
# Usage (manual nodes):
#   ./cluster/run_all.sh -r 4 -n 1,2,3,4
#
# Usage (auto nodes via gstat load filter):
#   ./cluster/run_all.sh
#
# Required:
# - Run from repository root on solstorm-login
# - Repo should be on shared storage, e.g. /storage/users/$USER/...
#
# Notes:
# - Reserves nodes using lockdirs under /storage/users/$USER/tdspevrp_node_locks
# - Writes outputs under Results/Cluster/

set -euo pipefail

TIMEOUT="24h"
PROJECT_DIR="$(pwd)"

NODE_ROWS="4"          # rows to pick from (auto mode)
MAX_NODES=5            # maximum number of nodes (auto mode)
LOAD_LIMIT=0.008       # don't use nodes with load higher than this (auto mode)

LOCK_ROOT="/storage/users/$USER/tdspevrp_node_locks"

RUNID=""
ROW=""
NODENUMS=""

while getopts ":r:n:j:t:" arg; do
  case ${arg} in
    r) ROW=${OPTARG} ;;
    n) NODENUMS=$(echo ${OPTARG} | awk -v RS='[,\n]' -F: 'NF == 1; NF == 2 { for (i = $1; i <= $2; ++i) print i }') ;;
    j) RUNID=${OPTARG} ;;
    t) TIMEOUT=${OPTARG} ;;
    :)
      echo "$0: Must supply an argument to -$OPTARG." >&2
      exit 1
      ;;
    ?)
      echo "Invalid option: -${OPTARG}."
      exit 2
      ;;
  esac
done

if [ -z "${RUNID}" ]; then
  echo "ERROR: missing -j <runid>. Create jobs first with: python3 cluster/create_jobs.py"
  echo "Then pass -j <runid> (same timestamp folder under cluster/jobs/)."
  exit 1
fi

JOBS_DIR="${PROJECT_DIR}/cluster/jobs/${RUNID}"
if [ ! -d "${JOBS_DIR}" ]; then
  echo "ERROR: jobs dir not found: ${JOBS_DIR}"
  exit 1
fi

mkdir -p "${LOCK_ROOT}"

# Build node list
NODES=()

if [ -n "${ROW}" ] && [ -n "${NODENUMS}" ]; then
  for i in ${NODENUMS}; do
    NODES+=("compute-${ROW}-${i}.local")
  done
else
  if ! command -v gstat >/dev/null 2>&1; then
    echo "ERROR: gstat not found; use manual mode: -r <row> -n <nodes>"
    exit 1
  fi
  mapfile -t CANDIDATES < <(gstat -i 10.1.1.1 -a1l \
    | grep "compute-[${NODE_ROWS}]" \
    | awk -v limit=${LOAD_LIMIT} '{ if(strtonum($7) < limit) printf("%s\n", $1); }' \
    | sort -r \
    | head -n ${MAX_NODES})

  for n in "${CANDIDATES[@]}"; do
    NODES+=("${n}")
  done
fi

if [ ${#NODES[@]} -eq 0 ]; then
  echo "ERROR: no nodes selected"
  exit 1
fi

# Reserve nodes (skip if already reserved)
RESERVED=()
for node in "${NODES[@]}"; do
  lockdir="${LOCK_ROOT}/${node}.lockdir"
  if mkdir "${lockdir}" 2>/dev/null; then
    echo "Reserved node: ${node}"
    RESERVED+=("${node}")
  else
    echo "Skipping node (already reserved): ${node}"
  fi
done

if [ ${#RESERVED[@]} -eq 0 ]; then
  echo "ERROR: all selected nodes are already reserved"
  exit 1
fi

cleanup() {
  for node in "${RESERVED[@]}"; do
    rm -rf "${LOCK_ROOT}/${node}.lockdir" || true
  done
}
trap cleanup EXIT

# Collect job files
mapfile -t JOBS < <(ls "${JOBS_DIR}"/job_*.json 2>/dev/null | sort)
num_nodes=${#RESERVED[@]}
num_jobs=${#JOBS[@]}

if [ ${num_jobs} -eq 0 ]; then
  echo "ERROR: no job_*.json files found in ${JOBS_DIR}"
  exit 1
fi

runs_per_node=$(python3 -c "import math; print(math.ceil(${num_jobs} / ${num_nodes}))")

echo "Runid: ${RUNID}"
echo "Jobs: ${num_jobs}"
echo "Nodes: ${num_nodes}"
echo "Jobs per node: ${runs_per_node}"
echo

node_counter=0
job_counter=0

# Clean previous node logs for this runid (local)
rm -f "Results/Cluster/${RUNID}".*.out "Results/Cluster/${RUNID}".*.err || true
mkdir -p "Results/Cluster"

while [ ${job_counter} -lt ${num_jobs} ]; do
  node="${RESERVED[$node_counter]}"
  node_counter=$((node_counter + 1))
  if [ ${node_counter} -ge ${num_nodes} ]; then
    node_counter=0
  fi

  echo "Sending to ${node}:"
  args=()
  for ((i=0; i<${runs_per_node}; i++)); do
    if [ ${job_counter} -ge ${num_jobs} ]; then
      break
    fi
    job="${JOBS[$job_counter]}"
    echo "  ${job}"
    args+=("${job}")
    job_counter=$((job_counter + 1))
  done

  # Run remotely
  ssh "${node}" "cd \"${PROJECT_DIR}\"; shopt -s huponexit; timeout \"${TIMEOUT}\" python3 cluster/run_job.py --runid \"${RUNID}\" ${args[*]}" \
    > "Results/Cluster/${RUNID}.${node}.out" \
    2> "Results/Cluster/${RUNID}.${node}.err" &

  echo
done

trap "kill 0" SIGINT
echo "Waiting for completion..."
wait

echo "All nodes finished."
echo "Raw outputs:"
echo "  Results/Cluster/output_${RUNID}.jsonl"
echo "  Results/Cluster/output_${RUNID}.csv"

