import sqlite3
import argparse
from datetime import datetime, timedelta
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'guesthouse.db')
# prices stored in DB are UGX
RATE_USD_TO_UGX = 3700


def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('''
    CREATE TABLE IF NOT EXISTS rooms (
        id INTEGER PRIMARY KEY,
        number TEXT UNIQUE,
        type TEXT,
        price REAL,
        available INTEGER DEFAULT 1
    )
    ''')
    cur.execute('''
    CREATE TABLE IF NOT EXISTS guests (
        id INTEGER PRIMARY KEY,
        name TEXT,
        phone TEXT,
        nin_number TEXT
    )
    ''')
    # ensure existing DB has ni_number column (safe to run multiple times)
    cur.execute("PRAGMA table_info('guests')")
    cols = [r[1] for r in cur.fetchall()]
    # if an older column `ni_number` exists, we'll add `nin_number` and copy values
    if 'nin_number' not in cols:
        try:
            cur.execute("ALTER TABLE guests ADD COLUMN nin_number TEXT")
            # if old column exists, copy its values
            if 'ni_number' in cols:
                cur.execute("UPDATE guests SET nin_number = ni_number WHERE nin_number IS NULL")
        except Exception:
            pass
    cur.execute('''
    CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY,
        guest_id INTEGER,
        room_id INTEGER,
        start_date TEXT,
        end_date TEXT,
        status TEXT,
        FOREIGN KEY(guest_id) REFERENCES guests(id),
        FOREIGN KEY(room_id) REFERENCES rooms(id)
    )
    ''')
    conn.commit()
    conn.close()


def add_room(number, rtype, price):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('INSERT INTO rooms(number, type, price) VALUES (?, ?, ?)', (number, rtype, price))
    conn.commit()
    conn.close()


def list_rooms():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT id, number, type, price, available FROM rooms ORDER BY number')
    rows = cur.fetchall()
    conn.close()
    if not rows:
        print('No rooms defined.')
        return
    print('{:>3}  {:>6}  {:10}  {:12}  {}'.format('ID','Number','Type','Price(UGX)','Available'))
    for r in rows:
        price_ugx = int(r[3] or 0)
        print('{:>3}  {:>6}  {:10}  {:12}  {}'.format(r[0], r[1], r[2], f'UGX {price_ugx:,}', 'Yes' if r[4] else 'No'))


