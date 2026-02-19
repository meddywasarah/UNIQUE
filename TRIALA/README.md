# Guest House Management System

Simple CLI guest house manager using SQLite.

Usage examples:

Initialize database:

```bash
python guest_house.py init-db
```

Add a room:

```bash
python guest_house.py add-room --number 101 --type single --price 25.0
```

Register a guest:

```bash
python guest_house.py register-guest --name "Alice" --phone "12345"
```

Check a guest in:

```bash
python guest_house.py check-in --guest-id 1 --room-id 1 --nights 3
```

List bookings:

```bash
python guest_house.py list-bookings --all
```

Requirements: Python 3.8+ (stdlib only)
