import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ── Strategy coordinates (EaR, Target Earnings) ──────────────────────────────
strategies = {
    'A': {'ear': 25, 'target': 100, 'color': '#185FA5'},
    'B': {'ear': 25, 'target': 110, 'color': '#3B6D11'},
    'C': {'ear': 35, 'target': 118, 'color': '#854F0B'},
}

# ── Efficient frontier curve ──────────────────────────────────────────────────
# As EaR increases (less hedging), target earnings rise — risk/return tradeoff
ear_curve   = np.linspace(10, 45, 200)
target_curve = 85 + 12 * np.log(ear_curve - 8)   # concave frontier shape

# ── Plot ──────────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(8, 6))
fig.patch.set_facecolor('#FAFAFA')
ax.set_facecolor('#FAFAFA')

# Efficient frontier
ax.plot(ear_curve, target_curve,
        color='#B5D4F4', linewidth=2.0, linestyle='--',
        zorder=1, label='Efficient frontier')

# Strategy points
for name, s in strategies.items():
    ax.scatter(s['ear'], s['target'],
               color=s['color'], s=120, zorder=4, clip_on=False)
    ax.annotate(
        f"  {name}\n  (EaR=${s['ear']}mm, target=${s['target']}mm)",
        xy=(s['ear'], s['target']),
        fontsize=9.5, color=s['color'], fontweight='bold',
        va='center'
    )

# ── Dominance arrow A → B (same EaR, higher target) ─────────────────────────
ax.annotate(
    '', xy=(strategies['B']['ear'], strategies['B']['target']),
    xytext=(strategies['A']['ear'], strategies['A']['target']),
    arrowprops=dict(arrowstyle='->', color='#3B6D11', lw=1.4,
                    connectionstyle='arc3,rad=0.0')
)
ax.text(
    strategies['A']['ear'] - 3.2,
    (strategies['A']['target'] + strategies['B']['target']) / 2,
    'B dominates A\n(same EaR,\nhigher target)',
    fontsize=8, color='#3B6D11', ha='right', va='center',
    bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
              edgecolor='#C0DD97', alpha=0.9)
)

# ── Risk/return arrow B → C ───────────────────────────────────────────────────
ax.annotate(
    '', xy=(strategies['C']['ear'], strategies['C']['target']),
    xytext=(strategies['B']['ear'], strategies['B']['target']),
    arrowprops=dict(arrowstyle='->', color='#854F0B', lw=1.4,
                    connectionstyle='arc3,rad=-0.25')
)
ax.text(
    (strategies['B']['ear'] + strategies['C']['ear']) / 2,
    strategies['B']['target'] - 3.5,
    'Higher return\nbut higher risk',
    fontsize=8, color='#854F0B', ha='center', va='top',
    bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
              edgecolor='#FAC775', alpha=0.9)
)

# ── Reference lines ───────────────────────────────────────────────────────────
for name, s in strategies.items():
    ax.plot([s['ear'], s['ear']], [ax.get_ylim()[0] if ax.get_ylim()[0] > 0 else 80, s['target']],
            color=s['color'], linewidth=0.6, linestyle=':', alpha=0.5, zorder=0)
    ax.plot([10, s['ear']], [s['target'], s['target']],
            color=s['color'], linewidth=0.6, linestyle=':', alpha=0.5, zorder=0)

# ── Axes & style ──────────────────────────────────────────────────────────────
ax.set_xlim(10, 48)
ax.set_ylim(80, 130)

ax.set_xlabel('Earnings-at-Risk — EaR (USD mm)', fontsize=11, color='#444')
ax.set_ylabel('Target earnings (USD mm)',          fontsize=11, color='#444')
ax.set_title('Chart 3.4\nHedging strategies: target earnings vs EaR',
             fontsize=11, color='#2C2C2A', pad=12, loc='left')

ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:.0f}mm'))
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:.0f}mm'))

ax.tick_params(colors='#666', labelsize=9)
ax.spines[['top', 'right']].set_visible(False)
ax.spines[['left', 'bottom']].set_color('#D3D1C7')
ax.grid(color='#D3D1C7', linewidth=0.5, linestyle='--', zorder=0)

# ── Legend ────────────────────────────────────────────────────────────────────
legend_elements = [
    mpatches.Patch(color='#185FA5', label='A — arbitrary hedge ratios (e.g. 50% across all)'),
    mpatches.Patch(color='#3B6D11', label='B — efficient: same EaR, higher target than A'),
    mpatches.Patch(color='#854F0B', label='C — higher target than B, but higher EaR'),
    plt.Line2D([0], [0], color='#B5D4F4', linewidth=2, linestyle='--',
               label='Efficient frontier'),
]
ax.legend(handles=legend_elements, fontsize=8.5, framealpha=0.7,
          loc='upper left', borderpad=0.8)

plt.tight_layout()
plt.savefig('chart_3_4.png', dpi=150, bbox_inches='tight', facecolor='#FAFAFA')
plt.show()
print("Saved: chart_3_4.png")