from flask import Flask, render_template, request, redirect, url_for, flash
from flask import send_file
import sqlite3
import os
from guest_house import DB_PATH

# conversion rate USD -> UGX
RATE_USD_TO_UGX = 3700

app = Flask(__name__)
app.secret_key = 'dev'


def get_conn():
    return sqlite3.connect(DB_PATH)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/rooms', methods=['GET', 'POST'])
def rooms():
    conn = get_conn()
    cur = conn.cursor()
    if request.method == 'POST':
        number = request.form['number'].strip()
        rtype = request.form['type'].strip()
        price = request.form['price']
        try:
            cur.execute('INSERT INTO rooms(number, type, price) VALUES (?, ?, ?)', (number, rtype, float(price)))
            conn.commit()
            flash('Room added', 'success')
        except Exception as e:
            flash(str(e), 'danger')
        return redirect(url_for('rooms'))
    cur.execute('SELECT id, number, type, price, available FROM rooms ORDER BY number')
    rows = cur.fetchall()
    rooms = []
    for r in rows:
        # r: (id, number, type, price, available)
        # price is stored in UGX
        price_ugx = int(r[3] or 0)
        price_str = f"UGX {price_ugx:,}"
        rooms.append((r[0], r[1], r[2], price_ugx, r[4], price_str))
    conn.close()
    return render_template('rooms.html', rooms=rooms)


@app.route('/guests', methods=['GET', 'POST'])
def guests():
    conn = get_conn()
    cur = conn.cursor()
    if request.method == 'POST':
        name = request.form['name'].strip()
        phone = request.form['phone'].strip()
        nin_number = request.form.get('nin_number','').strip() or None
        cur.execute('INSERT INTO guests(name, phone, nin_number) VALUES (?, ?, ?)', (name, phone, nin_number))
        conn.commit()
        flash('Guest registered', 'success')
        return redirect(url_for('guests'))
    cur.execute('SELECT id, name, phone, nin_number FROM guests ORDER BY id')
    guests = cur.fetchall()
    conn.close()
    return render_template('guests.html', guests=guests)


@app.route('/bookings', methods=['GET', 'POST'])
def bookings():
    conn = get_conn()
    cur = conn.cursor()
    if request.method == 'POST':
        guest_id = int(request.form['guest_id'])
        room_id = int(request.form['room_id'])
        nights = int(request.form['nights'])
        # check availability
        cur.execute('SELECT available FROM rooms WHERE id=?', (room_id,))
        row = cur.fetchone()
        if not row or row[0] == 0:
            flash('Room not available', 'danger')
            conn.close()
            return redirect(url_for('bookings'))
        from datetime import datetime, timedelta
        start = datetime.now().date()
        end = start + timedelta(days=nights)
        cur.execute('INSERT INTO bookings(guest_id, room_id, start_date, end_date, status) VALUES (?, ?, ?, ?, ?)',
                    (guest_id, room_id, start.isoformat(), end.isoformat(), 'checked_in'))
        cur.execute('UPDATE rooms SET available=0 WHERE id=?', (room_id,))
        conn.commit()
        flash('Checked in', 'success')
        conn.close()
        return redirect(url_for('bookings'))

    # allow optional filtering by guest via query param ?guest_id=
    guest_id = request.args.get('guest_id')
    guest_name = None
    if guest_id:
        try:
            gid = int(guest_id)
            cur.execute("SELECT name FROM guests WHERE id=?", (gid,))
            row = cur.fetchone()
            guest_name = row[0] if row else None
            cur.execute("SELECT b.id, g.name, r.number, b.start_date, b.end_date, b.status FROM bookings b JOIN guests g ON b.guest_id=g.id JOIN rooms r ON b.room_id=r.id WHERE b.guest_id=? ORDER BY b.id", (gid,))
        except Exception:
            cur.execute("SELECT b.id, g.name, r.number, b.start_date, b.end_date, b.status FROM bookings b JOIN guests g ON b.guest_id=g.id JOIN rooms r ON b.room_id=r.id ORDER BY b.id")
    else:
        cur.execute("SELECT b.id, g.name, r.number, b.start_date, b.end_date, b.status FROM bookings b JOIN guests g ON b.guest_id=g.id JOIN rooms r ON b.room_id=r.id ORDER BY b.id")
    bookings = cur.fetchall()
    cur.execute('SELECT id, name FROM guests ORDER BY id')
    guests = cur.fetchall()
    cur.execute('SELECT id, number FROM rooms WHERE available=1 ORDER BY number')
    rooms = cur.fetchall()
    conn.close()
    return render_template('bookings.html', bookings=bookings, guests=guests, rooms=rooms, guest_filter=guest_id, guest_name=guest_name)


