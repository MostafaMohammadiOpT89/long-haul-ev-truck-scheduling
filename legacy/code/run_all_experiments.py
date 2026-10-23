#!/usr/bin/env python3
"""
Master Runner Script for TDSPEVRP Experiments
==============================================

This script runs all three main experiments sequentially:
1. Partial Recharge - Main Algorithm (enhanced_main.py)
2. Partial Recharge - Greedy Scheduler (greedy_scheduler.py)
3. Full Recharge - Main Algorithm (enhanced_main.py)

Usage:
    python run_all_experiments.py

For Solstorm cluster:
    sbatch run_experiments.sh  (if using SLURM)
    or
    python run_all_experiments.py > run_all_experiments.log 2>&1 &
"""

import os
import sys
import subprocess
import time
from datetime import datetime

# Get the root directory of the project
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

# Define the three scripts to run
SCRIPTS = [
    {
        'name': 'Partial Recharge - Main Algorithm',
        'path': os.path.join(ROOT_DIR, 'Partial Recharge', 'EVTDSPalgorithmmain', 'enhanced_main.py'),
        'dir': os.path.join(ROOT_DIR, 'Partial Recharge', 'EVTDSPalgorithmmain')
    },
    {
        'name': 'Partial Recharge - Greedy Scheduler',
        'path': os.path.join(ROOT_DIR, 'Partial Recharge', 'EVTDSPalgorithmmain', 'greedy_scheduler.py'),
        'dir': os.path.join(ROOT_DIR, 'Partial Recharge', 'EVTDSPalgorithmmain')
    },
    {
        'name': 'Full Recharge - Main Algorithm',
        'path': os.path.join(ROOT_DIR, 'Full Recharge', 'EVTDSPalgorithmmain', 'enhanced_main.py'),
        'dir': os.path.join(ROOT_DIR, 'Full Recharge', 'EVTDSPalgorithmmain')
    }
]

def print_separator(char='=', length=80):
    """Print a separator line"""
    print(char * length)

def run_script(script_info):
    """Run a single script and return success status"""
    name = script_info['name']
    script_path = script_info['path']
    script_dir = script_info['dir']
    
    print_separator()
    print(f"Starting: {name}")
    print(f"Script: {script_path}")
    print(f"Directory: {script_dir}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print_separator()
    
    # Check if script exists
    if not os.path.exists(script_path):
        print(f"ERROR: Script not found: {script_path}")
        return False
    
    # Change to the script's directory
    original_dir = os.getcwd()
    try:
        os.chdir(script_dir)
        print(f"Changed to directory: {os.getcwd()}")
        
        # Record start time
        start_time = time.time()
        
        # Run the script
        print(f"\nExecuting script...\n")
        result = subprocess.run(
            [sys.executable, script_path],
            stdout=sys.stdout,
            stderr=sys.stderr,
            cwd=script_dir
        )
        
        # Record end time
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        # Check if successful
        if result.returncode == 0:
            print_separator()
            print(f"✓ SUCCESS: {name}")
            print(f"Execution time: {elapsed_time:.2f} seconds ({elapsed_time/60:.2f} minutes)")
            print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print_separator()
            return True
        else:
            print_separator()
            print(f"✗ FAILED: {name}")
            print(f"Return code: {result.returncode}")
            print(f"Execution time: {elapsed_time:.2f} seconds")
            print_separator()
            return False
            
    except Exception as e:
        print_separator()
        print(f"✗ ERROR running {name}: {str(e)}")
        print_separator()
        return False
    finally:
        # Return to original directory
        os.chdir(original_dir)

def main():
    """Main execution function"""
    print_separator('=')
    print("TDSPEVRP - Master Experiment Runner")
    print("=" * 80)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Root directory: {ROOT_DIR}")
    print(f"Python version: {sys.version}")
    print(f"Total scripts to run: {len(SCRIPTS)}")
    print_separator('=')
    print()
    
    # Track results
    results = []
    overall_start_time = time.time()
    
    # Run each script sequentially
    for i, script_info in enumerate(SCRIPTS, 1):
        print(f"\n[{i}/{len(SCRIPTS)}] Processing: {script_info['name']}\n")
        
        success = run_script(script_info)
        results.append({
            'name': script_info['name'],
            'success': success
        })
        
        # If a script fails, you can choose to continue or stop
        # For now, we continue to run all scripts
        if not success:
            print(f"WARNING: {script_info['name']} failed, but continuing with remaining scripts...")
        
        print("\n" + "=" * 80 + "\n")
    
    # Print summary
    overall_end_time = time.time()
    total_elapsed = overall_end_time - overall_start_time
    
    print_separator('=')
    print("EXPERIMENT RUNNER SUMMARY")
    print_separator('=')
    print(f"Total execution time: {total_elapsed:.2f} seconds ({total_elapsed/60:.2f} minutes)")
    print(f"End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("Results:")
    print("-" * 80)
    
    for i, result in enumerate(results, 1):
        status = "✓ SUCCESS" if result['success'] else "✗ FAILED"
        print(f"{i}. {result['name']}: {status}")
    
    print("-" * 80)
    successful = sum(1 for r in results if r['success'])
    print(f"Successful: {successful}/{len(results)}")
    print_separator('=')
    
    # Return exit code based on results
    if all(r['success'] for r in results):
        print("\n✓ All experiments completed successfully!")
        return 0
    else:
        print("\n✗ Some experiments failed. Check the output above for details.")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

