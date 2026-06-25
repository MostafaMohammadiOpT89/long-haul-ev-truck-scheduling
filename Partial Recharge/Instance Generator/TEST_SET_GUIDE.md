# Test Set Configuration Guide

## How to Generate the Test Set

To generate the test set matching your specification table, run:

```bash
python Test_Generator.py grid --seed 42
```

The `--seed` parameter ensures reproducible results. Change it to get different random variations.

## Where to Modify the Test Configuration

The test set is defined in the `run_grid()` function in `Test_Generator.py`, starting at **line 543**.

### Configuration Format

The configuration uses a list of tuples with the following format:

```python
grid_specs = [
    # Format: (route_class, clusters, customer_range, [total_customers_variant1, total_customers_variant2])
    ("short", 1, "Few", [2, 3]),    # Comment explaining the configuration
    ("med", 2, "Medium", [5, 4]),    # Another configuration
    # ... more configurations
]
```

### Parameters Explained

1. **route_class**: `"short"`, `"med"`, or `"long"`
   - **short**: 800-1200 km routes
   - **med**: 1500-2500 km routes  
   - **long**: 3000-4000 km routes

2. **clusters**: `1`, `2`, or `3` - Number of customer clusters

3. **customer_range**: `"Few"`, `"Medium"`, or `"Many"`
   - **Few**: 1-3 customers per cluster
   - **Medium**: 4-5 customers per cluster
   - **Many**: 6-15 customers per cluster

4. **[variant1, variant2]**: Two total customer counts for this configuration
   - Creates two test instances with these total customer counts
   - Customers are distributed across clusters while respecting the customer_range constraints
   - Variant 1 uses the first number, Variant 2 uses the second

### Current Test Set (from your specification table)

The current configuration generates **36 instances** (18 configurations × 2 variants each):

**Short Route (7 configurations = 14 instances):**
- 1 cluster: Few (2,3), Medium (4,5)
- 2 clusters: Few (3,2), Medium (5,4)
- 3 clusters: Few (3,2), Medium (5,4), Many (10,12)

**Medium Route (7 configurations = 14 instances):**
- 1 cluster: Few (2,3), Medium (4,5)
- 2 clusters: Few (3,2), Medium (5,4)
- 3 clusters: Few (3,2), Medium (5,4), Many (11,13)

**Long Route (6 configurations = 12 instances):**
- 1 cluster: Few (2,3), Medium (4,5)
- 2 clusters: Few (3,2), Medium (5,4)
- 3 clusters: Few (3,2), Medium (5,4), Many (14,12)

### How to Add/Remove/Modify Tests

#### Add a New Test Configuration

Add a new line to the `grid_specs` list:

```python
("short", 3, "Many", [15, 16]),  # Short, 3 clusters, Many range: 15, 16 total customers
```

#### Remove a Test Configuration

Simply delete or comment out the line:

```python
# ("short", 1, "Few", [2, 3]),    # Commented out - not generating
```

#### Change Customer Counts

Modify the numbers in the list:

```python
("short", 1, "Few", [3, 4]),    # Changed from [2, 3] to [3, 4] total customers
```

#### Change Customer Range

Modify the customer range constraint:

```python
("short", 1, "Medium", [2, 3]),  # Changed from "Few" to "Medium" range
```

#### Change Number of Variants

If you want only 1 variant instead of 2:

```python
("short", 1, "Few", [2]),       # Only variant 1 with 2 total customers
```

Or 3 variants:

```python
("short", 1, "Few", [2, 3, 4]), # Three variants with 2, 3, and 4 total customers
```

### Important Notes

1. **Seed Parameter**: Always use a fixed seed for reproducible test sets
2. **Instance Naming**: Generated instances are named as: `{route_class}_cl{clusters}_cu{customers}_v{variant}`
3. **Master Matrices**: The generator also creates `Master_DistanceMatrix.csv` and `Master_TimeMatrix.csv`
4. **Customer Range Constraints**: The system respects customer range constraints when distributing customers across clusters:
   - **Few (1-3)**: Each cluster gets 1-3 customers
   - **Medium (4-5)**: Each cluster gets 4-5 customers  
   - **Many (6-15)**: Each cluster gets 6-15 customers
5. **Clusters > Customers**: The code handles cases where there are more clusters than customers (some clusters will be empty)
6. **Customer Distribution**: Total customers are distributed across clusters while respecting the range constraints

### Example: Creating a Custom Test Set

To create a minimal test set with only short routes and 1-2 clusters:

```python
grid_specs = [
    ("short", 1, "Few", [2, 3]),
    ("short", 1, "Medium", [4, 5]),
    ("short", 2, "Few", [3, 5]),
]
```

This would generate 6 instances (3 configurations × 2 variants).

### Location Summary

- **Test configuration**: Lines **622-650** in `Test_Generator.py`
- **Function containing config**: `run_grid()` starting at line **618**
- **How to run**: `python Test_Generator.py grid --seed 42`