@app.route('/reports', methods=['GET', 'POST'])
def reports():
    report = None
    if request.method == 'POST':
        # accept new `month_year` (format YYYY-MM) or fallback to separate year/month fields
        month_year = request.form.get('month_year')
        if month_year:
            try:
                year, month = map(int, month_year.split('-'))
            except Exception:
                flash('Invalid month selection', 'danger')
                return render_template('report.html', report=None)
        else:
            year = int(request.form.get('year'))
            month = int(request.form.get('month'))
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
        cur.execute('SELECT g.name, COUNT(b.id) as bookings FROM bookings b JOIN guests g ON b.guest_id=g.id WHERE b.start_date BETWEEN ? AND ? GROUP BY g.id ORDER BY bookings DESC', (start.isoformat(), end.isoformat()))
        guests_breakdown = cur.fetchall()
        # total revenue in UGX for bookings starting in the period (cap end_date to period end)
        cur.execute(
            """
            SELECT SUM((julianday(CASE WHEN b.end_date > ? THEN ? ELSE b.end_date END) - julianday(b.start_date)) * r.price)
            FROM bookings b JOIN rooms r ON b.room_id=r.id
            WHERE b.start_date BETWEEN ? AND ?
            """,
            (end.isoformat(), end.isoformat(), start.isoformat(), end.isoformat())
        )
        total_ugx = cur.fetchone()[0] or 0
        total_ugx = int(round(total_ugx))
        total_usd = (total_ugx / RATE_USD_TO_UGX) if RATE_USD_TO_UGX else 0.0
        conn.close()

        report = {
            'year': year,
            'month': month,
            'total_bookings': total_bookings,
            'unique_guests': unique_guests,
            'guests_breakdown': guests_breakdown,
            'start': start.isoformat(),
            'end': end.isoformat()
            , 'total_ugx': f'UGX {total_ugx:,}',
            'total_usd': f'${total_usd:.2f}'
        }
    return render_template('report.html', report=report)


@app.route('/reports/pdf', methods=['POST'])
def reports_pdf():
    try:
        # expect year and month in form
        month_year = request.form.get('month_year')
        if month_year:
            try:
                year, month = map(int, month_year.split('-'))
            except Exception:
                flash('Invalid month selection', 'danger')
                return redirect(url_for('reports'))
        else:
            year = int(request.form.get('year'))
            month = int(request.form.get('month'))
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
        cur.execute('SELECT g.name, COUNT(b.id) as bookings FROM bookings b JOIN guests g ON b.guest_id=g.id WHERE b.start_date BETWEEN ? AND ? GROUP BY g.id ORDER BY bookings DESC', (start.isoformat(), end.isoformat()))
        guests_breakdown = cur.fetchall()
        # compute totals
        cur.execute(
            """
            SELECT SUM((julianday(CASE WHEN b.end_date > ? THEN ? ELSE b.end_date END) - julianday(b.start_date)) * r.price)
            FROM bookings b JOIN rooms r ON b.room_id=r.id
            WHERE b.start_date BETWEEN ? AND ?
            """,
            (end.isoformat(), end.isoformat(), start.isoformat(), end.isoformat())
        )
        total_ugx = cur.fetchone()[0] or 0
        total_ugx = int(round(total_ugx))
        total_usd = (total_ugx / RATE_USD_TO_UGX) if RATE_USD_TO_UGX else 0.0
        conn.close()

        # generate PDF
        from io import BytesIO
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        width, height = A4
        c.setFont('Helvetica-Bold', 16)
        c.drawString(40, height - 60, f'Monthly Report: {year}-{month:02d}')
        c.setFont('Helvetica', 12)
        c.drawString(40, height - 90, f'Period: {start.isoformat()} to {end.isoformat()}')
        c.drawString(40, height - 110, f'Total bookings: {total_bookings}')
        c.drawString(40, height - 130, f'Unique guests: {unique_guests}')
        c.drawString(40, height - 150, f'Total revenue (UGX): UGX {total_ugx:,}')
        c.drawString(40, height - 170, f'Total revenue (USD): ${total_usd:.2f}')
        y = height - 200
        c.setFont('Helvetica-Bold', 12)
        c.drawString(40, y, 'Guests breakdown:')
        y -= 20
        c.setFont('Helvetica', 11)
        for name, cnt in guests_breakdown:
            c.drawString(50, y, f'{name} — {cnt} booking(s)')
            y -= 18
            if y < 40:
                c.showPage()
                y = height - 40
        c.showPage()
        c.save()
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name=f'report_{year}_{month:02d}.pdf', mimetype='application/pdf')
    except Exception:
        import traceback
        tb = traceback.format_exc()
        # return stack trace to browser for debugging
        return tb, 500


