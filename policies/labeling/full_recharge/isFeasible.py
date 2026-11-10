# Parameters
maxElapsed_R = 13
maxElapsed_B = 6
maxTimeDrive_B = 4.5
maxTimeDrive_R = 9

batteryCapacity = None

def setGlobalParams(batteryCap):
    global batteryCapacity
    batteryCapacity = batteryCap



def check_feasibility(label):
	"""Return (is_feasible, reasons). Reasons list is empty if feasible."""
	reasons = []
	if label.drive_R > maxTimeDrive_R:
		reasons.append("drive_R>maxTimeDrive_R")
	if label.drive_R < 0:
		reasons.append("drive_R<0")
	if label.drive_B > maxTimeDrive_B:
		reasons.append("drive_B>maxTimeDrive_B")
	if label.drive_B < 0:
		reasons.append("drive_B<0")
	if label.elapsed_R > maxElapsed_R:
		reasons.append("elapsed_R>maxElapsed_R")
	if label.elapsed_R < 0:
		reasons.append("elapsed_R<0")
	if label.elapsed_B > maxElapsed_B:
		reasons.append("elapsed_B>maxElapsed_B")
	if label.elapsed_B < 0:
		reasons.append("elapsed_B<0")
	if label.done:
		reasons.append("label_done")
	if label.reqRT > batteryCapacity:
		reasons.append("reqRT>batteryCapacity")
	if label.reqRT < 0:
		reasons.append("reqRT<0")

	return (len(reasons) == 0), reasons


def isFeasible(label):
	feasible, _ = check_feasibility(label)
	return feasible