"""Draw the illustrative hours-of-service schedule in the problem definition.

From the repository root, run: python -m analysis.driver_schedule
"""
from pathlib import Path

import matplotlib as mpl
from matplotlib import pyplot as plt
from matplotlib.patches import Rectangle


FIGURES = Path(__file__).resolve().parents[1] / "manuscript/synch_paper_latex/figures"

# Each duration is in minutes. Charging overlaps the driver's break.
SCHEDULE = (
    ("Drive", 270),
    ("Break + charging", 45),
    ("Drive", 180),
    ("Service", 120),
    ("Drive", 90),
    ("Daily rest", 660),
)
FILLS = {
    "Drive": "#E5EAED",
    "Service": "#BED4E5",
    "Break + charging": "#F1D9C3",
    "Daily rest": "#DBD3E7",
}
INK = "#26343C"
OUTLINE = "#5F6971"
CHARGING = "#006B5F"


def duration_label(minutes):
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes / 60:g} h"


def main():
    total = sum(minutes for _, minutes in SCHEDULE)
    # Serif text matches the surrounding manuscript. Embed fonts in the PDF.
    with mpl.rc_context({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Liberation Serif", "DejaVu Serif"],
        "text.color": INK,
        "pdf.fonttype": 42,
        "pdf.compression": 6,
        "hatch.linewidth": 0.85,
    }):
        fig, ax = plt.subplots(figsize=(6.2, 1.04))
        fig.subplots_adjust(left=0.012, right=0.988, bottom=0, top=1)
        ax.set(xlim=(0, total), ylim=(0, 1))
        ax.set_axis_off()

        bottom, height = 0.38, 0.35
        start = 0
        for activity, minutes in SCHEDULE:
            mid = start + minutes / 2
            ax.add_patch(Rectangle((start, bottom), minutes, height,
                                   facecolor=FILLS[activity], edgecolor=OUTLINE,
                                   linewidth=0.65, clip_on=False))
            if activity == "Break + charging":
                # Leave the break fill visible underneath the charging hatch.
                ax.add_patch(Rectangle((start, bottom), minutes, height,
                                       facecolor="none", edgecolor=CHARGING,
                                       hatch="////", linewidth=0))
                ax.annotate(f"{activity} ({duration_label(minutes)})",
                            xy=(mid, bottom + height), xytext=(mid, 0.90),
                            ha="center", va="center", fontsize=9.5,
                            arrowprops=dict(arrowstyle="-", color=OUTLINE,
                                            linewidth=0.65, shrinkA=1, shrinkB=1))
            else:
                ax.text(mid, bottom + height * 0.68, activity,
                        ha="center", va="center", fontsize=9.5)
                ax.text(mid, bottom + height * 0.26, duration_label(minutes),
                        ha="center", va="center", fontsize=8, color="#40505C")
            start += minutes

        for minute in [*range(0, total, 360), total]:
            ax.plot([minute, minute], [bottom, bottom - 0.055],
                    color=OUTLINE, linewidth=0.65, clip_on=False)
            alignment = "left" if minute == 0 else "right" if minute == total else "center"
            ax.text(minute, 0.23, f"{minute / 60:g}", ha=alignment, va="center", fontsize=8.5)
        ax.text(total / 2, 0.075, "Elapsed time from departure (h)",
                ha="center", va="center", fontsize=8.5)

        fig.savefig(FIGURES / "driver_schedule.pdf")
        fig.savefig(FIGURES / "driver_schedule.png", dpi=240)
        plt.close(fig)


if __name__ == "__main__":
    main()
