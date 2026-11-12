from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt


def create_charts(frame, output: Path) -> list[Path]:
    """Save the temperature, rainfall, and humidity charts. Called by build_report."""
    charts = [
        ("temperature", "Daily temperature trends", "Temperature (°C)", [
            ("temperature_max_c", "Maximum", "#d05b40"),
            ("temperature_min_c", "Minimum", "#277da8"),
        ]),
        ("rainfall", "Daily rainfall distribution", "Rainfall (mm)", [
            ("rainfall_mm", "Rainfall", "#277da8"),
        ]),
        ("humidity", "Daily mean relative humidity", "Relative humidity (%)", [
            ("humidity_mean_pct", "Mean humidity", "#278576"),
        ]),
    ]
    paths = []
    for name, title, ylabel, series in charts:
        fig, ax = plt.subplots(figsize=(9, 3.4), layout="constrained")
        try:
            for column, label, color in series:
                if name == "rainfall":
                    ax.bar(frame["date"], frame[column], width=0.8, color=color, label=label)
                else:
                    ax.plot(frame["date"], frame[column], color=color, linewidth=1.7,
                            marker="." if len(frame) <= 45 else None, label=label)
            locator = mdates.AutoDateLocator(minticks=3, maxticks=8)
            ax.xaxis.set_major_locator(locator)
            ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
            ax.set(title=title, xlabel="Date (local time)", ylabel=ylabel)
            ax.grid(axis="y", alpha=0.2)
            ax.set_axisbelow(True)
            ax.spines[["top", "right"]].set_visible(False)
            if name == "humidity":
                ax.set_ylim(0, 100)
            if name == "rainfall":
                ax.set_ylim(bottom=0)
            ax.legend(loc="best", frameon=False)
            if not frame[[column for column, _, _ in series]].notna().any().any():
                ax.text(0.5, 0.5, "No valid measurements", transform=ax.transAxes, ha="center")
            path = output / f"{name}.png"
            fig.savefig(path, dpi=160)
            paths.append(path)
        finally:
            plt.close(fig)
    return paths
