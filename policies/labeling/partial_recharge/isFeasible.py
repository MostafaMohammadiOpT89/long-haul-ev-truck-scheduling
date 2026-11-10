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
	"""Return (is_feasible, reasons). Reasons list is empty if feasible.
	This function tracks infeasibility reasons while maintaining the exact same logic as isFeasible().
	Partial Recharge strategy uses remainingBattery_min/max and reqRT_min/max (not single values like Full Recharge).
	"""
	reasons = []
	
	# Check each condition from the original isFeasible logic and track reasons
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
	# Battery bounds - Partial Recharge uses min/max bounds
	if label.remainingBattery_min < 0:
		reasons.append("remainingBattery_min<0")
	if label.remainingBattery_min > batteryCapacity:
		reasons.append("remainingBattery_min>batteryCapacity")
	if label.remainingBattery_max < 0:
		reasons.append("remainingBattery_max<0")
	if label.remainingBattery_max > batteryCapacity:
		reasons.append("remainingBattery_max>batteryCapacity")
	# Recharge requirement bounds - Partial Recharge uses min/max bounds
	if label.reqRT_min < 0:
		reasons.append("reqRT_min<0")
	if label.reqRT_min > batteryCapacity:
		reasons.append("reqRT_min>batteryCapacity")
	if label.reqRT_max < 0:
		reasons.append("reqRT_max<0")
	if label.reqRT_max > batteryCapacity:
		reasons.append("reqRT_max>batteryCapacity")

	return (len(reasons) == 0), reasons


def isFeasible(label):
	"""Original Partial Recharge feasibility check logic - unchanged.
	This maintains the exact same boolean logic as before, just wrapped for compatibility.
	Partial Recharge strategy checks remainingBattery_min/max and reqRT_min/max bounds.
	"""
	feasible = (
		label.drive_R <= maxTimeDrive_R and label.drive_R >= 0 and
		label.drive_B <= maxTimeDrive_B and label.drive_B >= 0 and
		label.elapsed_R <= maxElapsed_R and label.elapsed_R >= 0 and
		label.elapsed_B <= maxElapsed_B and label.elapsed_B >= 0 and
		label.done == False and
		# Battery bounds
		label.remainingBattery_min >= 0 and label.remainingBattery_min <= batteryCapacity and
		label.remainingBattery_max >= 0 and label.remainingBattery_max <= batteryCapacity and
		# Recharge requirement bounds
		label.reqRT_min >= 0 and label.reqRT_min <= batteryCapacity and
		label.reqRT_max >= 0 and label.reqRT_max <= batteryCapacity
	)
	if feasible:
		return True
	return False