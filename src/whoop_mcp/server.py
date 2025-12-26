"""WHOOP MCP Server - Expose WHOOP recovery data to Claude Desktop."""

import asyncio

from fastmcp import FastMCP

from whoop_mcp.client import WhoopClient, WhoopAuthError, WhoopAPIError

# Create the MCP server
mcp = FastMCP("WHOOP Recovery")


def format_hours_minutes(hours: float) -> str:
    """Format hours as 'Xh Ym'."""
    h = int(hours)
    m = int((hours - h) * 60)
    return f"{h}h {m}m"


@mcp.tool()
async def get_today_summary() -> str:
    """Get today's complete WHOOP status: recovery, sleep, and strain in one call.

    This is the recommended daily check-in tool. Returns:
    - Recovery score with HRV and resting heart rate
    - Last night's sleep duration and quality
    - Current strain level and calories burned
    """
    try:
        client = WhoopClient()

        # Fetch all three in parallel
        recovery_task = client.get_today_recovery()
        sleep_task = client.get_last_sleep()
        cycles_task = client.get_cycles(limit=1)

        recovery, sleep, cycles = await asyncio.gather(
            recovery_task, sleep_task, cycles_task
        )

        lines = ["=== WHOOP Daily Summary ===", ""]

        # Recovery section
        lines.append("RECOVERY")
        if recovery and recovery.score_state == "SCORED" and recovery.score:
            score = recovery.score
            lines.append(f"  Score: {score.recovery_score}%")
            lines.append(f"  HRV: {score.hrv_rmssd_milli:.1f}ms")
            lines.append(f"  Resting HR: {score.resting_heart_rate}bpm")
            if score.spo2_percentage:
                lines.append(f"  SpO2: {score.spo2_percentage:.1f}%")
        elif recovery and recovery.score_state != "SCORED":
            lines.append(f"  {recovery.score_state.lower().replace('_', ' ')}")
        else:
            lines.append("  Not available yet")

        lines.append("")

        # Sleep section
        lines.append("SLEEP")
        if sleep and sleep.score_state == "SCORED" and sleep.score:
            score = sleep.score
            stages = score.stage_summary
            total = format_hours_minutes(stages.total_sleep_hours)
            deep = format_hours_minutes(stages.deep_sleep_hours)
            rem = format_hours_minutes(stages.rem_sleep_hours)
            lines.append(f"  Total: {total}")
            lines.append(f"  Deep: {deep} | REM: {rem}")
            if score.sleep_performance_percentage:
                lines.append(f"  Performance: {score.sleep_performance_percentage:.0f}%")
        elif sleep and sleep.score_state != "SCORED":
            lines.append(f"  {sleep.score_state.lower().replace('_', ' ')}")
        else:
            lines.append("  Not available yet")

        lines.append("")

        # Strain section
        lines.append("STRAIN")
        if cycles and cycles[0].score_state == "SCORED" and cycles[0].score:
            score = cycles[0].score
            calories = int(score.kilojoule * 0.239)
            lines.append(f"  Score: {score.strain:.1f} / 21")
            lines.append(f"  Calories: {calories} kcal")
            lines.append(f"  Avg HR: {score.average_heart_rate}bpm")
        elif cycles and cycles[0].score_state != "SCORED":
            lines.append(f"  {cycles[0].score_state.lower().replace('_', ' ')}")
        else:
            lines.append("  Not available yet")

        return "\n".join(lines)

    except WhoopAuthError as e:
        return f"Authentication error: {e}. Run the token setup script."
    except WhoopAPIError as e:
        return f"API error: {e}"


