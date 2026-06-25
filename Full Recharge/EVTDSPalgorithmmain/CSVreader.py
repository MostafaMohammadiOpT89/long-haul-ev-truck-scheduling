def CSVreader(filename):
    cityData = {}

    with open(filename, "r") as file:
        lines = file.readlines()

    # Assuming the first line contains city names (headers)
    headers = lines[0].strip().split(',')

    # Process each line (excluding the header line)
    for line in lines[1:]:
        data = line.strip().split(',')

        # The first element in each line is the city name
        cityName = data[0]
        cityData[cityName] = {}

        # Process each column for the current city
        for i, value in enumerate(data[1:], 1):
            if headers[i] == "Baatsfjord":
                cityData[cityName][headers[i]] = value
                break  # Stop after including Baatsfjord
            cityData[cityName][headers[i]] = value

    return cityData
