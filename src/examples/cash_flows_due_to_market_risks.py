import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

rng = np.random.default_rng(42)

N = 100_000

# ── Company parameters ────────────────────────────────────────────────────────
TARGETED_CF    = 120   # USD mm  — budgeted / expected cash flow
MIN_TOLERABLE  = 90    # USD mm  — floor below which dividend cut / capex freeze
MEAN_CF        = 120
STD_CF         = 18    # gives a realistic spread around the target

cash_flows = rng.normal(loc=MEAN_CF, scale=STD_CF, size=N)

pct5  = np.percentile(cash_flows, 5)   # actual CFaR threshold from distribution
cfar_max  = TARGETED_CF - MIN_TOLERABLE  # maximum tolerable CFaR = 30mm
cfar_actual = TARGETED_CF - pct5        # CFaR implied by the distribution

# ── Plot ──────────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 6))
fig.patch.set_facecolor('#FAFAFA')
ax.set_facecolor('#FAFAFA')

# ── Histogram ─────────────────────────────────────────────────────────────────
n_counts, bins, patches_list = ax.hist(
    cash_flows, bins=100,
    color='#B5D4F4', edgecolor='white', linewidth=0.3,
    zorder=2, density=True
)

# Colour zones:
#   red   — below minimum tolerable (unacceptable)
#   amber — between min tolerable and pct5 (warning zone)
#   blue  — above pct5 (normal range, already set)
for patch, left in zip(patches_list, bins[:-1]):
    if left < MIN_TOLERABLE:
        patch.set_facecolor('#F09595')       # red: below floor
    elif left < pct5:
        patch.set_facecolor('#FAC775')       # amber: warning zone

y_top = n_counts.max()

# ── Shaded regions ────────────────────────────────────────────────────────────
ax.axvspan(cash_flows.min(), MIN_TOLERABLE,
           alpha=0.08, color='#E24B4A', zorder=1, label='Unacceptable zone')
ax.axvspan(MIN_TOLERABLE, pct5,
           alpha=0.08, color='#EF9F27', zorder=1, label='Warning zone')

# ── Vertical lines ────────────────────────────────────────────────────────────
ax.axvline(TARGETED_CF,   color='#185FA5', linewidth=2.0, linestyle='-',  zorder=4)
ax.axvline(MIN_TOLERABLE, color='#A32D2D', linewidth=2.0, linestyle='--', zorder=4)
ax.axvline(pct5,          color='#854F0B', linewidth=1.6, linestyle=':',  zorder=4)

# ── Labels on vertical lines ─────────────────────────────────────────────────
ax.text(TARGETED_CF + 0.5,   y_top * 1.01, f'Targeted CF\n${TARGETED_CF}mm',
        ha='left',  va='bottom', fontsize=9, color='#185FA5', fontweight='bold')
ax.text(MIN_TOLERABLE - 0.5, y_top * 1.01, f'Minimum tolerable\n${MIN_TOLERABLE}mm',
        ha='right', va='bottom', fontsize=9, color='#A32D2D', fontweight='bold')
ax.text(pct5 - 0.5,          y_top * 0.60, f'5th pct\n${pct5:.1f}mm',
        ha='right', va='center', fontsize=8.5, color='#854F0B')

# ── Arrow: Maximum CFaR (targeted → minimum tolerable) ───────────────────────
y_arrow1 = y_top * 0.80
ax.annotate('', xy=(MIN_TOLERABLE, y_arrow1), xytext=(TARGETED_CF, y_arrow1),
            arrowprops=dict(arrowstyle='<->', color='#A32D2D', lw=1.6))
ax.text((TARGETED_CF + MIN_TOLERABLE) / 2, y_arrow1 * 1.032,
        f'Max CFaR limit = ${cfar_max}mm',
        ha='center', va='bottom', fontsize=9.5,
        color='#A32D2D', fontweight='bold')

# ── Arrow: Actual CFaR (targeted → pct5) ─────────────────────────────────────
y_arrow2 = y_top * 0.62
ax.annotate('', xy=(pct5, y_arrow2), xytext=(TARGETED_CF, y_arrow2),
            arrowprops=dict(arrowstyle='<->', color='#854F0B', lw=1.4))
ax.text((TARGETED_CF + pct5) / 2, y_arrow2 * 1.032,
        f'Actual CFaR (95%) = ${cfar_actual:.1f}mm',
        ha='center', va='bottom', fontsize=9,
        color='#854F0B', fontweight='bold')

# ── Footnote annotation ───────────────────────────────────────────────────────
ax.text(0.01, 0.03,
        'Below minimum tolerable: company may need to cut dividend\n'
        'or forego planned investment from internally generated funds.',
        transform=ax.transAxes, fontsize=8, color='#888',
        va='bottom', style='italic')

# ── Axes & style ──────────────────────────────────────────────────────────────
ax.set_xlabel('12-month cash flow (USD mm)', fontsize=11, color='#444')
ax.set_ylabel('Probability density',         fontsize=11, color='#444')
ax.set_title('Chart 3.5\nCash flow distribution — CFaR limit setting',
             fontsize=11, color='#2C2C2A', pad=12, loc='left')

ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:.0f}mm'))
ax.tick_params(colors='#666', labelsize=9)
ax.spines[['top', 'right']].set_visible(False)
ax.spines[['left', 'bottom']].set_color('#D3D1C7')
ax.grid(axis='x', color='#D3D1C7', linewidth=0.5, linestyle='--', zorder=0)

# ── Legend ────────────────────────────────────────────────────────────────────
from matplotlib.lines import Line2D
legend_elements = [
    Line2D([0], [0], color='#185FA5', lw=2,   linestyle='-',  label=f'Targeted cash flow (${TARGETED_CF}mm)'),
    Line2D([0], [0], color='#A32D2D', lw=2,   linestyle='--', label=f'Minimum tolerable (${MIN_TOLERABLE}mm)'),
    Line2D([0], [0], color='#854F0B', lw=1.6, linestyle=':',  label=f'5th percentile (${pct5:.1f}mm)'),
    mpatches.Patch(color='#F09595', alpha=0.6, label='Unacceptable zone'),
    mpatches.Patch(color='#FAC775', alpha=0.6, label='Warning zone'),
]
ax.legend(handles=legend_elements, fontsize=8.5, framealpha=0.7, loc='upper left')

plt.tight_layout()
plt.savefig('chart_3_5.png', dpi=150, bbox_inches='tight', facecolor='#FAFAFA')
plt.show()
print("Saved: chart_3_5.png")