def register_guest(name, phone, nin_number=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('INSERT INTO guests(name, phone, nin_number) VALUES (?, ?, ?)', (name, phone, nin_number))
    conn.commit()
    guest_id = cur.lastrowid
    conn.close()
    print(f'Guest registered with id {guest_id}')


def list_guests():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT id, name, phone, nin_number FROM guests ORDER BY id')
    rows = cur.fetchall()
    conn.close()
    if not rows:
        print('No guests found.')
        return
    print('{:>3}  {:20}  {:15}  {}'.format('ID','Name','Phone','NIN Number'))
    for g in rows:
        print('{:>3}  {:20}  {:15}  {}'.format(g[0], g[1], g[2], g[3] if len(g) > 3 else ''))


def check_in(guest_id, room_id, nights):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT available FROM rooms WHERE id=?', (room_id,))
    row = cur.fetchone()
    if not row:
        print('Room not found')
        conn.close()
        return
    if row[0] == 0:
        print('Room is not available')
        conn.close()
        return
    start = datetime.now().date()
    end = start + timedelta(days=int(nights))
    cur.execute('INSERT INTO bookings(guest_id, room_id, start_date, end_date, status) VALUES (?, ?, ?, ?, ?)',
                (guest_id, room_id, start.isoformat(), end.isoformat(), 'checked_in'))
    cur.execute('UPDATE rooms SET available=0 WHERE id=?', (room_id,))
    conn.commit()
    print(f'Guest {guest_id} checked into room {room_id} until {end.isoformat()}')
    conn.close()


def check_out(booking_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT b.room_id, b.start_date, b.end_date, b.status, g.name, r.number, r.price, g.phone FROM bookings b JOIN guests g ON b.guest_id=g.id JOIN rooms r ON b.room_id=r.id WHERE b.id=?', (booking_id,))
    row = cur.fetchone()
    if not row:
        print('Booking not found')
        conn.close()
        return
    room_id, start_date, end_date, status, guest_name, room_number, room_price, guest_phone = row
    if status == 'checked_out':
        print('Already checked out')
        conn.close()
        return
    # compute nights stayed (use today if earlier than end_date)
    from datetime import date
    s = date.fromisoformat(start_date)
    e = date.fromisoformat(end_date)
    today = date.today()
    last_day = min(e, today)
    nights = (last_day - s).days
    if nights <= 0:
        nights = 1
    # room_price stored in UGX
    amount_ugx = nights * int(room_price or 0)
    amount_usd = (amount_ugx / RATE_USD_TO_UGX) if RATE_USD_TO_UGX else 0.0

    # update booking status and room availability
    cur.execute('UPDATE bookings SET status=?, end_date=? WHERE id=?', ('checked_out', last_day.isoformat(), booking_id))
    cur.execute('UPDATE rooms SET available=1 WHERE id=?', (room_id,))
    conn.commit()

    # print receipt
    print('----- RECEIPT -----')
    print(f'Booking ID: {booking_id}')
    print(f'Guest: {guest_name} ({guest_phone})')
    print(f'Room: {room_number} (ID {room_id})')
    print(f'Start: {s.isoformat()}')
    print(f'Checked out: {last_day.isoformat()}')
    print(f'Nights stayed: {nights}')
    print(f'Amount (USD): ${amount_usd:.2f}')
    print(f'Amount (UGX): UGX {amount_ugx:,}')
    print('-------------------')
    conn.close()


def list_bookings(show_all=False):
    conn = get_conn()
    cur = conn.cursor()
    if show_all:
        cur.execute('SELECT b.id, g.name, r.number, b.start_date, b.end_date, b.status FROM bookings b JOIN guests g ON b.guest_id=g.id JOIN rooms r ON b.room_id=r.id ORDER BY b.id')
    else:
        cur.execute("SELECT b.id, g.name, r.number, b.start_date, b.end_date, b.status FROM bookings b JOIN guests g ON b.guest_id=g.id JOIN rooms r ON b.room_id=r.id WHERE b.status!='checked_out' ORDER BY b.id")
    rows = cur.fetchall()
    conn.close()
    if not rows:
        print('No bookings found.')
        return
    print('{:>3}  {:15}  {:6}  {:10}  {:10}  {}'.format('ID','Guest','Room','Start','End','Status'))
    for b in rows:
        print('{:>3}  {:15}  {:6}  {:10}  {:10}  {}'.format(b[0], b[1], b[2], b[3], b[4], b[5]))


def monthly_report(year: int, month: int):
    """Print a monthly report: number of bookings and unique guests with start_date in the month."""
    from datetime import date
    import calendar

    start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = date(year, month, last_day)

    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM bookings WHERE start_date BETWEEN ? AND ?', (start.isoformat(), end.isoformat()))
    total_bookings = cur.fetchone()[0]
    cur.execute('SELECT COUNT(DISTINCT guest_id) FROM bookings WHERE start_date BETWEEN ? AND ?', (start.isoformat(), end.isoformat()))
    unique_guests = cur.fetchone()[0]
    # list guest names optionally
    cur.execute('SELECT g.id, g.name, COUNT(b.id) as bookings FROM bookings b JOIN guests g ON b.guest_id=g.id WHERE b.start_date BETWEEN ? AND ? GROUP BY g.id ORDER BY bookings DESC', (start.isoformat(), end.isoformat()))
    guest_rows = cur.fetchall()
    conn.close()

    print(f'Monthly report for {year}-{month:02d}')
    print(f'Total bookings: {total_bookings}')
    print(f'Unique guests: {unique_guests}')
    print('Guests breakdown:')
    for gid, name, cnt in guest_rows:
        print(f' - {name} (id {gid}): {cnt} booking(s)')


def main():
    parser = argparse.ArgumentParser(description='Guest House Management CLI')
    sub = parser.add_subparsers(dest='cmd')

    sub.add_parser('init-db')

    p = sub.add_parser('add-room')
    p.add_argument('--number', required=True)
    p.add_argument('--type', required=True)
    p.add_argument('--price', required=True, type=float)

    sub.add_parser('list-rooms')

    p = sub.add_parser('register-guest')
    p.add_argument('--name', required=True)
    p.add_argument('--phone', required=True)
    p.add_argument('--nin-number', required=False, dest='nin_number')

    sub.add_parser('list-guests')

    p = sub.add_parser('check-in')
    p.add_argument('--guest-id', required=True, type=int)
    p.add_argument('--room-id', required=True, type=int)
    p.add_argument('--nights', required=True, type=int)

    p = sub.add_parser('check-out')
    p.add_argument('--booking-id', required=True, type=int)

    p = sub.add_parser('monthly-report')
    p.add_argument('--year', required=True, type=int)
    p.add_argument('--month', required=True, type=int)

    p = sub.add_parser('list-bookings')
    p.add_argument('--all', action='store_true')

    args = parser.parse_args()
    if args.cmd == 'init-db':
        init_db()
        print('Database initialized at', DB_PATH)
    elif args.cmd == 'add-room':
        add_room(args.number, args.type, args.price)
    elif args.cmd == 'list-rooms':
        list_rooms()
    elif args.cmd == 'register-guest':
        register_guest(args.name, args.phone, getattr(args, 'nin_number', None))
    elif args.cmd == 'list-guests':
        list_guests()
    elif args.cmd == 'check-in':
        check_in(args.guest_id, args.room_id, args.nights)
    elif args.cmd == 'check-out':
        check_out(args.booking_id)
    elif args.cmd == 'monthly-report':
        monthly_report(args.year, args.month)
    elif args.cmd == 'list-bookings':
        list_bookings(show_all=args.all)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
