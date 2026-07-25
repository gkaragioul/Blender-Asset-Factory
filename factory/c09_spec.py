from __future__ import annotations

from copy import deepcopy


_C09_SPEC = {
    "schema_version": 1,
    "units": "meters",
    "dimensions_m": {
        "overall_length": 1.12,
        "barrel_length": 0.71,
        "length_of_pull": 0.365,
        "receiver_length": 0.105,
        "receiver_width": 0.054,
        "receiver_height": 0.068,
        "barrel_center_spacing": 0.026,
        "fore_end_length": 0.265,
    },
    "barrels": [
        {
            "name": "barrel_left",
            "center_y_m": 0.013,
            "center_z_m": 0.045,
            "start_x_m": 0.035,
            "length_m": 0.71,
            "outer_radius_m": 0.0115,
            "bore_radius_m": 0.00925,
        },
        {
            "name": "barrel_right",
            "center_y_m": -0.013,
            "center_z_m": 0.045,
            "start_x_m": 0.035,
            "length_m": 0.71,
            "outer_radius_m": 0.0115,
            "bore_radius_m": 0.00925,
        },
    ],
    "hinge": {
        "axis": "Y",
        "center_x_m": 0.018,
        "center_y_m": 0.0,
        "center_z_m": 0.008,
        "pin_radius_m": 0.0105,
    },
    "stock_profile": [
        [-0.055, 0.036, 0.031],
        [-0.105, 0.022, 0.030],
        [-0.175, 0.006, 0.027],
        [-0.265, -0.020, 0.031],
        [-0.385, -0.058, 0.045],
        [-0.375, -0.150, 0.050],
        [-0.260, -0.137, 0.047],
        [-0.145, -0.082, 0.034],
        [-0.080, -0.047, 0.027],
    ],
    "fore_end": {
        "start_x_m": 0.075,
        "length_m": 0.265,
        "center_z_m": 0.015,
        "half_width_m": 0.021,
        "half_height_m": 0.021,
    },
    "semantic_parts": [
        "stock",
        "receiver",
        "barrel_left",
        "barrel_right",
        "rib",
        "fore_end",
        "hinge",
        "top_lever",
        "trigger_front",
        "trigger_rear",
        "trigger_guard",
        "bead_sight",
        "butt_pad",
        "extractor",
    ],
    "moving_groups": {
        "break_action": ["barrel_left", "barrel_right", "rib", "fore_end"],
        "controls": ["top_lever", "trigger_front", "trigger_rear"],
    },
}


def build_c09_spec() -> dict:
    """Return an isolated copy of the approved C09 mechanical contract."""
    return deepcopy(_C09_SPEC)