@mcp.tool()
async def get_sleep_trend(days: int = 7) -> str:
    """Get sleep data for the last N days.

    Args:
        days: Number of days to look back (default: 7, no limit)

    Shows sleep duration, efficiency, and performance trends.
    """

    try:
        client = WhoopClient()
        records = await client.get_sleep(limit=days)

        if not records:
            return "No sleep data available."

        # Filter to main sleeps only (no naps)
        main_sleeps = [r for r in records if not r.nap]

        if not main_sleeps:
            return "No main sleep data available."

        lines = [f"Sleep Trend (last {len(main_sleeps)} nights):", ""]

        for record in main_sleeps:
            if record.score_state == "SCORED" and record.score:
                stages = record.score.stage_summary
                hours = stages.total_sleep_hours
                perf = record.score.sleep_performance_percentage or 0
                date = record.start.strftime("%m/%d")

                # Visual bar based on hours (8h = full bar)
                filled = min(int(hours * 10 / 8), 10)
                bar = "█" * filled + "░" * (10 - filled)
                lines.append(f"{date}: {bar} {hours:.1f}h ({perf:.0f}% perf)")
            else:
                date = record.start.strftime("%m/%d")
                lines.append(f"{date}: [not scored]")

        # Calculate averages
        scored = [r for r in main_sleeps if r.score_state == "SCORED" and r.score]
        if scored:
            avg_hours = sum(r.score.stage_summary.total_sleep_hours for r in scored) / len(scored)
            avg_perf = sum(r.score.sleep_performance_percentage or 0 for r in scored) / len(scored)
            avg_deep = sum(r.score.stage_summary.deep_sleep_hours for r in scored) / len(scored)
            lines.append("")
            lines.append(f"Average: {avg_hours:.1f}h sleep, {avg_perf:.0f}% performance, {avg_deep:.1f}h deep")

        return "\n".join(lines)

    except WhoopAuthError as e:
        return f"Authentication error: {e}. Run the token setup script."
    except WhoopAPIError as e:
        return f"API error: {e}"


@mcp.tool()
async def get_recovery_trend(days: int = 7) -> str:
    """Get recovery scores for the last N days.

    Args:
        days: Number of days to look back (default: 7, no limit)

    Shows the trend of your recovery to help identify patterns.
    """

    try:
        client = WhoopClient()
        records = await client.get_recovery_trend(days)

        if not records:
            return "No recovery data available."

        lines = [f"Recovery Trend (last {len(records)} days):", ""]

        for record in records:
            if record.score_state == "SCORED" and record.score:
                score = record.score.recovery_score
                hrv = record.score.hrv_rmssd_milli
                date = record.created_at.strftime("%m/%d")

                # Simple visualization
                filled = int(score) // 10
                bar = "█" * filled + "░" * (10 - filled)
                lines.append(f"{date}: {bar} {score:.0f}% (HRV: {hrv:.0f}ms)")
            else:
                date = record.created_at.strftime("%m/%d")
                lines.append(f"{date}: [not scored]")

        # Calculate averages
        scored = [r for r in records if r.score_state == "SCORED" and r.score]
        if scored:
            avg_recovery = sum(r.score.recovery_score for r in scored) / len(scored)
            avg_hrv = sum(r.score.hrv_rmssd_milli for r in scored) / len(scored)
            lines.append("")
            lines.append(f"Average: {avg_recovery:.0f}% recovery, {avg_hrv:.0f}ms HRV")

        return "\n".join(lines)

    except WhoopAuthError as e:
        return f"Authentication error: {e}. Run the token setup script."
    except WhoopAPIError as e:
        return f"API error: {e}"


@mcp.tool()
async def get_workouts(limit: int = 5) -> str:
    """Get recent workouts with strain and heart rate data.

    Args:
        limit: Number of workouts to return (default: 5, no limit)

    Shows your recent activities including sport type, strain,
    duration, calories, and heart rate zones.
    """

    try:
        client = WhoopClient()
        workouts = await client.get_workouts(limit=limit)

        if not workouts:
            return "No workout data available."

        lines = [f"Recent Workouts ({len(workouts)}):", ""]

        for w in workouts:
            # Calculate duration
            duration_mins = (w.end - w.start).total_seconds() / 60
            date = w.start.strftime("%m/%d %H:%M")
            sport = w.sport_name.replace("_", " ").title()

            if w.score_state == "SCORED" and w.score:
                s = w.score
                workout_line = f"• {date} - {sport} ({duration_mins:.0f}min)"
                lines.append(workout_line)
                lines.append(f"  Strain: {s.strain:.1f} | {s.calories} cal | Avg HR: {s.average_heart_rate} bpm")

                # Show distance if available
                if s.distance_miles:
                    lines.append(f"  Distance: {s.distance_miles:.2f} mi")

                # Show HR zones summary (just the active ones)
                zones = s.zone_durations
                zone_parts = []
                if zones.zone_three_milli > 0:
                    zone_parts.append(f"Z3: {zones.zone_minutes(3):.0f}m")
                if zones.zone_four_milli > 0:
                    zone_parts.append(f"Z4: {zones.zone_minutes(4):.0f}m")
                if zones.zone_five_milli > 0:
                    zone_parts.append(f"Z5: {zones.zone_minutes(5):.0f}m")
                if zone_parts:
                    lines.append(f"  Zones: {' | '.join(zone_parts)}")

                lines.append("")
            else:
                lines.append(f"• {date} - {sport} ({duration_mins:.0f}min) [not scored]")
                lines.append("")

        return "\n".join(lines).strip()

    except WhoopAuthError as e:
        return f"Authentication error: {e}. Run the token setup script."
    except WhoopAPIError as e:
        return f"API error: {e}"


