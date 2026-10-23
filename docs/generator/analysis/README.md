# Test Instance Feature Analyzer

## Overview

The `Test_Analyzer.py` script is a standalone tool that analyzes all generated test instances and extracts comprehensive features for research and analysis purposes.

## Location

- **Script**: `analysis/Test_Analyzer.py`
- **Output**: `analysis/test_instance_features.csv`

## Features Extracted

The analyzer extracts **25 different features** for each test instance:

### 1. Basic Identification
- **Test_Name**: Instance identifier (e.g., `short_cl3_cu12_v2`)
- **Route_Class**: Route type (`short`, `med`, `long`)
- **Cluster_Count**: Number of clusters (1, 2, or 3)
- **Total_Customers**: Total number of customers
- **Variant**: Variant number (1 or 2)

### 2. Main Features
- **Total_Route_Distance_km**: Complete route distance from origin to destination
- **Total_Route_Time_hours**: Total travel time for the route

### 3. Cluster Analysis
- **Customers_Per_Cluster**: List showing customer distribution across clusters
- **Cluster_Distances_km**: Distances between consecutive clusters
- **Avg_Cluster_Distance_km**: Average distance between clusters
- **Min_Cluster_Distance_km**: Minimum distance between clusters
- **Max_Cluster_Distance_km**: Maximum distance between clusters

### 4. Customer Positioning Within Clusters
- **Avg_Customer_Distance_Within_Cluster_km**: Average distance between customers in same cluster
- **Min_Customer_Distance_Within_Cluster_km**: Minimum intra-cluster distance
- **Max_Customer_Distance_Within_Cluster_km**: Maximum intra-cluster distance

### 5. Inter-Cluster Distances
- **Inter_Cluster_Distances_km**: All pairwise distances between clusters
- **Avg_Inter_Cluster_Distance_km**: Average inter-cluster distance
- **Min_Inter_Cluster_Distance_km**: Minimum inter-cluster distance
- **Max_Inter_Cluster_Distance_km**: Maximum inter-cluster distance

### 6. Holistic Metrics
- **Cluster_Density_customers_per_km**: Customer density (customers per km)
- **Route_Efficiency_km_per_customer**: Route efficiency (km per customer)
- **Cluster_Balance_std_dev**: Standard deviation of customers per cluster
- **Spatial_Spread_km**: Total spatial spread of the route

### 7. Service Characteristics
- **Avg_Service_Time_hours**: Average service time per customer
- **Total_Service_Time_hours**: Total service time for all customers

## Usage

```bash
cd analysis
python Test_Analyzer.py
```

## Output

The analyzer generates a CSV file with:
- **42 rows** (one per test instance)
- **25 columns** (one per feature)
- **Comprehensive analysis** of all test instances

## Example Output

```csv
Test_Name,Route_Class,Cluster_Count,Total_Customers,Variant,Total_Route_Distance_km,...
short_cl3_cu12_v2,short,3,12,2,1200.45,17.1493,"[4, 4, 4]","[200.15, 180.23]",...
```

## Key Insights

The analyzer provides insights into:

1. **Route Characteristics**: Distance and time patterns across route classes
2. **Cluster Distribution**: How customers are distributed across clusters
3. **Spatial Relationships**: Distances between and within clusters
4. **Efficiency Metrics**: Route efficiency and customer density
5. **Service Patterns**: Service time variations across instances

## Research Applications

This comprehensive feature set enables:
- **Statistical Analysis**: Compare features across route classes and configurations
- **Machine Learning**: Use features as input for predictive models
- **Optimization**: Identify patterns for route optimization
- **Benchmarking**: Compare different test configurations
- **Visualization**: Create charts and graphs of instance characteristics

## File Structure

```
analysis/
├── Test_Analyzer.py          # Main analyzer script
└── test_instance_features.csv  # Generated analysis results
```

The analyzer automatically:
- Finds the `instances` directory in the parent folder
- Processes all test instance subdirectories
- Skips master matrix files
- Saves results in the same directory as the script
