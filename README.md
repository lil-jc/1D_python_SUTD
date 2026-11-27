# Skytrail Park · Virtual Queue

Skytrail Park is a fictional theme park where visitors can spend much of their visit standing in ride queues. Skytrail's virtual queue gives visitors a return window so they can explore the park until it's time to ride. This is a Track A project for SUTD 10.025 Introduction to Programming.

The main user is a visitor who wants to reserve a ride and make it back on time. Every visitor sees the same interface and can access only their own passes. An attraction attendant uses a separate verification screen.

## Run locally

Use Python 3.11 or newer. These commands use macOS/Linux shell syntax.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
SKYTRAIL_STAFF_PIN=482915 python -m streamlit run app.py
```

Open the local URL printed by Streamlit. Choose your own staff PIN. The example PIN is suitable for a local demo. The app stores accounts and passes in `skytrail.sqlite3` next to `app.py`. Set `SKYTRAIL_DB` to use a different database file.

## Pages and features

| Page | User | Purpose and actions |
| --- | --- | --- |
| Visitor access | Signed-out visitor | Create an account with a username and password or sign in. Signing out clears the current browser session. |
| Explore rides | Visitor | Filter attractions by park area, refresh availability and join a queue. Each ride shows its next return window and seats remaining. If that window changes, the visitor sees the new time before booking. |
| My passes | Visitor | See the ride, return window, confirmation code and current pass status. Present the QR code at the ride or leave the queue to release the reserved place. Completed, cancelled and expired passes remain in history. |
| Park route | Visitor | Choose a starting landmark and destination. The page defaults to the next reserved ride when possible, displays each walking leg and uses the estimated arrival time to warn if the booked window may be missed. |
| Staff check-in | Attendant | Unlock with the configured staff PIN and select the attraction. Focus the code field, scan the visitor's QR with a USB/Bluetooth keyboard-mode scanner, or enter the printed code. Confirming checks the attraction, time and pass status and admits the visitor once. |

A keyboard-mode scanner types the QR payload into the input as text. Use a scanner without an Enter suffix if you want to review the value before submission. The local demo works with manual code entry. The QR contains only the random confirmation code.

## Business rules

- One reservation represents one visitor. Each ride defines its own seats per five-minute window. The park uses Singapore time, and the prototype runs throughout the day using fictional ride and walking data.
- The app offers the earliest return window with capacity that does not overlap that visitor's other bookings. The current window can be booked if it has at least two minutes remaining. The app searches up to 90 minutes ahead.
- A visitor can hold only one active pass per ride. Check-in is accepted from the start time up to the end time, excluding the end time itself. Cancellation frees a reserved place. A checked-in visitor still counts toward capacity for that window.
- SQLite stores the shared state. Booking, cancellation and check-in run in write transactions so concurrent actions cannot sell the same remaining place or admit the same pass twice.
- Dijkstra's algorithm finds the shortest walking time between two landmarks. Edge weights are fixed minutes. Arrival estimates assume the visitor leaves now and use the same clock as the queue.
- Accounts use salted password hashes. The staff PIN controls access for the classroom demo. Visitors sign in again when a new browser session starts.

## Function reference

### `app.py` · Streamlit pages

| Function | Purpose |
| --- | --- |
| `show_access` | Render sign-in and registration forms and open the visitor session. |
| `book_ride` | Handle a join button using the window the visitor saw and report the result on the rides page. |
| `show_rides` | Display attraction details and availability, and handle queue joins. |
| `show_passes` | Display active and past passes and handle cancellations. |
| `show_route` | Choose landmarks, show the shortest path and compare arrival with the pass window. |
| `show_staff` | Authenticate the attendant and process check-ins at the selected ride. |
| `main` | Initialize the database, render navigation and dispatch to the selected page. |

### `park.py` · Park data and routing

| Function | Purpose |
| --- | --- |
| `shortest_path` | Visit the lowest-cost reachable landmark first, then reconstruct the route from its recorded predecessors. |
| `window_label` | Render a return window in Singapore time. |

### `queue_store.py` · Accounts and queue

| Function | Purpose |
| --- | --- |
| `connection` | Open a SQLite connection and commit or roll back changes on exit. |
| `init_db` | Create the account and reservation tables and a queue lookup index. |
| `password_hash` | Derive a salted password hash for account creation and sign-in. |
| `register` | Validate and create a unique visitor account. |
| `authenticate` | Check credentials and return the visitor ID on success. |
| `available_window` | Find the first window with room and no conflicting pass for the visitor. |
| `join_queue` | Reserve a place and generate an opaque QR code value in one transaction. |
| `visitor_passes` | Retrieve the visitor's reservations ordered by return time. |
| `pass_status` | Derive the display status from the stored reservation state and current time. |
| `cancel_pass` | Release an unused pass owned by the signed-in visitor. |
| `check_in` | Validate the scanned code and consume the pass if admission is allowed. |

### `qr_pass.py` · QR image

| Function | Purpose |
| --- | --- |
| `gf_multiply` | Multiply two finite-field values used by QR error correction. |
| `qr_codewords` | Encode the ASCII pass and calculate error correction bytes for a Version 1-L QR. |
| `qr_matrix` | Add the fixed QR patterns and place the masked data bits in the grid. |
| `png_chunk` | Package a PNG data block with its type, length and checksum. |
| `qr_png` | Render the grid and its quiet border to a PNG with Python's standard library. |

## Demo walkthrough

1. Register a visitor and book a ride. Open **My passes** and note the return window.
2. Open **Park route** and select the main entrance. Explain how the route adds walking times and checks the estimated arrival.
3. Open **Staff check-in** and unlock it. Select the ride and scan or paste the code during the displayed window.
4. Check that a second submission is rejected. Return to **My passes** to see the checked-in status.

## Resources

- SUTD 10.025 2026 1D project brief. Used to define the Track A scope and permitted libraries.
- [Streamlit documentation](https://docs.streamlit.io/develop). Used for the interface.
- [Python standard library](https://docs.python.org/3/library/). Used for SQLite, password hashing, time zones, the priority queue and PNG output.
- OpenAI Codex assisted with drafting the specification, implementing the app and running verification.