@mcp.tool()
async def get_morning_briefing() -> str:
    """Get a visual morning briefing banner with today's key WHOOP metrics.

    Returns the file path to a landscape dashboard image showing recovery,
    HRV, sleep, and strain at a glance. Designed for quick morning check-ins.
    """
    import matplotlib.pyplot as plt
    import tempfile
    import os

    try:
        client = WhoopClient()

        # Fetch all data in parallel
        recovery, sleep, cycles = await asyncio.gather(
            client.get_today_recovery(),
            client.get_last_sleep(),
            client.get_cycles(limit=1)
        )

        # Extract values
        recovery_pct = recovery.score.recovery_score if recovery and recovery.score else None
        hrv = recovery.score.hrv_rmssd_milli if recovery and recovery.score else None
        sleep_hours = sleep.score.stage_summary.total_sleep_hours if sleep and sleep.score else None
        strain = cycles[0].score.strain if cycles and cycles[0].score else None

        # Create landscape banner (800x200)
        fig, ax = plt.subplots(figsize=(8, 2))
        ax.set_xlim(0, 100)
        ax.set_ylim(0, 100)
        ax.axis('off')

        # Light background
        fig.patch.set_facecolor('#ffffff')
        ax.set_facecolor('#ffffff')

        # Recovery (large, left side, color-coded)
        if recovery_pct is not None:
            color = '#00a651' if recovery_pct >= 67 else '#f5a623' if recovery_pct >= 34 else '#d0021b'
            ax.text(12, 50, f"{recovery_pct:.0f}%", fontsize=36, fontweight='bold',
                   color=color, ha='center', va='center')
            ax.text(12, 20, "RECOVERY", fontsize=8, color='#666', ha='center')

        # HRV
        if hrv is not None:
            ax.text(35, 50, f"{hrv:.0f}", fontsize=24, fontweight='bold',
                   color='#333', ha='center', va='center')
            ax.text(35, 25, "HRV (ms)", fontsize=8, color='#666', ha='center')

        # Sleep
        if sleep_hours is not None:
            h = int(sleep_hours)
            m = int((sleep_hours - h) * 60)
            ax.text(58, 50, f"{h}h {m}m", fontsize=24, fontweight='bold',
                   color='#333', ha='center', va='center')
            ax.text(58, 25, "SLEEP", fontsize=8, color='#666', ha='center')

        # Strain
        if strain is not None:
            ax.text(82, 50, f"{strain:.1f}", fontsize=24, fontweight='bold',
                   color='#0077b6', ha='center', va='center')
            ax.text(82, 25, "STRAIN", fontsize=8, color='#666', ha='center')

        plt.tight_layout(pad=0.5)

        # Save to temp file
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, "whoop_morning_briefing.png")
        fig.savefig(file_path, format='png', dpi=150,
                   facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close(fig)

        return file_path

    except WhoopAuthError as e:
        return f"Authentication error: {e}. Run the token setup script."
    except WhoopAPIError as e:
        return f"API error: {e}"
    except Exception as e:
        return f"Error generating briefing: {e}"


# Entry point for running the server
def main():
    """Run the MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