@app.route('/check-out/<int:booking_id>', methods=['POST'])
def check_out(booking_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT b.id, b.guest_id, g.name, g.phone, g.nin_number, b.room_id, r.number, r.price, b.start_date, b.end_date, b.status FROM bookings b JOIN guests g ON b.guest_id=g.id JOIN rooms r ON b.room_id=r.id WHERE b.id=?', (booking_id,))
    b = cur.fetchone()
    if not b:
        flash('Booking not found', 'danger')
        conn.close()
        return redirect(url_for('bookings'))
    _, guest_id, guest_name, guest_phone, guest_nin, room_id, room_number, room_price, start_date, end_date, status = b
    if status == 'checked_out':
        flash('Already checked out', 'info')
        conn.close()
        return redirect(url_for('bookings'))

    from datetime import date
    s = date.fromisoformat(start_date)
    e = date.fromisoformat(end_date)
    today = date.today()
    last_day = min(e, today)
    nights = (last_day - s).days
    if nights <= 0:
        nights = 1
    # room_price is stored in UGX
    amount_ugx = nights * int(room_price or 0)
    amount_usd = (amount_ugx / RATE_USD_TO_UGX) if RATE_USD_TO_UGX else 0.0

    # update booking and room
    cur.execute('UPDATE bookings SET status=?, end_date=? WHERE id=?', ('checked_out', last_day.isoformat(), booking_id))
    cur.execute('UPDATE rooms SET available=1 WHERE id=?', (room_id,))
    conn.commit()
    conn.close()

    receipt = {
        'booking_id': booking_id,
        'guest_name': guest_name,
        'guest_phone': guest_phone,
        'guest_nin': guest_nin,
        'room_number': room_number,
        'start_date': s.isoformat(),
        'checkout_date': last_day.isoformat(),
        'nights': nights,
        'amount_usd': f'${amount_usd:.2f}',
        'amount_ugx': f'UGX {amount_ugx:,}'
    }
    return render_template('receipt.html', receipt=receipt)


@app.route('/invoice/<int:booking_id>')
def invoice(booking_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT b.id, g.name, g.phone, g.nin_number, b.room_id, r.number, r.price, b.start_date, b.end_date FROM bookings b JOIN guests g ON b.guest_id=g.id JOIN rooms r ON b.room_id=r.id WHERE b.id=?', (booking_id,))
    b = cur.fetchone()
    if not b:
        flash('Booking not found', 'danger')
        conn.close()
        return redirect(url_for('bookings'))
    bid, guest_name, guest_phone, guest_nin, room_id, room_number, room_price, start_date, end_date = b
    from datetime import date
    s = date.fromisoformat(start_date)
    e = date.fromisoformat(end_date)
    nights = (e - s).days
    if nights <= 0:
        nights = 1
    # room_price stored in UGX
    rate_ugx = int(room_price or 0)
    amount_ugx = nights * rate_ugx
    amount_usd = (amount_ugx / RATE_USD_TO_UGX) if RATE_USD_TO_UGX else 0.0

    # generate PDF invoice
    try:
        from io import BytesIO
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        width, height = A4
        c.setFont('Helvetica-Bold', 18)
        c.drawString(40, height - 60, f'Invoice — Booking #{bid}')
        from datetime import datetime
        c.setFont('Helvetica', 10)
        c.drawString(40, height - 80, f'Date: {datetime.now().date().isoformat()}')

        y = height - 120
        c.setFont('Helvetica-Bold', 12)
        c.drawString(40, y, 'Guest')
        c.setFont('Helvetica', 11)
        c.drawString(40, y - 18, f'Name: {guest_name}')
        c.drawString(40, y - 36, f'Phone: {guest_phone}')
        c.drawString(40, y - 54, f'NIN: {guest_nin or ""}')

        y = y - 70
        c.setFont('Helvetica-Bold', 12)
        c.drawString(40, y, 'Booking Details')
        c.setFont('Helvetica', 11)
        c.drawString(40, y - 18, f'Room: {room_number}')
        c.drawString(40, y - 36, f'Start: {s.isoformat()}')
        c.drawString(40, y - 54, f'End: {e.isoformat()}')
        c.drawString(40, y - 72, f'Nights: {nights}')

        y = y - 110
        c.setFont('Helvetica-Bold', 12)
        c.drawString(40, y, 'Charges')
        c.setFont('Helvetica', 11)
        c.drawString(40, y - 18, f'Rate (per night): UGX {rate_ugx:,}')
        c.drawString(40, y - 36, f'Subtotal (UGX): UGX {amount_ugx:,}')
        c.drawString(40, y - 54, f'Total (USD): ${amount_usd:.2f}')

        c.showPage()
        c.save()
        buf.seek(0)
        conn.close()
        return send_file(buf, as_attachment=False, download_name=f'invoice_{bid}.pdf', mimetype='application/pdf')
    except Exception:
        import traceback
        tb = traceback.format_exc()
        conn.close()
        return tb, 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
