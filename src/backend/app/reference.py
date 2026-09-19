"""Demonstration reference data for Mysuru.

IMPORTANT: locality coordinates and boundary polygons here are APPROXIMATE
DEMONSTRATION GEOGRAPHY generated for Mysuru CivicPulse. They are not authoritative
MCC ward boundaries and must be replaced with official GIS data before any
real deployment. See docs/limitations.md.
"""
from __future__ import annotations

# (name_en, name_kn, lat, lng) - approximate locality centres.
LOCALITIES: list[tuple[str, str, float, float]] = [
    ("Kuvempunagar", "ಕುವೆಂಪುನಗರ", 12.2846, 76.6205),
    ("Vijayanagar", "ವಿಜಯನಗರ", 12.3210, 76.6112),
    ("Jayalakshmipuram", "ಜಯಲಕ್ಷ್ಮೀಪುರಂ", 12.3086, 76.6266),
    ("Saraswathipuram", "ಸರಸ್ವತಿಪುರಂ", 12.3062, 76.6338),
    ("Gokulam", "ಗೋಕುಲಂ", 12.3155, 76.6353),
    ("Lakshmipuram", "ಲಕ್ಷ್ಮೀಪುರಂ", 12.3049, 76.6522),
    ("Chamarajapuram", "ಚಾಮರಾಜಪುರಂ", 12.3012, 76.6467),
    ("Agrahara", "ಅಗ್ರಹಾರ", 12.3068, 76.6552),
    ("Devaraja Mohalla", "ದೇವರಾಜ ಮೊಹಲ್ಲಾ", 12.3120, 76.6530),
    ("Nazarbad", "ನಜರ್‌ಬಾದ್", 12.3021, 76.6631),
    ("Siddhartha Nagar", "ಸಿದ್ಧಾರ್ಥ ನಗರ", 12.2920, 76.6455),
    ("Bannimantap", "ಬನ್ನಿಮಂಟಪ", 12.3300, 76.6540),
    ("Udayagiri", "ಉದಯಗಿರಿ", 12.3175, 76.6710),
    ("Rajiv Nagar", "ರಾಜೀವ್ ನಗರ", 12.2760, 76.6080),
    ("Hebbal", "ಹೆಬ್ಬಾಳ", 12.3480, 76.6180),
    ("Metagalli", "ಮೇಟಗಳ್ಳಿ", 12.3405, 76.6295),
    ("Vidyaranyapuram", "ವಿದ್ಯಾರಣ್ಯಪುರಂ", 12.2905, 76.6383),
    ("Bogadi", "ಬೋಗಾದಿ", 12.3212, 76.5942),
    ("Srirampura", "ಶ್ರೀರಾಂಪುರ", 12.2988, 76.6180),
    ("Ramakrishna Nagar", "ರಾಮಕೃಷ್ಣ ನಗರ", 12.2810, 76.6318),
    ("Hinkal", "ಹಿಂಕಲ್", 12.3455, 76.6045),
    ("Yelwal", "ಯಳವಾಲ", 12.3860, 76.5750),
    ("Rammanahalli", "ರಮ್ಮನಹಳ್ಳಿ", 12.3612, 76.5885),
    ("Alanahalli", "ಆಲನಹಳ್ಳಿ", 12.2690, 76.6540),
    ("Kadakola", "ಕಡಕೊಳ", 12.2180, 76.6480),
]

#: Sensitive places used by the priority engine's location-sensitivity factor.
SENSITIVE_PLACES: list[dict] = [
    {"type": "HOSPITAL", "name": "K R Hospital (demo)", "lat": 12.3070, "lng": 76.6512},
    {"type": "HOSPITAL", "name": "Cheluvamba Hospital (demo)", "lat": 12.3090, "lng": 76.6480},
    {"type": "HOSPITAL", "name": "JSS Hospital (demo)", "lat": 12.2933, "lng": 76.6390},
    {"type": "HOSPITAL", "name": "Apollo BGS (demo)", "lat": 12.3375, "lng": 76.6120},
    {"type": "SCHOOL", "name": "Kuvempunagar Govt School (demo)", "lat": 12.2860, "lng": 76.6190},
    {"type": "SCHOOL", "name": "Vijayanagar Public School (demo)", "lat": 12.3225, "lng": 76.6098},
    {"type": "SCHOOL", "name": "Saraswathipuram High School (demo)", "lat": 12.3055, "lng": 76.6350},
    {"type": "SCHOOL", "name": "Hebbal Primary School (demo)", "lat": 12.3470, "lng": 76.6195},
    {"type": "SCHOOL", "name": "Vidyaranyapuram School (demo)", "lat": 12.2915, "lng": 76.6372},
    {"type": "SCHOOL", "name": "Bogadi Govt School (demo)", "lat": 12.3220, "lng": 76.5950},
    {"type": "JUNCTION", "name": "Ring Road Junction (demo)", "lat": 12.3300, "lng": 76.6420},
    {"type": "JUNCTION", "name": "Highway Circle (demo)", "lat": 12.3140, "lng": 76.6690},
    {"type": "BUS_STAND", "name": "Central Bus Stand (demo)", "lat": 12.3095, "lng": 76.6555},
    {"type": "MARKET", "name": "Devaraja Market (demo)", "lat": 12.3096, "lng": 76.6540},
    {"type": "MARKET", "name": "Bannimantap Market (demo)", "lat": 12.3290, "lng": 76.6525},
]

