import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

rng = np.random.default_rng(42)

N = 100_000

MEAN_UNHEDGED   = 105
STD_UNHEDGED    = 15
TARGET_UNHEDGED = 105
EAR_UNHEDGED    = 25

MEAN_HEDGED     = 100
STD_HEDGED      = 6.1
TARGET_HEDGED   = 100
EAR_HEDGED      = 10


def generate_earnings(mean, std, n):
    return rng.normal(loc=mean, scale=std, size=n)


def plot_ear_chart(ax, earnings, target, ear, title, chart_label):
    pct5  = np.percentile(earnings, 5)
    mean  = np.mean(earnings)
    pct95 = np.percentile(earnings, 95)

    n_counts, bins, patches_list = ax.hist(
        earnings, bins=100,
        color='#B5D4F4', edgecolor='white', linewidth=0.3,
        zorder=2, density=True
    )

    for patch, left in zip(patches_list, bins[:-1]):
        if left < pct5:
            patch.set_facecolor('#F09595')

    ax.axvspan(earnings.min(), pct5, alpha=0.10, color='#E24B4A', zorder=1)

    ax.axvline(target, color='#185FA5', linewidth=2.0,
               linestyle='-', zorder=4, label=f'Earnings target: ${target}mm')
    ax.axvline(pct5,   color='#A32D2D', linewidth=1.8,
               linestyle='--', zorder=4, label=f'5th percentile: ${pct5:.1f}mm')

    y_top   = n_counts.max()
    y_arrow = y_top * 0.78

    ax.annotate(
        '',
        xy=(pct5, y_arrow), xytext=(target, y_arrow),
        arrowprops=dict(arrowstyle='<->', color='#A32D2D', lw=1.6)
    )
    ax.text(
        (pct5 + target) / 2, y_arrow * 1.035,
        f'EaR (95%) = ${ear}mm',
        ha='center', va='bottom', fontsize=9.5,
        color='#A32D2D', fontweight='bold'
    )

    ax.text(
        target, y_top * 1.01, f'${target}mm',
        ha='center', va='bottom', fontsize=9,
        color='#185FA5', fontweight='bold'
    )

    ax.set_title(f'{chart_label}  —  {title}',
                 fontsize=11, color='#2C2C2A', pad=10, loc='left')
    ax.set_xlabel('12-month earnings (USD mm)', fontsize=10, color='#555')
    ax.set_ylabel('Probability density',        fontsize=10, color='#555')

    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:.0f}mm'))
    ax.tick_params(colors='#666', labelsize=9)
    ax.spines[['top', 'right']].set_visible(False)
    ax.spines[['left', 'bottom']].set_color('#D3D1C7')
    ax.grid(axis='x', color='#D3D1C7', linewidth=0.5, linestyle='--', zorder=0)
    ax.legend(fontsize=9, framealpha=0.5, loc='upper left')

    summary = (
        f'Mean:       ${mean:.1f}mm\n'
        f'Target:     ${target}mm\n'
        f'EaR (95%):  ${ear}mm\n'
        f'Pct 5:      ${pct5:.1f}mm\n'
        f'Pct 95:     ${pct95:.1f}mm'
    )
    ax.text(
        0.98, 0.97, summary,
        transform=ax.transAxes,
        fontsize=8.5, va='top', ha='right', color='#444',
        bbox=dict(boxstyle='round,pad=0.5', facecolor='white',
                  edgecolor='#D3D1C7', alpha=0.85)
    )


# ── 2 rows, 1 column ──────────────────────────────────────────────────────────
fig = plt.figure(figsize=(10, 10))
fig.patch.set_facecolor('#FAFAFA')

gs = GridSpec(2, 1, figure=fig, hspace=0.45)
ax1 = fig.add_subplot(gs[0])
ax2 = fig.add_subplot(gs[1])
ax1.set_facecolor('#FAFAFA')
ax2.set_facecolor('#FAFAFA')

earnings_unhedged = generate_earnings(MEAN_UNHEDGED, STD_UNHEDGED, N)
earnings_hedged   = generate_earnings(MEAN_HEDGED,   STD_HEDGED,   N)

plot_ear_chart(ax1, earnings_unhedged,
               target=TARGET_UNHEDGED, ear=EAR_UNHEDGED,
               title='Earnings distribution — no hedge',
               chart_label='Chart 3.1')

plot_ear_chart(ax2, earnings_hedged,
               target=TARGET_HEDGED, ear=EAR_HEDGED,
               title='Earnings distribution — partial hedge',
               chart_label='Chart 3.2')

fig.suptitle(
    'Earnings-at-Risk (EaR) — commodity price exposure\n'
    '12-month horizon · 95% confidence level',
    fontsize=12, color='#2C2C2A', y=1.01
)

plt.savefig('charts_3_1_3_2.png', dpi=150, bbox_inches='tight',
            facecolor='#FAFAFA')
plt.show()
print("Saved: charts_3_1_3_2.png")