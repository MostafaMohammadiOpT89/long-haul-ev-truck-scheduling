# Enhanced EV-TDSP Analysis System

This enhanced system provides comprehensive data capture and analysis capabilities for the Electric Vehicle Time-Dependent Shortest Path (EV-TDSP) algorithm with synchronization metrics.

## Overview

The enhanced system captures detailed information about each test scenario, including:
- Instance metadata and configuration
- Feasibility and runtime information
- Activity timeline analysis
- Synchronization metrics between charging and rest events
- Performance profiling data

## Files Overview

### Core Files
- `enhanced_main.py` - Main execution script with comprehensive data capture
- `instanceResultClass.py` - Enhanced result class with all required data fields
- `post_analysis_utils.py` - Utilities for analyzing results and creating visualizations

### Data Capture Fields

#### 1. Instance Metadata / Configuration Info
- `test_bed_id` - Unique identifier for each test scenario
- `battery_capacity_kWh` - Battery capacity in kWh
- `charging_station_interval_km` - Distance between charging stations
- `charging_power_kW` - Charging power in kW
- `energy_consumption_rate_kWh_per_km` - Energy consumption rate
- `number_of_customer_locations` - Number of customer locations
- `synchronization_enabled` - Whether synchronization is enabled

#### 2. Feasibility and Runtime Info
- `feasible` - Whether the scenario is feasible
- `reason_if_infeasible` - Reason for infeasibility if applicable
- `total_route_time_minutes` - Total route time in minutes
- `computation_time_seconds` - Algorithm computation time
- `number_of_labels_generated` - Number of labels generated
- `number_of_labels_dominated` - Number of labels dominated

#### 3. Activity Analysis
- `number_of_cs_stops` - Number of charging station stops
- `number_of_rest_breaks` - Number of rest breaks
- `number_of_synchronized_events` - Number of synchronized charging/rest events
- `number_of_unsynchronized_charging_events` - Number of unsynchronized charging events
- `total_idle_charging_time_minutes` - Total idle charging time
- `number_of_dedicated_charging_stops` - Number of dedicated charging stops

#### 4. Activity Timeline
Detailed timeline of all activities with timestamps:
```json
{
  "type": "drive|charge|break|rest",
  "start_time": 0.0,
  "end_time": 30.0,
  "duration_minutes": 30.0,
  "distance_km": 30.0,  // for drive activities
  "power_kW": 350,      // for charge activities
  "location": "CS"      // for charge activities
}
```

#### 5. Synchronization Metrics
- `percentage_of_charging_events_synchronized` - Percentage of charging events that overlap with rest
- `average_sync_overlap_duration_minutes` - Average overlap duration
- `synchronization_efficiency_score` - Composite efficiency score

## Usage

### 1. Running the Enhanced Analysis

```bash
python enhanced_main.py
```

This will:
- Run all test instances (1-12) with all parameter combinations
- Generate comprehensive results in both JSON and CSV formats
- Create timestamped output files

### 2. Post-Analysis

```python
from post_analysis_utils import PostAnalysisUtils

# Load results
analyzer = PostAnalysisUtils('Results/enhanced_results_20241201_120000.json')

# Basic analysis
analyzer.get_feasibility_summary()
analyzer.analyze_synchronization_metrics()

# Parameter analysis
analyzer.analyze_by_parameter('battery_capacity_kWh')
analyzer.analyze_by_parameter('charging_power_kW')

# Get best scenarios
analyzer.get_best_scenarios('total_route_time_minutes', top_n=10)
analyzer.get_best_scenarios('synchronization_efficiency_score', top_n=10)

# Create visualizations (saved to Results/Post_Analysis/)
analyzer.create_synchronization_heatmap('sync_heatmap.png')
analyzer.create_feasibility_matrix('feasibility_matrix.png')

# Export filtered results (saved to Results/Post_Analysis/)
analyzer.export_filtered_results('high_battery_feasible.csv', {
    'feasible': True,
    'battery_capacity_kWh': [750, 1000]
})

# Save comprehensive analysis report
analyzer.save_analysis_report('comprehensive_analysis_report.txt')
```

### 3. Installing Dependencies

```bash
pip install -r requirements.txt
```

## Output Files

### JSON Output
Contains complete data including activity timelines:
```json
{
  "metadata": {
    "timestamp": "20241201_120000",
    "total_scenarios": 2016,
    "parameters": {...}
  },
  "results": [
    {
      "test_bed_id": "TB01",
      "battery_capacity_kWh": 350,
      "charging_power_kW": 350,
      "feasible": true,
      "total_route_time_minutes": 180.5,
      "activity_timeline": [...],
      "synchronization_efficiency_score": 75.2,
      ...
    }
  ]
}
```

### CSV Output
Tabular format for easy analysis in Excel or other tools:
- All metrics in columns
- One row per test scenario
- Easy to filter and sort

## Synchronization Analysis

The system automatically analyzes synchronization between charging and rest events:

1. **Overlap Detection**: Identifies when charging events overlap with rest breaks
2. **Efficiency Calculation**: Computes synchronization efficiency scores
3. **Timeline Analysis**: Provides detailed activity timelines for visualization

### Synchronization Metrics Explained

- **Synchronized Events**: Charging events that overlap with rest breaks
- **Unsynchronized Events**: Charging events that don't overlap with rest
- **Idle Charging Time**: Charging time not used for rest
- **Efficiency Score**: Composite metric considering both overlap frequency and duration

## Customization

### Adding New Parameters
To add new parameters to the analysis:

1. Modify `EnhancedInstanceResult.__init__()` in `instanceResultClass.py`
2. Update the CSV headers in `get_csv_headers()`
3. Add the parameter to the result creation in `enhanced_main.py`

### Modifying Synchronization Logic
The synchronization analysis is in `_calculate_synchronization_metrics()` method. You can modify:
- Overlap detection criteria
- Efficiency score calculation
- Timeline analysis logic

## Performance Considerations

- The system uses INFO-level logging to reduce log file size
- Results are saved incrementally to avoid memory issues
- CSV output is optimized for large datasets
- JSON output includes full detail for deep analysis

## Troubleshooting

### Common Issues

1. **Memory Issues**: If running all instances causes memory problems, modify the test instances list in `enhanced_main.py`
2. **Long Runtime**: The full analysis can take several hours. Consider running subsets of parameters first
3. **Missing Dependencies**: Install required packages with `pip install -r requirements.txt`

### Log Files
- `enhanced_results.log` - Main execution log
- `Results/enhanced_results_YYYYMMDD_HHMMSS.json` - Complete results
- `Results/enhanced_results_YYYYMMDD_HHMMSS.csv` - Tabular results

### Post-Analysis Output
- `Results/Post_Analysis/` - All post-analysis outputs
  - `filtered_results.csv` - Filtered data exports
  - `analysis_report.txt` - Comprehensive analysis reports
  - `sync_heatmap.png` - Synchronization heatmaps
  - `feasibility_matrix.png` - Feasibility matrices

## Future Enhancements

Potential improvements for the system:
1. Real-time synchronization optimization algorithms
2. Advanced timeline visualization tools
3. Machine learning-based parameter optimization
4. Integration with external optimization solvers
5. Real-time monitoring and alerting systems 