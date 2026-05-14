"""
Chip manager: create and reflow period chips (small QPushButton chips).
This is intentionally small and stateless; widget_chart keeps state.
"""
from PyQt5.QtWidgets import QPushButton, QLabel
from PyQt5.QtCore import Qt
import traceback


def reflow_chips(period_chip_layout, period_chip_container, selected_list, applied_interval,
                 apply_callback, chip_window_start, chip_window_size, period_slider=None):
    """
    Repopulate period_chip_layout with buttons for selected_list slice.
    Returns new (chip_window_start, chip_window_size).
    """
    try:
        # clear layout
        while period_chip_layout.count():
            itm = period_chip_layout.takeAt(0)
            w = itm.widget()
            if w is not None:
                try:
                    w.setParent(None)
                except Exception:
                    pass
                try:
                    w.deleteLater()
                except Exception:
                    pass

        # build chips
        show_list = selected_list[chip_window_start: chip_window_start + chip_window_size]
        for interval in show_list:
            label = interval.get("label") if isinstance(interval, dict) else interval
            btn = QPushButton(label, period_chip_container)
            btn.setObjectName("PeriodChip")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setCheckable(True)
            
            # Extract key from interval
            if isinstance(interval, dict):
                key = interval.get("key")
                is_active = (key == applied_interval)
            else:
                key = interval
                is_active = (interval == applied_interval)
            
            btn.setChecked(is_active)
            btn.setFixedHeight(24)
            
            # Apply active/inactive styles
            if is_active:
                btn.setStyleSheet(
                    "background-color: #3b82f6; color: white; "
                    "border-radius: 4px; padding: 2px 8px; font-weight: 600;"
                )
            else:
                btn.setStyleSheet(
                    "background-color: #e5e7eb; color: #374151; "
                    "border-radius: 4px; padding: 2px 8px;"
                )

            # ✅ FIX: Use functools.partial for proper closure binding
            # This ensures 'key' is captured correctly in the lambda scope
            def make_click_handler(interval_key):
                """Factory function to create click handler with proper closure."""
                return lambda checked: apply_callback(interval_key)
            
            btn.clicked.connect(make_click_handler(key))
            period_chip_layout.addWidget(btn)

        # add more indicator if needed (caller handles showing slider)
        # caller may add ellipsis etc.

    except Exception:
        traceback.print_exc()

    finally:
        return chip_window_start, chip_window_size