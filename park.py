"""Fictional park data and walking routes."""

from datetime import datetime, timedelta, timezone
from heapq import heappop, heappush

PARK_TIME = timezone(timedelta(hours=8), "SGT")

RIDES = {
    "Summit Coaster": {
        "zone": "Highlands",
        "kind": "Thrill ride",
        "description": "Race past the ridgeline on Skytrail’s fastest coaster.",
        "capacity": 4,
    },
    "Canopy Flyers": {
        "zone": "Highlands",
        "kind": "Family ride",
        "description": "Glide over the treetops in a two-seat glider.",
        "capacity": 3,
    },
    "Silverwater Rapids": {
        "zone": "Riverlands",
        "kind": "Water ride",
        "description": "Follow the river through twisting channels and a final splash.",
        "capacity": 5,
    },
    "Riverboat Drift": {
        "zone": "Riverlands",
        "kind": "Scenic ride",
        "description": "Take a gentle boat ride through the park’s wetlands.",
        "capacity": 4,
    },
    "Lantern Carousel": {
        "zone": "Lantern Square",
        "kind": "Family ride",
        "description": "Take a spin beneath the lanterns on a carved woodland animal.",
        "capacity": 6,
    },
    "Sky Observatory": {
        "zone": "Lantern Square",
        "kind": "Scenic ride",
        "description": "Rise above the square for a view across the entire park.",
        "capacity": 3,
    },
}

# Each tuple describes a walkway that visitors can use in either direction.
WALKWAYS = [
    ("Main Entrance", "Lantern Square", 2),
    ("Main Entrance", "River Bridge", 4),
    ("Lantern Square", "Lookout Junction", 3),
    ("Lantern Square", "River Bridge", 5),
    ("Lookout Junction", "River Bridge", 2),
    ("Lookout Junction", "Summit Coaster", 5),
    ("Lookout Junction", "Canopy Flyers", 2),
    ("Canopy Flyers", "Summit Coaster", 2),
    ("River Bridge", "Silverwater Rapids", 3),
    ("River Bridge", "Riverboat Drift", 2),
    ("Silverwater Rapids", "Riverboat Drift", 3),
    ("Lantern Square", "Lantern Carousel", 1),
    ("Lantern Square", "Sky Observatory", 3),
]
WALKING_GRAPH = {}
for start, end, minutes in WALKWAYS:
    WALKING_GRAPH.setdefault(start, {})[end] = minutes
    WALKING_GRAPH.setdefault(end, {})[start] = minutes


def shortest_path(start, destination, graph=WALKING_GRAPH):
    """Return the shortest path and total walking minutes, if reachable."""
    if start not in graph or destination not in graph:
        return None

    distances = {start: 0}
    previous = {}
    frontier = [(0, start)]

    while frontier:
        minutes, landmark = heappop(frontier)
        if minutes != distances[landmark]:
            continue  # This entry was replaced by a shorter route.
        if landmark == destination:
            path = [landmark]
            while path[-1] != start:
                path.append(previous[path[-1]])
            return list(reversed(path)), minutes

        for neighbor, walking_time in graph[landmark].items():
            new_distance = minutes + walking_time
            if neighbor not in distances or new_distance < distances[neighbor]:
                distances[neighbor] = new_distance
                previous[neighbor] = landmark
                heappush(frontier, (new_distance, neighbor))

    return None


def window_label(start_at, end_at):
    """Format a park return window, including the date if it crosses midnight."""
    start = datetime.fromtimestamp(start_at, PARK_TIME)
    end = datetime.fromtimestamp(end_at, PARK_TIME)
    start_label = start.strftime("%d %b, %H:%M")
    end_label = end.strftime("%H:%M" if start.date() == end.date() else "%d %b, %H:%M")
    return f"{start_label} – {end_label} SGT"
