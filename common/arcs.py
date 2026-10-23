class cityArcs:
	def __init__(self, name):
		self.name = name
		self.distances = {}
		self.times = {}

	def _addDistance(self, otherCity, distance):
		self.distances[otherCity] = distance

	def _addTime(self, otherCity, time):
		self.times[otherCity] = time

	def _getDistance(self, otherCity):
		return self.distances[otherCity]

	def _getTime(self, otherCity):
		return self.times[otherCity]


	@staticmethod
	def createArcs(distanceCSV, timeCSV):
		arcs = {}
		for cityName in distanceCSV:
			arc = cityArcs(cityName)
			for otherCity, distance in distanceCSV[cityName].items():
				arc._addDistance(otherCity, distance)
			for otherCity, time in timeCSV[cityName].items():
				arc._addTime(otherCity, time)
			arcs[cityName] = arc
		return arcs

