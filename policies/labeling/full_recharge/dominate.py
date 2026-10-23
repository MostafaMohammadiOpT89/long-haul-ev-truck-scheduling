import numpy as np
from functools import lru_cache

def array_to_tuple(array):
    return tuple(map(tuple, array))

@lru_cache(None)
def compare_labels(current_attrs, other_attrs):
    is_current_dominated = np.all(np.array(current_attrs) <= np.array(other_attrs))
    is_other_dominated = np.all(np.array(other_attrs) <= np.array(current_attrs))
    return is_current_dominated, is_other_dominated

def dominate(labelList):
    dominatedLabels = []
    label_attrs = []

    for label in labelList:
        attrs = (
            label.time, label.timeToNext, label.drive_R, label.drive_B, 
            label.elapsed_R, label.elapsed_B, -label.latest_R, -label.latest_B, label.reqRT
        )
        label_attrs.append(attrs)

    label_attrs = array_to_tuple(label_attrs)

    for i in range(len(labelList) - 1):
        for j in range(i + 1, len(labelList)):
            if labelList[i].detailedPath[-1] == labelList[j].detailedPath[-1]:
                is_current_dominated, is_other_dominated = compare_labels(label_attrs[i], label_attrs[j])

                if is_current_dominated:
                    dominatedLabels.append(j)
                elif is_other_dominated:
                    dominatedLabels.append(i)
                    break  # Early terminatation if dominated
    return list(set(dominatedLabels))  # Remove duplicate indices


# """
# def dominate(labelList):
#     dominatedLabels = []
#     for i, current_label in enumerate(labelList[:-1]):
#         for j in range(i + 1, len(labelList)):
#             other_label = labelList[j]
#             if current_label.detailedPath[-1] == other_label.detailedPath[-1]:
#                 current_attrs = (current_label.time, current_label.timeToNext, current_label.drive_R, current_label.drive_B, current_label.elapsed_R, -current_label.latest_R, current_label.reqRT)
#                 other_attrs = (other_label.time, other_label.timeToNext, other_label.drive_R, other_label.drive_B, other_label.elapsed_R, -other_label.latest_R, other_label.reqRT)
#                 if all(c <= o for c, o in zip(current_attrs, other_attrs)):
#                     dominatedLabels.append(j)
#                 elif all(o <= c for o, c in zip(other_attrs, current_attrs)):
#                     dominatedLabels.append(i)
#                     break
#     return dominatedLabels
# """


# import numpy as np
# from functools import lru_cache

# def array_to_tuple(array):
#     return tuple(map(tuple, array))

# @lru_cache(None)
# def compare_labels(current_attrs, other_attrs):
#     is_current_dominated = np.all(np.array(current_attrs) <= np.array(other_attrs))
#     is_other_dominated = np.all(np.array(other_attrs) <= np.array(current_attrs))
#     return is_current_dominated, is_other_dominated

# def dominate(labelList):
#     # Extract attributes using a list comprehension instead of a for-loop
#     label_attrs = np.array([
#         (
#             label.time, label.timeToNext, label.drive_R, label.drive_B, 
#             label.elapsed_R, label.elapsed_B, -label.latest_R, -label.latest_B, label.reqRT
#         )
#         for label in labelList
#     ])

#     dominatedLabels = []
#     n = len(labelList)

#     # Compare labels using broadcasting to remove explicit nested loops
#     for i in range(n):
#         if i in dominatedLabels:  # Skip already dominated labels
#             continue
#         same_path_indices = [j for j in range(i + 1, n) 
#                              if labelList[i].detailedPath[-1] == labelList[j].detailedPath[-1]]

#         # Compare only labels with the same ending path
#         for j in same_path_indices:
#             is_current_dominated, is_other_dominated = compare_labels(tuple(label_attrs[i]), tuple(label_attrs[j]))
#             if is_current_dominated:
#                 dominatedLabels.append(j)
#             elif is_other_dominated:
#                 dominatedLabels.append(i)
#                 break  # Early termination if label i is dominated

#     return list(set(dominatedLabels))  # Deduplicate results




# import numpy as np
# from functools import lru_cache

# def array_to_tuple(array):
#     return tuple(map(tuple, array))

# @lru_cache(None)
# def compare_labels(current_attrs, other_attrs):
#     is_current_dominated = np.all(np.array(current_attrs) <= np.array(other_attrs))
#     is_other_dominated = np.all(np.array(other_attrs) <= np.array(current_attrs))
#     return is_current_dominated, is_other_dominated

# def dominate(labelList):
#     dominatedLabels = []
#     label_attrs = []

#     # Precompute attributes for all labels
#     for label in labelList:
#         attrs = (
#             label.time, label.timeToNext, label.drive_R, label.drive_B, 
#             label.elapsed_R, label.elapsed_B, -label.latest_R, -label.latest_B, label.reqRT
#         )
#         label_attrs.append(attrs)
    
#     label_attrs = np.array(label_attrs)  # Convert to a NumPy array for efficient operations

#     # Compare all pairs of labels
#     n = len(labelList)
#     for i in range(n):
#         for j in range(i + 1, n):
#             if labelList[i].detailedPath[-1] == labelList[j].detailedPath[-1]:
#                 # Compare labels using NumPy vectorized operations
#                 is_current_dominated, is_other_dominated = compare_labels(tuple(label_attrs[i]), tuple(label_attrs[j]))

#                 if is_current_dominated:
#                     dominatedLabels.append(j)
#                 elif is_other_dominated:
#                     dominatedLabels.append(i)
#                     break  # Early termination if dominated
    
#     return list(set(dominatedLabels))  # Remove duplicate indices
