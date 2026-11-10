import CSVreader

def list_all_cities():
    """List all cities available in the distance matrix."""
    try:
        distance_data = CSVreader.CSVreader('DistanceMatrix.csv')
        if distance_data:
            cities = list(distance_data.keys())
            print(f"Total cities in distance matrix: {len(cities)}")
            print("\nAll available cities:")
            for i, city in enumerate(cities, 1):
                print(f"{i:3d}. {city}")
            return cities
        else:
            print("Could not load distance matrix")
            return []
    except Exception as e:
        print(f"Error: {e}")
        return []

if __name__ == "__main__":
    list_all_cities() 