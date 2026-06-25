#!/bin/bash
#SBATCH --job-name=tdspevrp_experiments
#SBATCH --output=tdspevrp_experiments_%j.out
#SBATCH --error=tdspevrp_experiments_%j.err
#SBATCH --time=48:00:00
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
# OPTIONAL: pin to specific nodes (remove if you want the scheduler to choose)
#SBATCH --nodelist=compute-6-3,compute-6-4,compute-6-6
# Start in the project directory so relative paths work
#SBATCH --chdir=/home/mostafm/Synchronization_EVTDS/Code_Final
# Don’t inherit a polluted login environment
#SBATCH --export=NONE

set -euo pipefail

echo "=========================================="
echo "Job ID:        ${SLURM_JOB_ID}"
echo "Job Name:      ${SLURM_JOB_NAME}"
echo "Nodes:         ${SLURM_NODELIST}"
echo "CPUs:          ${SLURM_CPUS_PER_TASK}"
echo "Mem:           ${SLURM_MEM_PER_NODE}"
echo "Partition:     ${SLURM_JOB_PARTITION}"
echo "Start:         $(date)"
echo "Work dir:      $(pwd)"
echo "=========================================="

module purge
module load Python/3.10.8-GCCcore-12.2.0
python3 --version

# Create the venv once if it doesn't exist, then activate
if [ ! -d ".venv" ]; then
  echo "Creating project venv..."
  python3 -m venv .venv
fi
source .venv/bin/activate
python3 -c "import sys; print('Python in venv:', sys.version)"

# Install/refresh requirements (comment out after first successful install)
if [ -f requirements.txt ]; then
  pip install --upgrade pip
  pip install -r requirements.txt
else
  echo "WARNING: requirements.txt not found; continuing."
fi

echo "Launching experiments..."
# srun binds your allocated CPUs/mem to the process
srun --cpu-bind=cores python3 run_all_experiments.py

echo "=========================================="
echo "End: $(date)"
echo "Job finished."
echo "=========================================="
