"""Streamlit interface for the Skytrail Park virtual queue."""

import hmac
import os
from datetime import datetime
from time import time

import streamlit as st

from park import PARK_TIME, RIDES, WALKING_GRAPH, shortest_path, window_label
from qr_pass import qr_png
from queue_store import (
    authenticate,
    available_window,
    cancel_pass,
    check_in,
    connection,
    init_db,
    join_queue,
    pass_status,
    register,
    visitor_passes,
)

ACTIVE_STATUSES = ("Upcoming", "Ready now")


def show_access():
    st.title("Spend your visit exploring")
    st.write("Reserve a place in line, then come back to the ride during your return window.")
    sign_in, sign_up = st.tabs(["Sign in", "Create account"])
    with sign_in, st.form("sign_in"):
        username = st.text_input("Username", max_chars=24, key="sign_in_name")
        password = st.text_input("Password", type="password", max_chars=128, key="sign_in_password")
        if st.form_submit_button("Sign in", type="primary"):
            visitor_id = authenticate(username, password)
            if visitor_id is None:
                st.error("The username or password is incorrect.")
            else:
                st.session_state.visitor_id = visitor_id
                st.session_state.username = username.strip().lower()
                st.rerun()

    with sign_up, st.form("register"):
        username = st.text_input("Username", max_chars=24, key="new_name")
        password = st.text_input("Password", type="password", max_chars=128, key="new_password")
        st.caption("Use 3–24 letters, digits or underscores, and a password with at least 8 characters.")
        if st.form_submit_button("Create account", type="primary"):
            try:
                visitor_id = register(username, password)
            except ValueError as error:
                st.error(str(error))
            else:
                st.session_state.visitor_id = visitor_id
                st.session_state.username = username.strip().lower()
                st.rerun()


def book_ride(visitor_id, ride, offered_start):
    """Use the window shown before the button click, even if availability has changed."""
    try:
        start, end = join_queue(visitor_id, ride, offered_start)
    except ValueError as error:
        st.session_state.ride_notice = ("warning", str(error))
    else:
        st.session_state.ride_notice = (
            "success",
            f"You’re in line for {ride}. Return {window_label(start, end)}. Find your QR in My passes.",
        )


def show_rides(visitor_id):
    st.title("Explore rides")
    st.write("Pick an attraction and reserve its next available return window.")
    notice = st.session_state.pop("ride_notice", None)
    if notice:
        kind, message = notice
        if kind == "success":
            st.success(message)
        else:
            st.warning(message)

    zones = list(dict.fromkeys(ride["zone"] for ride in RIDES.values()))
    zone = st.selectbox("Park area", ["All areas", *zones])
    st.button("Refresh availability")
    now = int(time())
    with connection() as db:
        for park_area in zones:
            if zone not in ("All areas", park_area):
                continue
            st.subheader(park_area)
            rides = [name for name, ride in RIDES.items() if ride["zone"] == park_area]
            columns = st.columns(2)
            for i, name in enumerate(rides):
                ride = RIDES[name]
                with columns[i % len(columns)], st.container(border=True):
                    st.caption(ride["kind"])
                    st.markdown(f"**{name}**")
                    st.write(ride["description"])
                    try:
                        start, end, remaining = available_window(db, visitor_id, name, now)
                    except ValueError as error:
                        st.caption(str(error))
                    else:
                        st.write(window_label(start, end))
                        st.caption(f"{remaining} {'place' if remaining == 1 else 'places'} left")
                        st.button(
                            f"Join {name}",
                            key=f"join_{name}",
                            on_click=book_ride,
                            args=(visitor_id, name, start),
                            type="primary",
                        )


def show_passes(visitor_id):
    st.title("My passes")
    st.write("Present your QR code at the attraction during your return window.")
    st.button("Refresh passes")
    notice = st.session_state.pop("pass_notice", None)
    if notice:
        st.success(notice)

    now = int(time())
    tickets = visitor_passes(visitor_id)
    active = []
    history = []
    for ticket in tickets:
        status = pass_status(ticket, now)
        if status in ACTIVE_STATUSES:
            active.append((ticket, status))
        else:
            history.append((ticket, status))

    if not active:
        st.info("You have no active passes. Join a queue from Explore rides.")
    for ticket, status in active:
        with st.container(border=True):
            st.subheader(ticket["ride"])
            st.write(window_label(ticket["start_at"], ticket["end_at"]))
            if status == "Ready now":
                st.success("Ready now")
            else:
                st.info("Upcoming")
            code_column, action_column = st.columns([1, 2])
            code = ticket["code"]
            with code_column:
                st.image(qr_png(code), caption="Return pass QR", width=174)
            with action_column:
                st.caption("Confirmation code")
                st.code(code, language=None)
                if st.button("Leave queue", key=f"cancel_{code}"):
                    try:
                        cancel_pass(visitor_id, code)
                    except ValueError as error:
                        st.error(str(error))
                    else:
                        st.session_state.pass_notice = f"Left the queue for {ticket['ride']}."
                        st.rerun()

    if history:
        with st.expander("Pass history"):
            for ticket, status in reversed(history):
                st.markdown(f"**{ticket['ride']}** · {status}")
                st.caption(window_label(ticket["start_at"], ticket["end_at"]))