#: (code, en, kn, base_severity 1-5, safety_impact 0-3, demo SLA hours, hist avg hours)
CATEGORIES: list[tuple[str, str, str, int, int, int, float]] = [
    ("POTHOLE", "Pothole / Road damage", "ಗುಂಡಿ / ರಸ್ತೆ ಹಾನಿ", 4, 3, 72, 96.0),
    ("GARBAGE", "Garbage overflow", "ಕಸ ತುಂಬಿ ಹರಿಯುವಿಕೆ", 3, 2, 24, 31.0),
    ("STREETLIGHT", "Streetlight not working", "ಬೀದಿ ದೀಪ ಕೆಟ್ಟಿದೆ", 3, 2, 48, 54.0),
    ("DRAIN", "Drain blockage", "ಚರಂಡಿ ಕಟ್ಟಿಕೊಂಡಿದೆ", 4, 2, 24, 44.0),
    ("WATER", "Water supply / leakage", "ನೀರು ಸರಬರಾಜು / ಸೋರಿಕೆ", 4, 1, 24, 38.0),
    ("ILLEGAL_DUMPING", "Illegal dumping", "ಅಕ್ರಮ ಕಸ ಸುರಿಯುವಿಕೆ", 3, 1, 24, 40.0),
    ("STRAY_ANIMAL", "Stray animal hazard", "ಬೀಡಾಡಿ ಪ್ರಾಣಿ ಅಪಾಯ", 3, 2, 48, 61.0),
    ("SEWAGE", "Sewage overflow", "ಒಳಚರಂಡಿ ಉಕ್ಕುವಿಕೆ", 5, 3, 24, 47.0),
    ("TREE_FALL", "Fallen tree / branch", "ಬಿದ್ದ ಮರ / ಕೊಂಬೆ", 4, 3, 12, 19.0),
    ("FOOTPATH", "Damaged footpath", "ಹಾನಿಗೊಂಡ ಪಾದಚಾರಿ ಮಾರ್ಗ", 2, 1, 96, 120.0),
    ("SIGNAGE", "Damaged signage / signal", "ಹಾನಿಗೊಂಡ ಸೂಚನಾ ಫಲಕ", 3, 2, 72, 80.0),
    ("PUBLIC_TOILET", "Public toilet condition", "ಸಾರ್ವಜನಿಕ ಶೌಚಾಲಯ ಸ್ಥಿತಿ", 2, 1, 48, 66.0),
]

#: Phrase banks used only by the synthetic seed generator.
COMPLAINT_PHRASES: dict[str, list[str]] = {
    "POTHOLE": [
        "Large pothole on the main road causing two-wheelers to swerve",
        "Deep pothole near the traffic signal, water collects during rain",
        "Road surface broken for nearly 20 feet, dangerous at night",
        "Multiple potholes along the stretch, autos are avoiding this route",
    ],
    "GARBAGE": [
        "Garbage bin overflowing for several days, stray dogs scattering waste",
        "Waste not collected this week, strong smell near the houses",
        "Heap of garbage dumped at the corner, blocking half the footpath",
    ],
    "STREETLIGHT": [
        "Streetlight not working for over a week, the lane is completely dark",
        "Three lights on this stretch are off, unsafe for women walking at night",
        "Light flickers all night and goes off completely after midnight",
    ],
    "DRAIN": [
        "Drain completely blocked, dirty water flowing onto the road",
        "Storm water drain choked with plastic, will flood in the next rain",
        "Open drain overflowing near the houses, mosquito problem increasing",
    ],
    "WATER": [
        "Pipeline leaking continuously, drinking water being wasted",
        "No water supply in this street for three days",
        "Water leaking from the main line and road is getting damaged",
    ],
    "ILLEGAL_DUMPING": [
        "Construction debris dumped on the empty site at night",
        "Someone is dumping hotel waste here regularly after dark",
    ],
    "STRAY_ANIMAL": [
        "Aggressive stray dogs near the school gate in the morning",
        "Cattle sitting on the main road, traffic hazard at night",
    ],
    "SEWAGE": [
        "Sewage overflowing onto the street, unbearable smell",
        "Manhole overflowing continuously, children walk through this road",
    ],
    "TREE_FALL": [
        "Large branch has fallen and is blocking half the road",
        "Tree leaning dangerously over the power line after the rain",
    ],
    "FOOTPATH": [
        "Footpath slabs broken, elderly people are forced onto the road",
        "Pavement tiles missing for a long stretch",
    ],
    "SIGNAGE": [
        "Traffic signal not functioning at the junction since yesterday",
        "Road sign bent and unreadable after an accident",
    ],
    "PUBLIC_TOILET": [
        "Public toilet has no water supply and is unusable",
        "Toilet block is not being cleaned, very poor condition",
    ],
}
