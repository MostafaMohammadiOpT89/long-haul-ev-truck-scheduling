import policies.labeling.full_recharge.label as label, policies.labeling.full_recharge.isFeasible as isFeasible, policies.labeling.full_recharge.dominate as dominate, heapq, time


def algorithm(network):

    # Initialise the parameterfree arcs
    networkArcs = network.paraArcs
    
    # Initialise lists unprocessed U (as a heap) and processed P
    U = []
    P = []

    # Initialise counters
    dominatedCounter = 0
    labelCounter = 0
    maxRuntime = 30*60 # 30 minutes in seconds
    startTime = time.time()

    # Initialise the first label with the depot using current battery capacity
    startLabel = label.Label(network._getDepot(), batteryCapacity=network.batteryCap)
    heapq.heappush(U, (startLabel.time, startLabel))
    labelCounter += 1

    while U and (time.time() - startTime) <= maxRuntime:
        # Pop the label with the lowest time from U
        _, L = heapq.heappop(U)
        currentNode = L.detailedPath[-1]
        currentNodeArcs = {arc: data for arc, data in networkArcs.items() if currentNode == arc[0] and currentNode != arc[1]}

        for arc, arcData in currentNodeArcs.items():
            startNode, endNode, transitionType = arc
            if currentNode == startNode and currentNode != endNode:
                # Create a copy of L using the custom copy method
                newL = L.custom_copy()
                # Invoke the relevant REF and update the path of newL
                network.invoke_REF(newL, startNode, endNode, transitionType)
                # Check feasibility
                if isFeasible.isFeasible(newL):
                    # Add newL to unprocessed labels U
                    heapq.heappush(U, (newL.time, newL))
                    # Update label 
                    labelCounter += 1
        
        # Mark L as done and add to processed labels P
        L.done = True
        P.append(L)

        # Dominance step
        if U:
            labels_only = [label for _, label in U]  # Extract Label instances from the heap
            dominated_indices = dominate.dominate(labels_only)
            # Update dominated counter
            dominatedCounter += len(dominated_indices)
            # Remove dominated labels from U and add them to P
            U = [(time, label) for i, (time, label) in enumerate(U) if i not in dominated_indices]
            for i in dominated_indices:
                P.append(labels_only[i])
            heapq.heapify(U)

    return P, labelCounter, dominatedCounter

