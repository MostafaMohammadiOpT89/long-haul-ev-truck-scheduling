"""Hours-of-service (HoS) rules and driving speed shared by every policy.

Single source of truth for Full labeling, Partial labeling and the Driver heuristic.
Change a rule here and all three algorithms use the new value.
All times are in hours, speeds in km/h.
"""

DRIVING_SPEED_KMH = 60.0      # constant driving speed

MAX_ELAPSED_REST_H = 13.0     # max elapsed time since the last daily rest
MAX_ELAPSED_BREAK_H = 6.0     # max elapsed time since the last break
MAX_DRIVE_BREAK_H = 4.5       # max driving time since the last break
MAX_DRIVE_REST_H = 9.0        # max driving time since the last daily rest
MIN_BREAK_H = 0.75            # minimum break duration
MIN_REST_H = 11.0             # minimum daily rest duration
DAY_H = 24.0                  # length of a day