def show_route(visitor_id):
    st.title("Park route")
    st.write("Find the shortest walk from your current landmark.")
    now = int(time())
    active_by_ride = {}
    for ticket in visitor_passes(visitor_id):
        if pass_status(ticket, now) in ACTIVE_STATUSES:
            active_by_ride[ticket["ride"]] = ticket

    landmarks = ["Main Entrance", *sorted(set(WALKING_GRAPH) - {"Main Entrance"})]
    destinations = [*active_by_ride, *sorted(set(WALKING_GRAPH) - set(active_by_ride))]
    start_column, end_column = st.columns(2)
    start = start_column.selectbox("From", landmarks)
    destination = end_column.selectbox("To", destinations)
    result = shortest_path(start, destination)
    if result is None:
        st.warning("No walking route is available between these landmarks.")
        return

    path, minutes = result
    arrival = now + minutes * 60
    arrival_label = datetime.fromtimestamp(arrival, PARK_TIME).strftime("%H:%M SGT")
    left, right = st.columns(2)
    left.metric("Walking time", f"{minutes} min")
    right.metric("Arrival if you leave now", arrival_label)
    if minutes == 0:
        st.info("You’re already at your destination.")
    else:
        with st.container(border=True):
            st.subheader("Walking directions")
            for step, (before, after) in enumerate(zip(path, path[1:]), start=1):
                st.markdown(f"{step}. **{before} → {after}** · {WALKING_GRAPH[before][after]} min")

    ticket = active_by_ride.get(destination)
    if ticket:
        st.caption(f"Return window · {window_label(ticket['start_at'], ticket['end_at'])}")
        if arrival >= ticket["end_at"]:
            st.warning("This walk may take you past the end of your return window.")
        elif arrival < ticket["start_at"]:
            st.info("You’re on track to arrive before your window opens.")
        else:
            st.success("You’re on track to arrive during your return window.")


def show_staff():
    st.title("Staff check-in")
    pin = os.environ.get("SKYTRAIL_STAFF_PIN")
    if not pin:
        st.info("Set SKYTRAIL_STAFF_PIN before launching the app to enable check-in.")
        return

    if not st.session_state.get("staff_authenticated"):
        with st.form("staff_unlock"):
            attempt = st.text_input("Staff PIN", type="password", max_chars=128)
            if st.form_submit_button("Unlock check-in", type="primary"):
                if hmac.compare_digest(attempt.encode(), pin.encode()):
                    st.session_state.staff_authenticated = True
                    st.rerun()
                else:
                    st.error("Incorrect staff PIN.")
        return

    if st.button("Lock check-in"):
        st.session_state.pop("staff_authenticated")
        st.rerun()

    st.write("Select the ride, then scan a visitor’s QR code or enter it by hand.")
    ride = st.selectbox("Attraction", list(RIDES))
    with st.form("check_in", clear_on_submit=True):
        code = st.text_input("Confirmation code", max_chars=32)
        st.caption("Focus the field before scanning with a keyboard-mode QR reader.")
        if st.form_submit_button("Check in visitor", type="primary"):
            try:
                check_in(ride, code)
            except ValueError as error:
                st.error(str(error))
            else:
                st.success(f"Visitor checked in for {ride}.")


def main():
    st.set_page_config(page_title="Skytrail Park", page_icon="🎢", layout="wide")
    init_db()
    with st.sidebar:
        st.header("Skytrail Park")
        st.caption("Virtual queue")
        visitor_id = st.session_state.get("visitor_id")
        visitor_pages = ["Explore rides", "My passes", "Park route"]
        if visitor_id is None:
            visitor_pages = ["Visitor access"]
        page = st.radio("Go to", [*visitor_pages, "Staff check-in"])
        if visitor_id is not None:
            st.divider()
            st.caption(f"Signed in as @{st.session_state.username}")
            if st.button("Sign out"):
                st.session_state.clear()
                st.rerun()

    if page == "Staff check-in":
        show_staff()
    elif page == "Visitor access":
        show_access()
    elif page == "Explore rides":
        show_rides(visitor_id)
    elif page == "My passes":
        show_passes(visitor_id)
    else:
        show_route(visitor_id)


if __name__ == "__main__":
    main()
