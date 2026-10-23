# class Label():

# 	#Initializing the label
# 	def __init__(self, startNode):
# 		startingNode = startNode	# This gets the starting city node ID
# 		self.path = [startingNode]		# Initialize path as a list with the starting city node ID
# 		self.detailedPath = [startingNode] # Path including intermediate nodes
# 		self.activityList = []
# 		self.time = 0.0
# 		self.timeToNext = 0.0
# 		self.drive_R = 0.0
# 		self.drive_B = 0.0
# 		self.elapsed_R = 0.0
# 		self.elapsed_B = 0.0
# 		self.latest_R = float('inf')
# 		self.latest_B = float('inf')
# 		self.reqRT = 0.0
# 		self.done = False

# 	def custom_copy(self):
# 		new_label = Label(None)  # Initialize with None since startNode is not used in copy
# 		new_label.path = self.path[:]
# 		new_label.detailedPath = self.detailedPath[:]
# 		new_label.activityList = self.activityList[:]
# 		new_label.time = self.time
# 		new_label.timeToNext = self.timeToNext
# 		new_label.drive_R = self.drive_R
# 		new_label.drive_B = self.drive_B
# 		new_label.elapsed_R = self.elapsed_R
# 		new_label.elapsed_B = self.elapsed_B
# 		new_label.latest_R = self.latest_R
# 		new_label.latest_B = self.latest_B
# 		new_label.reqRT = self.reqRT
# 		new_label.done = self.done
# 		return new_label

# 	def __str__(self):
# 		return (f"Path = {self.path}, Activities = {self.activityList}, Label(DetailedPath = {self.detailedPath},  reqRT = {self.reqRT}, time = {self.time}, timeToNext = {self.timeToNext}, "
# 			f"drive_R = {self.drive_R}, drive_B = {self.drive_B}, "
# 			f"elapsed_R = {self.elapsed_R}, elapsed_B = {self.elapsed_B}, latest_R = {self.latest_R}, latest_B = {self.latest_B} "
# 			f"done = {self.done})")

# 	def __repr__(self):
# 		return (f"Path={self.path}, Label(DetailedPath={self.detailedPath}"
# 		  	f"Activities={self.activityList}, reqRT = {self.reqRT}, time = {self.time}, timeToNext = {self.timeToNext}, "
# 			f"drive_R = {self.drive_R}, drive_B = {self.drive_B}, "
# 			f"elapsed_R = {self.elapsed_R}, elapsed_B = {self.elapsed_B}")
	
# 	def __lt__(self, other):
# 		return self.time < other.time
	

class Label:

    # Initializing the label
    def __init__(self, startNode, batteryCapacity=250.0):
        startingNode = startNode  # This gets the starting city node ID
        self.path = [startingNode]           # Path with city nodes only
        self.detailedPath = [startingNode]   # Path including intermediate nodes
        self.activityList = []               # Logs activities like charging, driving, breaks
        self.time = 0.0                      # Total elapsed time
        self.timeToNext = 0.0                # Time to reach the next node
        self.drive_R = 0.0                   # Driving time since the last rest
        self.drive_B = 0.0                   # Driving time since the last break
        self.elapsed_R = 0.0                 # Elapsed time since the last rest
        self.elapsed_B = 0.0                 # Elapsed time since the last break
        self.latest_R = float('inf')         # Latest possible rest time
        self.latest_B = float('inf')         # Latest possible break time
        self.reqRT = 0.0                     # Required recharge time
        self.remainingBattery = batteryCapacity  # Current battery level (initialize as full)
        self.batteryCapacity = batteryCapacity   # Battery capacity
        self.done = False                    # Flag to mark label as processed

    # Custom copy method
    def custom_copy(self):
        new_label = Label(None, self.batteryCapacity)  # Initialize with None and same battery capacity
        new_label.path = self.path[:]
        new_label.detailedPath = self.detailedPath[:]
        new_label.activityList = self.activityList[:]
        new_label.time = self.time
        new_label.timeToNext = self.timeToNext
        new_label.drive_R = self.drive_R
        new_label.drive_B = self.drive_B
        new_label.elapsed_R = self.elapsed_R
        new_label.elapsed_B = self.elapsed_B
        new_label.latest_R = self.latest_R
        new_label.latest_B = self.latest_B
        new_label.reqRT = self.reqRT
        new_label.remainingBattery = self.remainingBattery  # Copy battery level
        new_label.done = self.done
        return new_label

    # String representation for debugging and display
    def __str__(self):
        return (f"Path = {self.path}, Activities = {self.activityList}, "
                f"Label(DetailedPath = {self.detailedPath}, reqRT = {self.reqRT}, time = {self.time}, "
                f"timeToNext = {self.timeToNext}, drive_R = {self.drive_R}, drive_B = {self.drive_B}, "
                f"elapsed_R = {self.elapsed_R}, elapsed_B = {self.elapsed_B}, "
                f"latest_R = {self.latest_R}, latest_B = {self.latest_B}, "
                f"remainingBattery = {self.remainingBattery:.2f}/{self.batteryCapacity}, done = {self.done})")

    # Representation for debugging in lists or objects
    def __repr__(self):
        return (f"Path={self.path}, DetailedPath={self.detailedPath}, "
                f"Activities={self.activityList}, reqRT={self.reqRT}, time={self.time}, "
                f"timeToNext={self.timeToNext}, drive_R={self.drive_R}, drive_B={self.drive_B}, "
                f"elapsed_R={self.elapsed_R}, elapsed_B={self.elapsed_B}, "
                f"remainingBattery={self.remainingBattery:.2f}/{self.batteryCapacity})")

    # Comparison for priority queues (time-based priority)
    def __lt__(self, other):
        return self.time < other.time
