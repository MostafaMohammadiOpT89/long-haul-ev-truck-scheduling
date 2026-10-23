# Running Experiments on Solstorm Cluster

This guide explains how to run all three TDSPEVRP experiments on the Solstorm cluster at NTNU.

## Overview

The master runner script (`run_all_experiments.py`) will execute all three experiments sequentially:

1. **Partial Recharge - Main Algorithm** (`enhanced_main.py`)
2. **Partial Recharge - Greedy Scheduler** (`greedy_scheduler.py`)
3. **Full Recharge - Main Algorithm** (`enhanced_main.py`)

## Files Created

- `run_all_experiments.py` - Master Python script that runs all experiments
- `run_experiments.sh` - SLURM batch script for submitting to Solstorm
- `SOLSTORM_RUNNER_README.md` - This file

## Quick Start

### Option 1: Using SLURM (Recommended for Solstorm)

1. **Upload your project to Solstorm:**
   ```bash
   # On your local machine, compress the project
   tar -czf TDSPEVRP_Code_Final.tar.gz Code_Final/
   
   # Upload to Solstorm (adjust path as needed)
   scp TDSPEVRP_Code_Final.tar.gz username@solstorm.hpc.ntnu.no:/cluster/home/username/
   ```

2. **On Solstorm, extract and navigate:**
   ```bash
   ssh username@solstorm.hpc.ntnu.no
   cd /cluster/home/username/
   tar -xzf TDSPEVRP_Code_Final.tar.gz
   cd Code_Final/
   ```

3. **Set up Python virtual environment:**
   ```bash
   # Check available Python versions
   module avail python
   
   # Load Python module (adjust version as needed)
   module load python/3.10.4
   
   # Verify Python version
   python3 --version
   
   # Create virtual environment in project folder
   python3 -m venv .venv
   
   # Activate virtual environment
   source .venv/bin/activate
   
   # Upgrade pip
   pip install --upgrade pip
   
   # Install all required packages
   pip install -r requirements.txt
   ```

4. **Modify the SLURM script if needed:**
   - Edit `run_experiments.sh` to adjust:
     - Time limit (currently 48 hours)
     - Memory requirements (currently 16GB)
     - CPU cores (currently 1)
     - Python module loading (uncomment and adjust)

5. **Submit the job:**
   ```bash
   sbatch run_experiments.sh
   ```

6. **Monitor the job:**
   ```bash
   # Check job status
   squeue -u $USER
   
   # View output (replace JOBID with actual job ID)
   tail -f tdspevrp_experiments_JOBID.out
   
   # View errors
   tail -f tdspevrp_experiments_JOBID.err
   ```

### Option 2: Using Screen (Interactive Session)

`screen` allows you to run long processes that continue even if you disconnect. This is useful for interactive sessions or when you want to monitor progress in real-time.

**Basic Screen Commands:**

```bash
# Start a new screen session
screen -S tdspevrp_experiments

# Or with a descriptive name
screen -S tdspevrp

# List all screen sessions
screen -ls

# Reattach to a session (replace SESSION_NAME with your session name)
screen -r tdspevrp_experiments

# Reattach to a detached session by ID
screen -r SESSION_ID

# Detach from current session (keep it running)
# Press: Ctrl+A, then press D

# Kill a screen session
screen -X -S tdspevrp_experiments quit
```

**Running Experiments with Screen:**

```bash
# 1. SSH into Solstorm
ssh username@solstorm.hpc.ntnu.no

# 2. Navigate to project directory
cd /path/to/Code_Final/

# 3. Load Python and activate virtual environment
module load python/3.10.4
source .venv/bin/activate

# 4. Start a new screen session
screen -S tdspevrp

# 5. Run the master script
python3 run_all_experiments.py

# 6. Detach from screen (Ctrl+A, then D)
# The process will continue running

# 7. Later, reattach to see progress
screen -r tdspevrp
```

**Screen Keyboard Shortcuts:**

- `Ctrl+A` then `D` - Detach from screen (keeps process running)
- `Ctrl+A` then `C` - Create a new window
- `Ctrl+A` then `N` - Next window
- `Ctrl+A` then `P` - Previous window
- `Ctrl+A` then `"` - List all windows
- `Ctrl+A` then `K` - Kill current window
- `Ctrl+A` then `\` - Kill all windows and exit screen
- `Ctrl+A` then `?` - Show help

**Tips:**
- Always give your screen session a descriptive name with `-S name`
- Use `screen -ls` to see all your sessions
- You can have multiple screen sessions running different tasks
- Screen sessions persist even after logging out

### Option 3: Direct Python Execution (Background)

If you prefer to run directly without SLURM or screen:

```bash
# Navigate to project root
cd /path/to/Code_Final/

# Load Python and activate venv
module load python/3.10.4
source .venv/bin/activate

# Run the master script in background
nohup python3 run_all_experiments.py > run_all_experiments.log 2>&1 &

# Check the process
ps aux | grep run_all_experiments

# View output
tail -f run_all_experiments.log
```

## Output Files

Each experiment will create its own results:

- **Partial Recharge - Main Algorithm:**
  - `Partial Recharge/EVTDSPalgorithmmain/Results/enhanced_results_TIMESTAMP.json`
  - `Partial Recharge/EVTDSPalgorithmmain/Results/enhanced_results_TIMESTAMP.csv`

- **Partial Recharge - Greedy Scheduler:**
  - `Partial Recharge/EVTDSPalgorithmmain/Results/Greedy_Scheduler_Results/greedy_results_TIMESTAMP.json`
  - `Partial Recharge/EVTDSPalgorithmmain/Results/Greedy_Scheduler_Results/greedy_results_TIMESTAMP.csv`

- **Full Recharge - Main Algorithm:**
  - `Full Recharge/EVTDSPalgorithmmain/Results/enhanced_results_TIMESTAMP.json`
  - `Full Recharge/EVTDSPalgorithmmain/Results/enhanced_results_TIMESTAMP.csv`

## Configuration

The experiments use the following configuration (already set in the scripts):

- **Energy consumption (kWh/km):** [1.12, 1.49, 2.08]
- **Battery capacities (kWh):** [750, 1000]
- **Charging power (kW):** [350, 500, 1000]
- **Inter-CS spacing (km):** [40, 50, 60, 70, 80, 90, 100]
- **Speed:** 60 km/h (for greedy scheduler)

## Troubleshooting

### Python Module Not Found

If you get import errors, you may need to:
1. Install required packages in a virtual environment
2. Load the correct Python module on Solstorm
3. Adjust the module loading in `run_experiments.sh`

### Out of Memory

If jobs fail due to memory:
- Increase `--mem=16G` in `run_experiments.sh`
- Or reduce the number of instances being processed

### Time Limit Exceeded

If jobs are killed due to time limits:
- Increase `--time=48:00:00` in `run_experiments.sh`
- Or process instances in smaller batches

### Path Issues

Make sure all relative paths are correct. The scripts automatically change to each script's directory before running.

## Notes

- The master runner will continue even if one script fails (you'll see warnings)
- Each script runs from its own directory to ensure relative paths work correctly
- All output is logged with timestamps
- The master script provides a summary at the end showing which experiments succeeded/failed

## Contact

For Solstorm-specific issues, contact NTNU HPC support.

