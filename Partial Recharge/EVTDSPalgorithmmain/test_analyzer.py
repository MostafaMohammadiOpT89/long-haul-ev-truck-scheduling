import CSVreader
import os

def check_distance(city1, city2):
    """Check distance between two cities."""
    try:
        print(f"Loading distance matrix...")
        distance_data = CSVreader.CSVreader('DistanceMatrix.csv')
        
        if distance_data is None:
            print("Error: Could not load distance matrix")
            return None
            
        print(f"Distance matrix loaded successfully with {len(distance_data)} cities")
        
        if city1 in distance_data and city2 in distance_data:
            distance = distance_data[city1][city2]
            print(f"Distance from {city1} to {city2}: {distance} km")
            return distance
        else:
            print(f"One or both cities not found: {city1}, {city2}")
            print(f"Available cities: {list(distance_data.keys())[:10]}...")  # Show first 10 cities
            return None
    except Exception as e:
        print(f"Error reading distance matrix: {e}")
        return None

def analyze_test_instance(filename):
    """Analyze a test instance file."""
    try:
        if not os.path.exists(filename):
            print(f"File {filename} not found")
            return []
            
        with open(filename, 'r') as file:
            lines = file.readlines()
        
        print(f"\n=== Analyzing {filename} ===")
        
        # Find vehicle location (depot)
        depot_location = "Unknown"
        depot_id = "Unknown"
        for line in lines:
            if line.startswith('0,') and ',' in line:
                parts = line.strip().split(',')
                if len(parts) >= 3:
                    depot_location = parts[1]
                    depot_id = parts[2]
                    print(f"Vehicle starts at (depot): {depot_location} (ID: {depot_id})")
                    break
        
        # Find all cities including depot
        all_cities = []
        
        # Add depot as first city
        all_cities.append((depot_location, depot_id, "Depot"))
        
        # Find all other cities
        for line in lines:
            if line.startswith(('1,', '2,', '3,', '4,', '5,', '6,', '7,', '8,', '9,', '10,', '11,', '12,', '13,', '14,', '15,', '16,', '17,', '18,', '19,', '20,')):
                parts = line.strip().split(',')
                if len(parts) >= 3:
                    city_name = parts[1]
                    city_id = parts[2]
                    all_cities.append((city_name, city_id, "City"))
        
        print(f"Total number of cities in route: {len(all_cities)} (including depot)")
        print("Complete route:")
        for i, (city, city_id, city_type) in enumerate(all_cities):
            print(f"  {i}. {city} (ID: {city_id}) - {city_type}")
        
        # Check distances between consecutive cities in the route
        if len(all_cities) > 1:
            print(f"\nChecking distances along the complete route:")
            try:
                distance_data = CSVreader.CSVreader('DistanceMatrix.csv')
                if distance_data is not None:
                    total_distance = 0.0
                    for i in range(len(all_cities) - 1):
                        city1, id1, type1 = all_cities[i]
                        city2, id2, type2 = all_cities[i + 1]
                        if city1 in distance_data and city2 in distance_data:
                            distance = distance_data[city1][city2]
                            # Convert distance to float if it's a string
                            try:
                                distance_float = float(distance)
                                total_distance += distance_float
                                print(f"  {city1} → {city2}: {distance_float} km")
                            except (ValueError, TypeError):
                                print(f"  {city1} → {city2}: Invalid distance value '{distance}'")
                        else:
                            print(f"  {city1} → {city2}: Distance not available")
                    
                    print(f"\nTotal route distance: {total_distance:.2f} km")
                else:
                    print("  Could not load distance matrix for distance checking")
            except Exception as e:
                print(f"  Error checking distances: {e}")
        
        return all_cities
        
    except FileNotFoundError:
        print(f"File {filename} not found")
        return []
    except Exception as e:
        print(f"Error reading file: {e}")
        return []

def interactive_mode():
    """Interactive mode for testing."""
    print("\n=== Interactive Distance Checker ===")
    
    while True:
        print("\nOptions:")
        print("1. Check distance between two cities")
        print("2. Analyze a test instance")
        print("3. Test distance matrix loading")
        print("4. Quit")
        
        choice = input("\nEnter your choice (1-4): ").strip()
        
        if choice == '1':
            city1 = input("First city: ").strip()
            city2 = input("Second city: ").strip()
            check_distance(city1, city2)
            
        elif choice == '2':
            filename = input("Enter test instance filename (e.g., testInstance1.txt): ").strip()
            analyze_test_instance(filename)
            
        elif choice == '3':
            print("Testing distance matrix loading...")
            try:
                distance_data = CSVreader.CSVreader('DistanceMatrix.csv')
                if distance_data:
                    print(f"✓ Distance matrix loaded successfully")
                    print(f"  Number of cities: {len(distance_data)}")
                    print(f"  Sample cities: {list(distance_data.keys())[:5]}")
                else:
                    print("✗ Distance matrix loading failed")
            except Exception as e:
                print(f"✗ Error loading distance matrix: {e}")
            
        elif choice == '4':
            print("Goodbye!")
            break
            
        else:
            print("Invalid choice. Please enter 1-4.")

if __name__ == "__main__":
    print("=== Test Instance Distance Analyzer ===")
    
    # Example usage
    print("\nExample 1: Check distance between OsloS and Drammen")
    check_distance("OsloS", "Drammen")
    
    print("\nExample 2: Analyze testInstance11.txt")
    analyze_test_instance("testInstance12.txt")
    
    #print("\nStarting interactive mode...")
    #interactive_mode() 